---
name: weaver-key
description: |
  🕸️ WeaverCode — تغيير أو تحديث مفتاح API أو المزود
  الاستخدام: /weaver-key [اسم المزود]
allowed-tools: Bash, Read, Edit, Write, MemorySave
---

# 🕸️ weaver-key — تغيير مفتاح API

المعامل: `$ARGUMENTS` (اسم المزود — اختياري)

---

## الخطوة 1 — عرض الإعدادات الحالية

```bash
grep -E "WEAVER_MODEL|WEAVER_BASE_URL" \
    ~/WeaverCode/config/.env 2>/dev/null | \
    sed 's/WEAVER_API_KEY=.*/WEAVER_API_KEY=***/'
```

---

## الخطوة 2 — اختيار المزود

إذا لم يُحدَّد `$ARGUMENTS`، اسأل المستخدم:

```
🕸️ اختر المزود:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. OpenRouter  → يدعم كل النماذج (مُوصى به)
2. Groq        → مجاني وسريع (llama)
3. DeepSeek    → رخيص ومتميز
4. Anthropic   → Claude مباشرة
5. OpenAI      → GPT مباشرة
6. Ollama      → محلي مجاناً (لا إنترنت)
7. مزود مخصص  → أدخل URL يدوياً
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## الخطوة 3 — إعدادات كل مزود

بناءً على الاختيار، حضّر القيم:

### OpenRouter
```
WEAVER_BASE_URL=https://openrouter.ai/api/v1
WEAVER_MODEL=anthropic/claude-sonnet-4-6
```
رابط المفاتيح: https://openrouter.ai/keys

### Groq (مجاني)
```
WEAVER_BASE_URL=https://api.groq.com/openai/v1
WEAVER_MODEL=llama-3.3-70b-versatile
```
رابط المفاتيح: https://console.groq.com/keys

### DeepSeek
```
WEAVER_BASE_URL=https://api.deepseek.com/v1
WEAVER_MODEL=deepseek-chat
```
رابط المفاتيح: https://platform.deepseek.com

### Anthropic
```
WEAVER_BASE_URL=https://api.anthropic.com/v1
WEAVER_MODEL=claude-sonnet-4-6
```

### OpenAI
```
WEAVER_BASE_URL=https://api.openai.com/v1
WEAVER_MODEL=gpt-4o
```

### Ollama (محلي)
```
WEAVER_BASE_URL=http://localhost:11434/v1
WEAVER_API_KEY=ollama
WEAVER_MODEL=llama3.2
```
تأكد أن Ollama يعمل: `ollama serve`

---

## الخطوة 4 — طلب المفتاح

اطلب من المستخدم إدخال المفتاح ثم حدّث `config/.env`:

```bash
# تحديث .env بالقيم الجديدة
sed -i "s|^WEAVER_BASE_URL=.*|WEAVER_BASE_URL=$BASE_URL|" ~/WeaverCode/config/.env
sed -i "s|^WEAVER_API_KEY=.*|WEAVER_API_KEY=$API_KEY|" ~/WeaverCode/config/.env
sed -i "s|^WEAVER_MODEL=.*|WEAVER_MODEL=$MODEL|" ~/WeaverCode/config/.env
echo "✅ الإعدادات حُدِّثت"
```

---

## الخطوة 5 — اختبار المفتاح الجديد

```bash
cd ~/WeaverCode && python3 weaver.py "قل: المفتاح يعمل" 2>&1 | tail -3
```

---

## الخطوة 6 — حفظ في الذاكرة

احفظ في MemorySave (بدون المفتاح الفعلي):
- مفتاح `weaver_provider`: اسم المزود
- مفتاح `weaver_model`: النموذج الحالي

---

## التقرير النهائي

```
🕸️ المفتاح محدَّث
━━━━━━━━━━━━━━━━━━━━━━
المزود:  [المزود الجديد]
النموذج: [النموذج الجديد]
الاتصال: ✅ يعمل
━━━━━━━━━━━━━━━━━━━━━━
```
