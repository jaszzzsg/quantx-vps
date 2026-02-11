#!/bin/bash
echo "📝 REGISTRY UPDATE CHECKLIST:"
echo ""
echo "1. Edit main registry:"
echo "   nano /root/shared/ibkr/CLIENT_ID_REGISTRY.md"
echo ""
echo "2. Update project overview (if needed):"
echo "   nano /root/projects/PROJECT_OVERVIEW.md"
echo ""
echo "3. Or tell Claude in your next chat:"
echo '   "Please read /root/projects/PROJECT_OVERVIEW.md first,"'
echo '   "then update CLIENT_ID_REGISTRY.md: add ID XXX for YYY"'
echo ""
echo "4. View current registry:"
cat /root/shared/ibkr/QUICK_REFERENCE.txt
