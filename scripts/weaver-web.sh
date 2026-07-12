#!/bin/bash
# تشغيل لوحة الويب في المقدّمة (Termux / Linux / macOS)
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
exec python3 web/server.py
