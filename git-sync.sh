#!/bin/bash
# git-sync.sh — stage, commit, and push all changes in /root/projects
# Usage:  ./git-sync.sh "your message"
#         ./git-sync.sh          (uses auto message with timestamp)

cd /root/projects

MSG="${1:-Auto-sync $(date '+%Y%m%d %H:%M') UTC}"

git add -A
CHANGED=$(git status --short | wc -l)

if [ "$CHANGED" -eq 0 ]; then
  echo "Nothing to commit — working tree clean."
  exit 0
fi

git status --short
echo ""
git commit -m "$MSG"
git push origin main
echo ""
echo "✅ Pushed to github.com/jaszzzsg/quantx-vps"
