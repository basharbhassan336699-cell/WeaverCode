# 🕸️ WeaverCode — نظام الوكيل البرمجي المستقل

> الأيقونة الرسمية: `assets/icon_store_dark.png` (خارجية) | `assets/icon_internal_256.png` (داخلية)
> الألوان: `#C67121` برتقالي | `#0F0F19` كحلي داكن

## هوية المشروع
WeaverCode هو نظام وكيل برمجي مستقل تماماً عن أي شركة أو منصة بعينها.
يعمل مع أي نموذج ذكاء اصطناعي من أي مزود عبر مفاتيح API قابلة للتبديل.

**المستودع:** https://github.com/basharbhassan336699-cell/WeaverCode
**المطور:** Bashar
**اللغة الأساسية:** Python + TypeScript (Bun)
**بيئة التشغيل:** Android/Termux + Linux/Windows

---

## قواعد العمل الأساسية

### 1. استقلالية المزود
- لا تفترض أبداً أن النموذج هو Claude أو GPT أو غيره
- استخدم دائماً `WEAVER_MODEL` و`WEAVER_API_KEY` و`WEAVER_BASE_URL` من البيئة
- كل استدعاء API يمر عبر `core/engine/provider.py`

### 2. هيكل الملفات
```
WeaverCode/
├── CLAUDE.md              ← هذا الملف
├── .claude/               ← إعدادات وأوامر Claude Code
│   ├── commands/          ← أوامر slash مخصصة
│   ├── skills/            ← مهارات قابلة للاستدعاء
│   ├── agents/            ← تعريفات الوكلاء
│   └── hooks/             ← hooks الدورة الحياتية
├── core/
│   ├── engine/            ← محرك الوكيل الرئيسي
│   ├── tools/             ← الأدوات المدمجة (46 أداة)
│   ├── memory/            ← نظام الذاكرة SQLite
│   └── skills/            ← نظام المهارات
├── providers/             ← موصلات المزودين
├── config/                ← إعدادات المشروع
├── scripts/               ← سكربتات التشغيل والبناء
└── prompts/               ← البروموهات النظامية
```

### 3. أولويات الأدوات
- قراءة الملفات: استخدم `Read` لا `cat`
- تعديل الملفات: استخدم `Edit` لا `sed`
- البحث: استخدم `Grep` لا `grep` مباشرة
- البحث عن ملفات: استخدم `Glob` لا `find`

### 4. قواعد Python
- Python 3.10+ مطلوب
- استخدم `pip install --break-system-packages` في Termux
- المكتبات المطلوبة في `config/requirements.txt`
- لا تستخدم f-strings متداخلة

### 5. قواعد التوثيق
- كل دالة لها docstring عربي + إنجليزي
- كل ملف يبدأ بتعليق يشرح وظيفته
- سجل كل تغيير في `docs/CHANGELOG.md`

---

## المزودون المدعومون
| المزود | BASE_URL | ملاحظة |
|--------|----------|--------|
| Anthropic | https://api.anthropic.com/v1 | Claude |
| OpenAI | https://api.openai.com/v1 | GPT |
| OpenRouter | https://openrouter.ai/api/v1 | متعدد |
| DeepSeek | https://api.deepseek.com/v1 | DeepSeek |
| Together | https://api.together.xyz/v1 | مفتوح |
| Groq | https://api.groq.com/openai/v1 | سريع |
| Ollama | http://localhost:11434/v1 | محلي |

---

## الأصول البصرية (assets/)
| الملف | الاستخدام |
|-------|-----------|
| `icon_store_dark.png` | GitHub README / متاجر التطبيقات |
| `icon_store_light.png` | خلفيات فاتحة |
| `icon_512x512.png` | App Store / Play Store |
| `icon_256x256.png` | GitHub / سطح المكتب |
| `icon_internal_256.png` | داخل التطبيق |
| `icon_white_256.png` | على خلفيات داكنة |
| `favicon.ico` | مواقع الويب |

## متغيرات البيئة المطلوبة
```bash
WEAVER_API_KEY=your_key_here
WEAVER_BASE_URL=https://api.openrouter.ai/api/v1
WEAVER_MODEL=anthropic/claude-sonnet-4-6
WEAVER_MAX_TOKENS=8192
WEAVER_TEMPERATURE=0.7
WEAVER_DB_PATH=~/.weaver/memory.db
```

---

## سير العمل الأساسي
1. المستخدم يعطي مهمة
2. `QueryEngine` يحلل المهمة ويختار الأدوات
3. الأدوات تُنفَّذ بالتسلسل أو بالتوازي
4. النتائج تُحفظ في الذاكرة SQLite
5. الرد النهائي يُعاد للمستخدم

## GitHub
مرتبط عبر GitHub CLI (gh). الأدوات: GitHubStatus, GitHubCreateRepo, GitHubListRepos, GitHubCreateIssue.
للتحقق: `gh auth status`

---

## الميزات المضافة (v3.0)

### نظام Sessions (الجلسات)
- `python weaver.py --resume` — استئناف جلسة سابقة
- `python weaver.py --sessions` — عرض الجلسات
- `/weaver-resume` — استئناف من داخل Claude Code
- الجلسات تُحفظ في SQLite: `~/.weaver/memory.db` جدول `sessions`

### Hooks الموسّع (9 أحداث)
- `SessionStart` — يحمّل السياق + additionalContext
- `SessionEnd` — تنظيف وتسجيل
- `PreCompact` — منع أو إثراء التلخيص (exit 2 = منع)
- `PostCompact` — بعد التلخيص
- `InstructionsLoaded` — عند تحميل CLAUDE.md

### نظام Skills
- مجلد: `.claude/skills/<name>/SKILL.md`
- أداة `Skill` مدمجة في الوكيل
- `/weaver-skills` لعرض المتاح

### نظام Plugins
- مجلد: `plugins/<name>/.claude-plugin/plugin.json`
- يدمج hooks + commands تلقائياً
- `/weaver-plugins` لعرض المثبت

### MCP الموسّع
- يدعم الآن: stdio + SSE + HTTP
- صيغة config/mcp.json: أضف `"transport": "sse"` أو `"transport": "http"`

### FTS5 الحقيقي
- `get_relevant()` تستخدم FTS5 الحقيقي مع triggers تلقائية
