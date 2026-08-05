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
│   ├── tools/             ← الأدوات المدمجة (49 أداة)
│   ├── index/             ← فهرس رموز الكود (SymbolIndex)
│   ├── memory/            ← نظام الذاكرة SQLite
│   ├── backup.py          ← نسخ احتياطي/تصدير الذاكرة والجلسات
│   ├── autopush.py        ← الرفع التلقائي إلى GitHub (اختياري)
│   └── skills/            ← نظام المهارات
├── integrations/          ← جسور الأدوات الخارجية (ocr_bridge / loop_bridge)
├── vendors/               ← أدوات خارجية مدمجة (olmOCR/Chandra/Loop) — لا تُعدَّل
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
- التنقّل في مشروع كبير («أين تُعرَّف X؟»): استخدم `SymbolIndex`
- استخراج نصّ من PDF/صورة: استخدم `OCR`

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

---

## الميزات المضافة (v4.0) — Plugins والأمان

### Plugins المدمجة (plugins/)
- **security-guidance**: مراجعة أمنية تلقائية بـ LLM على كل edit وcommit وstop
  - يكتشف: SQL injection، XSS، SSRF، hardcoded secrets، command injection
  - **معطّل افتراضياً** (SessionStart يثبّت SDK + مراجعات LLM = استهلاك مفاتيح/بطء
    على Termux). للتفعيل: أزل `"disabled": true` من
    `plugins/security-guidance/.claude-plugin/plugin.json` (يتطلب `ANTHROPIC_API_KEY`).
  - `/weaver-security` للمراجعة اليدوية
- **pr-review-toolkit**: 6 agents متخصصة لمراجعة الكود → `/weaver-review-pr`
- **feature-dev**: تطوير features بمنهجية architect→explorer→reviewer → `/weaver-feature`
- **commit-commands**: commit ذكي + push + PR → `/weaver-commit`, `/weaver-commit-push`, `/weaver-clean-gone`
- **code-review**: مراجعة كود شاملة → `/weaver-code-review`
- **agent-sdk-dev**: إنشاء agents جديدة → `/weaver-new-sdk-app`

### نظام Permissions (core/permissions.py)
- قواعد على مستوى الملفات: `Edit(src/**)`, `Read(~/.ssh/**)`
- قواعد على مستوى الأوامر: `Bash(git:*)`, `Bash(npm:*)`
- أولويات: deny → allow → ask (افتراضي)
- إعدادات في: `config/settings-strict.json`, `config/settings-lax.json`
- طبقة اختيارية: بلا `settings.json` يبقى السلوك "ask" (لا تغيير)
- `/weaver-permissions` لإدارة القواعد

### asyncRewake Support
- hooks الآن تدعم `asyncRewake: true` و`if` لإعادة تنبيه WeaverCode بعد تنفيذ الأدوات
- `run()` يبقى يُرجع bool (منع PreToolUse) — الدعم إضافي غير كاسر

### DevContainer (بيئة عزل)
- `.devcontainer/` جاهز لـ VS Code DevContainers / Codespaces (لا يعمل على Termux)

### GCP Gateway
- `scripts/weaver-gateway.sh [setup|deploy|destroy]` + Terraform في `scripts/gateway/`

---

## الميزات المضافة (v4.5x) — أدوات مدمجة جديدة

### فهرس رموز الكود — أداة `SymbolIndex` (core/index/symbols.py)
- «أين تُعرَّف دالة/صنف/طريقة؟» بسرعة على المشاريع الكبيرة، مع الملف والسطر.
- **Python عبر `ast`** (دقيق) و**JS/TS/Go/Rust/Java عبر regex**. بناء **تزايدي**
  (يعيد تحليل الملفات المتغيّرة فقط) وكاش في `~/.weaver/cache`.
- الأوضاع: `build` | `find` | `outline`. ومن الطرفية: `weaver symbols …`.

### OCR — أداة `OCR` (integrations/ocr_bridge.py → vendors/)
- استخراج نصّ (Markdown) من PDF/صور. توجيه تلقائي: **PDF↦olmOCR، صور↦Chandra**.
- `detect_only=true` يُرجع الأداة المناسبة دون تشغيل؛ التشغيل الفعلي يتطلّب
  خادم vLLM (`server_url`). تتطلّب إذناً وتتدهور بأمان عند غياب أداة/تبعية.

### Loop Engineering — أداة `LoopEngine` (integrations/loop_bridge.py → vendors/)
- أدوات Node لهندسة الحلقات المستقلة: `audit` (درجة جاهزية) | `gate`
  (تقييم commit/merge مقابل `gate.yaml` → مسموح/تصعيد) | `context` (قاطِع دائرة
  على سجلّ تشغيل → متابعة/تصعيد). تتطلّب إذناً + Node.

### قاعدة الأدوات المدمجة (vendors/)
- **لا تُعدّل أيّ شيفرة داخل `vendors/`** — أيّ تحسين يكون في `integrations/` فقط.
- الجسور تُشغّل الأدوات كعمليات منفصلة (subprocess)؛ `node_modules` مُتجاهَلة في git.

### ميزات مساندة أخرى
- **نسخ احتياطي**: `weaver backup [--keep N]` · `backups` · `restore-backup`
  (core/backup.py) — أرشيف محمول للذاكرة والجلسات.
- **رفع تلقائي** (اختياري، `WEAVER_AUTO_PUSH=1`): core/autopush.py — يشترك فيه
  الطرفية ولوحة الويب.
- **بثّ حيّ** (اختياري، `WEAVER_STREAM=1`): عرض الردّ توكِناً بتوكِن في لوحة الويب.
- **CI**: `.github/workflows/tests.yml` يشغّل الاختبارات على كل push/PR.

---

## التحقق الذاتي الإلزامي (Self-Verification)

بعد أي مهمة برمجية أنشأت/عدّلت فيها ملفات، **لا تُعلن الانتهاء** قبل التحقق فعلياً:

### ١. تحقق نحوي فوري (لكل ملف Python أنشأته/عدّلته)
```bash
python3 -m py_compile <الملف> && echo "✅" || echo "❌"
```

### ٢. اختبار الاستيراد
```bash
python3 -c "import <الوحدة>; print('✅ يُستورَد بنجاح')"
```

### ٣. تشغيل الاختبارات إن وُجدت
```bash
python3 -m pytest tests/ -q 2>&1 | tail -5
```

### ٤. تحقق من الملفات المُنشأة
```bash
wc -l <الملف>        # غير فارغ
```

### القاعدة الذهبية
**لا تكتب «اكتملت المهمة» حتى تُشغّل اختباراً فعلياً وتقرأ مخرجاته**، واختم
بسطر: `✅ تم التحقق: N ملف — كل الاختبارات تمر / الكود يعمل بدون أخطاء`.
(لا ينطبق على المحادثات العادية بلا كتابة كود.)
