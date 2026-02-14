from zoneinfo import ZoneInfo

import os, json
from telegram_notify import tg_send
import pandas as pd
import joblib
from datetime import datetime, timezone

DATA_DIR = "/root/odte_strategy/data"
MODEL_PATH = f"{DATA_DIR}/rf_model.joblib"
PRED_CSV = f"{DATA_DIR}/rf_daily_predictions.csv"
ARM_JSON = "/root/projects/quantx_arm/state/regime_state.json"
ARM_HIST = f"{DATA_DIR}/arm_state_history.csv"

# Default gate threshold — validated 2026-02-14 (AUC 0.935, bad_rate@0.65 = 3.8% vs 24.7% baseline)
RF_TRADE_THRESH = 0.65

# Per-regime overrides (optional — regimes with higher risk use stricter gates)
REGIME_THR = {
    "R0": RF_TRADE_THRESH,
    "R1": RF_TRADE_THRESH,
    "R1.5": 0.70,
    "R2": 0.75,
    "R3": 0.78,
    "R4": RF_TRADE_THRESH,
    "R5": RF_TRADE_THRESH,
}

# RF_THR env var overrides RF_TRADE_THRESH (useful for testing; normally not set)
DEFAULT_RF_THR = float(os.environ.get("RF_THR", str(RF_TRADE_THRESH)))

def norm_regime_str(reg):
    if reg is None:
        return None
    r = str(reg).strip()
    if not r:
        return None
    if not r.startswith("R"):
        r = "R" + r
    return r

def regime_to_num(reg):
    r = norm_regime_str(reg)
    if r is None:
        return None
    try:
        return float(r.replace("R",""))
    except Exception:
        return None

def load_features_from_arm_history(prefer_date=None):
    """
    Best source because it contains extra columns:
    trade_date, spy_trend_score, vix_risk_flag, rs_iwm_spy, etc.
    We will take the last row by default, or match prefer_date if provided.
    """
    if not os.path.isfile(ARM_HIST):
        return None
    df = pd.read_csv(ARM_HIST)
    if df.empty:
        return None

    date_col = "trade_date" if "trade_date" in df.columns else ("date" if "date" in df.columns else None)
    if date_col is None:
        return None

    df[date_col] = pd.to_datetime(df[date_col]).dt.date.astype(str)

    if prefer_date is not None and prefer_date in set(df[date_col].astype(str)):
        row = df[df[date_col].astype(str) == str(prefer_date)].iloc[-1].to_dict()
    else:
        row = df.iloc[-1].to_dict()

    reg = row.get("arm_regime") or row.get("regime") or row.get("armRegime")
    rstr = norm_regime_str(reg)
    rnum = row.get("regime_num")
    if rnum is None:
        rnum = regime_to_num(rstr)

    feats = dict(row)
    feats["date"] = str(row[date_col])
    feats["arm_regime"] = rstr
    feats["regime_num"] = float(rnum) if rnum is not None else None
    return feats

def today_ny_yyyymmdd() -> str:
    return datetime.now(ZoneInfo("America/New_York")).strftime("%Y%m%d")

def load_arm_state():
    if not os.path.isfile(ARM_JSON):
        return {}
    try:
        with open(ARM_JSON, "r") as f:
            return json.load(f)
    except Exception:
        return {}

def make_skip_row(date_str: str, reason: str, arm_regime=None):
    # Always produce a valid row for rf_daily_predictions.csv
    r = norm_regime_str(arm_regime)
    thr = REGIME_THR.get(r, DEFAULT_RF_THR) if r else DEFAULT_RF_THR
    return {
        "date": str(date_str).replace("-", ""),
        "prob_safe": 0.0,
        "threshold": thr,
        "decision": "SKIP",
        "regime_num": regime_to_num(r),
        "risk_off": 0,
        "caution": 0,
        "risk_on": 0,
        "reason": reason,
        "ts_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    }

def load_date_from_arm_json():
    if not os.path.isfile(ARM_JSON):
        return None
    with open(ARM_JSON, "r") as f:
        s = json.load(f)
    asof = s.get("asof_date") or s.get("trade_date") or s.get("date")
    if asof is None:
        return None
    try:
        return pd.to_datetime(asof).date().isoformat()
    except Exception:
        return str(asof)

def upsert_pred(row):
    new = pd.DataFrame([row])
    if os.path.isfile(PRED_CSV):
        old = pd.read_csv(PRED_CSV)
        df = pd.concat([old, new], ignore_index=True)
        df["date"] = pd.to_datetime(df["date"], format="mixed").dt.strftime("%Y%m%d")
        df = df.drop_duplicates(subset=["date"], keep="last").sort_values("date")
    else:
        df = new
    df.to_csv(PRED_CSV, index=False)

def main():
    # Prefer using ARM JSON date to pick matching arm_history row (avoids mismatch)
    prefer_date = load_date_from_arm_json()
    output_date = today_ny_yyyymmdd()
    date_str = output_date

    feats = load_features_from_arm_history(prefer_date=prefer_date)
    if feats is None:

        # Fail-safe: still upsert a SKIP row so odte-strategy never dies with "RF row missing"
        arm_state = load_arm_state()
        arm_regime = arm_state.get("regime")
        degraded = int(arm_state.get("data_degraded", 0) or 0)
        d_reason = arm_state.get("degraded_reason", "") or ""
        reason = "MISSING_ARM_HISTORY"
        if degraded:
            reason = "ARM_DATA_DEGRADED: " + d_reason
        date_str = output_date
        out = make_skip_row(date_str, reason, arm_regime=arm_regime)
        upsert_pred(out)
        print(out)
        try:
            tg_send(f"⚠️ RF FAILSAFE {out['date']} | {out.get('reason','')} | decision=SKIP")
        except Exception:
            pass
        return

    obj = joblib.load(MODEL_PATH)
    model = obj["model"]
    cols = obj["features"]

    # Build X with exactly the trained columns (missing -> 0)
    row = {}
    for c in cols:
        v = feats.get(c, 0)
        if v is None or (isinstance(v, float) and pd.isna(v)):
            v = 0
        row[c] = v

    X = pd.DataFrame([row]).astype(float)
    prob_safe = float(model.predict_proba(X)[0][1])

    rstr = feats.get("arm_regime")
    thr = REGIME_THR.get(norm_regime_str(rstr), DEFAULT_RF_THR)
    decision = "TRADE" if prob_safe >= thr else "SKIP"

    out = {
        "date": output_date,
        "prob_safe": round(prob_safe, 6),
        "threshold": thr,
        "decision": decision,
        "regime_num": feats.get("regime_num"),
        "risk_off": int(feats.get("risk_off", 0) or 0),
        "caution": int(feats.get("caution", 0) or 0),
        "risk_on": int(feats.get("risk_on", 0) or 0),
        "ts_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    }

    upsert_pred(out)

    # Verbose scoring report (written to systemd journal / stdout)
    gate = prob_safe >= thr
    print(
        f"\n=== RF Score | {output_date} ===\n"
        f"  prob_safe      : {prob_safe:.4f}\n"
        f"  threshold      : {thr:.2f}  (RF_TRADE_THRESH={RF_TRADE_THRESH})\n"
        f"  gate           : {'TRADE ✓' if gate else 'SKIP ✗'}\n"
        f"  regime         : {rstr}\n"
        f"  days_in_regime : {feats.get('days_in_regime', 'n/a')}\n"
        f"  rs_iwm_spy     : {feats.get('rs_iwm_spy', 'n/a')}\n"
        f"  vix_risk_flag  : {feats.get('vix_risk_flag', 'n/a')}\n"
        f"  spy_trend_score: {feats.get('spy_trend_score', 'n/a')}\n"
    )

    # Daily Telegram RF report
    try:
        decision_icon = "✅ TRADE" if decision == "TRADE" else "🚫 SKIP"
        tg_send(
            f"🤖 RF Score | {output_date}\n"
            f"{decision_icon} | prob={prob_safe:.3f} ≥ thr={thr:.2f}? {'YES' if decision == 'TRADE' else 'NO'}\n"
            f"Regime: {rstr} | features: {len(cols)}"
        )
    except Exception:
        pass

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # Absolute fail-safe: still write a SKIP row for today
        arm_state = load_arm_state()
        prefer_date = load_date_from_arm_json()
        output_date = today_ny_yyyymmdd()
        date_str = output_date
        arm_regime = arm_state.get("regime")
        reason = f"RF_SCORE_EXCEPTION: {type(e).__name__}: {e}"
        out = make_skip_row(date_str, reason, arm_regime=arm_regime)
        # include degraded info
        out["arm_data_degraded"] = int(arm_state.get("data_degraded", 0) or 0)
        out["arm_degraded_reason"] = arm_state.get("degraded_reason", "") or ""
        upsert_pred(out)
        print(out)
        try:
            tg_send(f"⚠️ RF EXCEPTION {out['date']} | {out.get('reason','')} | decision=SKIP")
        except Exception:
            pass
        # IMPORTANT: exit 0 so systemd chain continues
        raise SystemExit(0)
