---
name: setup
description: إعداد WeaverCode كاملاً — تثبيت التبعيات واستنساخ المستودعات
allowed-tools: Bash, Read, Write, Edit, Glob, GitClone, PipInstall
---

# إعداد WeaverCode الكامل

قم بتنفيذ الخطوات التالية بالترتيب:

## 1. فحص البيئة
```bash
python3 --version
pip --version
git --version
```
تأكد أن Python 3.10+ مثبت. إذا لم يكن كذلك، أخبر المستخدم.

## 2. تثبيت التبعيات
```bash
pip install httpx python-dotenv rich --break-system-packages
```

## 3. إنشاء مجلد الإعدادات
```bash
mkdir -p ~/.weaver
```

## 4. إعداد ملف .env
اقرأ `config/.env.example` وانسخه إلى `config/.env` إذا لم يكن موجوداً.
ثم اسأل المستخدم عن:
- مزود النموذج المفضل (OpenRouter / Anthropic / OpenAI / DeepSeek / Groq / Ollama)
- مفتاح API
- اسم النموذج

## 5. اختبار الاتصال
```bash
python3 weaver.py "قل مرحباً بكلمة واحدة"
```

## 6. التقرير النهائي
أخبر المستخدم بما تم وكيفية الاستخدام:
```bash
python3 weaver.py "مهمتك"           # مهمة واحدة
python3 weaver.py --interactive      # محادثة تفاعلية
python3 weaver.py --mode coding "..." # وضع البرمجة
```
