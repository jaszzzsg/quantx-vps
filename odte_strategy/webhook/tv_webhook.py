from fastapi import FastAPI, Request, HTTPException
from datetime import datetime, timezone
import json
import os

APP = FastAPI()

# Simple shared secret (set the same in TradingView alert message)
SECRET = os.environ.get("TV_WEBHOOK_SECRET", "CHANGE_ME")

OUT_PATH = "/root/odte_strategy/state/spcfd.json"

@APP.post("/tv")
async def tv(request: Request):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    # auth
    if payload.get("secret") != SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Expecting: {"secret":"...","symbol":"SPCFD","value":123.45,"ts":"2026-01-08T12:34:56-05:00"}
    val = payload.get("value", None)
    if val is None:
        raise HTTPException(status_code=400, detail="Missing 'value'")

    try:
        val = float(val)
    except Exception:
        raise HTTPException(status_code=400, detail="'value' must be a number")

    record = {
        "source": "tradingview",
        "symbol": payload.get("symbol", "SPCFD"),
        "value": val,
        "tv_ts": payload.get("ts", None),
        "received_utc": datetime.now(timezone.utc).isoformat(),
    }

    tmp_path = OUT_PATH + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump(record, f, indent=2)
    os.replace(tmp_path, OUT_PATH)

    return {"ok": True, "saved": OUT_PATH, "value": val}
