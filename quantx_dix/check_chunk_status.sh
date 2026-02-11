#!/bin/bash
# Quick chunk status checker

echo "=== 📊 6Y CHUNK STATUS ==="
echo ""

# Check if chunk 2020 is running
if ps aux | grep "chunk_2020" | grep -v grep > /dev/null; then
    echo "✅ Chunk 2020: RUNNING"
    PID=$(ps aux | grep "chunk_2020.csv" | grep -v grep | awk '{print $2}')
    echo "   PID: $PID"
    
    # Show latest progress
    LOG=$(ls -t /root/projects/quantx_dix/logs/chunk_2020_FINAL_*.log 2>/dev/null | head -1)
    if [ -f "$LOG" ]; then
        echo "   Latest:"
        tail -3 "$LOG" | head -1
    fi
else
    echo "⭕ Chunk 2020: Not running"
fi

echo ""
echo "=== 📁 CHUNK FILES ==="
for year in 2020 2021 2022 2023 2024 2025; do
    FILE="/root/projects/quantx_dix/data/dix/history/chunk_${year}.csv"
    if [ -f "$FILE" ]; then
        LINES=$(wc -l < "$FILE")
        SIZE=$(du -h "$FILE" | cut -f1)
        echo "✅ chunk_${year}.csv: $LINES rows, $SIZE"
    else
        echo "⭕ chunk_${year}.csv: Not created yet"
    fi
done

echo ""
echo "Monitor live: python scripts/tools/monitor_chunk_progress.py 2020"
