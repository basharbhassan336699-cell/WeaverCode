---
name: switch-model
description: تبديل نموذج الذكاء الاصطناعي الذي يشغل WeaverCode — استخدام: /switch-model groq
allowed-tools: Read, Edit, Write, Bash
---

# تبديل النموذج لـ WeaverCode

المعامل: $ARGUMENTS (اسم المزود أو النموذج)

## قائمة الإعدادات الجاهزة

اقرأ `config/.env` الحالي أولاً، ثم حدّثه وفق الاختيار:

### إذا كان $ARGUMENTS = "openrouter" أو "or"
```
WEAVER_BASE_URL=https://openrouter.ai/api/v1
WEAVER_MODEL=anthropic/claude-sonnet-4-6
```

### إذا كان $ARGUMENTS = "anthropic" أو "claude"
```
WEAVER_BASE_URL=https://api.anthropic.com/v1
WEAVER_MODEL=claude-sonnet-4-6
```

### إذا كان $ARGUMENTS = "openai" أو "gpt"
```
WEAVER_BASE_URL=https://api.openai.com/v1
WEAVER_MODEL=gpt-4o
```

### إذا كان $ARGUMENTS = "deepseek" أو "ds"
```
WEAVER_BASE_URL=https://api.deepseek.com/v1
WEAVER_MODEL=deepseek-chat
```

### إذا كان $ARGUMENTS = "groq"
```
WEAVER_BASE_URL=https://api.groq.com/openai/v1
WEAVER_MODEL=llama-3.3-70b-versatile
```

### إذا كان $ARGUMENTS = "ollama" أو "local"
```
WEAVER_BASE_URL=http://localhost:11434/v1
WEAVER_API_KEY=ollama
WEAVER_MODEL=llama3.2
```

### إذا كان $ARGUMENTS نموذجاً محدداً (مثل "gpt-4o-mini")
حدّث WEAVER_MODEL فقط.

## بعد التحديث
اختبر الاتصال:
```bash
python3 weaver.py "قل: الاتصال يعمل"
```

أخبر المستخدم بالإعدادات الجديدة والنموذج الحالي.
