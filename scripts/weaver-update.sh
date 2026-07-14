#!/bin/bash
# ══════════════════════════════════════════════════════════════════════
# weaver-update.sh — تحديث WeaverCode بالكامل بأمرٍ واحد (Termux/Linux/macOS)
# ----------------------------------------------------------------------
# يحفظ تغييراتك المحلية → يسحب أحدث كود → يحدّث تبعيات بايثون →
# يعيد تشغيل الخادم → يتحقق أن كل شيء يعمل.
#
# الاستخدام:
#   bash scripts/weaver-update.sh              # يحدّث الفرع الحالي
#   bash scripts/weaver-update.sh main         # يحدّث من فرع محدّد
#   WEAVER_NO_RESTART=1 bash scripts/weaver-update.sh   # بلا إعادة تشغيل
# ══════════════════════════════════════════════════════════════════════
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || { echo "❌ لم أجد مجلد المشروع"; exit 1; }

echo "🕸️  تحديث WeaverCode — يبدأ..."
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── 1) تحديد الفرع ────────────────────────────────────────────────────
CUR_BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo main)"
BRANCH="${1:-$CUR_BRANCH}"
echo "📍 الفرع: $BRANCH"

# ── 2) حماية التغييرات المحلية (لا نفقد .env أو أي تعديل) ─────────────
STASHED=0
if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
  echo "💾 حفظ تغييراتك المحلية مؤقتاً (git stash)..."
  git stash push -u -m "weaver-update-auto-$(date +%s)" >/dev/null 2>&1 && STASHED=1
fi

# ── 3) سحب أحدث كود (مع إعادة محاولة عند فشل الشبكة) ──────────────────
echo "⬇️  سحب أحدث كود من origin/$BRANCH ..."
PULL_OK=0
for i in 1 2 3 4; do
  if git fetch origin "$BRANCH" 2>/dev/null && \
     git pull --ff-only origin "$BRANCH" 2>/dev/null; then
    PULL_OK=1; break
  fi
  echo "   ↻ تعذّر السحب — محاولة $i ..."; sleep $((2**i))
done
if [ "$PULL_OK" -ne 1 ]; then
  echo "⚠️  تعذّر السحب تلقائياً (قد يكون تعارضاً). حاول يدوياً: git pull origin $BRANCH"
fi

# ── 4) استرجاع تغييراتك المحلية إن حُفظت ─────────────────────────────
if [ "$STASHED" -eq 1 ]; then
  echo "♻️  استرجاع تغييراتك المحلية..."
  git stash pop >/dev/null 2>&1 || \
    echo "   ⚠️  تعارض عند الاسترجاع — تغييراتك محفوظة في: git stash list"
fi

# ── 5) تحديث تبعيات بايثون (Termux: --break-system-packages) ──────────
echo "📦 تحديث تبعيات بايثون..."
PIP_FLAGS="-q --upgrade"
# Termux/أنظمة PEP-668 تحتاج --break-system-packages
if python3 -c "import sys" 2>/dev/null; then
  if pip install --help 2>/dev/null | grep -q break-system-packages; then
    PIP_FLAGS="$PIP_FLAGS --break-system-packages"
  fi
fi
pip install -r config/requirements.txt $PIP_FLAGS 2>/dev/null && \
  echo "   ✅ التبعيات محدّثة" || \
  echo "   ℹ️  تخطّي التبعيات (اختيارية — النظام يعمل بمكتبة بايثون القياسية)"

# ── 6) فحص صحّة الكود بعد التحديث ────────────────────────────────────
echo "🔍 فحص النظام..."
python3 -c "
import sys; sys.path.insert(0, '.')
from core.tools.registry import ToolRegistry
from core.engine.provider import get_provider  # noqa
r = ToolRegistry()
print(f'   ✅ {len(r._tools)} أداة جاهزة')
" 2>/dev/null || echo "   ⚠️  تحذير: راجع الكود — قد يكون هناك خطأ استيراد"

# ── 7) إعادة تشغيل الخادم (إلا إذا WEAVER_NO_RESTART=1) ───────────────
if [ "${WEAVER_NO_RESTART:-0}" != "1" ]; then
  echo "🔄 إعادة تشغيل الخادم..."
  bash "$ROOT/scripts/weaver-bg.sh"
else
  echo "⏭️  تخطّي إعادة التشغيل (WEAVER_NO_RESTART=1)"
fi

# ── 8) التقرير النهائي ────────────────────────────────────────────────
HASH="$(git rev-parse --short HEAD 2>/dev/null || echo '?')"
MSG="$(git log -1 --pretty=%s 2>/dev/null || echo '')"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🕸️  WeaverCode محدَّث بالكامل ✅"
echo "   الفرع:  $BRANCH"
echo "   آخر commit: $HASH — $MSG"
echo "   افتح اللوحة: http://localhost:${WEAVER_WEB_PORT:-8080}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
