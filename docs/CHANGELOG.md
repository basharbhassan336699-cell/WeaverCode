# سجل التغييرات — WeaverCode 🕸️

## v1.3.0 — دعم مزدوج للمزودين ونقل عبر curl

### أُصلح / تغيّر
- **`core/engine/provider.py`** — إعادة كتابة كاملة لمحرك الاتصال:
  - دعم صيغة **Anthropic** (`POST /v1/messages`) تلقائياً عند اكتشاف
    `aerolink` أو `anthropic` في `WEAVER_BASE_URL`.
  - دعم صيغة **OpenAI** (`POST /chat/completions`) لبقية المزودين
    (OpenRouter، Groq، DeepSeek، OpenAI، Ollama...).
  - استخدام **curl** داخلياً بدل httpx لتجاوز مشاكل إعادة التوجيه (redirect)
    والحالة 305، مع خيارات `follow_redirects` و`--location-trusted`.
  - دعم **بروكسي اختياري** عبر `WEAVER_PROXY` أو `HTTPS_PROXY`/`HTTP_PROXY`.
  - **توحيد الاستجابة**: يُحوَّل رد Anthropic إلى شكل OpenAI (`choices[0].message`)
    فيبقى `query_engine` موحّداً دون تغيير، مع تحويل مخطط الأدوات والرسائل
    (system/tool_use/tool_result) بين الصيغتين.
  - **معالجة كاملة للأخطاء برسائل عربية واضحة** لكل حالات HTTP الشائعة
    (401, 403, 404, 305, 307, 308, 429, 500, 503) وأخطاء الشبكة وJSON.
  - إجبار الصيغة يدوياً عبر `WEAVER_API_FORMAT=anthropic|openai`.
- **`prompts/system.py`** — تشديد قاعدة الهوية: يعرّف الوكيل عن نفسه كـ
  WeaverCode فقط، ولا يذكر أي نموذج أو شركة أو منصة (لا إثباتاً ولا نفياً)،
  والعربية هي اللغة الافتراضية.
- **`config/.env.example`** — شرح الفرق بين صيغتي OpenAI وAnthropic، وإضافة
  **aerolink** كمثال جاهز لمزوّد متوافق مع Anthropic
  (`WEAVER_BASE_URL=https://capi.aerolink.lat`، `WEAVER_MODEL=claude-fable-5`)،
  وإضافة متغيرات `WEAVER_API_FORMAT` و`WEAVER_PROXY` و`WEAVER_FOLLOW_REDIRECTS`
  و`WEAVER_TIMEOUT`.
- **`weaver.py`** — تحميل `config/.env` تلقائياً عند بدء التشغيل، وتحسين قارئ
  `.env` (دعم `export` وإزالة علامات الاقتباس). البانر يعرض اسم WeaverCode فقط.

### ملاحظة
- الآن `python3 weaver.py "قل مرحباً"` يعمل مع أي مزوّد
  (aerolink / groq / openrouter / anthropic / openai) بمجرد ضبط المفتاح في `.env`.

## v1.2.0 — الهوية البصرية
### أُضيف
- `assets/` — 15 أيقونة بأحجام وأنماط مختلفة
  - أيقونة خارجية (شبكة برتقالية على خلفيات داكنة/فاتحة)
  - أيقونة داخلية مفرغة (شفافة لواجهة التطبيق)
  - نسخ: بيضاء، سوداء، favicon، متاجر
- `core/ui.py` — واجهة terminal ملونة بألوان WeaverCode
  - بانر ASCII مع الأيقونة
  - ألوان رسمية: `#C67121` برتقالي | `#0F0F19` كحلي
  - تنسيق موحد للأدوات والردود والأخطاء
  - دعم عرض الصور في Kitty terminal
- `README.md` — توثيق كامل مع الشارات والأيقونات
- تكامل UI في `weaver.py` — البانر والألوان في كل الأوضاع
- أوامر تفاعلية جديدة: `/icon`، `/stats`

## v1.1.0 — توسيع الأدوات

## v1.0.0 — البنية الأولية
### أُضيف
- `core/engine/provider.py` — محرك الاتصال بأي مزود API
- `core/engine/query_engine.py` — المحرك الرئيسي للحلقة الوكيلية
- `core/tools/registry.py` — 26 أداة مدمجة
- `core/memory/store.py` — ذاكرة SQLite دائمة
- `prompts/system.py` — 6 بروموهات نظامية متخصصة
- `weaver.py` — واجهة سطر الأوامر
- `.claude/commands/` — 5 أوامر Claude Code مخصصة
- `scripts/` — سكربتات التثبيت والرفع

### الميزات
- دعم أي مزود OpenAI-compatible
- ذاكرة دائمة عبر الجلسات
- 6 أوضاع تخصصية
- وضع تفاعلي ووضع مهمة واحدة
- دعم Termux/Android
