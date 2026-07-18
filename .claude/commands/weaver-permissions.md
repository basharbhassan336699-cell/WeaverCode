---
description: عرض وإدارة قواعد الأذونات في WeaverCode
argument-hint: [list | allow <rule> | deny <rule>]
allowed-tools: ["Read", "Write", "Bash"]
---

إدارة قواعد أذونات WeaverCode من core/permissions.py وconfig/settings.json

الأوامر:
- بدون وسائط أو `list`: عرض كل القواعد الحالية (allow/deny/default)
- `allow Edit(src/**)`: إضافة قاعدة سماح
- `deny Bash(rm:*)`: إضافة قاعدة رفض
- `strict`: تطبيق إعدادات config/settings-strict.json
- `lax`: تطبيق إعدادات config/settings-lax.json

الأمر: $ARGUMENTS
