#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
weaver-cli.py — shim للتوافق: يستدعي weaver_cli.main().
المنطق الفعلي في weaver_cli.py (اسم قابل للاستيراد ليعمل كأمر مثبَّت عبر pip).
Backward-compat entry so `python weaver-cli.py <cmd>` keeps working.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from weaver_cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
