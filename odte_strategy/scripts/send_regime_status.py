import sys
sys.path.insert(0, "/root/odte_strategy")

import json
from datetime import datetime, timezone
from utils.tg_notify import tg_send

ARM_JSON = "/root/projects/quantx_arm/state/regime_state.json"

def _ts():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def main():
    try:
        with open(ARM_JSON, "r") as f:
            arm = json.load(f)
        regime = arm.get("regime", "NA")
        asof = arm.get("asof_date") or arm.get("asof") or "NA"
        blocked = arm.get("blocked_strategies_today", []) or []
        notes = arm.get("notes") or arm.get("reason") or ""
        msg = (
            "📌 REGIME STATUS\n"
            f"Regime: {regime}\n"
            f"AsOf: {asof}\n"
            f"BlockedToday: {blocked}\n"
        )
        if notes:
            msg += f"Notes: {notes}\n"
        msg += f"Time: {_ts()}"
        ok = tg_send(msg)
        print("SENT:", ok)
    except Exception as e:
        ok = tg_send(f"⚠️ REGIME STATUS FAILED\nError: {type(e).__name__}: {e}\nTime: {_ts()}")
        print("SENT_ERR:", ok)
        raise

if __name__ == "__main__":
    main()
