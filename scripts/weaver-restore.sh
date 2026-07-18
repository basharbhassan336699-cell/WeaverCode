#!/bin/bash
# ══════════════════════════════════════════════════════════════════════
# weaver-restore.sh — استعادة WeaverCode كاملاً بأمرٍ واحد (Termux/Linux/macOS)
# ----------------------------------------------------------------------
# يجمع كل خطوات الاستعادة في أمر واحد:
#   1) سحب أحدث كود من main (مع حماية .env وتعديلاتك المحلية)
#   2) تحديث تبعيات بايثون
#   3) فحص صحّة الكود (عدد الأدوات جاهز؟)
#   4) التحقق من الاتصال بالمفاتيح (المزوّد/النموذج/المفتاح)
#   5) إعادة تشغيل البوابة (لوحة الويب + الخلفية daemon)
#   6) تقرير نهائي بالحالة والرابط
#
# الاستخدام:
#   bash scripts/weaver-restore.sh                # استعادة كاملة من main
#   bash scripts/weaver-restore.sh <branch>       # من فرع محدّد
#   WEAVER_NO_RESTART=1 bash scripts/weaver-restore.sh   # بلا تشغيل الخادم
#   WEAVER_NO_PULL=1    bash scripts/weaver-restore.sh   # بلا سحب (اتصال فقط)
# ══════════════════════════════════════════════════════════════════════
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || { echo "❌ لم أجد مجلد المشروع"; exit 1; }

BRANCH="${1:-main}"
echo "🕸️  استعادة WeaverCode — يبدأ..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── 1) سحب أحدث كود (مع حماية تعديلاتك و.env) ─────────────────────────
if [ "${WEAVER_NO_PULL:-0}" != "1" ]; then
  STASHED=0
  if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
    echo "💾 حفظ تعديلاتك المحلية مؤقتاً (git stash)..."
    git stash push -u -m "weaver-restore-$(date +%s)" >/dev/null 2>&1 && STASHED=1
  fi
  echo "⬇️  سحب أحدث كود من origin/$BRANCH ..."
  PULL_OK=0
  for i in 1 2 3 4; do
    if git fetch origin "$BRANCH" 2>/dev/null && \
       git checkout "$BRANCH" 2>/dev/null && \
       git pull --ff-only origin "$BRANCH" 2>/dev/null; then
      PULL_OK=1; break
    fi
    echo "   ↻ تعذّر السحب — محاولة $i ..."; sleep $((2**i))
  done
  [ "$PULL_OK" -ne 1 ] && echo "⚠️  تعذّر السحب تلقائياً — حاول يدوياً: git pull origin $BRANCH"
  if [ "$STASHED" -eq 1 ]; then
    echo "♻️  استرجاع تعديلاتك المحلية..."
    git stash pop >/dev/null 2>&1 || echo "   ⚠️  تعارض — تعديلاتك في: git stash list"
  fi
else
  echo "⏭️  تخطّي السحب (WEAVER_NO_PULL=1)"
fi

# ── 2) تحديث تبعيات بايثون (Termux: --break-system-packages) ──────────
echo "📦 تحديث التبعيات..."
PIP_FLAGS="-q"
if pip install --help 2>/dev/null | grep -q break-system-packages; then
  PIP_FLAGS="$PIP_FLAGS --break-system-packages"
fi
pip install -r config/requirements.txt $PIP_FLAGS 2>/dev/null && \
  echo "   ✅ التبعيات جاهزة" || \
  echo "   ℹ️  تخطّي (النظام يعمل بمكتبة بايثون القياسية)"

# ── 3) فحص صحّة الكود ────────────────────────────────────────────────
echo "🔍 فحص النظام..."
python3 -c "
import sys; sys.path.insert(0, '.')
from core.tools.registry import ToolRegistry
r = ToolRegistry()
print(f'   ✅ {len(r._tools)} أداة جاهزة')
" 2>/dev/null || echo "   ⚠️  تحذير: راجع الكود (خطأ استيراد محتمل)"

# ── 4) التحقق من الاتصال بالمفاتيح ───────────────────────────────────
echo "🔑 فحص الاتصال بالمفاتيح..."
python3 -c "
import sys, os; sys.path.insert(0, '.')
# تحميل config/.env إن وُجد
envf = os.path.join('config', '.env')
if os.path.exists(envf):
    for line in open(envf, encoding='utf-8'):
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip())
model = os.environ.get('WEAVER_MODEL', '(غير محدد)')
base  = os.environ.get('WEAVER_BASE_URL', '(غير محدد)')
key   = os.environ.get('WEAVER_API_KEY', '')
print(f'   النموذج: {model}')
print(f'   المزوّد: {base}')
print(f'   المفتاح: {\"✓ مضبوط\" if key else \"✗ غير مضبوط — عدّل config/.env\"}')
" 2>/dev/null || echo "   ⚠️  تعذّر قراءة الإعدادات"

# ── 5) إعادة تشغيل البوابة (لوحة الويب + الخلفية) ─────────────────────
if [ "${WEAVER_NO_RESTART:-0}" != "1" ]; then
  echo "🔄 تشغيل البوابة (لوحة الويب + الخلفية)..."
  bash "$ROOT/scripts/weaver-bg.sh"
else
  echo "⏭️  تخطّي التشغيل (WEAVER_NO_RESTART=1)"
fi

# ── 6) التقرير النهائي ────────────────────────────────────────────────
HASH="$(git rev-parse --short HEAD 2>/dev/null || echo '?')"
MSG="$(git log -1 --pretty=%s 2>/dev/null || echo '')"
PORT="${WEAVER_WEB_PORT:-8080}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🕸️  WeaverCode مُستعاد بالكامل ✅"
echo "   الفرع:      $(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo $BRANCH)"
echo "   آخر commit: $HASH — $MSG"
echo "   البوابة:    http://localhost:$PORT"
echo "   محادثة:     python3 weaver.py -i"
echo "   تشخيص:      python3 scripts/weaver-doctor.py"
echo "   إيقاف:      bash scripts/weaver-stop.sh"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
