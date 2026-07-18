---
description: إنشاء تطبيق agent جديد باستخدام WeaverCode SDK
argument-hint: [اسم التطبيق ووصفه]
allowed-tools: ["Write", "Bash", "Read"]
---

أنشئ تطبيق agent جديد: $ARGUMENTS

الخطوات:
1. أنشئ مجلد باسم التطبيق
2. أنشئ `weaver_agent.py` بهيكل أساسي:
   - استيراد WeaverCode SDK
   - تعريف system prompt
   - حلقة agent رئيسية
3. أنشئ `README.md` يشرح كيفية التشغيل
4. أنشئ `requirements.txt`
5. اشرح للمستخدم كيف يشغّل ويخصّص الـ agent
