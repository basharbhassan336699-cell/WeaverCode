#!/bin/bash
# ═══════════════════════════════════════════════
#  install_termux.sh — تثبيت WeaverCode على Termux
#  الاستخدام: bash scripts/install_termux.sh
# ═══════════════════════════════════════════════

ORANGE='\033[38;2;198;113;33m'
RESET='\033[0m'

echo -e "${ORANGE}"
echo "   🕸️  WeaverCode — التثبيت على Termux"
echo -e "${RESET}"

# تحديث الحزم
pkg update -y -q

# تثبيت Python وGit
pkg install -y python git

# تثبيت تبعيات Python
pip install httpx python-dotenv rich nbformat watchdog \
    pyflakes plyer --break-system-packages -q

# إنشاء مجلدات النظام
mkdir -p ~/.weaver/{logs,cache,sessions,backup}

# نسخ ملف .env إذا لم يكن موجوداً
if [ ! -f "config/.env" ]; then
    cp config/.env.example config/.env
    echo ""
    echo "⚠️  أضف مفتاح API:"
    echo "   nano config/.env"
fi

# جعل weaver.py قابلاً للتنفيذ
chmod +x weaver.py
chmod +x scripts/weaver.sh

# تثبيت أمر weaver في النظام
mkdir -p ~/.local/bin
cp scripts/weaver.sh ~/.local/bin/weaver
chmod +x ~/.local/bin/weaver

# إضافة PATH
if ! grep -q '\.local/bin' ~/.bashrc; then
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
fi

# alias سريع
if ! grep -q 'alias weaver' ~/.bashrc; then
    echo "alias w='weaver'" >> ~/.bashrc
fi

echo ""
echo -e "${ORANGE}✅ WeaverCode مثبت!${RESET}"
echo ""
echo "الخطوات التالية:"
echo "  1. أضف مفتاح API: nano config/.env"
echo "  2. أعد تشغيل الـ terminal أو: source ~/.bashrc"
echo "  3. شغّل: weaver -i"
echo ""
echo "الأوامر المتاحة:"
echo "  weaver \"مهمتك\"    ← مهمة واحدة"
echo "  weaver -i         ← وضع تفاعلي"
echo "  weaver --status   ← فحص الحالة"
echo "  weaver --help     ← المساعدة"
