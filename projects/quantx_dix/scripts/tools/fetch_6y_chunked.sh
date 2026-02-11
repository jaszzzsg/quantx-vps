#!/bin/bash
# Fetch 6 years in yearly chunks to avoid IBKR timeout

cd /root/projects/quantx_dix
source .venv/bin/activate

CHUNKS=(
    "20200417:20201231:2020"
    "20210101:20211231:2021"
    "20220101:20221231:2022"
    "20230101:20231231:2023"
    "20240101:20241231:2024"
    "20250101:20260129:2025-2026"
)

for CHUNK in "${CHUNKS[@]}"; do
    IFS=':' read -r START END LABEL <<< "$CHUNK"
    
    echo ""
    echo "========================================"
    echo "Fetching $LABEL ($START → $END)"
    echo "========================================"
    
    OUT="data/dix/history/diy_dix_chunk_${LABEL}.csv"
    
    python scripts/core/compute_diy_dix_6y_optimized.py \
        --start $START \
        --end $END \
        --host 127.0.0.1 \
        --port 4002 \
        --clientId 26 \
        --sleep 0.02 \
        --top_n 1200 \
        --min_total_vol 200000 \
        --out $OUT
    
    echo "✓ Chunk $LABEL saved to $OUT"
    echo "Waiting 2 minutes before next chunk..."
    sleep 120
done

echo ""
echo "✅ All chunks complete!"
echo "Now merge them with:"
echo "  cat data/dix/history/diy_dix_chunk_*.csv > data/dix/history/diy_dix_6y_merged.csv"
