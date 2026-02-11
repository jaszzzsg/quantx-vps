# QuantX ARM Project - Claude Quick Reference

**Parent Overview:** `/root/projects/PROJECT_OVERVIEW.md`

## What This Project Does
Calculates ARM (Advanced Regime Model) using VIX, breadth, volatility for market regime detection.

## Key Scripts
- `arm_regime_engine.py` - Main regime calculator
- `ib_vix.py` - Fetches VIX from IBKR (client_id=991)

## Client IDs Used
See: `CLIENT_ID_REGISTRY.md` (symlink to `/root/shared/ibkr/CLIENT_ID_REGISTRY.md`)
- ID 991: VIX fetch (ACTIVE, 10:45pm SGT daily)

## Check Status
```bash
systemctl status arm-rf-update.timer
journalctl -u arm-rf-update.service -n 50
```
