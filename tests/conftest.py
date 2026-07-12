"""إعداد مشترك للاختبارات — إضافة جذر المشروع للمسار وعزل قاعدة البيانات."""

import os
import sys
import tempfile
from pathlib import Path

# جذر المشروع في المسار
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# عزل ذاكرة الاختبارات في ملف مؤقت (لا تلمس ~/.weaver)
os.environ.setdefault(
    "WEAVER_DB_PATH",
    str(Path(tempfile.gettempdir()) / "weaver_test_memory.db"),
)
# سلوك ثابت للاختبارات
os.environ.setdefault("WEAVER_IDENTITY_SANITIZE", "full")
