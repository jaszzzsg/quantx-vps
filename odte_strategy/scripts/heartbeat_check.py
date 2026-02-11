import sys
sys.path.insert(0, "/root/odte_strategy")

import subprocess
from datetime import datetime, timezone
from utils.tg_notify import tg_send

SERVICES = ["regime-status.service", "odte-strategy.service"]

def run(cmd):
    return subprocess.check_output(cmd, text=True).strip()

def last_run_date_utc(service: str) -> str | None:
    # Get last log line timestamp in ISO (UTC) from journal
    try:
        out = run(["journalctl", "-u", service, "-n", "1", "--no-pager", "-o", "short-iso"])
        if not out:
            return None
        # Format: "2025-12-30T15:23:11+00:00 ...."
        ts = out.split(" ", 1)[0]
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        return None

def main():
    today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = []
    ok_all = True
    for svc in SERVICES:
        d = last_run_date_utc(svc)
        if d == today_utc:
            lines.append(f"✅ {svc} ran today (UTC)")
        else:
            ok_all = False
            lines.append(f"❌ {svc} NOT seen today (last: {d or 'never'})")

    msg = "🫀 VPS HEARTBEAT\n" + "\n".join(lines) + f"\nTime: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}"
    # Send only if problem OR (optional) always-send:
    if not ok_all:
        tg_send(msg)
        print("ALERT_SENT: True")
    else:
        print("ALERT_SENT: False (all good)")

if __name__ == "__main__":
    main()
