# QuantX DIX Project - Claude Quick Reference

**Parent Overview:** `/root/projects/PROJECT_OVERVIEW.md`

## What This Project Does
Fetches FINRA short volume data + IBKR close prices to calculate DIX (Dark Index) - an institutional flow indicator.

## Key Scripts
- `scripts/core/compute_diy_dix_one_day_ibkr.py` - Daily fetch (ID 22, runs 1am UTC)
- `scripts/core/compute_diy_dix_6y_optimized.py` - Historical chunked fetch
- `scripts/core/weekly_dix_report.py` - Weekly Telegram report
- `scripts/core/daily_precious_metals_report.py` - Precious metals focus

## Client IDs Used
See: `CLIENT_ID_REGISTRY.md` (symlink to `/root/shared/ibkr/CLIENT_ID_REGISTRY.md`)
- ID 22: Daily fetch (ACTIVE)
- ID 80: Chunk 2020 (RUNNING)
- IDs 20-26: Reserved

## Check Progress
```bash
# Daily fetch logs
ls -lt data/dix/details/*.csv | head -5

# Chunk progress
tail -3 logs/chunk_2020_FINAL_*.log | head -1

# Weekly report status
systemctl status quantx-dix-weekly-report.timer
```
