---
description: commit وpush وإنشاء PR بخطوة واحدة
allowed-tools: ["Bash"]
argument-hint: [رسالة commit اختيارية]
---

commit ثم push ثم إنشاء Pull Request:

1. `git add -A` ثم `git status` لعرض ما سيُضاف
2. اكتب رسالة commit مناسبة (أو استخدم $ARGUMENTS)
3. `git commit -m "الرسالة"`
4. `git push origin HEAD`
5. `gh pr create --fill` لإنشاء PR (إذا كان gh مثبتاً)
6. أعرض رابط الـ PR
