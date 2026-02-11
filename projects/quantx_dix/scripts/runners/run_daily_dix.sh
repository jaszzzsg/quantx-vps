#!/usr/bin/env bash
set -euo pipefail

BASE=/root/projects/quantx_dix
VENV="$BASE/.venv/bin/activate"

echo "[0%] Starting QuantX DIX daily pipeline"

source "$VENV"
cd "$BASE"

echo "[10%] Step 1/2: Fetch daily DIX (raw ticker-level)"
# Step 1 script lives under scripts/core now
python scripts/core/compute_diy_dix_one_day_ibkr.py

# Find newest details file produced by Step 1 (support BOTH old and new output dirs)
DETAILS_A="$BASE/data/dix/details"
DETAILS_B="$BASE/scripts/data/dix/details"

DETAILS_CSV="$(ls -1t \
  "$DETAILS_A"/diy_dix_details_*_ibkr.csv \
  "$DETAILS_B"/diy_dix_details_*_ibkr.csv \
  2>/dev/null | head -n 1 || true)"

if [ -z "${DETAILS_CSV}" ]; then
  echo "[FAIL] No details CSV found in:"
  echo " - $DETAILS_A"
  echo " - $DETAILS_B"
  exit 2
fi

DATE_YYYYMMDD="$(basename "$DETAILS_CSV" | sed -E 's/^diy_dix_details_([0-9]{8})_ibkr\.csv$/\1/')"

# Profile cache can be in different places depending on older/newer scripts
PROFILE_A="$BASE/data/ibkr_symbol_profile_cache.csv"
PROFILE_B="$BASE/scripts/data/ibkr_symbol_profile_cache.csv"
PROFILE_CACHE=""
if [ -f "$PROFILE_A" ]; then PROFILE_CACHE="$PROFILE_A"; fi
if [ -z "$PROFILE_CACHE" ] && [ -f "$PROFILE_B" ]; then PROFILE_CACHE="$PROFILE_B"; fi

if [ -z "$PROFILE_CACHE" ]; then
  echo "[FAIL] Missing profile cache. Looked for:"
  echo " - $PROFILE_A"
  echo " - $PROFILE_B"
  exit 2
fi

OUT_DIR="$BASE/data/dix/summary"

# Find sector flow script (core path first, else fallback search)
SECTOR_SCRIPT=""
if [ -f "$BASE/scripts/core/compute_dix_sector_flow.py" ]; then
  SECTOR_SCRIPT="$BASE/scripts/core/compute_dix_sector_flow.py"
else
  SECTOR_SCRIPT="$(ls -1 $BASE/scripts/**/compute_dix_sector_flow.py 2>/dev/null | head -n 1 || true)"
fi

if [ -z "${SECTOR_SCRIPT}" ]; then
  echo "[FAIL] compute_dix_sector_flow.py not found under $BASE/scripts/"
  exit 2
fi

echo "[60%] Step 2/2: Sector flow + Top20 summaries | date=$DATE_YYYYMMDD"
echo "       details=$DETAILS_CSV"
echo "       profile=$PROFILE_CACHE"
echo "       out_dir=$OUT_DIR"
echo "       sector_script=$SECTOR_SCRIPT"

python "$SECTOR_SCRIPT" \
  --details_csv "$DETAILS_CSV" \
  --profile_cache "$PROFILE_CACHE" \
  --out_dir "$OUT_DIR" \
  --date "$DATE_YYYYMMDD"

echo "[85%] Step 3/3: Persistence (10d + weekly streak)"
python scripts/core/compute_dix_persistence.py


echo "[100%] Done ✅  details=$DETAILS_CSV  out_dir=$OUT_DIR"
