# IBKR Client ID Complete Registry
**Last Updated:** 2026-02-11 UTC

---

## 📋 Port Allocation Strategy

| Port | Type | Auto-Assign Range | Reserved IDs |
|------|------|-------------------|--------------|
| 4001 | LIVE | 100-199 | TBD |
| 4002 | Paper | 200-299 | 20-26, 80, 991 |
| 7497 | TWS | 300-399 | None |

---

## 🔒 Reserved IDs (Hardcoded - DO NOT AUTO-ASSIGN)

### Port 4002 (Paper Trading)

| ID | Purpose | Project | File/Script | Status | Notes |
|----|---------|---------|-------------|--------|-------|
| 20 | dix_history_smoke | quantx_dix | `config/ibkr_client_ids.json` | Reserved | Smoke test |
| 21 | dix_history_6y_run | quantx_dix | `config/ibkr_client_ids.json` | Reserved | 6Y historical run |
| **22** | **dix_daily_one_day** | **quantx_dix** | `compute_diy_dix_one_day_ibkr.py:157` | **🟢 ACTIVE** | **Daily 1am UTC fetch** |
| 23 | ibkr_symbol_profile_cache | quantx_dix | `config/ibkr_client_ids.json` | Reserved | Profile cache |
| 24 | dix_history_6y | quantx_dix | `config/ibkr_client_ids.json` | Reserved | 6Y historical |
| 26 | fetch_6y_chunked | quantx_dix | `fetch_6y_chunked.sh:31` | Reserved | Chunked fetch |
| **80** | **chunk_2020_part1** | **quantx_dix** | Manual launch | ✅ DONE | PID 2279141 finished — chunk_2020.csv complete (20200417→20201231, 97.77% coverage) |
| **81** | *unused* | *unused* | *unused* | ⏳ AVAILABLE | Skipped — Parts 2-3 already complete |
| **82** | **chunk_2021_part1** | **quantx_dix** | Manual launch | ✅ DONE (dead) | PID 2610294 died Feb 10 (gateway down) — covered 20210104→20210311, 49 days, 96.6% coverage |
| **83** | **chunk_2021_part2** | **quantx_dix** | Manual launch | 🟢 ACTIVE | PID 2675397, fetching 20210312→20211231 (211 days), started Feb 11 |
| **991** | **arm_vix_fetch** | **quantx_arm** | `ib_vix.py:19` | **🟢 ACTIVE** | **Daily 14:45 UTC** |

### Port 4001 (LIVE Trading)

| ID | Purpose | Project | File/Script | Status | Notes |
|----|---------|---------|-------------|--------|-------|
| TBD | ARM regime (unknown) | quantx_arm | To be identified | Unknown | Check if ARM uses LIVE port |

---

## 🔄 Dynamic Allocation (Auto-Assigned)

### QuantX_Dashboard_Monitor Strategies
- Uses legacy `get_or_allocate_client_id()` function
- **Location:** `utils/client_id_manager.py` (old version)
- **Strategies:**
  - `001_alpha_spx_1330_0dte_bear_call.py`
  - `002_alpha_spx_1330_0dte_bull_put.py`
- **Migration Status:** ⏳ Needs migration to centralized manager

---

## 📊 Active Processes Summary

| PID | Script | Client ID | Port | Status | Details |
|-----|--------|-----------|------|--------|---------|
| Daily cron | `compute_diy_dix_one_day_ibkr.py` | 22 | 4002 | 🟢 Automated | 1am UTC daily |
| 2675397 | `compute_diy_dix_6y_optimized.py` | 83 | 4002 | 🟢 Running | 2021 Part 2: 20210312→20211231 (211 days), started Feb 11 |
| Daily cron | `arm_regime_engine.py` | 991 | 4002 | 🟢 Automated | 14:45 UTC daily |

---

## 🛠️ Centralized Manager

**Files:**
- Manager: `/root/shared/ibkr/client_id_manager.py`
- Excel Log: `/root/shared/ibkr/client_id_log.xlsx`
- Lock File: `/root/shared/ibkr/client_ids.json`
- Registry: `/root/shared/ibkr/CLIENT_ID_REGISTRY.md` (this file)

**View Commands:**
```bash
# View all reserved IDs
python << 'END'
import sys; sys.path.insert(0, '/root/shared/ibkr')
from client_id_manager import list_reserved_ids
for k,v in list_reserved_ids().items():
    print(f"ID {k}: {v['purpose']} ({v['project']}) port={v['port']}")
END

# View active IDs
python -c "import sys; sys.path.insert(0, '/root/shared/ibkr'); from client_id_manager import list_active_ids; print(list_active_ids())"

# View full Excel log
python -c "import sys; sys.path.insert(0, '/root/shared/ibkr'); from client_id_manager import view_log; print(view_log())"
```

---

## ✅ Migration Checklist

- [x] Document all existing hardcoded IDs
- [x] Create centralized manager at `/root/shared/ibkr/`
- [x] Add all reserved IDs to centralized manager
- [x] Create symlinks from projects to centralized manager
- [ ] Migrate Dashboard strategies to use centralized manager
- [ ] Identify ARM LIVE port client IDs (if any)
- [ ] Update future scripts to use auto-assignment

---

## 🚨 Important Notes

1. **IDs 20-26, 991 are HARDCODED** — do not modify without updating the relevant scripts
2. **ID 22, 83, 991 are ACTIVE** — in use as of Feb 11, 2026
3. **Port 4002 range collision**: ID 991 is outside the 200-299 range (legacy assignment, do not change)
4. **Dashboard uses dynamic allocation** — needs migration to new centralized system
5. **Always check this registry before manually assigning new IDs**

### ♻️ ID Reuse Rule
**An ID is FREE to reuse as soon as its PID is dead.**
- Before starting a new fetch, run: `ps -p <PID>` to confirm old process is gone
- If dead: mark old row ✅ DONE (dead) and reuse the same ID — no need to increment
- If alive: pick the next available ID (check AVAILABLE rows above)
- **Do NOT permanently increment IDs on every restart** — this wastes the range needlessly

---

**End of Registry**
