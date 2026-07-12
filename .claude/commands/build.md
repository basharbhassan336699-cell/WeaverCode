---
name: build
description: بناء وتطوير WeaverCode — إضافة ميزات وأدوات جديدة
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, GitCommit, GitPush, PipInstall, PythonRun, MemorySave
---

# بناء WeaverCode

## الوضع الحالي للمشروع
اقرأ أولاً:
1. `CLAUDE.md` — لفهم قواعد المشروع
2. `core/engine/provider.py` — محرك الاتصال
3. `core/engine/query_engine.py` — المحرك الرئيسي
4. `core/tools/registry.py` — الأدوات المتاحة

## مهام البناء المتاحة

### إضافة مزود جديد
إذا طُلب إضافة مزود (مثلاً: Gemini، Mistral):
1. افحص `core/engine/provider.py`
2. أضف منطق التحويل في `_build_payload` إذا لزم
3. اختبر بـ `python3 weaver.py --url URL --model MODEL "اختبار"`

### إضافة أداة جديدة
إذا طُلب إضافة أداة:
1. افتح `core/tools/registry.py`
2. أضف الأداة في دالة `_register_all`
3. نفذ الدالة `_اسم_الأداة`
4. اختبرها عبر `python3 weaver.py "استخدم الأداة الجديدة"`

### إصلاح خطأ
1. ابحث عن رسالة الخطأ بـ `Grep`
2. اقرأ الملف المشكلة
3. عدّل بـ `Edit`
4. اختبر

### رفع للـ GitHub
بعد أي تغيير:
```bash
git add -A
git commit -m "وصف موجز للتغيير"
git push origin main
```

## قواعد البناء
- لا تكسر الـ API الموجود — أضف فوقه
- كل ميزة جديدة تحتاج تعليقاً عربياً
- اختبر قبل الـ commit
- حدّث CLAUDE.md إذا تغير الهيكل
