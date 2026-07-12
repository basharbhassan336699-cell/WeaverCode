#!/bin/bash
# تشغيل WeaverCode في الخلفية مع لوحة الويب (Termux / Linux / macOS)
# الـ daemon يعمل داخل خادم الويب نفسه، فيكفي تشغيل الخادم.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p ~/.weaver/logs

nohup python3 web/server.py > ~/.weaver/logs/web.log 2>&1 &
WEB_PID=$!
echo "$WEB_PID" > ~/.weaver/pids.txt
HOST="${WEAVER_WEB_HOST:-0.0.0.0}"
PORT="${WEAVER_WEB_PORT:-7878}"
echo "🕸️ WeaverCode Dashboard يعمل — http://$HOST:$PORT (PID: $WEB_PID)"
echo "   السجل: ~/.weaver/logs/web.log | للإيقاف: bash scripts/weaver-stop.sh"
