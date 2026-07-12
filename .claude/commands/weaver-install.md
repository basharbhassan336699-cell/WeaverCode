---
name: weaver-install
description: |
  🕸️ WeaverCode — التثبيت الأولي الكامل (للمرة الأولى فقط)
  يثبت كل التبعيات ويعد البيئة ويربط المشروع بـ GitHub
allowed-tools: Bash, Read, Write, Edit, GitClone, TaskCreate, TaskUpdate, MemorySave
---

# 🕸️ weaver-install — التثبيت الأولي لـ WeaverCode

> شغّل هذا الأمر **مرة واحدة فقط** عند أول استخدام للمشروع.

---

## الخطوة 1 — فحص البيئة

```bash
echo "=== فحص البيئة ===" && \
python3 --version && \
pip --version && \
git --version && \
echo "المجلد الحالي: $(pwd)"
```

إذا كان Python أقل من 3.10 أخبر المستخدم بالتحديث أولاً.

---

## الخطوة 2 — استنساخ المشروع من GitHub

إذا لم يكن المجلد موجوداً:
```bash
git clone https://github.com/basharbhassan336699-cell/WeaverCode ~/WeaverCode
cd ~/WeaverCode
```

إذا كان موجوداً:
```bash
cd ~/WeaverCode && git pull origin main
```

---

## الخطوة 3 — إنشاء مجلدات النظام

```bash
mkdir -p ~/.weaver/{logs,cache,sessions,backup} && \
echo "✅ مجلدات .weaver جاهزة"
```

---

## الخطوة 4 — تثبيت التبعيات

```bash
pip install httpx python-dotenv rich nbformat watchdog \
    schedule websockets aiofiles pyflakes plyer \
    beautifulsoup4 --break-system-packages -q && \
echo "✅ التبعيات مثبتة"
```

عند الفشل جرب حزمة حزمة وسجّل الناجح والفاشل.

---

## الخطوة 5 — إعداد ملف البيئة

اقرأ `config/.env.example` ثم:

```bash
if [ ! -f ~/WeaverCode/config/.env ]; then
    cp ~/WeaverCode/config/.env.example ~/WeaverCode/config/.env
    echo "✅ تم إنشاء config/.env"
else
    echo "ℹ️  config/.env موجود مسبقاً"
fi
```

ثم اسأل المستخدم:
1. **أي مزود تريد؟** (OpenRouter / Groq / DeepSeek / Anthropic / OpenAI / Ollama)
2. **ما مفتاح API؟**
3. **ما اسم النموذج؟** (اعطِه الخيار الافتراضي لكل مزود)

بناءً على اختياره، عدّل `config/.env` بالقيم الصحيحة.

---

## الخطوة 6 — إنشاء أوامر النظام

```bash
# إنشاء أمر weaver في النظام
echo '#!/bin/bash
cd ~/WeaverCode && python3 weaver.py "$@"' > ~/.local/bin/weaver
chmod +x ~/.local/bin/weaver

# إضافة للـ PATH إذا لزم
grep -q "~/.local/bin" ~/.bashrc || \
    echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc

echo "✅ أمر 'weaver' مثبت في النظام"
```

---

## الخطوة 7 — اختبار التثبيت

```bash
cd ~/WeaverCode && python3 weaver.py "قل: WeaverCode جاهز!"
```

إذا نجح اعرض رسالة النجاح.
إذا فشل اعرض الخطأ واقترح الحل.

---

## الخطوة 8 — حفظ بيانات التثبيت في الذاكرة

احفظ في MemorySave:
- مفتاح `weaver_installed`: "نعم"
- مفتاح `weaver_install_date`: تاريخ اليوم
- مفتاح `weaver_provider`: المزود الذي اختاره المستخدم
- مفتاح `weaver_model`: النموذج المختار

---

## التقرير النهائي

```
🕸️ WeaverCode مثبت بنجاح!
━━━━━━━━━━━━━━━━━━━━━━━━━━
📁 المسار:    ~/WeaverCode
🤖 النموذج:  [النموذج]
🔑 المزود:   [المزود]
━━━━━━━━━━━━━━━━━━━━━━━━━━
أوامر الاستخدام:
  weaver "مهمتك"          ← مهمة واحدة
  weaver -i               ← وضع تفاعلي
  weaver --help           ← المساعدة
━━━━━━━━━━━━━━━━━━━━━━━━━━
أوامر Claude Code:
  /weaver-start           ← تشغيل بعد إغلاق الجهاز
  /weaver-update          ← تحديث المشروع
  /weaver-status          ← فحص الحالة
```
