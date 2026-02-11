import os, pandas as pd

DATA_DIR = "/root/odte_strategy/data"
FEATURES = f"{DATA_DIR}/rf_features.csv"
BULL = f"{DATA_DIR}/bull_put_daily_outcomes.csv"
BEAR = f"{DATA_DIR}/bear_call_rf_overlay_results.csv"

def load_outcomes():
    for path in [BULL, BEAR]:
        if not os.path.isfile(path): 
            continue
        df = pd.read_csv(path)
        date_cols = [c for c in df.columns if "date" in c.lower()]
        if not date_cols:
            print(f"[skip] {os.path.basename(path)} no date col")
            continue
        df = df.rename(columns={date_cols[0]: "date"})
        df["date"] = pd.to_datetime(df["date"]).dt.date.astype(str)

        if "breach" in df.columns and "full_loss" in df.columns:
            df["unsafe"] = ((df["breach"]==1)|(df["full_loss"]==1)).astype(int)
            return df[["date","unsafe"]]
    raise RuntimeError("No usable daily outcome file")

print("[1] load features")
feats = pd.read_csv(FEATURES)
feats["date"] = pd.to_datetime(feats["date"]).dt.date.astype(str)

print("[2] load outcomes")
out = load_outcomes()

print("[3] merge + label")
df = feats.merge(out, on="date", how="left")
df.loc[df["unsafe"].notna(), "label"] = 1 - df["unsafe"]
df = df.drop(columns=["unsafe"])

print("[4] write features")
df.to_csv(FEATURES, index=False)
print("OK")
