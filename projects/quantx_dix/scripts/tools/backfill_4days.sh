#!/bin/bash
cd /root/projects/quantx_dix
source .venv/bin/activate

DAYS=("20260123" "20260126" "20260127" "20260128")

for YMD in "${DAYS[@]}"; do
    echo ""
    echo "========================================="
    echo "Backfilling $YMD with Top 1200"
    echo "========================================="
    
    # Backup old S&P500 file
    OLD="data/dix/details/diy_dix_details_${YMD}_ibkr.csv"
    if [ -f "$OLD" ]; then
        mv "$OLD" "${OLD}.sp500backup"
        echo "Backed up old file"
    fi
    
    # Fetch with Top 1200 strategy
    python scripts/core/compute_diy_dix_one_day_ibkr.py $YMD
    
    echo "Waiting 30s before next day..."
    sleep 30
done

echo ""
echo "✅ Backfill complete!"
