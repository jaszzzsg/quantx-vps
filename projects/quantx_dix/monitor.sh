#!/bin/bash
# Live progress monitor for chunk 2020 fetch
# Shows real-time progress bar in VS Code

cd /root/projects/quantx_dix
source .venv/bin/activate
python scripts/tools/live_monitor_2020.py
