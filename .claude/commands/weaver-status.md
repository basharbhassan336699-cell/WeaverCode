---
name: weaver-status
description: |
  🕸️ WeaverCode — فحص شامل لحالة النظام والمشروع والاتصال
allowed-tools: Bash, Read, MemorySearch, TaskList, GitStatus, DirectoryList
---

# 🕸️ weaver-status — فحص حالة WeaverCode

> يعطيك صورة كاملة عن كل شيء دفعة واحدة.

---

## 1. فحص الملفات الأساسية

```bash
echo "=== ملفات المشروع ===" && \
ls -la ~/WeaverCode/weaver.py \
       ~/WeaverCode/config/.env \
       ~/WeaverCode/core/engine/provider.py \
       ~/WeaverCode/core/tools/registry.py \
       2>/dev/null | awk '{print $1, $5, $9}'
```

---

## 2. فحص الإعدادات الحالية

```bash
echo "=== الإعدادات ===" && \
grep -E "WEAVER_MODEL|WEAVER_BASE_URL|WEAVER_MAX_TOKENS" \
    ~/WeaverCode/config/.env 2>/dev/null || echo "⚠️  .env غير موجود"
```

---

## 3. فحص Python والتبعيات

```bash
python3 -c "
import sys
print(f'Python: {sys.version.split()[0]}')

libs = [
    ('httpx',     'httpx'),
    ('dotenv',    'python-dotenv'),
    ('rich',      'rich'),
    ('nbformat',  'nbformat'),
    ('watchdog',  'watchdog'),
    ('pyflakes',  'pyflakes'),
    ('plyer',     'plyer'),
    ('bs4',       'beautifulsoup4'),
]
missing = []
for imp, pkg in libs:
    try:
        __import__(imp)
        print(f'  ✅ {pkg}')
    except ImportError:
        print(f'  ❌ {pkg}')
        missing.append(pkg)

if missing:
    print(f'\nلتثبيت الناقص:')
    print(f'pip install {\" \".join(missing)} --break-system-packages')
else:
    print('\n✅ كل التبعيات مثبتة')
"
```

---

## 4. فحص الأدوات المسجّلة

```bash
cd ~/WeaverCode && python3 -c "
import sys; sys.path.insert(0,'.')
try:
    from core.tools.registry import ToolRegistry
    r = ToolRegistry()
    tools = sorted(r._tools.keys())
    print(f'إجمالي الأدوات: {len(tools)}')
    cats = {
        'الملفات':    [t for t in tools if t in ['Read','Write','Edit','Glob','Grep']],
        'التنفيذ':    [t for t in tools if t in ['Bash','Monitor','PythonRun']],
        'الذاكرة':   [t for t in tools if 'Memory' in t],
        'المهام':    [t for t in tools if 'Task' in t or 'Cron' in t],
        'الويب':     [t for t in tools if 'Web' in t],
        'Git':       [t for t in tools if 'Git' in t or 'Worktree' in t],
        'الوكلاء':   [t for t in tools if t in ['Agent','Workflow','SendMessage']],
        'أخرى':      [t for t in tools if not any(t in g for g in [
            ['Read','Write','Edit','Glob','Grep'],
            ['Bash','Monitor','PythonRun'],
        ] + [[x for x in tools if 'Memory' in x or 'Task' in x or 'Cron' in x or 'Web' in x or 'Git' in x or 'Worktree' in x or x in ['Agent','Workflow','SendMessage']]])],
    }
    for cat, ts in cats.items():
        if ts: print(f'  {cat}: {len(ts)} ({", ".join(ts)})')
except Exception as e:
    print(f'❌ خطأ: {e}')
"
```

---

## 5. فحص الذاكرة

```bash
cd ~/WeaverCode && python3 -c "
import sys; sys.path.insert(0,'.')
try:
    from core.memory.store import MemoryStore
    m = MemoryStore()
    s = m.get_stats()
    print(f'المحادثات المحفوظة: {s[\"conversations\"]}')
    print(f'الحقائق المحفوظة:   {s[\"facts\"]}')
    import os
    db = os.path.expanduser('~/.weaver/memory.db')
    size = os.path.getsize(db) if os.path.exists(db) else 0
    print(f'حجم قاعدة البيانات: {size:,} بايت')
except Exception as e:
    print(f'❌ خطأ في الذاكرة: {e}')
"
```

---

## 6. فحص Git

```bash
cd ~/WeaverCode && \
echo "=== Git ===" && \
git log --oneline -3 2>/dev/null || echo "لا يوجد git" && \
echo "الفرع: $(git branch --show-current 2>/dev/null)" && \
git status --short 2>/dev/null | head -5
```

---

## 7. فحص الاتصال بالـ API

```bash
cd ~/WeaverCode && python3 -c "
import sys, os; sys.path.insert(0,'.')
# تحميل .env
try:
    from dotenv import load_dotenv
    load_dotenv('config/.env')
except: pass

url = os.environ.get('WEAVER_BASE_URL','غير محدد')
model = os.environ.get('WEAVER_MODEL','غير محدد')
key = os.environ.get('WEAVER_API_KEY','')
key_preview = key[:8]+'...' if len(key)>8 else '❌ غير محدد'

print(f'المزود:  {url}')
print(f'النموذج: {model}')
print(f'المفتاح: {key_preview}')

# اختبار بسيط
import urllib.request
try:
    domain = url.split('//')[1].split('/')[0]
    req = urllib.request.Request(f'https://{domain}', method='HEAD')
    urllib.request.urlopen(req, timeout=5)
    print(f'الاتصال: ✅ {domain} يستجيب')
except Exception as e:
    print(f'الاتصال: ⚠️  {e}')
"
```

---

## 8. فحص الأيقونات

```bash
echo "=== الأيقونات ===" && \
ls ~/WeaverCode/assets/*.png 2>/dev/null | wc -l | \
    xargs -I{} echo "أيقونات: {} ملف" && \
ls ~/WeaverCode/assets/icon_store_dark.png 2>/dev/null && \
echo "✅ الأيقونة الرئيسية موجودة"
```

---

## التقرير النهائي

قدّم ملخصاً بهذا الشكل:

```
🕸️ تقرير حالة WeaverCode
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅/❌  الملفات الأساسية
✅/❌  التبعيات (X من Y مثبتة)
✅/❌  الأدوات (X أداة مسجلة)
✅/❌  الذاكرة (X محادثة)
✅/❌  الاتصال بـ API
✅/❌  الأيقونات (X ملف)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
النموذج الحالي: [النموذج]
آخر commit:     [الرسالة]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

إذا كان هناك مشاكل، اقترح الأمر المناسب لإصلاحها.
