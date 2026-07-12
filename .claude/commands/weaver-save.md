---
name: weaver-save
description: |
  🕸️ WeaverCode — حفظ العمل الحالي ورفعه لـ GitHub
  الاستخدام: /weaver-save "وصف التغييرات"
allowed-tools: Bash, Read, GitStatus, GitCommit, GitPush, MemorySave
---

# 🕸️ weaver-save — حفظ ورفع WeaverCode

المعامل: `$ARGUMENTS` (وصف التغييرات — اختياري)

---

## الخطوة 1 — عرض التغييرات

```bash
cd ~/WeaverCode && \
echo "=== الملفات المعدّلة ===" && \
git status --short && \
echo "" && \
echo "=== ملخص التغييرات ===" && \
git diff --stat HEAD 2>/dev/null | tail -5
```

إذا لم تكن هناك تغييرات:
```
ℹ️  لا يوجد شيء جديد للحفظ
```
وأوقف.

---

## الخطوة 2 — تأكيد الحفظ

إذا كان `$ARGUMENTS` موجوداً استخدمه كرسالة commit.
إذا لم يكن موجوداً، ولّد رسالة تلقائية من التغييرات:

```bash
# رسالة تلقائية من الملفات المعدلة
FILES=$(git diff --name-only HEAD 2>/dev/null | head -3 | tr '\n' ', ')
MSG="🕸️ تحديث: ${FILES}$(date '+%Y-%m-%d %H:%M')"
```

---

## الخطوة 3 — حماية الملفات الحساسة

```bash
# تأكد أن .env لن يُرفع
grep -q "config/.env" ~/WeaverCode/.gitignore || \
    echo "config/.env" >> ~/WeaverCode/.gitignore && \
echo "✅ .env محمي من الرفع"
```

---

## الخطوة 4 — الحفظ المحلي

```bash
cd ~/WeaverCode && \
git add -A && \
git commit -m "$COMMIT_MESSAGE" && \
echo "✅ تم الحفظ محلياً"
```

---

## الخطوة 5 — الرفع لـ GitHub

```bash
cd ~/WeaverCode && \
git push origin main && \
echo "✅ تم الرفع لـ GitHub"
```

إذا فشل الرفع بسبب diverged:
```bash
git pull --rebase origin main && git push origin main
```

---

## الخطوة 6 — تحديث الذاكرة

احفظ في MemorySave:
- مفتاح `weaver_last_save`: تاريخ ووقت الحفظ
- مفتاح `weaver_last_commit`: رسالة الـ commit

---

## التقرير النهائي

```
🕸️ تم الحفظ والرفع
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ commit: [hash] — [رسالة]
✅ GitHub: محدَّث
🔗 https://github.com/basharbhassan336699-cell/WeaverCode
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```
