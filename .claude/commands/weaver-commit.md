---
description: إنشاء commit ذكي مع رسالة وصفية مناسبة
allowed-tools: ["Bash"]
argument-hint: [رسالة commit اختيارية]
---

أنشئ commit للتغييرات الحالية:

1. شغّل `git status` و `git diff --staged` لفهم التغييرات
2. إذا لم تكن هناك تغييرات staged، شغّل `git add -A` أولاً
3. إذا أُعطيت رسالة في $ARGUMENTS استخدمها، وإلا اكتب رسالة وصفية بصيغة conventional commits:
   - `feat: وصف feature جديدة`
   - `fix: وصف إصلاح خطأ`
   - `refactor: وصف تحسين بنيوي`
   - `docs: تحديث توثيق`
4. شغّل `git commit -m "الرسالة"`
5. اسأل المستخدم هل يريد `git push` مباشرة
