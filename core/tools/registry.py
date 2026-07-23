"""
registry.py — سجل الأدوات المدمجة في WeaverCode
27 أداة مدمجة حقيقية (ملفات/بحث/تنفيذ/ذاكرة/مهام/ويب/git/تعديل متعدد/وكيل فرعي)،
مع إمكانية تسجيل أدوات خارجية ديناميكياً عبر MCP (register_dynamic).
"""

import os
import subprocess
import glob as _glob
import asyncio
import json
import re
from pathlib import Path
from typing import Dict, Any, List, Callable, Optional


class Tool:
    """تعريف أداة واحدة"""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: Dict,
        fn: Callable,
        requires_permission: bool = False,
    ):
        self.name = name
        self.description = description
        self.parameters = parameters
        self.fn = fn
        self.requires_permission = requires_permission

    def to_schema(self, compact: bool = False) -> Dict:
        """تحويل لصيغة OpenAI tool schema.

        compact=True: وصف مختصر (السطر الأول ≤100 حرف) ووصف وسائط ≤40 حرفاً —
        يوفّر ~نصف توكنات الأدوات لكل طلب دون إسقاط أي أداة أو وسيط.
        """
        if not compact:
            return {
                "type": "function",
                "function": {
                    "name": self.name,
                    "description": self.description,
                    "parameters": self.parameters,
                },
            }
        desc = (self.description or "").strip().splitlines()[0][:100]

        def _trim(node):
            if isinstance(node, dict):
                out = {}
                for k, v in node.items():
                    if k == "description" and isinstance(v, str):
                        out[k] = v[:40]
                    else:
                        out[k] = _trim(v)
                return out
            if isinstance(node, list):
                return [_trim(x) for x in node]
            return node

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": desc,
                "parameters": _trim(self.parameters),
            },
        }


class ToolRegistry:
    """سجل جميع الأدوات المتاحة"""

    def __init__(self, work_dir: Optional[str] = None):
        self.work_dir = work_dir or os.getcwd()
        self._tools: Dict[str, Tool] = {}
        # يضبطه QueryEngine ليمكّن أداة Agent من تشغيل وكيل فرعي
        # التوقيع: async (prompt: str, mode: str) -> str
        self.agent_runner: Optional[Callable] = None
        # قائمة المهام الحيّة (TodoWrite) — تُحفظ لكل جلسة على مستوى السجل
        self._todos: List[Dict[str, Any]] = []
        # أوامر bash العاملة في الخلفية: shell_id → معلومات العملية
        self._bg_shells: Dict[str, Dict[str, Any]] = {}
        self._bg_counter = 0
        # مجلدات عمل إضافية (multi-workspace / --add-dir)
        self.extra_dirs: List[str] = []
        # الملفات التي أنشأها/عدّلها الوكيل (لنسخها لمجلد التنزيلات)
        self._created_files: List[str] = []
        self._register_all()

    def _resolve(self, path: str) -> Path:
        """يحلّل المسار: المطلق كما هو، والنسبي بالنسبة لمجلد العمل (لا CWD)."""
        p = Path(path).expanduser()
        if not p.is_absolute():
            p = Path(self.work_dir) / p
        return p

    def _register_all(self):
        """تسجيل جميع الأدوات المدمجة"""

        # ── الملفات ─────────────────────────────────────────────────────────

        self._add(Tool(
            name="Read",
            description=("قراءة أي ملف: نص وكود، CSV/JSON، أرشيفات ZIP/TAR (يسرد "
                         "العناصر ويستخرج النصوص)، مستندات Office (docx/xlsx/pptx)، "
                         "وملفات ثنائية (معاينة hex). الصور و PDF تُرسَل للنموذج "
                         "كمحتوى مرئي تلقائياً — يمكنك تحليلها مباشرةً. استخدم مسارات مطلقة."),
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "مسار الملف"},
                    "offset": {"type": "integer", "description": "رقم السطر للبداية"},
                    "limit": {"type": "integer", "description": "عدد الأسطر للقراءة"},
                },
                "required": ["path"],
            },
            fn=self._read,
        ))

        self._add(Tool(
            name="Write",
            description="إنشاء ملف جديد أو استبدال محتوى ملف موجود كاملاً.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string", "description": "المحتوى الكامل للكتابة"},
                },
                "required": ["path", "content"],
            },
            fn=self._write,
            requires_permission=True,
        ))

        self._add(Tool(
            name="WriteBinary",
            description=("إنشاء ملف من أي نوع (صورة/PDF/أرشيف/ثنائي) من محتوى "
                         "base64. استخدمه عندما يكون المحتوى غير نصّي."),
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "data_base64": {"type": "string", "description": "محتوى الملف مُرمَّزاً base64"},
                },
                "required": ["path", "data_base64"],
            },
            fn=self._write_binary,
            requires_permission=True,
        ))

        self._add(Tool(
            name="ExtractArchive",
            description="فكّ ضغط أرشيف ZIP أو TAR إلى مجلد (dest اختياري).",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "مسار الأرشيف"},
                    "dest": {"type": "string", "description": "مجلد الوجهة (اختياري)"},
                },
                "required": ["path"],
            },
            fn=self._extract_archive,
            requires_permission=True,
        ))

        self._add(Tool(
            name="Edit",
            description="تعديل نص محدد داخل ملف. يستبدل old_string بـ new_string (مطابقة دقيقة).",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_string": {"type": "string", "description": "النص المراد استبداله"},
                    "new_string": {"type": "string", "description": "النص الجديد"},
                    "replace_all": {"type": "boolean", "default": False},
                },
                "required": ["path", "old_string", "new_string"],
            },
            fn=self._edit,
            requires_permission=True,
        ))

        self._add(Tool(
            name="Glob",
            description="البحث عن ملفات بنمط glob مثل **/*.py أو src/**/*.ts",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "base_dir": {"type": "string", "description": "مجلد البداية (اختياري)"},
                },
                "required": ["pattern"],
            },
            fn=self._glob,
        ))

        self._add(Tool(
            name="Grep",
            description="البحث عن نمط regex داخل محتوى الملفات",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "نمط regex"},
                    "path": {"type": "string", "description": "مجلد أو ملف للبحث فيه"},
                    "file_glob": {"type": "string", "description": "نمط اسم الملف مثل *.py"},
                    "output_mode": {
                        "type": "string",
                        "enum": ["files_with_matches", "content", "count"],
                        "default": "content",
                    },
                    "ignore_case": {"type": "boolean", "default": False},
                },
                "required": ["pattern"],
            },
            fn=self._grep,
        ))

        # ── تنفيذ الأوامر ────────────────────────────────────────────────────

        self._add(Tool(
            name="Bash",
            description="""تنفيذ أوامر bash في البيئة الحالية.
- لا تستخدم: cat، head، tail، sed، awk، echo لقراءة الملفات (استخدم Read)
- لا تستخدم: find، grep للبحث (استخدم Glob و Grep)
- للعمليات الطويلة: أضف timeout مناسب
- المهلة الافتراضية: 120 ثانية""",
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "الأمر المراد تنفيذه"},
                    "timeout": {"type": "integer", "description": "المهلة بالثواني", "default": 120},
                    "work_dir": {"type": "string", "description": "مجلد التنفيذ"},
                    "run_in_background": {
                        "type": "boolean", "default": False,
                        "description": ("تشغيل الأمر في الخلفية وإرجاع shell_id "
                                        "لمتابعته عبر BashOutput/KillShell"),
                    },
                },
                "required": ["command"],
            },
            fn=self._bash,
            requires_permission=True,
        ))

        self._add(Tool(
            name="BashOutput",
            description=("قراءة الإخراج المتراكم من أمر bash يعمل في الخلفية "
                         "(بواسطة shell_id). يُرجع الجديد منذ آخر قراءة وحالة العملية."),
            parameters={
                "type": "object",
                "properties": {
                    "shell_id": {"type": "string",
                                 "description": "معرّف الـ shell الخلفي"},
                },
                "required": ["shell_id"],
            },
            fn=self._bash_output,
        ))

        self._add(Tool(
            name="KillShell",
            description="إنهاء أمر bash يعمل في الخلفية (بواسطة shell_id).",
            parameters={
                "type": "object",
                "properties": {
                    "shell_id": {"type": "string",
                                 "description": "معرّف الـ shell الخلفي"},
                },
                "required": ["shell_id"],
            },
            fn=self._kill_shell,
            requires_permission=True,
        ))

        # ── الذاكرة ─────────────────────────────────────────────────────────

        self._add(Tool(
            name="MemorySave",
            description="حفظ معلومة مهمة في الذاكرة الدائمة للوكيل",
            parameters={
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "مفتاح تعريفي"},
                    "value": {"type": "string", "description": "المحتوى المراد حفظه"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["key", "value"],
            },
            fn=self._memory_save,
        ))

        self._add(Tool(
            name="MemorySearch",
            description="البحث في الذاكرة الدائمة",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
            fn=self._memory_search,
        ))

        self._add(Tool(
            name="MemoryDelete",
            description="حذف معلومة من الذاكرة",
            parameters={
                "type": "object",
                "properties": {"key": {"type": "string"}},
                "required": ["key"],
            },
            fn=self._memory_delete,
        ))

        self._add(Tool(
            name="MemoryList",
            description="عرض قائمة بكل المفاتيح المحفوظة في الذاكرة",
            parameters={"type": "object", "properties": {}, "required": []},
            fn=self._memory_list,
        ))

        # ── المهام ───────────────────────────────────────────────────────────

        self._add(Tool(
            name="TaskCreate",
            description="إنشاء مهمة جديدة في قائمة المهام",
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "priority": {"type": "string", "enum": ["low", "medium", "high"], "default": "medium"},
                },
                "required": ["title"],
            },
            fn=self._task_create,
        ))

        self._add(Tool(
            name="TaskList",
            description="عرض جميع المهام وحالتها",
            parameters={
                "type": "object",
                "properties": {
                    "status": {"type": "string", "enum": ["all", "pending", "done"], "default": "all"},
                },
                "required": [],
            },
            fn=self._task_list,
        ))

        self._add(Tool(
            name="TaskUpdate",
            description="تحديث حالة مهمة",
            parameters={
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "status": {"type": "string", "enum": ["pending", "in_progress", "done", "cancelled"]},
                    "notes": {"type": "string"},
                },
                "required": ["task_id"],
            },
            fn=self._task_update,
        ))

        # ── الويب ────────────────────────────────────────────────────────────

        self._add(Tool(
            name="WebFetch",
            description="جلب محتوى صفحة ويب وتحويلها لنص مقروء",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "extract_prompt": {"type": "string", "description": "ما الذي تريد استخراجه"},
                },
                "required": ["url"],
            },
            fn=self._web_fetch,
            requires_permission=True,
        ))

        self._add(Tool(
            name="WebSearch",
            description="البحث على الإنترنت باستخدام DuckDuckGo",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "max_results": {"type": "integer", "default": 5},
                },
                "required": ["query"],
            },
            fn=self._web_search,
            requires_permission=True,
        ))

        # ── Git ──────────────────────────────────────────────────────────────

        self._add(Tool(
            name="GitStatus",
            description="عرض حالة المستودع الحالي (git status)",
            parameters={
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "مسار المستودع (اختياري)"},
                },
                "required": [],
            },
            fn=self._git_status,
        ))

        self._add(Tool(
            name="GitClone",
            description="استنساخ مستودع من GitHub أو أي مصدر git",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string"},
                    "destination": {"type": "string", "description": "مجلد الوجهة"},
                    "branch": {"type": "string", "description": "الفرع (اختياري)"},
                    "depth": {"type": "integer", "description": "عمق الاستنساخ (1 = سطحي)"},
                },
                "required": ["url"],
            },
            fn=self._git_clone,
            requires_permission=True,
        ))

        self._add(Tool(
            name="GitCommit",
            description="إنشاء commit جديد",
            parameters={
                "type": "object",
                "properties": {
                    "message": {"type": "string"},
                    "repo_path": {"type": "string"},
                    "add_all": {"type": "boolean", "default": True},
                },
                "required": ["message"],
            },
            fn=self._git_commit,
            requires_permission=True,
        ))

        self._add(Tool(
            name="GitPush",
            description=("رفع التغييرات إلى GitHub فعلياً. يعمل تلقائياً على المستودع "
                         "المتصل/المستنسَخ الحالي ويستخدم التوكن المتصل للمصادقة — "
                         "لا يلزم تمرير مسار أو فرع. استخدمه بعد GitCommit."),
            parameters={
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "اختياري"},
                    "branch": {"type": "string", "description": "اختياري (افتراضي: فرع المستودع)"},
                    "remote": {"type": "string", "default": "origin"},
                },
                "required": [],
            },
            fn=self._git_push,
            requires_permission=True,
        ))

        # ── Python/Code ──────────────────────────────────────────────────────

        self._add(Tool(
            name="PipInstall",
            description="تثبيت حزمة Python",
            parameters={
                "type": "object",
                "properties": {
                    "package": {"type": "string"},
                    "break_system": {"type": "boolean", "default": True, "description": "للـ Termux"},
                },
                "required": ["package"],
            },
            fn=self._pip_install,
            requires_permission=True,
        ))

        self._add(Tool(
            name="PythonRun",
            description="تشغيل سكربت Python",
            parameters={
                "type": "object",
                "properties": {
                    "script": {"type": "string", "description": "كود Python للتشغيل"},
                    "file_path": {"type": "string", "description": "أو مسار ملف .py"},
                    "timeout": {"type": "integer", "default": 60},
                },
                "required": [],
            },
            fn=self._python_run,
            requires_permission=True,
        ))

        # ── النظام ──────────────────────────────────────────────────────────

        self._add(Tool(
            name="EnvSet",
            description="تعيين متغير بيئة في الجلسة الحالية",
            parameters={
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "value": {"type": "string"},
                },
                "required": ["key", "value"],
            },
            fn=self._env_set,
        ))

        self._add(Tool(
            name="EnvGet",
            description="قراءة قيمة متغير بيئة",
            parameters={
                "type": "object",
                "properties": {"key": {"type": "string"}},
                "required": ["key"],
            },
            fn=self._env_get,
        ))

        self._add(Tool(
            name="DirectoryList",
            description="عرض محتويات مجلد",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "default": "."},
                    "show_hidden": {"type": "boolean", "default": False},
                    "depth": {"type": "integer", "default": 2},
                },
                "required": [],
            },
            fn=self._dir_list,
        ))

        self._add(Tool(
            name="AskUser",
            description="طرح سؤال على المستخدم والانتظار لإجابته",
            parameters={
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "options": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["question"],
            },
            fn=self._ask_user,
        ))

        # ── تعديل متعدد الكتل في ملف واحد ────────────────────────────────────
        self._add(Tool(
            name="MultiEdit",
            description="تطبيق عدة تعديلات (استبدالات) متتابعة على ملف واحد بعملية واحدة",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "edits": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "old_string": {"type": "string"},
                                "new_string": {"type": "string"},
                                "replace_all": {"type": "boolean", "default": False},
                            },
                            "required": ["old_string", "new_string"],
                        },
                    },
                },
                "required": ["path", "edits"],
            },
            fn=self._multi_edit,
            requires_permission=True,
        ))

        # ── وكيل فرعي (subagent) ─────────────────────────────────────────────
        self._add(Tool(
            name="Agent",
            description=("تشغيل وكيل فرعي مستقل لمهمة فرعية محددة (بحث/تحليل/تنفيذ) "
                         "ثم إرجاع خلاصته. مفيد لعزل المهام الكبيرة."),
            parameters={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "المهمة الفرعية"},
                    "mode": {"type": "string",
                             "enum": ["main", "coding", "project", "security",
                                      "autonomous", "analysis"],
                             "default": "main"},
                },
                "required": ["prompt"],
            },
            fn=self._agent,
        ))

        # ── مهام مجدولة (crontab) ────────────────────────────────────────────
        self._add(Tool(
            name="CronCreate",
            description="جدولة مهمة WeaverCode دورية عبر crontab (Linux/Termux)",
            parameters={
                "type": "object",
                "properties": {
                    "schedule": {"type": "string",
                                 "description": "تعبير cron مثل '0 9 * * *' (كل يوم 9 صباحاً)"},
                    "task": {"type": "string", "description": "المهمة التي ستُمرَّر لـ weaver.py"},
                    "name": {"type": "string", "description": "اسم مميّز للمهمة"},
                },
                "required": ["schedule", "task", "name"],
            },
            fn=self._cron_create,
            requires_permission=True,
        ))
        self._add(Tool(
            name="CronList",
            description="عرض مهام WeaverCode المجدولة",
            parameters={"type": "object", "properties": {}},
            fn=self._cron_list,
        ))
        self._add(Tool(
            name="CronDelete",
            description="حذف مهمة WeaverCode مجدولة بالاسم",
            parameters={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
            fn=self._cron_delete,
            requires_permission=True,
        ))

        # ── مراقبة (تشغيل أمر حتى ينجح أو تنتهي المهلة) ──────────────────────
        self._add(Tool(
            name="Monitor",
            description=("تشغيل أمر بشكل متكرر حتى ينجح (رمز خروج 0) أو تنتهي المهلة. "
                         "مفيد لانتظار خدمة أو شرط."),
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "timeout": {"type": "integer", "default": 60},
                    "interval": {"type": "integer", "default": 3},
                },
                "required": ["command"],
            },
            fn=self._monitor,
            requires_permission=True,
        ))

        # ── تشخيص لغوي (LSP-lite) ────────────────────────────────────────────
        self._add(Tool(
            name="LSP",
            description=("فحص أخطاء الصياغة/التشخيص لملف كود (Python/JS/JSON) "
                         "وإرجاع الأخطاء إن وُجدت."),
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            fn=self._lsp,
        ))

        # ── وضع التخطيط ──────────────────────────────────────────────────────
        self._add(Tool(
            name="EnterPlanMode",
            description="الدخول في وضع التخطيط: لا تُنفَّذ أي أدوات تعديل حتى تعتمد الخطة",
            parameters={"type": "object", "properties": {}},
            fn=lambda: "✅ دخلت وضع التخطيط. خطّط أولاً ثم استدعِ ExitPlanMode.",
        ))
        self._add(Tool(
            name="ExitPlanMode",
            description=("تقديم الخطة النهائية للمستخدم لاعتمادها قبل التنفيذ. "
                         "مرّر الخطة في 'plan'."),
            parameters={
                "type": "object",
                "properties": {"plan": {"type": "string", "description": "الخطة المقترحة"}},
                "required": ["plan"],
            },
            fn=lambda plan="": "PLAN_SUBMITTED",  # يعالجها المحرّك خصيصاً
        ))

        # ── أدوات GitHub CLI ────────────────────────────────────────────

        self._add(Tool(
            name="GitHubCreateRepo",
            description="إنشاء مستودع جديد على GitHub عبر gh CLI",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "اسم المستودع"},
                    "description": {"type": "string", "default": ""},
                    "private": {"type": "boolean", "default": False},
                },
                "required": ["name"],
            },
            fn=self._gh_create_repo,
            requires_permission=True,
        ))

        self._add(Tool(
            name="GitHubListRepos",
            description="عرض مستودعات المستخدم على GitHub",
            parameters={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 10},
                },
                "required": [],
            },
            fn=self._gh_list_repos,
        ))

        self._add(Tool(
            name="GitHubCreateIssue",
            description="إنشاء Issue جديد في مستودع على GitHub",
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "body": {"type": "string", "default": ""},
                    "repo": {"type": "string", "description": "owner/repo أو المستودع الحالي"},
                },
                "required": ["title"],
            },
            fn=self._gh_create_issue,
            requires_permission=True,
        ))

        self._add(Tool(
            name="GitHubStatus",
            description="فحص حالة اتصال GitHub وبيانات الحساب المرتبط",
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            },
            fn=self._gh_status,
        ))

        # ── مهارات (Skills) ─────────────────────────────────────────────

        self._add(Tool(
            name="Skill",
            description="تحميل مهارة (skill) وإضافة محتواها كسياق للمحادثة الحالية",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string",
                             "description": "اسم الـ skill (مثل: frontend-design)"},
                    "list": {"type": "boolean", "default": False,
                             "description": "عرض قائمة بكل الـ skills المتاحة"},
                },
                "required": [],
            },
            fn=self._skill_load,
        ))

        # ── قائمة المهام الحيّة (TodoWrite) ──────────────────────────────────

        self._add(Tool(
            name="TodoWrite",
            description=("إدارة قائمة مهام حيّة للمهمة الحالية. مرّر قائمة كاملة "
                         "من العناصر، كل عنصر {content, status, activeForm}. "
                         "الحالات: pending | in_progress | completed. "
                         "استخدمه باعتدال: مرة عند بداية مهمة كبيرة ومرة عند "
                         "الاكتمال — لا تحدّثه بعد كل خطوة صغيرة."),
            parameters={
                "type": "object",
                "properties": {
                    "todos": {
                        "type": "array",
                        "description": "القائمة الكاملة للمهام (تستبدل السابقة)",
                        "items": {
                            "type": "object",
                            "properties": {
                                "content": {"type": "string",
                                            "description": "وصف المهمة"},
                                "status": {"type": "string",
                                           "enum": ["pending", "in_progress",
                                                    "completed"]},
                                "activeForm": {"type": "string",
                                               "description": "الصيغة الجارية للعرض"},
                            },
                            "required": ["content", "status"],
                        },
                    },
                },
                "required": ["todos"],
            },
            fn=self._todo_write,
        ))

        # ── تعديل خلايا دفتر Jupyter (NotebookEdit) ──────────────────────────

        self._add(Tool(
            name="NotebookEdit",
            description=("تعديل خلية في دفتر Jupyter (.ipynb). الأوضاع: "
                         "replace (استبدال المصدر) | insert (إدراج خلية جديدة) | "
                         "delete (حذف الخلية)."),
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "مسار ملف .ipynb"},
                    "cell_id": {"type": "string",
                                "description": "معرّف الخلية أو رقمها (0-based)"},
                    "new_source": {"type": "string",
                                   "description": "المصدر الجديد للخلية"},
                    "cell_type": {"type": "string",
                                  "enum": ["code", "markdown"],
                                  "description": "نوع الخلية عند الإدراج"},
                    "edit_mode": {"type": "string",
                                  "enum": ["replace", "insert", "delete"],
                                  "default": "replace"},
                },
                "required": ["path"],
            },
            fn=self._notebook_edit,
            requires_permission=True,
        ))

    # ── تنفيذ الأدوات ────────────────────────────────────────────────────────

    def _add(self, tool: Tool):
        self._tools[tool.name] = tool

    def register_dynamic(self, name: str, description: str, parameters: Dict,
                         fn: Callable, requires_permission: bool = True) -> None:
        """تسجيل أداة خارجية ديناميكياً (تُستخدم لأدوات MCP)."""
        self._add(Tool(name=name, description=description, parameters=parameters,
                       fn=fn, requires_permission=requires_permission))

    def names(self) -> List[str]:
        return list(self._tools.keys())

    def get_schema(self, compact: Optional[bool] = None) -> List[Dict]:
        """مخطط الأدوات. compact=True يختصر الأوصاف (~نصف التوكنات).
        الافتراضي None → يقرأ WEAVER_COMPACT_TOOLS (0/1)."""
        if compact is None:
            compact = os.environ.get(
                "WEAVER_COMPACT_TOOLS", "0").strip().lower() in ("1", "true", "yes", "on")
        return [t.to_schema(compact=compact) for t in self._tools.values()]

    def get_tool(self, name: str) -> Optional[Tool]:
        """إرجاع تعريف الأداة (أو None إن لم توجد)"""
        return self._tools.get(name)

    def requires_permission(self, name: str) -> bool:
        """هل تحتاج الأداة إذناً قبل التنفيذ؟ (الأدوات المجهولة تُعتبر خطرة)"""
        tool = self._tools.get(name)
        if tool is None:
            return True
        return tool.requires_permission

    async def execute(self, name: str, args: Dict[str, Any]) -> Any:
        if name not in self._tools:
            return f"خطأ: الأداة '{name}' غير موجودة"
        tool = self._tools[name]
        result = tool.fn(**args)
        if asyncio.iscoroutine(result):
            return await result
        return result

    # ── مهام مجدولة عبر crontab ───────────────────────────────────────────────

    _CRON_TAG = "# WEAVER_CRON"

    def _cron_create(self, schedule: str, task: str, name: str) -> str:
        weaver = str(Path(self.work_dir) / "weaver.py")
        safe_task = task.replace('"', r'\"')
        line = f'{schedule} cd {self.work_dir} && python3 {weaver} --yes "{safe_task}"  {self._CRON_TAG} {name}'
        try:
            current = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
            existing = current.stdout if current.returncode == 0 else ""
            lines = [l for l in existing.splitlines()
                     if not l.strip().endswith(f"{self._CRON_TAG} {name}")]
            lines.append(line)
            proc = subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n", text=True,
                                  capture_output=True)
            if proc.returncode != 0:
                return f"تعذّر ضبط crontab: {proc.stderr.strip()}"
            return f"✅ جُدولت المهمة '{name}' ({schedule})."
        except FileNotFoundError:
            return "خطأ: crontab غير متوفر على هذا النظام."
        except Exception as e:
            return f"خطأ: {e}"

    def _cron_list(self) -> str:
        try:
            current = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
            if current.returncode != 0:
                return "لا توجد مهام مجدولة."
            jobs = [l for l in current.stdout.splitlines() if self._CRON_TAG in l]
            return "\n".join(jobs) if jobs else "لا توجد مهام WeaverCode مجدولة."
        except FileNotFoundError:
            return "خطأ: crontab غير متوفر."
        except Exception as e:
            return f"خطأ: {e}"

    def _cron_delete(self, name: str) -> str:
        try:
            current = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
            if current.returncode != 0:
                return "لا توجد مهام."
            lines = current.stdout.splitlines()
            kept = [l for l in lines if not l.strip().endswith(f"{self._CRON_TAG} {name}")]
            if len(kept) == len(lines):
                return f"لم يُعثر على مهمة باسم '{name}'."
            subprocess.run(["crontab", "-"], input="\n".join(kept) + "\n", text=True)
            return f"✅ حُذفت المهمة '{name}'."
        except FileNotFoundError:
            return "خطأ: crontab غير متوفر."
        except Exception as e:
            return f"خطأ: {e}"

    # ── مراقبة: تشغيل أمر حتى ينجح أو تنتهي المهلة ─────────────────────────────

    def _monitor(self, command: str, timeout: int = 60, interval: int = 3) -> str:
        danger = self._is_dangerous_command(command)
        if danger:
            return f"🛑 رُفض أمر المراقبة لخطورته (النمط: {danger})."
        import time as _time
        start = _time.time()
        attempts = 0
        last = ""
        while _time.time() - start < timeout:
            attempts += 1
            try:
                r = subprocess.run(command, shell=True, capture_output=True, text=True,
                                   timeout=min(timeout, 30), cwd=self.work_dir)
                last = (r.stdout or "") + (r.stderr or "")
                if r.returncode == 0:
                    return f"✅ نجح بعد {attempts} محاولة:\n{last[:2000]}"
            except subprocess.TimeoutExpired:
                last = "(انتهت مهلة المحاولة)"
            _time.sleep(interval)
        return f"⏱️ لم ينجح خلال {timeout}ث ({attempts} محاولة). آخر إخراج:\n{last[:2000]}"

    # ── تشخيص لغوي بسيط (LSP-lite) ────────────────────────────────────────────

    def _lsp(self, path: str) -> str:
        p = Path(path)
        if not p.exists():
            return f"الملف غير موجود: {path}"
        ext = p.suffix.lower()
        try:
            if ext == ".py":
                r = subprocess.run(["python3", "-m", "py_compile", str(p)],
                                   capture_output=True, text=True, timeout=30)
                return "✅ لا أخطاء صياغة." if r.returncode == 0 else f"❌ أخطاء:\n{r.stderr.strip()}"
            if ext in (".js", ".mjs", ".cjs"):
                r = subprocess.run(["node", "--check", str(p)],
                                   capture_output=True, text=True, timeout=30)
                return "✅ لا أخطاء صياغة." if r.returncode == 0 else f"❌ أخطاء:\n{r.stderr.strip()}"
            if ext == ".json":
                try:
                    json.loads(p.read_text(encoding="utf-8"))
                    return "✅ JSON صالح."
                except json.JSONDecodeError as e:
                    return f"❌ JSON غير صالح: {e}"
            return f"لا يوجد فاحص متاح للامتداد '{ext}'. المدعوم: .py .js .json"
        except FileNotFoundError as e:
            return f"الفاحص غير مثبّت: {e}"
        except Exception as e:
            return f"خطأ: {e}"

    # ── تنفيذ كل أداة ────────────────────────────────────────────────────────

    def _read(self, path: str, offset: int = 0, limit: Optional[int] = None) -> str:
        try:
            p = self._resolve(path)
            if not p.exists():
                return f"الملف غير موجود: {path}"
            # وسائط (صورة/PDF): تُرسَل للنموذج الرؤيوي على مستوى الرسالة تلقائياً.
            # هنا نُرجع وصفاً مختصراً + تأكيداً أنها مرئية للنموذج.
            try:
                from core.multimodal import is_multimodal, describe
                if is_multimodal(str(p)):
                    return (describe(str(p))
                            + "\n\n✅ هذا الملف مُرسَل للنموذج كمحتوى مرئي — "
                              "يمكنك تحليله/وصفه مباشرةً في ردّك.")
            except Exception:
                pass
            # قراءة ذكية لكل الأنواع (نص/CSV/zip/tar/office/ثنائي)
            try:
                from core.filetypes import read_any
                return read_any(str(p), offset or 0, limit)
            except Exception:
                pass
            # احتياط: نص خام
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
            if offset:
                lines = lines[offset:]
            if limit:
                lines = lines[:limit]
            return "\n".join(f"{i+offset+1}\t{l}" for i, l in enumerate(lines))
        except Exception as e:
            return f"خطأ في قراءة {path}: {e}"

    def _write_binary(self, path: str, data_base64: str) -> str:
        """إنشاء ملف ثنائي من base64 (صور/PDF/أرشيفات/أي نوع)."""
        try:
            import base64 as _b64
            raw = _b64.b64decode(data_base64)
            p = self._resolve(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(raw)
            sp = str(p)
            if sp not in self._created_files:
                self._created_files.append(sp)
            return (f"✅ تم إنشاء ملف ثنائي {p} ({len(raw)} بايت) — "
                    f"متاح في شاشة «الملفات» للتنزيل.")
        except Exception as e:
            return f"خطأ في كتابة الملف الثنائي: {e}"

    def _extract_archive(self, path: str, dest: Optional[str] = None) -> str:
        """فكّ ضغط أرشيف (zip/tar) إلى مجلد."""
        try:
            from core.filetypes import extract_archive
            src = self._resolve(path)
            out = self._resolve(dest) if dest else src.parent / (src.stem + "_extracted")
            result = extract_archive(str(src), str(out))
            try:
                for f in Path(out).rglob("*"):
                    if f.is_file():
                        sp = str(f)
                        if sp not in self._created_files:
                            self._created_files.append(sp)
            except Exception:
                pass
            return result
        except Exception as e:
            return f"خطأ في فكّ الأرشيف: {e}"

    def _diff_and_log(self, path, old: str, new: str, is_new: bool) -> str:
        """يحسب +/- عبر difflib ويسجّل العملية في سجل العمليات. يُرجع سطر الإحصاء."""
        try:
            import difflib
            diff = list(difflib.unified_diff(
                old.splitlines(), new.splitlines(), lineterm=""))
            added = sum(1 for l in diff if l.startswith("+") and not l.startswith("+++"))
            removed = sum(1 for l in diff if l.startswith("-") and not l.startswith("---"))
            from core.oplog import log_operation, stat_label
            entry = log_operation(str(path), "created" if is_new else "edited",
                                  added, removed)
            return stat_label(entry)
        except Exception:
            return ""

    def _write(self, path: str, content: str) -> str:
        try:
            p = self._resolve(path)
            is_new = not p.exists()
            old = "" if is_new else p.read_text(encoding="utf-8", errors="replace")
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            # تتبّع الملف المُنشأ (لنسخه لمجلد التنزيلات لاحقاً)
            sp = str(p)
            if sp not in self._created_files:
                self._created_files.append(sp)
            stat = self._diff_and_log(p, old, content, is_new)
            return (f"✅ {stat or f'تم إنشاء/تحديث {p.name}'} — "
                    f"متاح في شاشة «الملفات» للتنزيل. ({p})")
        except Exception as e:
            return f"خطأ في الكتابة: {e}"

    def _edit(self, path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
        try:
            p = self._resolve(path)
            content = p.read_text(encoding="utf-8")
            if old_string not in content:
                return f"لم يُعثر على النص المطلوب في {path}"
            count = content.count(old_string)
            if count > 1 and not replace_all:
                return f"النص موجود {count} مرات. استخدم replace_all=true أو أضف سياقاً أكثر."
            new_content = content.replace(old_string, new_string)
            p.write_text(new_content, encoding="utf-8")
            stat = self._diff_and_log(p, content, new_content, False)
            return f"✅ {stat or f'تم التعديل في {p.name}'}"
        except Exception as e:
            return f"خطأ في التعديل: {e}"

    def _multi_edit(self, path: str, edits: List[Dict[str, Any]]) -> str:
        """تطبيق عدة استبدالات على ملف واحد بشكل ذرّي (كلها أو لا شيء)."""
        try:
            p = self._resolve(path)
            content = p.read_text(encoding="utf-8")
        except Exception as e:
            return f"خطأ في قراءة {path}: {e}"
        original = content
        applied = 0
        for i, ed in enumerate(edits, 1):
            old = ed.get("old_string", "")
            new = ed.get("new_string", "")
            replace_all = ed.get("replace_all", False)
            if old not in content:
                return f"التعديل رقم {i} فشل: لم يُعثر على النص المطلوب (لم يُحفظ أي تغيير)."
            count = content.count(old)
            if count > 1 and not replace_all:
                return (f"التعديل رقم {i}: النص موجود {count} مرات. "
                        f"استخدم replace_all=true أو أضف سياقاً (لم يُحفظ أي تغيير).")
            content = content.replace(old, new)
            applied += 1
        try:
            p.write_text(content, encoding="utf-8")
        except Exception as e:
            return f"خطأ في الكتابة: {e}"
        stat = self._diff_and_log(p, original, content, False)
        return f"✅ طُبّقت {applied} تعديلات — {stat or p.name}"

    # ── قائمة المهام الحيّة (TodoWrite) ──────────────────────────────────────

    _TODO_MARK = {"pending": "☐", "in_progress": "▶", "completed": "☑"}

    def _todo_write(self, todos: List[Dict[str, Any]]) -> str:
        """يستبدل قائمة المهام الحالية ويُرجع عرضاً مُنسّقاً لها."""
        if not isinstance(todos, list):
            return "خطأ: يجب أن تكون todos قائمة."
        cleaned: List[Dict[str, Any]] = []
        for t in todos:
            if not isinstance(t, dict):
                continue
            content = str(t.get("content", "")).strip()
            if not content:
                continue
            status = t.get("status", "pending")
            if status not in self._TODO_MARK:
                status = "pending"
            cleaned.append({
                "content": content,
                "status": status,
                "activeForm": str(t.get("activeForm", "")).strip(),
            })
        self._todos = cleaned
        if not cleaned:
            return "📋 قائمة المهام فارغة."
        lines = ["📋 قائمة المهام:"]
        done = 0
        for t in cleaned:
            mark = self._TODO_MARK[t["status"]]
            label = t["content"]
            if t["status"] == "in_progress" and t["activeForm"]:
                label = t["activeForm"]
            lines.append(f"  {mark} {label}")
            if t["status"] == "completed":
                done += 1
        lines.append(f"  ({done}/{len(cleaned)} مكتملة)")
        return "\n".join(lines)

    def get_todos(self) -> List[Dict[str, Any]]:
        """إرجاع نسخة من قائمة المهام الحالية (للواجهات)."""
        return list(self._todos)

    # ── تعديل دفتر Jupyter (NotebookEdit) ────────────────────────────────────

    def _notebook_edit(self, path: str, cell_id: Optional[str] = None,
                       new_source: str = "", cell_type: Optional[str] = None,
                       edit_mode: str = "replace") -> str:
        """تعديل/إدراج/حذف خلية في دفتر Jupyter (.ipynb)."""
        p = Path(path)
        if not p.exists():
            return f"الدفتر غير موجود: {path}"
        try:
            nb = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            return f"خطأ في قراءة الدفتر (JSON غير صالح؟): {e}"
        cells = nb.setdefault("cells", [])

        def _resolve_index() -> Optional[int]:
            if cell_id is None or cell_id == "":
                return None
            # مطابقة على المعرّف id أولاً
            for i, c in enumerate(cells):
                if str(c.get("id")) == str(cell_id):
                    return i
            # ثم كرقم فهرس
            try:
                idx = int(cell_id)
                if -len(cells) <= idx < len(cells):
                    return idx
            except (ValueError, TypeError):
                pass
            return None

        # مصدر الخلية يُخزّن كقائمة أسطر في صيغة nbformat
        src_lines = new_source.splitlines(keepends=True) if new_source else []

        if edit_mode == "insert":
            new_cell: Dict[str, Any] = {
                "cell_type": cell_type or "code",
                "metadata": {},
                "source": src_lines,
            }
            if (cell_type or "code") == "code":
                new_cell["outputs"] = []
                new_cell["execution_count"] = None
            idx = _resolve_index()
            pos = (idx + 1) if idx is not None else len(cells)
            cells.insert(pos, new_cell)
            action = f"أُدرجت خلية جديدة عند الموضع {pos}"

        elif edit_mode == "delete":
            idx = _resolve_index()
            if idx is None:
                return "خطأ: يجب تحديد cell_id صالح للحذف."
            cells.pop(idx)
            action = f"حُذفت الخلية {cell_id}"

        else:  # replace
            idx = _resolve_index()
            if idx is None:
                return "خطأ: يجب تحديد cell_id صالح للاستبدال."
            cells[idx]["source"] = src_lines
            if cell_type:
                cells[idx]["cell_type"] = cell_type
            if cells[idx].get("cell_type") == "code":
                cells[idx].setdefault("outputs", [])
                cells[idx].setdefault("execution_count", None)
            action = f"استُبدل مصدر الخلية {cell_id}"

        try:
            p.write_text(json.dumps(nb, ensure_ascii=False, indent=1),
                         encoding="utf-8")
        except Exception as e:
            return f"خطأ في كتابة الدفتر: {e}"
        return f"✅ {action} في {path} ({len(cells)} خلية إجمالاً)."

    async def _agent(self, prompt: str, mode: str = "main") -> str:
        """تشغيل وكيل فرعي عبر agent_runner الذي يضبطه QueryEngine."""
        if self.agent_runner is None:
            return "خطأ: الوكلاء الفرعيون غير مفعّلين في هذا السياق."
        try:
            result = self.agent_runner(prompt, mode)
            if asyncio.iscoroutine(result):
                result = await result
            return str(result)
        except Exception as e:
            return f"خطأ في الوكيل الفرعي: {e}"

    def add_dir(self, path: str) -> str:
        """يضيف مجلد عمل إضافياً (multi-workspace). يُرجع رسالة حالة."""
        try:
            p = Path(path).expanduser().resolve()
        except Exception as e:
            return f"مسار غير صالح: {e}"
        if not p.exists() or not p.is_dir():
            return f"المجلد غير موجود: {path}"
        sp = str(p)
        if sp == str(Path(self.work_dir).resolve()) or sp in self.extra_dirs:
            return f"المجلد مُضاف مسبقاً: {sp}"
        self.extra_dirs.append(sp)
        return f"✅ أُضيف مجلد العمل: {sp}"

    def workspace_dirs(self) -> List[str]:
        """كل مجلدات العمل: الأساسي ثم الإضافية."""
        return [str(Path(self.work_dir).resolve())] + list(self.extra_dirs)

    def _search_roots(self, base_dir: Optional[str] = None) -> List[str]:
        """المجلدات التي يُجرى البحث فيها: base_dir المحدّد وإلا كل مساحات العمل."""
        if base_dir:
            return [base_dir]
        return self.workspace_dirs()

    def _glob(self, pattern: str, base_dir: Optional[str] = None) -> str:
        try:
            roots = self._search_roots(base_dir)
            files: List[str] = []
            for base in roots:
                files.extend(_glob.glob(os.path.join(base, pattern),
                                        recursive=True))
            # إزالة التكرار مع الحفاظ على الأحدث أولاً
            files = list(dict.fromkeys(files))
            files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
            if not files:
                return "لا توجد ملفات تطابق النمط"
            return "\n".join(files[:100])
        except Exception as e:
            return f"خطأ: {e}"

    def _grep(self, pattern: str, path: Optional[str] = None, file_glob: Optional[str] = None,
               output_mode: str = "content", ignore_case: bool = False) -> str:
        try:
            flags = re.IGNORECASE if ignore_case else 0
            results = []
            if path and os.path.isfile(path):
                files = [path]
            else:
                # ابحث في المسار المحدّد وإلا في كل مساحات العمل (multi-workspace)
                search_paths = [path] if path else self.workspace_dirs()
                files = []
                for sp in search_paths:
                    file_pattern = os.path.join(sp, f"**/{file_glob or '*'}")
                    files.extend(_glob.glob(file_pattern, recursive=True))
                files = [f for f in dict.fromkeys(files) if os.path.isfile(f)]

            for fp in files:
                try:
                    content = Path(fp).read_text(encoding="utf-8", errors="replace")
                    if output_mode == "files_with_matches":
                        if re.search(pattern, content, flags):
                            results.append(fp)
                    elif output_mode == "count":
                        count = len(re.findall(pattern, content, flags))
                        if count:
                            results.append(f"{fp}: {count}")
                    else:
                        for i, line in enumerate(content.splitlines(), 1):
                            if re.search(pattern, line, flags):
                                results.append(f"{fp}:{i}: {line}")
                except Exception:
                    continue

            return "\n".join(results[:500]) if results else "لا توجد نتائج"
        except Exception as e:
            return f"خطأ: {e}"

    # أنماط أوامر كارثية تُرفض دائماً (حتى لو وافق المستخدم بالخطأ)
    _BASH_DENY = [
        r"\brm\s+-rf?\s+(?:--no-preserve-root\s+)?/(?:\s|$|\*)",  # rm -rf /
        r":\(\)\s*\{\s*:\|:&\s*\}\s*;\s*:",                      # fork bomb
        r"\bmkfs\.",                                              # تهيئة قرص
        r"\bdd\b[^\n]*\bof=/dev/(?:sd|nvme|mmcblk|disk)",        # dd على قرص
        r">\s*/dev/(?:sd|nvme|mmcblk)",                          # كتابة على قرص
        r"\bchmod\s+-R?\s*777\s+/(?:\s|$)",                      # chmod 777 /
        r"\b(?:curl|wget)\b[^\n|]*\|\s*(?:sudo\s+)?(?:bash|sh)\b",  # تنزيل ثم تنفيذ
    ]

    def _is_dangerous_command(self, command: str) -> Optional[str]:
        """يُرجع سبب الرفض إن كان الأمر كارثياً، وإلا None."""
        for pat in self._BASH_DENY:
            if re.search(pat, command):
                return pat
        return None

    def _bash(self, command: str, timeout: int = 120,
              work_dir: Optional[str] = None,
              run_in_background: bool = False) -> str:
        # ── حماية (sandbox خفيف): رفض الأوامر الكارثية دائماً ────────────────
        danger = self._is_dangerous_command(command)
        if danger:
            return ("🛑 رُفض الأمر لأنه يطابق نمطاً خطيراً جداً "
                    f"(قد يُتلف النظام أو البيانات). النمط: {danger}\n"
                    "إن كنت متأكداً فنفّذه يدوياً خارج WeaverCode.")
        # في وضع sandbox: امنع sudo وحصر التنفيذ داخل مجلد العمل
        if os.environ.get("WEAVER_BASH_SANDBOX", "0").strip().lower() in ("1", "true", "yes", "on"):
            if re.search(r"\bsudo\b", command):
                return "🛑 وضع sandbox: أوامر sudo ممنوعة."

        # ── تشغيل في الخلفية: يُرجع shell_id فوراً ─────────────────────────────
        if run_in_background:
            return self._bash_background(command, work_dir or self.work_dir)

        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True,
                timeout=timeout, cwd=work_dir or self.work_dir,
            )
            output = result.stdout
            if result.stderr:
                output += f"\n[STDERR]: {result.stderr}"
            if result.returncode != 0:
                output += f"\n[EXIT CODE]: {result.returncode}"
            return output[:30000] if output else "(لا يوجد إخراج)"
        except subprocess.TimeoutExpired:
            return f"انتهت المهلة ({timeout}ث)"
        except Exception as e:
            return f"خطأ: {e}"

    # ── تشغيل أوامر bash في الخلفية + متابعتها ────────────────────────────────

    def _bash_background(self, command: str, cwd: str) -> str:
        """يُطلق أمراً في الخلفية ويُرجع shell_id لمتابعته."""
        import tempfile
        self._bg_counter += 1
        shell_id = f"bash_{self._bg_counter}"
        try:
            out_f = tempfile.NamedTemporaryFile(
                mode="w+", suffix=".out", prefix=f"weaver_{shell_id}_",
                delete=False)
            out_path = out_f.name
            out_f.close()
            fh = open(out_path, "wb")
            proc = subprocess.Popen(
                command, shell=True, stdout=fh, stderr=subprocess.STDOUT,
                cwd=cwd,
            )
        except Exception as e:
            return f"خطأ في تشغيل الخلفية: {e}"
        self._bg_shells[shell_id] = {
            "proc": proc,
            "command": command,
            "out_path": out_path,
            "fh": fh,
            "read_pos": 0,
        }
        return (f"🚀 يعمل في الخلفية: {shell_id}\n"
                f"الأمر: {command[:120]}\n"
                f"استخدم BashOutput(shell_id='{shell_id}') لقراءة الإخراج، "
                f"و KillShell لإنهائه.")

    def _bash_output(self, shell_id: str) -> str:
        """يقرأ الإخراج الجديد من shell خلفي منذ آخر قراءة + حالته."""
        info = self._bg_shells.get(shell_id)
        if not info:
            return f"لا يوجد shell خلفي بالمعرّف '{shell_id}'."
        proc = info["proc"]
        # اقرأ الجديد من ملف الإخراج
        new_output = ""
        try:
            with open(info["out_path"], "r", encoding="utf-8",
                      errors="replace") as rf:
                rf.seek(info["read_pos"])
                new_output = rf.read()
                info["read_pos"] = rf.tell()
        except Exception as e:
            new_output = f"(تعذّر قراءة الإخراج: {e})"
        rc = proc.poll()
        if rc is None:
            status = "▶ لا يزال يعمل"
        else:
            status = f"✅ انتهى (رمز الخروج: {rc})"
            # تنظيف مقبض الملف عند الانتهاء
            try:
                info["fh"].close()
            except Exception:
                pass
        body = new_output.strip() or "(لا إخراج جديد)"
        return f"[{shell_id}] {status}\n{body[:30000]}"

    def _kill_shell(self, shell_id: str) -> str:
        """ينهي shell خلفياً ويحرّر موارده."""
        info = self._bg_shells.get(shell_id)
        if not info:
            return f"لا يوجد shell خلفي بالمعرّف '{shell_id}'."
        proc = info["proc"]
        if proc.poll() is None:
            try:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
            except Exception as e:
                return f"تعذّر إنهاء {shell_id}: {e}"
        try:
            info["fh"].close()
        except Exception:
            pass
        try:
            os.unlink(info["out_path"])
        except Exception:
            pass
        del self._bg_shells[shell_id]
        return f"🛑 أُنهي الـ shell الخلفي '{shell_id}'."

    def list_background_shells(self) -> List[Dict[str, Any]]:
        """قائمة الـ shells الخلفية النشطة (للواجهات)."""
        out = []
        for sid, info in self._bg_shells.items():
            rc = info["proc"].poll()
            out.append({
                "shell_id": sid,
                "command": info["command"],
                "running": rc is None,
                "exit_code": rc,
            })
        return out

    def _memory_save(self, key: str, value: str, tags: Optional[List[str]] = None) -> str:
        # يستخدم MemoryStore عبر QueryEngine — هنا نحفظ في ملف
        mem_file = Path.home() / ".weaver" / "memory.json"
        mem_file.parent.mkdir(exist_ok=True)
        try:
            data = json.loads(mem_file.read_text()) if mem_file.exists() else {}
        except Exception:
            data = {}
        data[key] = {"value": value, "tags": tags or []}
        mem_file.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        return f"✅ تم حفظ '{key}' في الذاكرة"

    def _memory_search(self, query: str, limit: int = 5) -> str:
        mem_file = Path.home() / ".weaver" / "memory.json"
        if not mem_file.exists():
            return "الذاكرة فارغة"
        try:
            data = json.loads(mem_file.read_text())
            results = []
            for key, val in data.items():
                if query.lower() in key.lower() or query.lower() in str(val["value"]).lower():
                    results.append(f"[{key}]: {val['value'][:200]}")
            return "\n".join(results[:limit]) if results else "لا توجد نتائج"
        except Exception as e:
            return f"خطأ: {e}"

    def _memory_delete(self, key: str) -> str:
        mem_file = Path.home() / ".weaver" / "memory.json"
        if not mem_file.exists():
            return "الذاكرة فارغة"
        data = json.loads(mem_file.read_text())
        if key in data:
            del data[key]
            mem_file.write_text(json.dumps(data, ensure_ascii=False, indent=2))
            return f"✅ تم حذف '{key}'"
        return f"المفتاح '{key}' غير موجود"

    def _memory_list(self) -> str:
        mem_file = Path.home() / ".weaver" / "memory.json"
        if not mem_file.exists():
            return "الذاكرة فارغة"
        data = json.loads(mem_file.read_text())
        return "\n".join(f"• {k}" for k in data.keys()) if data else "الذاكرة فارغة"

    def _task_create(self, title: str, description: str = "", priority: str = "medium") -> str:
        tasks_file = Path.home() / ".weaver" / "tasks.json"
        tasks_file.parent.mkdir(exist_ok=True)
        try:
            tasks = json.loads(tasks_file.read_text()) if tasks_file.exists() else []
        except Exception:
            tasks = []
        import time
        task_id = str(int(time.time()))[-6:]
        tasks.append({"id": task_id, "title": title, "description": description,
                       "priority": priority, "status": "pending", "notes": ""})
        tasks_file.write_text(json.dumps(tasks, ensure_ascii=False, indent=2))
        return f"✅ مهمة #{task_id}: {title}"

    def _task_list(self, status: str = "all") -> str:
        tasks_file = Path.home() / ".weaver" / "tasks.json"
        if not tasks_file.exists():
            return "لا توجد مهام"
        tasks = json.loads(tasks_file.read_text())
        if status != "all":
            tasks = [t for t in tasks if t["status"] == status]
        if not tasks:
            return "لا توجد مهام"
        lines = []
        for t in tasks:
            icon = {"pending": "⏳", "in_progress": "🔄", "done": "✅", "cancelled": "❌"}.get(t["status"], "•")
            lines.append(f"{icon} [{t['id']}] {t['title']} ({t['priority']})")
        return "\n".join(lines)

    def _task_update(self, task_id: str, status: Optional[str] = None, notes: Optional[str] = None) -> str:
        tasks_file = Path.home() / ".weaver" / "tasks.json"
        if not tasks_file.exists():
            return "لا توجد مهام"
        tasks = json.loads(tasks_file.read_text())
        for t in tasks:
            if t["id"] == task_id:
                if status:
                    t["status"] = status
                if notes:
                    t["notes"] = notes
                tasks_file.write_text(json.dumps(tasks, ensure_ascii=False, indent=2))
                return f"✅ تم تحديث المهمة #{task_id}"
        return f"المهمة #{task_id} غير موجودة"

    def _http_get(self, url: str, timeout: int = 30,
                  user_agent: str = "WeaverCode/1.0") -> str:
        """
        جلب صفحة عبر HTTP. يجرّب httpx إن توفّر، وإلا يسقط إلى curl
        (متوفّر دائماً على Termux) — فيعمل الاتصال بالمواقع بلا اعتمادية إضافية.
        يُرجع نص الرد الخام (HTML) أو رسالة خطأ تبدأ بـ 'خطأ'.
        """
        # (1) httpx إن كان مثبّتاً
        try:
            import httpx  # noqa
            import asyncio as _asyncio

            async def _fetch():
                async with httpx.AsyncClient(follow_redirects=True,
                                             timeout=timeout) as client:
                    r = await client.get(url, headers={"User-Agent": user_agent})
                    return r.text

            try:
                loop = _asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop is None:
                return _asyncio.run(_fetch())
            # داخل حلقة قائمة: نفّذ في خيط منفصل
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as ex:
                return ex.submit(lambda: _asyncio.run(_fetch())).result()
        except ImportError:
            pass
        except Exception:
            pass
        # (2) fallback: curl (نفس نهج المزوّد على Termux)
        try:
            proc = subprocess.run(
                ["curl", "-sSL", "--max-time", str(timeout),
                 "-A", user_agent, url],
                capture_output=True, text=True, timeout=timeout + 5)
            if proc.returncode != 0:
                return f"خطأ في جلب {url}: {proc.stderr.strip()[:200]}"
            return proc.stdout
        except FileNotFoundError:
            return f"خطأ: لا httpx ولا curl متوفّر لجلب {url}"
        except Exception as e:
            return f"خطأ في جلب {url}: {e}"

    async def _web_fetch(self, url: str, extract_prompt: str = "") -> str:
        raw = self._http_get(url, timeout=30)
        if raw.startswith("خطأ"):
            return raw
        # إزالة HTML بسيطة → نص قابل للقراءة
        text = re.sub(r"<script[\s\S]*?</script>", " ", raw, flags=re.I)
        text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:10000] if text else "(الصفحة فارغة أو تعذّرت قراءتها)"

    async def _web_search(self, query: str, max_results: int = 5) -> str:
        url = f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}"
        text = self._http_get(url, timeout=15, user_agent="Mozilla/5.0")
        if text.startswith("خطأ"):
            return text
        results = re.findall(r'class="result__title"[^>]*>.*?<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', text, re.S)
        output = []
        for link, title in results[:max_results]:
            title_clean = re.sub(r"<[^>]+>", "", title).strip()
            output.append(f"• {title_clean}\n  {link}")
        return "\n".join(output) if output else "لا توجد نتائج"

    def _git_status(self, repo_path: Optional[str] = None) -> str:
        return self._bash("git status", work_dir=repo_path)

    def _git_clone(self, url: str, destination: Optional[str] = None,
                   branch: Optional[str] = None, depth: Optional[int] = None) -> str:
        cmd = "git clone"
        if depth:
            cmd += f" --depth {depth}"
        if branch:
            cmd += f" -b {branch}"
        cmd += f" {url}"
        if destination:
            cmd += f" {destination}"
        return self._bash(cmd, timeout=300)

    def _weaver_root(self) -> Path:
        return Path(__file__).resolve().parents[2]

    def _github_token(self) -> str:
        """توكن GitHub المتصل (من config/integrations.json)."""
        try:
            f = self._weaver_root() / "config" / "integrations.json"
            data = json.loads(f.read_text(encoding="utf-8"))
            items = data if isinstance(data, list) else data.get("integrations", [])
            for it in items:
                if it.get("id") == "github":
                    return str(it.get("token", "")).strip()
        except Exception:
            pass
        return ""

    def _active_workspace(self) -> dict:
        """المستودع المستنسَخ النشِط (من config/workspace.json)."""
        try:
            f = self._weaver_root() / "config" / "workspace.json"
            d = json.loads(f.read_text(encoding="utf-8"))
            if d.get("work_dir") and os.path.isdir(d["work_dir"]):
                return d
        except Exception:
            pass
        return {}

    def _git_commit(self, message: str, repo_path: Optional[str] = None, add_all: bool = True) -> str:
        # افتراضياً commit في المستودع المستنسَخ النشِط (أو مجلد العمل)
        cwd = repo_path or self._active_workspace().get("work_dir") or self.work_dir
        cmds = []
        if add_all:
            cmds.append("git add -A")
        safe = message.replace('"', r'\"')
        cmds.append(f'git commit -m "{safe}"')
        return self._bash(" && ".join(cmds), work_dir=cwd)

    def _git_push(self, repo_path: Optional[str] = None, branch: str = "",
                  remote: str = "origin") -> str:
        """رفع فعلي إلى GitHub. يحقن توكن الاتصال وقت الرفع (لا يُخزَّن) فيعمل
        الوكيل مثل Claude Code — يبني في المستودع ثم يرفعه ذاتياً."""
        ws = self._active_workspace()
        cwd = repo_path or ws.get("work_dir") or self.work_dir
        br = branch or ws.get("branch") or "main"
        token = self._github_token()
        clone_url = ws.get("clone_url", "")
        if token and clone_url.startswith("https://"):
            auth = "https://x-access-token:" + token + "@" + clone_url[len("https://"):]
            out = self._bash(f"git push {auth} {br}", work_dir=cwd, timeout=90)
            return out.replace(token, "***") if token else out
        return self._bash(f"git push {remote} {br}", work_dir=cwd, timeout=90)

    def _pip_install(self, package: str, break_system: bool = True) -> str:
        flag = " --break-system-packages" if break_system else ""
        return self._bash(f"pip install {package}{flag}", timeout=120)

    def _python_run(self, script: Optional[str] = None, file_path: Optional[str] = None,
                    timeout: int = 60) -> str:
        if script:
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as f:
                f.write(script)
                file_path = f.name
        if file_path:
            return self._bash(f"python3 {file_path}", timeout=timeout)
        return "خطأ: يجب تحديد script أو file_path"

    def _env_set(self, key: str, value: str) -> str:
        os.environ[key] = value
        return f"✅ {key}={value}"

    def _env_get(self, key: str) -> str:
        return os.environ.get(key, f"(غير معين: {key})")

    def _dir_list(self, path: str = ".", show_hidden: bool = False, depth: int = 2) -> str:
        try:
            result = subprocess.run(
                ["find", path, "-maxdepth", str(depth), "-not", "-path", "*/.*"] +
                ([] if not show_hidden else []),
                capture_output=True, text=True, timeout=10
            )
            lines = sorted(result.stdout.strip().splitlines())
            return "\n".join(lines[:200])
        except Exception as e:
            return f"خطأ: {e}"

    def _ask_user(self, question: str, options: Optional[List[str]] = None) -> str:
        print(f"\n🤖 WeaverCode يسأل: {question}")
        if options:
            for i, opt in enumerate(options, 1):
                print(f"  {i}. {opt}")
        try:
            answer = input("إجابتك: ").strip()
            return answer
        except Exception:
            return "(لا إجابة)"

    # ── تنفيذ أدوات GitHub CLI ──────────────────────────────────────────

    def _gh_status(self) -> str:
        """فحص حالة GitHub"""
        result = self._bash("gh auth status 2>&1 && gh api user --jq '.login + \" (\" + .name + \")\"' 2>/dev/null")
        if "not logged" in result.lower() or "error" in result.lower():
            return "❌ غير مرتبط بـ GitHub\nشغّل: gh auth login --web"
        return f"✅ GitHub مرتبط\n{result}"

    def _gh_create_repo(self, name: str, description: str = "",
                         private: bool = False) -> str:
        """إنشاء مستودع جديد"""
        visibility = "--private" if private else "--public"
        desc_flag = f'--description "{description}"' if description else ""
        result = self._bash(
            f"gh repo create {name} {visibility} {desc_flag} --confirm 2>&1 || "
            f"gh repo create {name} {visibility} {desc_flag} 2>&1"
        )
        if "https://github.com" in result:
            return f"✅ تم إنشاء المستودع\n{result.strip()}"
        return f"❌ فشل إنشاء المستودع\n{result}"

    def _gh_list_repos(self, limit: int = 10) -> str:
        """عرض المستودعات"""
        result = self._bash(
            f"gh repo list --limit {limit} "
            f"--json name,description,isPrivate,updatedAt "
            f"--jq '.[] | \"\\(.isPrivate | if . then \"🔒\" else \"🌐\" end) \\(.name) — \\(.description // \"\")\"' 2>&1"
        )
        if not result.strip():
            return "لا توجد مستودعات أو GitHub غير مرتبط"
        return f"مستودعاتك على GitHub:\n{result}"

    def _gh_create_issue(self, title: str, body: str = "",
                          repo: str = "") -> str:
        """إنشاء Issue"""
        repo_flag = f"--repo {repo}" if repo else ""
        body_flag = f'--body "{body}"' if body else ""
        result = self._bash(
            f'gh issue create --title "{title}" {body_flag} {repo_flag} 2>&1'
        )
        if "https://github.com" in result:
            return f"✅ تم إنشاء Issue\n{result.strip()}"
        return f"❌ فشل\n{result}"

    # ── تحميل المهارات (Skills) ─────────────────────────────────────────

    def _skill_load(self, name: str = "", list: bool = False) -> str:
        try:
            from core.skills import SkillLoader
            loader = SkillLoader()
            if list or not name:
                names = loader.names()
                return ("Skills المتاحة:\n" + "\n".join(f"• {n}" for n in names)
                        if names else "لا توجد skills مثبتة.")
            return loader.get_context(name)
        except Exception as e:
            return f"خطأ في تحميل الـ skill: {e}"
