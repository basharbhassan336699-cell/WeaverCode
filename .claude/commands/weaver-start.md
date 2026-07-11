---
name: weaver-start
description: |
  🕸️ WeaverCode — إعادة التشغيل بعد إغلاق الجهاز أو إنهاء الجلسة
  يفحص البيئة ويُعيد تفعيل كل شيء ويستأنف آخر جلسة
allowed-tools: Bash, Read, MemorySearch, TaskList, GitStatus
---

# 🕸️ weaver-start — إعادة تشغيل WeaverCode

> شغّل هذا الأمر **في كل مرة** تعود فيها بعد إغلاق الجهاز أو إنهاء الجلسة.

---

## الخطوة 1 — فحص وجود المشروع

```bash
if [ -d ~/WeaverCode ]; then
    echo "✅ المشروع موجود: ~/WeaverCode"
    cd ~/WeaverCode
else
    echo "❌ المشروع غير موجود — شغّل /weaver-install أولاً"
fi
```

إذا لم يكن موجوداً، أخبر المستخدم بتشغيل `/weaver-install` وأوقف.

---

## الخطوة 2 — فحص ملف البيئة

```bash
if [ -f ~/WeaverCode/config/.env ]; then
    echo "✅ config/.env موجود"
    grep "WEAVER_MODEL" ~/WeaverCode/config/.env
    grep "WEAVER_BASE_URL" ~/WeaverCode/config/.env
else
    echo "⚠️  config/.env غير موجود — سأنشئه"
    cp ~/WeaverCode/config/.env.example ~/WeaverCode/config/.env
fi
```

---

## الخطوة 3 — إعادة تفعيل Psiphon (إذا كان في الإمارات)

ابحث في الذاكرة عن `weaver_proxy` — إذا كان محفوظاً:

```bash
# إذا كان المستخدم يستخدم Psiphon
export https_proxy=http://127.0.0.1:52694
export http_proxy=http://127.0.0.1:52694
echo "✅ Proxy مفعّل"
```

إذا لم يكن محفوظاً، تخطَّ هذه الخطوة.

---

## الخطوة 4 — فحص اتصال الإنترنت والـ API

```bash
python3 -c "
import urllib.request
try:
    urllib.request.urlopen('https://api.openrouter.ai', timeout=5)
    print('✅ الإنترنت يعمل')
except:
    print('⚠️  لا يوجد اتصال بالإنترنت')
"
```

---

## الخطوة 5 — تحقق من التبعيات السريع

```bash
python3 -c "
deps = ['httpx','dotenv','rich']
for d in deps:
    try:
        __import__(d)
        print(f'  ✅ {d}')
    except:
        print(f'  ❌ {d} — شغّل: pip install {d} --break-system-packages')
"
```

---

## الخطوة 6 — عرض آخر جلسة

```bash
# أحدث جلسة محفوظة
ls -t ~/.weaver/sessions/ 2>/dev/null | head -3 || echo "لا جلسات محفوظة"
```

اعرض التاريخ والمهمة الأخيرة من MemorySearch باستعلام "آخر مهمة".

---

## الخطوة 7 — اختيار وضع التشغيل

اسأل المستخدم:
- **1** ← استمر من آخر جلسة: `python3 weaver.py --interactive`
- **2** ← مهمة جديدة: `python3 weaver.py "مهمتك"`
- **3** ← فحص الحالة فقط: شغّل `/weaver-status`

---

## الخطوة 8 — التشغيل

بناءً على اختيار المستخدم شغّل المناسب:

```bash
cd ~/WeaverCode

# وضع تفاعلي
python3 weaver.py --interactive

# أو مهمة محددة
python3 weaver.py "$TASK"
```

---

## عند نجاح التشغيل

```
🕸️ WeaverCode يعمل!
━━━━━━━━━━━━━━━━━━━━━━━━━━
النموذج:  [من .env]
المزود:   [من .env]
الجلسة:   جديدة / مستأنفة
━━━━━━━━━━━━━━━━━━━━━━━━━━
```
