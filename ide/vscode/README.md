# WeaverCode — امتداد VS Code 🕸️

يشغّل وكيل **WeaverCode** البرمجي المستقل من داخل VS Code، عبر الطرفية المدمجة.
يعمل مع أي مزوّد ونموذج AI (Anthropic / OpenAI / OpenRouter / DeepSeek / Groq /
Ollama...) — لأنه يعتمد على بيئة `weaver.py` نفسها ولا يخزّن أي مفاتيح.

> Runs the provider-agnostic WeaverCode agent inside VS Code. It never stores
> API keys — `weaver.py` resolves its own credentials from `.env` / environment.

## المتطلبات
- Python 3.10+ و`weaver.py` في جذر مساحة العمل (أو اضبط مساره في الإعدادات).
- المفاتيح مضبوطة مسبقاً في `.env` أو متغيرات البيئة (`WEAVER_API_KEY`،
  `WEAVER_BASE_URL`، `WEAVER_MODEL`).

## الأوامر
| الأمر | الوظيفة | الاختصار |
|-------|---------|----------|
| `WeaverCode: Open Interactive Chat` | فتح المحادثة التفاعلية في الطرفية | `Ctrl+Alt+C` |
| `WeaverCode: Run Task` | تنفيذ مهمة تكتبها | `Ctrl+Alt+W` |
| `WeaverCode: Run on Selection` | تحليل النص المحدّد (قائمة السياق) | — |
| `WeaverCode: Explain This File` | شرح الملف الحالي (عبر `@file`) | — |
| `WeaverCode: Show Status` | فحص الإصدار والحالة | — |

## الإعدادات
| المفتاح | الافتراضي | الوصف |
|---------|-----------|-------|
| `weavercode.pythonPath` | `python3` | مفسّر Python |
| `weavercode.weaverPath` | (تلقائي) | مسار `weaver.py` |
| `weavercode.mode` | `main` | وضع الوكيل |
| `weavercode.autoApprove` | `false` | تمرير `--yes` (بحذر) |

## التثبيت (تطوير)
```bash
cd ide/vscode
# افتح المجلد في VS Code واضغط F5 لتشغيل نافذة تطوير الامتداد
# أو حزّمه:  npx @vscode/vsce package
```

## الأمان
- لا يقرأ الامتداد المفاتيح ولا يرسلها — يشغّل `weaver.py` فقط الذي يدير مفاتيحه.
- كل الوسائط تُقتبَس بأمان (`shellQuote`) لمنع حقن الأوامر.
