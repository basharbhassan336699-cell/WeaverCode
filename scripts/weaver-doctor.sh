#!/bin/bash
# فاحص تشخيصي: ماذا يتكلّم المزوّد وماذا يُرجع؟ (يحلّ «النموذج لا يرد»)
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1
python3 scripts/weaver-doctor.py
