---
description: حذف الـ branches المحلية التي حُذف ما يقابلها في remote
allowed-tools: ["Bash"]
---

نظّف الـ branches المحلية التي لم يعد لها مقابل في remote:

1. `git fetch --prune` لتحديث معلومات الـ remote
2. `git branch -vv` لعرض كل الـ branches وحالتها
3. حدد الـ branches التي تظهر `[origin/...: gone]`
4. احذفها بـ `git branch -d branch-name`
5. أبلغ المستخدم بعدد الـ branches المحذوفة
