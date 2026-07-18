"""
permissions.py — نظام أذونات WeaverCode على مستوى الملفات والأدوات
===================================================================

يدعم قواعد مثل:
  Edit(src/**)          — السماح بتعديل ملفات src فقط
  Read(~/.ssh/**)       — السماح بقراءة .ssh فقط
  Bash(git:*)           — السماح بأوامر git فقط
  Bash(npm:*)           — السماح بأوامر npm فقط

الإعداد من settings.json أو managed-settings.json.

الأولويات: deny > allow > ask (السؤال الافتراضي)
"""

import fnmatch
import os
import re
import json
from pathlib import Path
from typing import Optional, Dict, List


class PermissionRule:
    """قاعدة إذن واحدة."""

    def __init__(self, raw: str):
        """
        raw أمثلة:
          "Edit(src/**)"
          "Bash(git:*)"
          "Read(~/.ssh/**)"
          "Write"          ← بدون نمط = ينطبق على كل الحالات
        """
        self.raw = raw
        m = re.match(r'^(\w+)(?:\((.+)\))?$', raw.strip())
        if m:
            self.tool = m.group(1)
            self.pattern = m.group(2) or "*"
        else:
            self.tool = raw.strip()
            self.pattern = "*"

    def matches(self, tool_name: str, arg: str = "") -> bool:
        """هل تنطبق هذه القاعدة على استدعاء الأداة؟"""
        if self.tool != tool_name:
            return False
        if self.pattern == "*":
            return True
        # توسيع ~ في المسارات
        expanded = os.path.expanduser(self.pattern)
        # مطابقة glob
        return fnmatch.fnmatch(arg, expanded)


class PermissionManager:
    """
    يُحمَّل من settings.json ويتخذ قرارات allow/deny/ask.

    صيغة settings.json:
    {
      "permissions": {
        "allow": ["Edit(src/**)", "Bash(git:*)", "Read"],
        "deny":  ["Bash(rm:*)", "Write(/etc/**)"],
        "defaultMode": "ask"   // ask | allow | deny
      }
    }
    """

    DECISION_ALLOW = "allow"
    DECISION_DENY = "deny"
    DECISION_ASK = "ask"

    def __init__(self, config_path: Optional[Path] = None):
        self._allow: List[PermissionRule] = []
        self._deny: List[PermissionRule] = []
        self._default = self.DECISION_ASK
        self._session_allow: set = set()   # أذونات مؤقتة للجلسة
        self._session_deny: set = set()
        self._load(config_path)

    def _load(self, config_path: Optional[Path]) -> None:
        """تحميل الإعدادات من الملف."""
        root = Path(__file__).resolve().parent.parent
        candidates = [
            config_path,
            root / ".claude" / "settings.json",
            root / "config" / "settings.json",
            Path.home() / ".weaver" / "settings.json",
        ]
        for path in candidates:
            if path and Path(path).exists():
                try:
                    data = json.loads(Path(path).read_text(encoding="utf-8"))
                    perms = data.get("permissions", {})
                    self._allow = [PermissionRule(r)
                                   for r in perms.get("allow", [])]
                    self._deny = [PermissionRule(r)
                                  for r in perms.get("deny", [])]
                    self._default = perms.get("defaultMode", self.DECISION_ASK)
                    return
                except Exception:
                    continue

    def decide(self, tool_name: str, primary_arg: str = "") -> str:
        """
        يُرجع: "allow" | "deny" | "ask"

        primary_arg هو أهم وسيط للأداة:
          - Edit/Write/Read → مسار الملف
          - Bash → نص الأمر
          - WebFetch → الـ URL
          - بقية الأدوات → فارغ
        """
        key = f"{tool_name}:{primary_arg}"

        # فحص أذونات الجلسة أولاً
        if key in self._session_allow or tool_name in self._session_allow:
            return self.DECISION_ALLOW
        if key in self._session_deny or tool_name in self._session_deny:
            return self.DECISION_DENY

        # deny له الأولوية
        for rule in self._deny:
            if rule.matches(tool_name, primary_arg):
                return self.DECISION_DENY

        # ثم allow
        for rule in self._allow:
            if rule.matches(tool_name, primary_arg):
                return self.DECISION_ALLOW

        return self._default

    def session_allow(self, tool_name: str, primary_arg: str = "") -> None:
        """إضافة إذن مؤقت للجلسة الحالية."""
        key = f"{tool_name}:{primary_arg}" if primary_arg else tool_name
        self._session_allow.add(key)

    def session_deny(self, tool_name: str, primary_arg: str = "") -> None:
        """إضافة رفض مؤقت للجلسة الحالية."""
        key = f"{tool_name}:{primary_arg}" if primary_arg else tool_name
        self._session_deny.add(key)

    def add_rule(self, decision: str, raw: str) -> None:
        """إضافة قاعدة ديناميكياً."""
        rule = PermissionRule(raw)
        if decision == self.DECISION_ALLOW:
            self._allow.append(rule)
        elif decision == self.DECISION_DENY:
            self._deny.append(rule)

    def list_rules(self) -> Dict[str, List[str]]:
        """عرض كل القواعد الحالية."""
        return {
            "allow": [r.raw for r in self._allow],
            "deny": [r.raw for r in self._deny],
            "default": self._default,
            "session_allow": list(self._session_allow),
            "session_deny": list(self._session_deny),
        }
