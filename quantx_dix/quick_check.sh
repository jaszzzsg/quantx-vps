#!/bin/bash
# Quick progress checker for chunk 2020

echo "======================================"
echo "📊 Chunk 2020 Progress"
echo "======================================"
echo ""
echo "Latest progress:"
grep -E "\[[[:space:]]*[0-9]+%\] Day" /root/projects/quantx_dix/logs/chunk_2020_FINAL_20260131_071207.log | tail -1
echo ""
echo "Process status:"
ps aux | grep "compute_diy_dix_6y_optimized" | grep -v grep | awk '{print "✓ Running (PID " $2 ") - Started at " $9}'
echo ""
echo "To watch live updates:"
echo "  tail -f /root/projects/quantx_dix/logs/chunk_2020_FINAL_20260131_071207.log | grep --line-buffered 'Day '"
