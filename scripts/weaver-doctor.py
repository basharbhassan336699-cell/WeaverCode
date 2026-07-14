#!/usr/bin/env python3
"""
weaver-doctor.py — فاحص تشخيصي: ماذا يتكلّم المزوّد وماذا يُرجع؟
يرسل رسالة "hi" بصيغتين (OpenAI و Anthropic) ويطبع رمز الحالة والجسم الخام،
فيتّضح أي صيغة يقبلها المزوّد وأي شكل يُرجعه — لحلّ مشكلة «النموذج لا يرد».

الاستخدام:  python3 scripts/weaver-doctor.py
"""
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def load_env():
    env_file = ROOT / "config" / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):].strip()
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
            v = v[1:-1]
        if k:
            os.environ.setdefault(k, v)


def curl_post(url, headers, payload):
    args = ["curl", "-sS", "-L", "--location-trusted", "-X", "POST", url]
    for k, v in headers.items():
        args += ["-H", f"{k}: {v}"]
    args += ["--max-time", "60", "--data-binary", "@-",
             "-w", "\nWEAVER_HTTP_STATUS:%{http_code}"]
    try:
        p = subprocess.run(args, input=json.dumps(payload).encode(),
                           capture_output=True, timeout=90)
    except Exception as e:
        return None, f"(تعذّر تشغيل curl: {e})"
    raw = p.stdout.decode("utf-8", "replace")
    status = "?"
    if "WEAVER_HTTP_STATUS:" in raw:
        raw, _, s = raw.rpartition("WEAVER_HTTP_STATUS:")
        raw, status = raw.rstrip("\n"), s.strip()
    if p.returncode != 0 and not raw:
        raw = p.stderr.decode("utf-8", "replace")
    return status, raw


def extract_text(body):
    """يحاول استخراج نص الرد من أي شكل شائع."""
    try:
        d = json.loads(body)
    except Exception:
        return None, "ليس JSON"
    # OpenAI shape
    if isinstance(d.get("choices"), list) and d["choices"]:
        m = d["choices"][0].get("message", {})
        return (m.get("content") or "").strip() or None, "OpenAI (choices[0].message.content)"
    # Anthropic shape
    c = d.get("content")
    if isinstance(c, list):
        parts = [b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text"]
        return ("".join(parts).strip() or None), "Anthropic (content[].text)"
    if isinstance(c, str):
        return c.strip() or None, "content كسلسلة"
    if isinstance(d.get("error"), (dict, str)):
        return None, f"خطأ من المزوّد: {json.dumps(d['error'], ensure_ascii=False)[:200]}"
    return None, "شكل غير معروف"


def main():
    load_env()
    key = os.environ.get("WEAVER_API_KEY", "")
    base = os.environ.get("WEAVER_BASE_URL", "").rstrip("/")
    model = os.environ.get("WEAVER_MODEL", "")

    print("🕸️  WeaverCode Doctor — فحص المزوّد")
    print("=" * 55)
    print(f"المزوّد : {base or '(غير مضبوط!)'}")
    print(f"النموذج : {model or '(غير مضبوط!)'}")
    print(f"المفتاح : {'مضبوط (' + str(len(key)) + ' حرف)' if key else '❌ غير مضبوط'}")
    print("=" * 55)
    if not base or not key or not model:
        print("❌ أكمل WEAVER_BASE_URL و WEAVER_API_KEY و WEAVER_MODEL في config/.env")
        return

    results = {}

    # ── (1) صيغة OpenAI → /chat/completions ──────────────────────────────
    oai_url = base + ("" if base.endswith("/chat/completions")
                      else "/chat/completions")
    print(f"\n▶ اختبار صيغة OpenAI:  POST {oai_url}")
    st, body = curl_post(
        oai_url,
        {"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        {"model": model, "max_tokens": 64,
         "messages": [{"role": "user", "content": "قل مرحبا بكلمة واحدة"}]},
    )
    text, shape = extract_text(body)
    print(f"   الحالة HTTP: {st}")
    print(f"   الشكل: {shape}")
    print(f"   النص المستخرَج: {text!r}")
    print(f"   الجسم الخام (أول 600 حرف):\n   {body[:600]}")
    results["openai"] = (st, bool(text))

    # ── (2) صيغة Anthropic → /v1/messages ────────────────────────────────
    if base.endswith("/messages"):
        ant_url = base
    elif base.endswith("/v1"):
        ant_url = base + "/messages"
    else:
        ant_url = base + "/v1/messages"
    print(f"\n▶ اختبار صيغة Anthropic:  POST {ant_url}")
    st2, body2 = curl_post(
        ant_url,
        {"Content-Type": "application/json", "x-api-key": key,
         "anthropic-version": "2023-06-01", "Authorization": f"Bearer {key}"},
        {"model": model, "max_tokens": 64,
         "messages": [{"role": "user", "content": "قل مرحبا بكلمة واحدة"}]},
    )
    text2, shape2 = extract_text(body2)
    print(f"   الحالة HTTP: {st2}")
    print(f"   الشكل: {shape2}")
    print(f"   النص المستخرَج: {text2!r}")
    print(f"   الجسم الخام (أول 600 حرف):\n   {body2[:600]}")
    results["anthropic"] = (st2, bool(text2))

    # ── الخلاصة والتوصية ─────────────────────────────────────────────────
    print("\n" + "=" * 55)
    print("📋 الخلاصة:")
    oai_ok = results["openai"][1]
    ant_ok = results["anthropic"][1]
    if ant_ok:
        print("✅ صيغة Anthropic تعمل. الإعداد الحالي صحيح — لا تغيّر شيئاً.")
    elif oai_ok:
        print("✅ صيغة OpenAI هي التي تعمل، لا Anthropic!")
        print("   الحلّ: أجبر صيغة OpenAI بإضافة هذا السطر إلى config/.env:")
        print("       WEAVER_API_FORMAT=openai")
        print("   ثم أعد التشغيل. (سيرسل WeaverCode بصيغة OpenAI لهذا المزوّد.)")
    else:
        print("❌ لم تُرجِع أيّ صيغة نصاً. غالباً السبب رصيد/مفتاح.")
        print("   افحص رسالة الخطأ في الجسم الخام أعلاه (كثيراً ما تكون: انتهاء")
        print("   الاستخدام المجاني أو الحاجة لإضافة رصيد في لوحة المزوّد).")
    print("=" * 55)
    print("انسخ هذا الإخراج كاملاً وأرسله للمطوّر لحلٍّ دقيق.")


if __name__ == "__main__":
    main()
