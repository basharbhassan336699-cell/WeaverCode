---
name: weaver-memory
description: |
  🕸️ WeaverCode — إدارة الذاكرة الدائمة (عرض، بحث، حذف، تصدير)
  الاستخدام: /weaver-memory [show|search|clear|export]
allowed-tools: Bash, Read, Write, MemorySearch, MemoryList, MemoryDelete, MemorySave
---

# 🕸️ weaver-memory — إدارة ذاكرة WeaverCode

المعامل: `$ARGUMENTS`

---

## تحليل المعامل

### إذا كان `$ARGUMENTS` = "show" أو فارغاً
اعرض ملخص الذاكرة:

```bash
cd ~/WeaverCode && python3 -c "
import sys; sys.path.insert(0,'.')
from core.memory.store import MemoryStore
m = MemoryStore()
s = m.get_stats()
print('🕸️ ذاكرة WeaverCode')
print('━' * 30)
print(f'محادثات: {s[\"conversations\"]}')
print(f'حقائق:   {s[\"facts\"]}')
import os
db = os.path.expanduser('~/.weaver/memory.db')
if os.path.exists(db):
    size = os.path.getsize(db)
    print(f'الحجم:   {size:,} بايت')
"
```

ثم استخدم MemoryList لعرض الحقائق المحفوظة.

---

### إذا كان `$ARGUMENTS` يبدأ بـ "search"
```
استخرج الاستعلام من $ARGUMENTS
استخدم MemorySearch بالاستعلام
اعرض النتائج
```

---

### إذا كان `$ARGUMENTS` = "clear"
اسأل المستخدم تأكيداً، ثم:

```bash
cd ~/WeaverCode && python3 -c "
import sys; sys.path.insert(0,'.')
from core.memory.store import MemoryStore
m = MemoryStore()
m.clear_old(days=0)  # حذف القديم
print('✅ تم تنظيف المحادثات القديمة')
"
```

---

### إذا كان `$ARGUMENTS` = "export"
```bash
cd ~/WeaverCode && python3 -c "
import sys, json, os; sys.path.insert(0,'.')
import sqlite3
from pathlib import Path

db = Path.home() / '.weaver' / 'memory.db'
if not db.exists():
    print('❌ لا قاعدة بيانات')
    exit()

conn = sqlite3.connect(db)
export = {
    'conversations': conn.execute('SELECT * FROM conversations ORDER BY created_at DESC LIMIT 50').fetchall(),
    'facts': conn.execute('SELECT * FROM facts').fetchall(),
}
conn.close()

out = Path.home() / '.weaver' / 'memory_export.json'
out.write_text(json.dumps({
    'conversations': [list(r) for r in export['conversations']],
    'facts': [list(r) for r in export['facts']],
}, ensure_ascii=False, indent=2))
print(f'✅ تم التصدير: {out}')
print(f'محادثات: {len(export[\"conversations\"])}')
print(f'حقائق: {len(export[\"facts\"])}')
"
```

---

### إذا كان `$ARGUMENTS` = "backup"
```bash
cp ~/.weaver/memory.db \
   ~/.weaver/backup/memory_$(date +%Y%m%d_%H%M).db && \
echo "✅ نسخة احتياطية محفوظة"
```

---

### إذا كان `$ARGUMENTS` = "stats"
عرض إحصاءات تفصيلية:
```bash
cd ~/WeaverCode && python3 -c "
import sys, sqlite3; sys.path.insert(0,'.')
from pathlib import Path

db = Path.home() / '.weaver' / 'memory.db'
conn = sqlite3.connect(db)

# أكثر الأدوات استخداماً
tools_raw = conn.execute('SELECT tools_used FROM conversations').fetchall()
from collections import Counter
import json
counter = Counter()
for (t,) in tools_raw:
    try:
        for tool in json.loads(t or '[]'):
            counter[tool] += 1
    except: pass

print('🔧 أكثر الأدوات استخداماً:')
for tool, count in counter.most_common(10):
    print(f'  {tool}: {count} مرة')

# أيام النشاط
days = conn.execute('''
    SELECT date(created_at, \"unixepoch\") as day, COUNT(*) as cnt
    FROM conversations
    GROUP BY day ORDER BY day DESC LIMIT 7
''').fetchall()
print(\"\n📅 النشاط الأسبوعي:\")
for day, cnt in days:
    print(f'  {day}: {cnt} محادثة')
conn.close()
"
```

---

## التقرير

قدّم ملخصاً واضحاً بناءً على العملية المنفّذة.
