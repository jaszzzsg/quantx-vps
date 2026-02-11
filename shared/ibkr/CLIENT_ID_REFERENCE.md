# IBKR Client ID Reference

## Port Ranges
- **4001 (LIVE)**: IDs 100-199
- **4002 (Paper)**: IDs 200-299
- **7497 (TWS)**: IDs 300-399

## Reserved IDs (Hardcoded in Scripts)

### Port 4002 (Paper Trading)
| ID | Purpose | Script | Status |
|----|---------|--------|--------|
| 22 | Daily DIX fetch (automated) | `compute_diy_dix_one_day_ibkr.py` | Active (runs 1am UTC daily) |
| 80 | Chunk 2020 fetch | Manual 6Y fetch | Active (running now) |

### Port 4001 (LIVE Trading)
| ID | Purpose | Script | Status |
|----|---------|--------|--------|
| TBD | ARM regime report | Unknown | Active (runs 10:45pm SGT) |

## Auto-Assigned IDs (via client_id_manager.py)
Check live status: `python -c "import sys; sys.path.insert(0, '/root/shared/ibkr'); from client_id_manager import list_active_ids; print(list_active_ids())"`

## View Excel Log
```bash
python << 'ENDPY'
import sys
sys.path.insert(0, '/root/shared/ibkr')
from client_id_manager import view_log
print(view_log())
ENDPY
```

## Files
- Manager: `/root/shared/ibkr/client_id_manager.py`
- Excel Log: `/root/shared/ibkr/client_id_log.xlsx`
- Lock File: `/root/shared/ibkr/client_ids.json`
