---
name: weaver-update
description: |
  🕸️ WeaverCode — تحديث المشروع من GitHub وتحديث التبعيات
allowed-tools: Bash, Read, Edit, GitStatus, GitPull, GitCommit, GitPush, MemorySave
---

# 🕸️ weaver-update — تحديث WeaverCode

> يجلب آخر التحديثات من GitHub ويحدّث التبعيات.

---

## الخطوة 1 — حفظ التغييرات المحلية أولاً

```bash
cd ~/WeaverCode && \
git status --short
```

إذا كان هناك ملفات معدّلة، اسأل المستخدم:
- **احفظها في commit**: `git add -A && git commit -m "حفظ تلقائي قبل التحديث"`
- **تجاهلها وخذ التحديثات**: `git stash`

---

## الخطوة 2 — سحب التحديثات

```bash
cd ~/WeaverCode && \
git fetch origin && \
git log HEAD..origin/main --oneline 2>/dev/null | \
    head -10 || echo "لا تحديثات جديدة"
```

إذا كان هناك تحديثات، اعرضها للمستخدم ثم:

```bash
git pull origin main
```

---

## الخطوة 3 — تحديث التبعيات

```bash
pip install -r ~/WeaverCode/config/requirements.txt \
    --break-system-packages -q --upgrade && \
echo "✅ التبعيات محدّثة"
```

---

## الخطوة 4 — فحص تعارض config/.env

```bash
# حماية .env من الكتابة فوقه
if [ -f ~/WeaverCode/config/.env ]; then
    echo "✅ config/.env محفوظ"
    diff ~/WeaverCode/config/.env \
         ~/WeaverCode/config/.env.example 2>/dev/null | \
        grep "^>" | head -5 && \
    echo "ℹ️  مفاتيح جديدة في .env.example (راجعها)"
fi
```

---

## الخطوة 5 — اختبار بعد التحديث

```bash
cd ~/WeaverCode && \
python3 -c "
import sys; sys.path.insert(0,'.')
from core.tools.registry import ToolRegistry
r = ToolRegistry()
print(f'✅ {len(r._tools)} أداة تعمل بعد التحديث')
"
```

---

## الخطوة 6 — حفظ تاريخ التحديث

احفظ في MemorySave:
- مفتاح `weaver_last_update`: تاريخ اليوم
- مفتاح `weaver_version`: آخر commit hash (`git rev-parse --short HEAD`)

---

## التقرير النهائي

```
🕸️ WeaverCode محدَّث
━━━━━━━━━━━━━━━━━━━━━━━━
✅ الكود: آخر تحديث من GitHub
✅ التبعيات: محدّثة
✅ config/.env: محفوظ
━━━━━━━━━━━━━━━━━━━━━━━━
آخر commit: [hash] — [رسالة]
```
