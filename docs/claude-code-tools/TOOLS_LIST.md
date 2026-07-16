# WeaverCode Built-in Tools

## الأدوات المدمجة في WeaverCode

استُخرجت هذه القائمة من تحليل كود المستودع الرسمي `claude-code-main`.

---

## 1. Read
- **الوظيفة:** قراءة محتوى الملفات
- **الاستخدام:** `Read(file_path)`, `Read(~/.ssh/**)`, `Read(src/**)`
- **الخيارات:** يدعم offset للقراءة الجزئية

## 2. Write
- **الوظيفة:** إنشاء ملف جديد أو الكتابة الكاملة فيه
- **الاستخدام:** `Write(file_path)`
- **ملاحظة:** يستبدل المحتوى بالكامل

## 3. Edit
- **الوظيفة:** تعديل جزء محدد من ملف موجود
- **الاستخدام:** `Edit(file_path)`, `Edit(src/**)`
- **ملاحظة:** يتطلب قراءة الملف أولاً (Read) قبل التعديل

## 4. MultiEdit
- **الوظيفة:** تعديل أجزاء متعددة من ملف في عملية واحدة
- **الاستخدام:** `MultiEdit`
- **ملاحظة:** مثل Edit لكن يطبق عدة تعديلات دفعة واحدة

## 5. Bash
- **الوظيفة:** تشغيل أوامر shell/terminal
- **الاستخدام:** `Bash(git:*)`, `Bash(npm:*)`, `Bash(docker:*)`
- **الخيارات:** يدعم command filters للتقييد

## 6. PowerShell (Windows)
- **الوظيفة:** تشغيل أوامر PowerShell على Windows
- **الاستخدام:** مشابه لـ Bash

## 7. Glob
- **الوظيفة:** البحث عن ملفات بنمط معين
- **الاستخدام:** `Glob(pattern)`
- **مثال:** البحث عن `*.ts` أو `src/**/*.py`

## 8. Grep
- **الوظيفة:** البحث عن نص داخل الملفات
- **الاستخدام:** `Grep(pattern)`
- **الخيارات:** يدعم count mode وpagination

## 9. LS
- **الوظيفة:** عرض محتويات مجلد
- **الاستخدام:** `LS(directory)`

## 10. WebFetch
- **الوظيفة:** جلب محتوى صفحة ويب
- **الاستخدام:** `WebFetch(domain:*.example.com)`
- **الخيارات:** يدعم domain filtering

## 11. WebSearch
- **الوظيفة:** البحث في الإنترنت
- **الاستخدام:** `WebSearch`

## 12. Task
- **الوظيفة:** تشغيل subagent لمهمة مستقلة
- **الاستخدام:** `Task`
- **ملاحظة:** يطلق agent منفصل لإنجاز مهمة

## 13. TodoWrite
- **الوظيفة:** كتابة وإدارة قائمة المهام للجلسة
- **الاستخدام:** `TodoWrite`

## 14. NotebookRead
- **الوظيفة:** قراءة Jupyter Notebooks
- **الاستخدام:** `NotebookRead`

## 15. NotebookEdit
- **الوظيفة:** تعديل Jupyter Notebooks
- **الاستخدام:** `NotebookEdit(path)`

## 16. AskUserQuestion
- **الوظيفة:** طرح سؤال تفاعلي على المستخدم مع خيارات
- **الاستخدام:** `AskUserQuestion`
- **الخيارات:** single-select, multi-select

## 17. Skill
- **الوظيفة:** تحميل وتشغيل skill محددة
- **الاستخدام:** `Skill(name *)`, `Skill(name)`

---

## أنواع Hook Events للأدوات

- **PreToolUse** → يُنفَّذ قبل أي tool call
- **PostToolUse** → يُنفَّذ بعد أي tool call

---

## ملفات هذا الأرشيف

| الملف | الوصف |
|-------|-------|
| `pretooluse.py` | Hook يعترض أي tool قبل تنفيذه |
| `posttooluse.py` | Hook يعترض أي tool بعد تنفيذه |
| `rule_engine.py` | محرك قواعد تقييم أذونات الأدوات |
| `config_loader.py` | محمّل إعدادات قواعد الأدوات |
| `tool-usage.md` | توثيق استخدام الأدوات مع MCP |
| `frontmatter-reference.md` | مرجع allowed-tools في الأوامر |
| `hook-development-SKILL.md` | دليل تطوير hooks للأدوات |
| `patterns.md` | أنماط hook للأدوات |
| `advanced.md` | أنماط متقدمة لـ hooks |
| `bash_command_validator_example.py` | مثال validator لأوامر Bash |
| `settings-strict.json` | إعدادات أذونات صارمة |
| `settings-lax.json` | إعدادات أذونات مرنة |
| `settings-bash-sandbox.json` | إعدادات sandbox للـ Bash |
