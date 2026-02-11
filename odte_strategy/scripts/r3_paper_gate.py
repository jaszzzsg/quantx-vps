import json
from pathlib import Path
from datetime import datetime

STATE = Path("/root/projects/quantx_arm/state/regime_state.json")
LOG   = Path("/root/odte_strategy/logs/trade_gate.log")

def log(line: str):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        f.write(line + "\n")

def main():
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

    if not STATE.exists():
        msg = f"{ts} | ERROR | missing {STATE} -> SKIP"
        log(msg)
        print(msg)
        return 2

    state = json.loads(STATE.read_text(encoding="utf-8"))
    reg = state.get("regime") or state.get("arm_regime") or state.get("armRegime")

    # 1) Obey ARM's daily blocklist first (stronger rule)
    blocked_today = set(state.get("blocked_strategies_today", []))
    if "BULL_PUT" in blocked_today:
        msg = f"{ts} | SKIP | regime={reg} | BULL_PUT_BLOCKED_BY_ARM | PAPER_ONLY_WEEK"
        log(msg)
        print(msg)
        return 1

    # 2) Regime rule: R3 is paper-only week
    if reg == "R3":
        msg = f"{ts} | SKIP | regime=R3 | PAPER_ONLY_WEEK"
        log(msg)
        print(msg)
        return 1

    # 3) Otherwise allow (paper)
    msg = f"{ts} | ALLOW | regime={reg} | PAPER_OK"
    log(msg)
    print(msg)
    return 0



if __name__ == "__main__":
    raise SystemExit(main())
