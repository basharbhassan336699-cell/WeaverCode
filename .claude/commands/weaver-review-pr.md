---
description: مراجعة شاملة لـ Pull Request أو مجموعة تغييرات
allowed-tools: ["Bash", "Read", "Glob", "Grep"]
argument-hint: [رقم PR أو اسم branch]
---

راجع التغييرات في $ARGUMENTS (رقم PR أو branch أو "HEAD~3..HEAD").

استخدم هؤلاء المحللين المتخصصين بالترتيب:

**code-reviewer**: راجع جودة الكود، المنطق، الأداء، والأنماط.
**code-simplifier**: هل يمكن تبسيط أي جزء دون فقدان الوظيفة؟
**comment-analyzer**: هل التعليقات والـ comments مفيدة وصحيحة؟
**pr-test-analyzer**: هل الاختبارات كافية وتغطي الحالات الحدية؟
**silent-failure-hunter**: ابحث عن أخطاء تُبتلع صامتة بدون logging.
**type-design-analyzer**: هل تصميم الأنواع (types) صحيح ومتسق؟

قدّم تقريراً موحداً يشمل: ✅ نقاط قوية، ❌ مشكلات، 💡 اقتراحات.
