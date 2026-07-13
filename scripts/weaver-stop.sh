#!/bin/bash
# إيقاف كل خوادم WeaverCode
[ -f ~/.weaver/pids.txt ] && kill $(cat ~/.weaver/pids.txt) 2>/dev/null
pkill -f "web/server.py" 2>/dev/null
rm -f ~/.weaver/pids.txt
echo "🕸️ WeaverCode أُوقف (كل الخوادم)."
