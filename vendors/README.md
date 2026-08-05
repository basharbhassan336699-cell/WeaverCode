# 🕸️ vendors/ — أدوات خارجية مدمجة (vendored)

هذا المجلد يحوي أدوات خارجية **كما هي، دون أي تعديل على شيفرتها**. WeaverCode لا
يستدعيها مباشرةً بل عبر جسور رقيقة (bridges) في `integrations/` تُشغّلها كعمليات
منفصلة (subprocess)، فلا تُحمَّل تبعياتها الثقيلة إلا عند الحاجة الفعلية.

> ⚠️ **لا تُعدّل أيّ ملف داخل هذه المجلدات.** أيّ تحسين يكون في `integrations/` فقط.

## الأدوات

| المجلد | الأداة | الغرض | التشغيل |
|--------|--------|-------|---------|
| `olmocr/` | **olmOCR** (AllenAI) | تحويل ملفات PDF والمستندات الصورية إلى نصّ/Markdown نظيف عبر نموذج رؤيوي على خادم vLLM. | Python — يتطلّب خادم vLLM (‏`--server`) وتبعيات ثقيلة (torch/boto3) |
| `chandra/` | **Chandra** (datalab-to) | نماذج حديثة لفهم المستندات (OCR) — تُخرج Markdown/HTML. تعمل محلياً (‏`hf`) أو عبر خادم vLLM (‏`vllm`). | Python — `chandra <in> <out> --method vllm\|hf` |
| `loop/` | **Loop Engineering** (cobusgreyling) | حزمة أدوات Node لهندسة الحلقات المستقلة (autonomous loops): تقييم الجاهزية، بوّابة سياسات قبل الإجراءات، وقاطِع دائرة للسياق. | Node — `node tools/<tool>/dist/cli.js …` |

### أدوات loop الفرعية (المستخدَمة في الجسر)
- **loop-audit** — «درجة جاهزية الحلقة» (Loop Readiness Score) لمشروع.
- **loop-gate** — يقيّم إجراءً مقترحاً (‏commit/merge + الملفات المتغيّرة) مقابل
  سياسة `gate.yaml` ويُرجع allow/escalate.
- **loop-context** — قاطِع دائرة: يقرأ «سجلّ تشغيل» (ledger) ويقرّر
  continue/escalate لمنع الحلقات الجامحة.

## ملاحظات التثبيت (اختيارية — عند الرغبة بالتشغيل الفعلي)
هذه الأدوات ثقيلة وتُشغَّل عند الطلب فقط؛ الجسور تعمل بأمان وتُرجع رسالة واضحة إن
غابت التبعيات.

```bash
# olmOCR / Chandra (Python) — بيئة معزولة مستحسنة (تتطلّب GPU/vLLM للتشغيل الحقيقي)
pip install ./vendors/olmocr          # أو اتبع vendors/olmocr/README.md
pip install ./vendors/chandra         # أو اتبع vendors/chandra/README.md

# loop (Node) — ثبّت تبعيات كل أداة تحتاجها
cd vendors/loop/tools/loop-audit && npm install
cd vendors/loop/tools/loop-gate   && npm install
cd vendors/loop/tools/loop-context && npm install
```

> `node_modules/` **مُتجاهَلة في git** (‏~18MB / 5200+ ملف) — تُعاد توليدها بـ
> `npm install`. الشيفرة المصدرية والملفات المبنيّة (`dist/`) محفوظة.

## الرخص
كل أداة تحتفظ برخصتها الأصلية داخل مجلدها (`LICENSE`). راجعها قبل أيّ استخدام أو
إعادة توزيع.
