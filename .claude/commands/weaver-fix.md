---
name: weaver-fix
description: |
  🕸️ WeaverCode — إصلاح تلقائي للمشاكل الشائعة
  يشخّص المشكلة ويصلحها تلقائياً
allowed-tools: Bash, Read, Write, Edit, GitStatus, PipInstall, MemorySearch
---

# 🕸️ weaver-fix — إصلاح WeaverCode

المعامل: `$ARGUMENTS` (وصف المشكلة — اختياري)

---

## الخطوة 1 — تشخيص المشكلة

شغّل فحصاً شاملاً أولاً:

```bash
cd ~/WeaverCode && python3 -c "
import sys; sys.path.insert(0,'.')
errors = []

# فحص الملفات
import os
files = ['weaver.py','core/engine/provider.py','core/tools/registry.py','config/.env']
for f in files:
    if not os.path.exists(os.path.expanduser(f'~/WeaverCode/{f}')):
        errors.append(f'ملف مفقود: {f}')

# فحص المكتبات
libs = ['httpx','dotenv','rich']
for lib in libs:
    try: __import__(lib)
    except ImportError: errors.append(f'مكتبة مفقودة: {lib}')

# فحص .env
try:
    content = open(os.path.expanduser('~/WeaverCode/config/.env')).read()
    if 'YOUR_KEY_HERE' in content:
        errors.append('مفتاح API لم يُعيَّن في config/.env')
    if not content.strip():
        errors.append('config/.env فارغ')
except: errors.append('config/.env غير موجود')

if errors:
    print('🔴 مشاكل مكتشفة:')
    for e in errors: print(f'  ❌ {e}')
else:
    print('✅ لا مشاكل واضحة')
" 2>&1
```

---

## الخطوة 2 — الإصلاح التلقائي بناءً على المشكلة

### إذا كانت المشكلة: مكتبة مفقودة
```bash
pip install httpx python-dotenv rich nbformat \
    --break-system-packages -q
echo "✅ المكتبات مُثبَّتة"
```

### إذا كانت المشكلة: config/.env غير موجود
```bash
cp ~/WeaverCode/config/.env.example ~/WeaverCode/config/.env
echo "✅ .env مُنشأ — افتحه وأضف مفتاحك"
```

### إذا كانت المشكلة: خطأ import أو module
```bash
cd ~/WeaverCode && python3 -c "
import sys; sys.path.insert(0,'.')
# إعادة تحميل كل الوحدات
try:
    from core.engine.provider import get_provider
    from core.tools.registry import ToolRegistry
    from core.memory.store import MemoryStore
    print('✅ كل الوحدات تُحمَّل بنجاح')
except Exception as e:
    print(f'❌ خطأ: {e}')
    import traceback
    traceback.print_exc()
"
```

### إذا كانت المشكلة: خطأ في الاتصال بالـ API
```bash
cd ~/WeaverCode && python3 -c "
import os
from dotenv import load_dotenv
load_dotenv('config/.env')

url = os.environ.get('WEAVER_BASE_URL','')
key = os.environ.get('WEAVER_API_KEY','')

print(f'URL: {url}')
print(f'Key: {key[:8]}...' if key else 'Key: غير محدد')

# اختبار الاتصال
import urllib.request
try:
    domain = url.split('//')[1].split('/')[0]
    urllib.request.urlopen(f'https://{domain}', timeout=10)
    print(f'✅ {domain} يستجيب')
except Exception as e:
    print(f'❌ لا يستجيب: {e}')
    print('جرب: تفعيل Psiphon أو تغيير المزود')
"
```

### إذا كانت المشكلة: git push يرفض
```bash
cd ~/WeaverCode && \
git pull --rebase origin main && \
git push origin main && \
echo "✅ تم الرفع بعد المزامنة"
```

### إذا كانت المشكلة: الذاكرة تالفة
```bash
# نسخة احتياطية ثم إعادة إنشاء
mkdir -p ~/.weaver/backup
cp ~/.weaver/memory.db ~/.weaver/backup/memory_backup_$(date +%Y%m%d).db 2>/dev/null
rm -f ~/.weaver/memory.db
cd ~/WeaverCode && python3 -c "
import sys; sys.path.insert(0,'.')
from core.memory.store import MemoryStore
m = MemoryStore()
print('✅ قاعدة بيانات جديدة أُنشئت')
"
```

### إذا كانت المشكلة: أوامر weaver غير موجودة في PATH
```bash
mkdir -p ~/.local/bin
echo '#!/bin/bash
cd ~/WeaverCode && python3 weaver.py "$@"' > ~/.local/bin/weaver
chmod +x ~/.local/bin/weaver
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
echo "✅ أمر weaver متاح الآن"
```

---

## الخطوة 3 — تحقق من الإصلاح

```bash
cd ~/WeaverCode && python3 weaver.py "قل: تم الإصلاح" 2>&1 | head -5
```

---

## التقرير

```
🕸️ تقرير الإصلاح
━━━━━━━━━━━━━━━━━━━━━━━
المشاكل المكتشفة:  X
تم إصلاحها:        X
تحتاج تدخل يدوي:   X
━━━━━━━━━━━━━━━━━━━━━━━
[قائمة ما تم إصلاحه]
[قائمة ما يحتاج تدخلاً]
```
