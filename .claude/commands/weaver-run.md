---
name: weaver-run
description: |
  🕸️ WeaverCode — تشغيل سريع بأي وضع أو نموذج
  الاستخدام: /weaver-run [الوضع] [المهمة]
  مثال: /weaver-run coding "راجع كود provider.py"
allowed-tools: Bash, Read, MemorySearch
---

# 🕸️ weaver-run — تشغيل WeaverCode

المعامل: `$ARGUMENTS`

---

## تحليل المعامل

حلّل `$ARGUMENTS` لتحديد:
- الوضع المطلوب (إذا ذُكر)
- المهمة المطلوبة

### الأوضاع المتاحة:
| الوضع | الاستخدام |
|-------|-----------|
| `main` | الوضع العام (افتراضي) |
| `coding` | مراجعة وكتابة الكود |
| `project` | إدارة المشاريع |
| `security` | فحص أمني |
| `autonomous` | تشغيل مستقل |
| `analysis` | تحليل عميق |

---

## تشغيل بالوضع المناسب

```bash
cd ~/WeaverCode

# الوضع التفاعلي (بلا معامل)
python3 weaver.py --interactive

# مهمة واحدة بوضع محدد
python3 weaver.py --mode [MODE] "[TASK]"

# تدفق مباشر (للمهام السريعة)
python3 weaver.py --stream "[TASK]"

# بنموذج مختلف مؤقتاً
python3 weaver.py --model "[MODEL]" "[TASK]"
```

---

## أمثلة جاهزة

**إذا كان $ARGUMENTS = "coding ...":**
```bash
cd ~/WeaverCode && python3 weaver.py --mode coding "$TASK"
```

**إذا كان $ARGUMENTS = "security":**
```bash
cd ~/WeaverCode && python3 weaver.py --mode security "افحص المشروع أمنياً"
```

**إذا كان $ARGUMENTS = "groq ...":**
```bash
cd ~/WeaverCode && python3 weaver.py \
    --url "https://api.groq.com/openai/v1" \
    --model "llama-3.3-70b-versatile" "$TASK"
```

**إذا كان $ARGUMENTS فارغاً:**
شغّل الوضع التفاعلي مباشرة:
```bash
cd ~/WeaverCode && python3 weaver.py --interactive
```

---

## تذكير بالأوامر السريعة بعد التشغيل

```
داخل WeaverCode التفاعلي:
  /mode coding      ← تبديل للكود
  /model groq       ← تبديل النموذج مؤقتاً
  /icon             ← عرض الأيقونة
  /stats            ← الإحصاءات
  خروج             ← إنهاء
```
