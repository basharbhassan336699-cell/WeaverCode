#!/bin/bash
# ═══════════════════════════════════════════════════════════
#  weaver — أمر النظام لـ WeaverCode
#  ضعه في ~/.local/bin/weaver وامنحه chmod +x
#
#  الاستخدام:
#    weaver "مهمتك"           ← مهمة واحدة
#    weaver -i                ← وضع تفاعلي
#    weaver -m coding "..."   ← وضع محدد
#    weaver -k groq           ← تبديل المزود
#    weaver --status          ← فحص الحالة
#    weaver --update          ← تحديث
#    weaver --help            ← المساعدة
# ═══════════════════════════════════════════════════════════

WEAVER_DIR="${WEAVER_DIR:-$HOME/WeaverCode}"
PYTHON="${PYTHON:-python3}"

# ── ألوان ────────────────────────────────────────────────
ORANGE='\033[38;2;198;113;33m'
GRAY='\033[90m'
RESET='\033[0m'
BOLD='\033[1m'

# ── التحقق من وجود المشروع ───────────────────────────────
if [ ! -d "$WEAVER_DIR" ]; then
    echo -e "${ORANGE}🕸️  WeaverCode${RESET}"
    echo -e "${GRAY}المشروع غير موجود في: $WEAVER_DIR${RESET}"
    echo ""
    echo "للتثبيت:"
    echo "  git clone https://github.com/basharbhassan336699-cell/WeaverCode ~/WeaverCode"
    echo "  bash ~/WeaverCode/scripts/install_termux.sh"
    exit 1
fi

# ── تحميل متغيرات البيئة ─────────────────────────────────
ENV_FILE="$WEAVER_DIR/config/.env"
if [ -f "$ENV_FILE" ]; then
    export $(grep -v '^#' "$ENV_FILE" | grep -v '^$' | xargs 2>/dev/null)
fi

# ── معالجة الأوامر الخاصة ───────────────────────────────

case "$1" in

    --help|-h|help|"")
        echo -e "${ORANGE}"
        echo "   🕸️  WeaverCode"
        echo -e "${RESET}"
        echo -e "${GRAY}الاستخدام:${RESET}"
        echo "  weaver \"مهمتك\"         ← مهمة واحدة"
        echo "  weaver -i              ← وضع تفاعلي"
        echo "  weaver -m coding \"...\" ← وضع محدد"
        echo "  weaver -s \"...\"        ← تدفق مباشر"
        echo ""
        echo -e "${GRAY}أوامر النظام:${RESET}"
        echo "  weaver --status        ← فحص الحالة"
        echo "  weaver --update        ← تحديث المشروع"
        echo "  weaver --key [مزود]    ← تغيير المفتاح"
        echo "  weaver --logs          ← عرض السجلات"
        echo "  weaver --version       ← الإصدار"
        echo ""
        echo -e "${GRAY}الأوضاع المتاحة (-m):${RESET}"
        echo "  main | coding | project | security | autonomous | analysis"
        ;;

    --status|status)
        echo -e "${ORANGE}🕸️  فحص WeaverCode...${RESET}"
        cd "$WEAVER_DIR"
        $PYTHON -c "
import sys, os
sys.path.insert(0,'.')
checks = []

# الملفات
for f in ['weaver.py','config/.env','core/engine/provider.py']:
    exists = os.path.exists(f)
    checks.append(('✅' if exists else '❌', f))

# المكتبات
for lib in ['httpx','dotenv','rich']:
    try:
        __import__(lib)
        checks.append(('✅', f'lib:{lib}'))
    except:
        checks.append(('❌', f'lib:{lib} — مفقود'))

# الأدوات
try:
    from core.tools.registry import ToolRegistry
    r = ToolRegistry()
    checks.append(('✅', f'أدوات: {len(r._tools)} مسجلة'))
except Exception as e:
    checks.append(('❌', f'أدوات: {e}'))

# الذاكرة
try:
    from core.memory.store import MemoryStore
    m = MemoryStore()
    s = m.get_stats()
    checks.append(('✅', f'ذاكرة: {s[\"conversations\"]} محادثة'))
except Exception as e:
    checks.append(('❌', f'ذاكرة: {e}'))

print()
for icon, msg in checks:
    print(f'  {icon}  {msg}')
print()

model = os.environ.get('WEAVER_MODEL','غير محدد')
url = os.environ.get('WEAVER_BASE_URL','غير محدد')
print(f'  النموذج: {model}')
print(f'  المزود:  {url.split(\"//\")[-1].split(\"/\")[0] if \"//\" in url else url}')
"
        ;;

    --update|update)
        echo -e "${ORANGE}🕸️  تحديث WeaverCode...${RESET}"
        cd "$WEAVER_DIR"
        git pull origin main && \
        $PYTHON -m pip install -r config/requirements.txt \
            --break-system-packages -q && \
        echo -e "${ORANGE}✅ WeaverCode محدَّث${RESET}"
        ;;

    --key|key)
        PROVIDER="${2:-}"
        echo -e "${ORANGE}🕸️  تغيير مفتاح API...${RESET}"
        echo ""
        echo "المزودون المتاحون:"
        echo "  1. openrouter  → https://openrouter.ai/keys"
        echo "  2. groq        → https://console.groq.com/keys (مجاني)"
        echo "  3. deepseek    → https://platform.deepseek.com"
        echo "  4. anthropic   → https://console.anthropic.com"
        echo "  5. openai      → https://platform.openai.com"
        echo "  6. ollama      → محلي (لا مفتاح)"
        echo ""

        if [ -z "$PROVIDER" ]; then
            read -p "اختر المزود: " PROVIDER
        fi

        case "$PROVIDER" in
            1|openrouter|or)
                BASE_URL="https://openrouter.ai/api/v1"
                MODEL="anthropic/claude-sonnet-4-6"
                ;;
            2|groq)
                BASE_URL="https://api.groq.com/openai/v1"
                MODEL="llama-3.3-70b-versatile"
                ;;
            3|deepseek|ds)
                BASE_URL="https://api.deepseek.com/v1"
                MODEL="deepseek-chat"
                ;;
            4|anthropic|claude)
                BASE_URL="https://api.anthropic.com/v1"
                MODEL="claude-sonnet-4-6"
                ;;
            5|openai|gpt)
                BASE_URL="https://api.openai.com/v1"
                MODEL="gpt-4o"
                ;;
            6|ollama|local)
                BASE_URL="http://localhost:11434/v1"
                MODEL="llama3.2"
                read -p "اسم النموذج [llama3.2]: " MODEL_INPUT
                MODEL="${MODEL_INPUT:-llama3.2}"
                # كتابة مباشرة بلا مفتاح
                sed -i "s|^WEAVER_BASE_URL=.*|WEAVER_BASE_URL=$BASE_URL|" "$ENV_FILE"
                sed -i "s|^WEAVER_API_KEY=.*|WEAVER_API_KEY=ollama|" "$ENV_FILE"
                sed -i "s|^WEAVER_MODEL=.*|WEAVER_MODEL=$MODEL|" "$ENV_FILE"
                echo -e "${ORANGE}✅ Ollama محلي مضبوط${RESET}"
                exit 0
                ;;
            *)
                echo "مزود غير معروف: $PROVIDER"
                exit 1
                ;;
        esac

        read -p "أدخل مفتاح API: " API_KEY
        echo ""

        # تحديث .env
        sed -i "s|^WEAVER_BASE_URL=.*|WEAVER_BASE_URL=$BASE_URL|" "$ENV_FILE"
        sed -i "s|^WEAVER_API_KEY=.*|WEAVER_API_KEY=$API_KEY|" "$ENV_FILE"
        sed -i "s|^WEAVER_MODEL=.*|WEAVER_MODEL=$MODEL|" "$ENV_FILE"

        echo -e "${ORANGE}✅ تم التحديث:${RESET}"
        echo "  المزود:  $BASE_URL"
        echo "  النموذج: $MODEL"
        echo ""
        echo "اختبار..."
        cd "$WEAVER_DIR" && $PYTHON weaver.py "قل: يعمل" 2>&1 | tail -3
        ;;

    --logs|logs)
        LOG_DIR="$HOME/.weaver/logs"
        if [ -d "$LOG_DIR" ]; then
            ls -t "$LOG_DIR"/*.log 2>/dev/null | head -5 | \
                xargs -I{} sh -c 'echo "=== {} ===" && tail -20 {}'
        else
            echo "لا سجلات متاحة"
        fi
        ;;

    --version|version|-v)
        cd "$WEAVER_DIR"
        COMMIT=$(git rev-parse --short HEAD 2>/dev/null || echo "غير معروف")
        echo -e "${ORANGE}🕸️  WeaverCode${RESET}"
        echo "  commit: $COMMIT"
        echo "  النموذج: ${WEAVER_MODEL:-غير محدد}"
        ;;

    -i|--interactive|interactive)
        cd "$WEAVER_DIR"
        exec $PYTHON weaver.py --interactive
        ;;

    -m|--mode)
        MODE="$2"
        shift 2
        cd "$WEAVER_DIR"
        exec $PYTHON weaver.py --mode "$MODE" "$@"
        ;;

    -s|--stream)
        shift
        cd "$WEAVER_DIR"
        exec $PYTHON weaver.py --stream "$@"
        ;;

    --model)
        MODEL_ARG="$2"
        shift 2
        cd "$WEAVER_DIR"
        exec $PYTHON weaver.py --model "$MODEL_ARG" "$@"
        ;;

    *)
        # تشغيل مهمة عادية
        cd "$WEAVER_DIR"
        exec $PYTHON weaver.py "$@"
        ;;

esac
