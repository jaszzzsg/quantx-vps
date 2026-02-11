# =========================================================
# RF TRAIN ONCE — VPS
# =========================================================
# Trains RandomForest once and saves model to disk
# =========================================================

import os
import json
import joblib
import pandas as pd
from datetime import datetime
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report


# =========================================================
# PATHS
# =========================================================
FEATURE_CSV = "/root/odte_strategy/data/rf_features.csv"
MODEL_DIR   = "/root/odte_strategy/models"
MODEL_PATH  = f"{MODEL_DIR}/rf_model.joblib"
META_PATH   = f"{MODEL_DIR}/rf_model_meta.json"


# =========================================================
# PARAMS (CONSERVATIVE)
# =========================================================
RF_PARAMS = dict(
    n_estimators=800,
    max_depth=10,
    min_samples_leaf=5,
    random_state=42,
    n_jobs=-1
)


# =========================================================
# MAIN
# =========================================================
def main():
    print("[RF] Loading features...")

    if not os.path.isfile(FEATURE_CSV):
        raise FileNotFoundError(f"Feature file not found: {FEATURE_CSV}")

    df = pd.read_csv(FEATURE_CSV)

    if "label" not in df.columns:
        raise ValueError("Feature CSV must contain 'label' column")

    # Separate X / y
    y = df["label"]
    X = df.drop(columns=["label", "date", "arm_regime"], errors="ignore")

    print(f"[RF] Rows: {len(df)}, Features: {X.shape[1]}")

    # Train
    print("[RF] Training RandomForest (one-time)...")
    rf = RandomForestClassifier(**RF_PARAMS)
    rf.fit(X, y)

    # Basic sanity check
    preds = rf.predict(X)
    print("[RF] Training set report:")
    print(classification_report(y, preds, digits=3))

    # Save model
    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump(rf, MODEL_PATH)

    # Save metadata
    meta = {
        "trained_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC"),
        "rows": len(df),
        "features": list(X.columns),
        "params": RF_PARAMS
    }

    with open(META_PATH, "w") as f:
        json.dump(meta, f, indent=2)

    print(f"[RF] Model saved to: {MODEL_PATH}")
    print(f"[RF] Meta saved to:  {META_PATH}")


if __name__ == "__main__":
    main()
