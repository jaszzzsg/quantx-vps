#!/usr/bin/env python3
"""
RF Scoreboard Daily Update
==========================

Runs as the final step in arm-rf-update.service (after rf_score_daily.py).

Steps:
  A  Fill dd_next + label for the most recent UNFILLED row in rf_scoreboard.csv
     (SPY next-trading-day mapping, positional shift — no calendar guessing)
  B  Upsert that label into rf_features.csv (enables model to learn from it)
  C  Append today's row to rf_scoreboard.csv from arm_state_history + rf_daily_predictions
  D  Check retrain checkpoints (120 / 150 / 200 labeled rows in rf_features.csv)
     If a new checkpoint is crossed: retrain rf_model.joblib + save timestamped copy
     + run time-based 70/30 forward validation and log results

Scoreboard CSV columns:
  date, arm_regime, prob_safe, gate_thr, rs_iwm_spy, vix_change_1d, spy_gap,
  spy_return_1d, vix_risk_flag, spy_trend_score, dd_next, label

Checkpoint state: data/rf_retrain_checkpoints.json
  { "triggered": [120, 150] }   <- tracks which thresholds already fired

Usage:
    source /root/odte_strategy/venv/bin/activate
    python3 /root/odte_strategy/scripts/rf_scoreboard_update.py
"""
from __future__ import annotations

import os
import json
import subprocess
import sys
import joblib
from datetime import timedelta
from datetime import datetime, timezone

import pandas as pd
import numpy as np
import yfinance as yf
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score, confusion_matrix, classification_report

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DD_THRESH   = -0.007
CHECKPOINTS = [120, 150, 200]

PREFERRED_COLS = [
    "regime_num", "risk_off", "caution", "risk_on",
    "regime_change", "days_in_regime",
    "spy_trend_score", "vix_risk_flag", "rs_iwm_spy",
    "vix_change_1d", "spy_return_1d", "spy_gap",
]
RF_PARAMS = dict(n_estimators=500, max_depth=6, random_state=42,
                 class_weight="balanced_subsample", n_jobs=-1)

DATA_DIR    = "/root/odte_strategy/data"
SCOREBOARD  = f"{DATA_DIR}/rf_scoreboard.csv"
FEATURES    = f"{DATA_DIR}/rf_features.csv"
PREDS_CSV   = f"{DATA_DIR}/rf_daily_predictions.csv"
ARM_HIST    = f"{DATA_DIR}/arm_state_history.csv"
MODEL_PATH  = f"{DATA_DIR}/rf_model.joblib"
CKPT_FILE   = f"{DATA_DIR}/rf_retrain_checkpoints.json"

SCOREBOARD_COLS = [
    "date", "arm_regime", "prob_safe", "gate_thr",
    "rs_iwm_spy", "vix_change_1d", "spy_gap", "spy_return_1d",
    "vix_risk_flag", "spy_trend_score",
    "dd_next", "label",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_checkpoint_state() -> set:
    if os.path.exists(CKPT_FILE):
        with open(CKPT_FILE) as f:
            d = json.load(f)
        return set(d.get("triggered", []))
    return set()


def save_checkpoint_state(triggered: set):
    with open(CKPT_FILE, "w") as f:
        json.dump({"triggered": sorted(triggered)}, f, indent=2)


def fetch_spy_ohlc(start_date: str, end_date: str) -> pd.DataFrame:
    """Fetch SPY OHLC and return a clean DataFrame indexed by normalized date."""
    raw = yf.download("SPY", start=start_date, end=end_date,
                      auto_adjust=True, progress=False)
    if raw.empty:
        return pd.DataFrame()
    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    raw.index = pd.to_datetime(raw.index).normalize()
    raw = raw.sort_index()
    return raw[["Open", "High", "Low", "Close"]].dropna()


def build_next_day_map(spy: pd.DataFrame) -> dict:
    dates = spy.index
    return {dates[i]: dates[i + 1] for i in range(len(dates) - 1)}


def compute_dd(spy: pd.DataFrame, date: pd.Timestamp) -> float | None:
    if date not in spy.index:
        return None
    open_ = float(spy.loc[date, "Open"])
    low_  = float(spy.loc[date, "Low"])
    if open_ <= 0:
        return None
    return (low_ / open_) - 1


def load_scoreboard() -> pd.DataFrame:
    if os.path.exists(SCOREBOARD):
        df = pd.read_csv(SCOREBOARD)
        df["date"] = pd.to_datetime(df["date"]).dt.normalize()
        return df
    return pd.DataFrame(columns=SCOREBOARD_COLS)


def save_scoreboard(df: pd.DataFrame):
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df = df.drop_duplicates(subset=["date"], keep="last").sort_values("date")
    df.to_csv(SCOREBOARD, index=False)


def labeled_count_in_features() -> int:
    if not os.path.exists(FEATURES):
        return 0
    f = pd.read_csv(FEATURES)
    return int(f["label"].notna().sum())


# ---------------------------------------------------------------------------
# Step A: Fill dd_next + label for most recent unfilled scoreboard row
# ---------------------------------------------------------------------------
def step_a_fill_previous(sb: pd.DataFrame, spy: pd.DataFrame,
                          next_day_map: dict) -> tuple[pd.DataFrame, str | None]:
    """
    Find the most recent scoreboard row where dd_next is null.
    Look up D_next, compute dd_next, assign label.
    Returns updated sb and the date string that was filled (or None).
    """
    unfilled_mask = sb["dd_next"].isna() & sb["date"].notna()
    if unfilled_mask.sum() == 0:
        print("[A] No unfilled rows — nothing to backfill")
        return sb, None

    # Most recent unfilled
    idx = sb[unfilled_mask]["date"].idxmax()
    d   = sb.loc[idx, "date"]

    d_next = next_day_map.get(d)
    if d_next is None:
        print(f"[A] {d.date()}: no next trading day in SPY data yet — skipping")
        return sb, None

    dd = compute_dd(spy, d_next)
    if dd is None:
        print(f"[A] {d.date()}: SPY data for {d_next.date()} not available yet")
        return sb, None

    lbl = 0 if dd <= DD_THRESH else 1
    sb.loc[idx, "dd_next"] = round(dd, 6)
    sb.loc[idx, "label"]   = lbl

    print(f"[A] Filled {d.date()} → D_next={d_next.date()}  dd={dd:.4f}  label={lbl}")
    return sb, d.strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Step B: Upsert that label into rf_features.csv
# ---------------------------------------------------------------------------
def step_b_upsert_features(filled_date: str | None, sb: pd.DataFrame):
    if filled_date is None or not os.path.exists(FEATURES):
        return
    feat = pd.read_csv(FEATURES)
    feat["date"] = pd.to_datetime(feat["date"]).dt.strftime("%Y-%m-%d")

    row_sb = sb[sb["date"] == pd.to_datetime(filled_date).normalize()]
    if row_sb.empty:
        return
    lbl = row_sb.iloc[0]["label"]
    if pd.isna(lbl):
        return

    if filled_date in feat["date"].values:
        feat.loc[feat["date"] == filled_date, "label"] = int(lbl)
        action = "updated"
    else:
        print(f"[B] {filled_date} not in rf_features.csv — date not in ARM history, skipping upsert")
        feat.to_csv(FEATURES, index=False)
        return

    feat.to_csv(FEATURES, index=False)
    new_count = feat["label"].notna().sum()
    print(f"[B] rf_features.csv label upserted for {filled_date} (label={int(lbl)}, {action}) — total labeled: {new_count}")


# ---------------------------------------------------------------------------
# Step C: Append today's row
# ---------------------------------------------------------------------------
def step_c_append_today(sb: pd.DataFrame) -> pd.DataFrame:
    # Load today's score from rf_daily_predictions
    if not os.path.exists(PREDS_CSV):
        print("[C] rf_daily_predictions.csv not found — skipping today append")
        return sb
    preds = pd.read_csv(PREDS_CSV)
    preds["date"] = pd.to_datetime(preds["date"].astype(str),
                                    format="%Y%m%d", errors="coerce").dt.normalize()
    preds = preds.dropna(subset=["date"]).sort_values("date")
    if preds.empty:
        print("[C] No predictions found")
        return sb

    today_pred = preds.iloc[-1]
    today_date = today_pred["date"]

    # Already in scoreboard?
    if not sb.empty and (sb["date"] == today_date).any():
        print(f"[C] {today_date.date()} already in scoreboard — skipping append")
        return sb

    # Load feature snapshot from arm_state_history
    arm = pd.read_csv(ARM_HIST)
    dc  = "trade_date" if "trade_date" in arm.columns else "date"
    arm[dc] = pd.to_datetime(arm[dc]).dt.normalize()
    arm = arm.sort_values(dc)

    arm_row = arm[arm[dc] == today_date]
    if arm_row.empty:
        # Fall back to last row
        arm_row = arm.iloc[[-1]]
        print(f"[C] WARNING: {today_date.date()} not in arm_state_history — using last row")
    arm_row = arm_row.iloc[0]

    gate_thr = float(today_pred.get("threshold", 0.65))

    new_row = {
        "date":            today_date,
        "arm_regime":      arm_row.get("arm_regime"),
        "prob_safe":       round(float(today_pred.get("prob_safe", 0.0)), 6),
        "gate_thr":        gate_thr,
        "rs_iwm_spy":      arm_row.get("rs_iwm_spy"),
        "vix_change_1d":   arm_row.get("vix_change_1d"),
        "spy_gap":         arm_row.get("spy_gap"),
        "spy_return_1d":   arm_row.get("spy_return_1d"),
        "vix_risk_flag":   arm_row.get("vix_risk_flag"),
        "spy_trend_score": arm_row.get("spy_trend_score"),
        "dd_next":         None,
        "label":           None,
    }

    sb = pd.concat([sb, pd.DataFrame([new_row])], ignore_index=True)
    print(f"[C] Appended today: {today_date.date()}  prob_safe={new_row['prob_safe']:.4f}  "
          f"regime={new_row['arm_regime']}  gate_thr={gate_thr:.2f}")
    return sb


# ---------------------------------------------------------------------------
# Step D: Retrain checkpoint check
# ---------------------------------------------------------------------------
def step_d_retrain_check():
    labeled = labeled_count_in_features()
    print(f"\n[D] Labeled rows in rf_features.csv: {labeled}")

    triggered = load_checkpoint_state()
    new_triggers = []

    for cp in CHECKPOINTS:
        if labeled >= cp and cp not in triggered:
            new_triggers.append(cp)

    if not new_triggers:
        print(f"[D] No new checkpoints crossed (triggered so far: {sorted(triggered)})")
        return

    print(f"[D] NEW CHECKPOINT(S) CROSSED: {new_triggers} — starting retrain")

    # ---- retrain inline (same as rf_train_once.py logic) ----
    feat = pd.read_csv(FEATURES)
    feat = feat.dropna(subset=["label"]).copy()
    feat["label"] = feat["label"].astype(int)
    feat["date"]  = pd.to_datetime(feat["date"])
    feat = feat.sort_values("date").reset_index(drop=True)

    usable = [c for c in PREFERRED_COLS
              if c in feat.columns and feat[c].notna().mean() >= 0.5]
    print(f"[D] Training on {len(feat)} labeled rows, {len(usable)} features: {usable}")

    X = feat[usable].fillna(0).astype(float)
    y = feat["label"].astype(int)

    clf = RandomForestClassifier(**RF_PARAMS)
    clf.fit(X, y)

    # Save timestamped copy
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    ts_path = f"{DATA_DIR}/rf_model_{ts}.joblib"
    joblib.dump({"model": clf, "features": usable}, ts_path)
    print(f"[D] Timestamped model saved → {ts_path}")

    # Overwrite latest
    joblib.dump({"model": clf, "features": usable}, MODEL_PATH)
    print(f"[D] rf_model.joblib updated (latest)")

    # Save metadata
    meta = {
        "trained_at":     f"{ts[:4]}-{ts[4:6]}-{ts[6:8]} {ts[9:11]}:{ts[11:13]}:{ts[13:15]} UTC",
        "rows_total":     len(feat),
        "features":       usable,
        "n_features":     len(usable),
        "label_dist":     feat["label"].value_counts().to_dict(),
        "checkpoint":     new_triggers,
        "checkpoint_model": ts_path,
    }
    meta_path = f"{DATA_DIR}/rf_model_meta.json"
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)

    # ---- 70/30 forward validation ----
    split_idx = int(len(feat) * 0.70)
    train = feat.iloc[:split_idx]
    test  = feat.iloc[split_idx:]

    u2  = [c for c in PREFERRED_COLS
           if c in train.columns and train[c].notna().mean() >= 0.5]
    clf2 = RandomForestClassifier(**RF_PARAMS)
    clf2.fit(train[u2].fillna(0).astype(float), train["label"].astype(int))
    probs = clf2.predict_proba(test[u2].fillna(0).astype(float))[:, 1]
    preds = clf2.predict(test[u2].fillna(0).astype(float))
    yte   = test["label"].astype(int)

    try:
        auc = roc_auc_score(yte, probs)
    except Exception:
        auc = float("nan")
    acc = (preds == yte).mean()

    print(f"\n[D] Forward validation — train {len(train)} / test {len(test)}")
    print(f"    Accuracy: {acc:.3f}   AUC: {auc:.3f}")
    bl = (yte == 0).mean()
    print(f"    Baseline bad_rate: {bl:.3f}")
    for thr in [0.60, 0.65, 0.70]:
        mask = probs >= thr
        if mask.sum() == 0:
            continue
        bad = (yte[mask] == 0).mean()
        lift = bl / bad if bad > 0 else float("inf")
        print(f"    thr={thr:.2f}  trade_rate={mask.mean():.1%}  bad_rate={bad:.3f}  ({bl:.3f}) → {lift:.1f}x lift")

    # Save validation results
    val_path = f"{DATA_DIR}/rf_validation_{ts}.json"
    with open(val_path, "w") as f:
        json.dump({
            "trained_at":   meta["trained_at"],
            "checkpoint":   new_triggers,
            "labeled_rows": len(feat),
            "train_rows":   len(train),
            "test_rows":    len(test),
            "accuracy":     round(acc, 4),
            "forward_auc":  round(auc, 4) if not np.isnan(auc) else None,
            "baseline_bad_rate": round(bl, 4),
            "thresholds": {
                str(thr): {
                    "trade_rate": round((probs >= thr).mean(), 4),
                    "bad_rate":   round((yte[probs >= thr] == 0).mean(), 4) if (probs >= thr).sum() > 0 else None,
                }
                for thr in [0.60, 0.65, 0.70]
            },
        }, f, indent=2)
    print(f"[D] Validation results saved → {val_path}")

    # Mark checkpoints as triggered
    triggered.update(new_triggers)
    save_checkpoint_state(triggered)
    print(f"[D] Checkpoint state updated: triggered={sorted(triggered)}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    print(f"=== RF Scoreboard Update | {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')} ===\n")

    # Fetch SPY OHLC for the full scoreboard range (wide window)
    # We need enough history to cover all scoreboard dates
    arm = pd.read_csv(ARM_HIST)
    dc  = "trade_date" if "trade_date" in arm.columns else "date"
    min_date = pd.to_datetime(arm[dc]).min()

    spy_start = (min_date - timedelta(days=5)).strftime("%Y-%m-%d")
    # end = today + 3 days to ensure latest data is included
    spy_end   = (pd.Timestamp.now() + timedelta(days=3)).strftime("%Y-%m-%d")
    print(f"[init] Fetching SPY OHLC {spy_start} → {spy_end}")
    spy = fetch_spy_ohlc(spy_start, spy_end)
    if spy.empty:
        print("[init] ERROR: SPY fetch returned empty — aborting")
        return
    print(f"[init] SPY rows: {len(spy)}  ({spy.index.min().date()} → {spy.index.max().date()})")
    next_day_map = build_next_day_map(spy)

    # Load scoreboard
    sb = load_scoreboard()
    print(f"[init] Scoreboard rows: {len(sb)}\n")

    # Steps
    sb, filled_date = step_a_fill_previous(sb, spy, next_day_map)
    step_b_upsert_features(filled_date, sb)
    sb = step_c_append_today(sb)
    save_scoreboard(sb)
    print(f"\n[save] Scoreboard saved → {SCOREBOARD}  ({len(sb)} rows)")

    step_d_retrain_check()

    print("\n=== Done ===")


if __name__ == "__main__":
    main()
