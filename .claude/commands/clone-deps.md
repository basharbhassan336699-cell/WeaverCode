---
name: clone-deps
description: استنساخ جميع المكتبات والمستودعات المطلوبة لـ WeaverCode من GitHub
allowed-tools: Bash, Write, Read, GitClone, DirectoryList
---

# استنساخ تبعيات WeaverCode من GitHub

هذا الأمر يستنسخ المستودعات المرجعية لدراستها وتطوير WeaverCode.

## المستودعات للاستنساخ

أنشئ مجلد `deps/` ثم استنسخ التالي:

### 1. Claude Code الرسمي (مرجع رئيسي)
```bash
git clone --depth 1 https://github.com/anthropics/claude-code deps/claude-code
```

### 2. MCP SDK (بروتوكول الأدوات)
```bash
git clone --depth 1 https://github.com/modelcontextprotocol/typescript-sdk deps/mcp-sdk-ts
git clone --depth 1 https://github.com/modelcontextprotocol/python-sdk deps/mcp-sdk-py
```

### 3. Anthropic SDKs (للمقارنة)
```bash
git clone --depth 1 https://github.com/anthropics/anthropic-sdk-python deps/anthropic-py
git clone --depth 1 https://github.com/anthropics/anthropic-sdk-typescript deps/anthropic-ts
```

### 4. نماذج وكلاء مفتوحة المصدر (للاستلهام)
```bash
git clone --depth 1 https://github.com/anthropics/claude-cookbooks deps/cookbooks
```

## بعد الاستنساخ

1. اقرأ `deps/claude-code/README.md` وأخبرني بأبرز ما فيه
2. افحص هيكل `deps/claude-code/` واقارنه بهيكل WeaverCode
3. ابحث عن أي أدوات أو مفاهيم يمكن استعارتها لـ WeaverCode

## ملاحظة
هذه المستودعات للدراسة فقط. WeaverCode يعيد بناء المفاهيم بكود مستقل.
