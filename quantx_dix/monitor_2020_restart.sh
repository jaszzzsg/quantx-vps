#!/bin/bash
# Quick monitor for chunk 2020 restart

LOG_FILE="/root/projects/quantx_dix/logs/chunk_20200528_20201231_20260131_151405.log"

echo "====================================================================="
echo "📊 Chunk 2020 Restart Monitor (May 28 - Dec 31, 2020)"
echo "====================================================================="
echo ""

# Show latest progress
echo "Latest progress:"
tail -20 "$LOG_FILE" | grep -E "Day |closes" | tail -3
echo ""

# Check process
echo "Process status:"
ps aux | grep "1909404" | grep -v grep | awk '{print "  ✓ Running (PID " $2 ") - CPU: " $3 "% - Mem: " $4 "%"}' || echo "  ✗ Process not found!"
echo ""

# Check for connection errors
echo "Recent warnings/errors:"
tail -50 "$LOG_FILE" | grep -iE "warn|error|connectivity|reconnect" | tail -3 || echo "  ✓ No warnings/errors"
echo ""

# Check output file
if [ -f "/root/projects/quantx_dix/data/dix/history/chunk_2020_part2.csv" ]; then
    rows=$(wc -l < /root/projects/quantx_dix/data/dix/history/chunk_2020_part2.csv)
    size=$(ls -lh /root/projects/quantx_dix/data/dix/history/chunk_2020_part2.csv | awk '{print $5}')
    echo "Output file:"
    echo "  Rows: $rows | Size: $size"
else
    echo "Output file: Not created yet"
fi
echo ""

echo "To watch live:"
echo "  tail -f $LOG_FILE | grep --line-buffered 'Day '"
echo "====================================================================="
