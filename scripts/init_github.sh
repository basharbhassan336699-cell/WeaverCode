#!/bin/bash
# ═══════════════════════════════════════════════
#  init_github.sh — رفع WeaverCode لـ GitHub
#  الاستخدام: bash scripts/init_github.sh
# ═══════════════════════════════════════════════

set -e

REPO_NAME="WeaverCode"
GITHUB_USER="${GITHUB_USER:-basharbhassan336699-cell}"

echo "🕸️  رفع WeaverCode إلى GitHub..."
echo "المستخدم: $GITHUB_USER"
echo "المستودع: $REPO_NAME"
echo ""

# التحقق من وجود git
if ! command -v git &> /dev/null; then
    echo "❌ git غير مثبت"
    exit 1
fi

# التحقق من توكن GitHub
if [ -z "$GITHUB_TOKEN" ]; then
    echo "❌ GITHUB_TOKEN غير محدد"
    echo "أضفه: export GITHUB_TOKEN=ghp_YOUR_TOKEN"
    exit 1
fi

# تهيئة git إذا لم يكن مهيأً
if [ ! -d ".git" ]; then
    git init
    git branch -M main
fi

# إنشاء المستودع على GitHub
echo "📡 إنشاء المستودع على GitHub..."
curl -s -X POST \
    -H "Authorization: Bearer $GITHUB_TOKEN" \
    -H "Accept: application/vnd.github+json" \
    https://api.github.com/user/repos \
    -d "{
        \"name\": \"$REPO_NAME\",
        \"description\": \"وكيل برمجي مستقل مدعوم بالذكاء الاصطناعي\",
        \"private\": false,
        \"auto_init\": false
    }" | python3 -c "
import sys, json
data = json.load(sys.stdin)
if 'html_url' in data:
    print('✅ المستودع:', data['html_url'])
elif 'errors' in data:
    print('ℹ️ المستودع موجود مسبقاً')
else:
    print('⚠️ ', json.dumps(data, ensure_ascii=False)[:200])
"

REMOTE_URL="https://$GITHUB_TOKEN@github.com/$GITHUB_USER/$REPO_NAME.git"

# إضافة remote إذا لم يكن موجوداً
if ! git remote get-url origin &> /dev/null; then
    git remote add origin "$REMOTE_URL"
    echo "✅ Remote أضيف"
else
    git remote set-url origin "$REMOTE_URL"
    echo "✅ Remote حُدِّث"
fi

# إضافة الملفات ورفعها
git add -A
git status --short

if git diff --cached --quiet; then
    echo "ℹ️ لا يوجد تغييرات للرفع"
else
    git commit -m "🕸️ WeaverCode v1.0 — البنية الأولية"
    git push -u origin main --force
    echo ""
    echo "✅ تم الرفع بنجاح!"
    echo "🔗 https://github.com/$GITHUB_USER/$REPO_NAME"
fi
