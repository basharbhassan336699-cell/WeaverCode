---
description: تشغيل مراجعة أمنية على الكود الحالي باستخدام security-guidance plugin
allowed-tools: ["Bash", "Read", "Glob"]
---

شغّل مراجعة أمنية شاملة على الكود المُعدَّل في المشروع الحالي.

الخطوات:
1. شغّل `git diff HEAD` لرؤية التغييرات الأخيرة
2. فحص الأنماط الأمنية في الملفات المُعدَّلة (SQL injection، hardcoded secrets، command injection، path traversal، XSS، SSRF)
3. قدّم تقريراً بالمشكلات مرتّباً حسب الخطورة: Critical → High → Medium → Low
4. اقترح إصلاحات محددة لكل مشكلة

إذا لم تكن هناك تغييرات، افحص الملفات المشار إليها في $ARGUMENTS أو افحص المشروع بالكامل.
