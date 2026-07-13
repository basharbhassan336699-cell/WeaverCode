#!/bin/bash
# تشغيل WeaverCode في الخلفية مع لوحة الويب (Termux / Linux / macOS)
# يقتل أي خادم قديم أولاً حتى يعمل الكود الجديد فعلاً (لا يبقى القديم مشغّلاً).
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p ~/.weaver/logs

# ── إيقاف أي خادم WeaverCode سابق (السبب الشائع لبقاء الكود القديم) ──
if [ -f ~/.weaver/pids.txt ]; then kill $(cat ~/.weaver/pids.txt) 2>/dev/null; fi
pkill -f "web/server.py" 2>/dev/null
# انتظر تحرّر المنفذ
sleep 1

nohup python3 web/server.py > ~/.weaver/logs/web.log 2>&1 &
WEB_PID=$!
echo "$WEB_PID" > ~/.weaver/pids.txt
sleep 1
HOST="${WEAVER_WEB_HOST:-0.0.0.0}"
PORT="${WEAVER_WEB_PORT:-7878}"
# تأكّد أن الخادم الجديد اشتغل فعلاً (لم يفشل بسبب المنفذ)
if kill -0 "$WEB_PID" 2>/dev/null; then
  echo "🕸️ WeaverCode Dashboard يعمل — http://$HOST:$PORT (PID: $WEB_PID)"
  echo "   ⚠️  في المتصفح: حدّث الصفحة بقوة (اسحب للأسفل) لتحميل أحدث واجهة."
  echo "   السجل: ~/.weaver/logs/web.log | للإيقاف: bash scripts/weaver-stop.sh"
else
  echo "❌ فشل تشغيل الخادم — راجع ~/.weaver/logs/web.log"
  tail -5 ~/.weaver/logs/web.log
fi
