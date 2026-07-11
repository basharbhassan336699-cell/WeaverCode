#!/usr/bin/env python3
"""
expand_tools.py — سكربت تلقائي لتثبيت الأدوات الناقصة في WeaverCode
الاستخدام: python3 scripts/expand_tools.py
"""

import subprocess
import sys
import os
import json
from pathlib import Path

ROOT = Path(__file__).parent.parent


def run(cmd: str, check: bool = False) -> tuple[int, str]:
    result = subprocess.run(
        cmd, shell=True, capture_output=True, text=True
    )
    return result.returncode, (result.stdout + result.stderr).strip()


def pip_install(package: str) -> bool:
    code, out = run(f"pip install {package} --break-system-packages -q")
    if code == 0:
        print(f"  ✅ {package}")
        return True
    else:
        print(f"  ⚠️  {package} — {out[:80]}")
        return False


def check_installed(package: str) -> bool:
    code, _ = run(f"python3 -c 'import {package}'")
    return code == 0


def main():
    print("🕸️  WeaverCode — تثبيت الأدوات الناقصة")
    print("=" * 50)

    # ── فحص البيئة ──────────────────────────────────
    print("\n📋 فحص البيئة:")
    _, py_ver = run("python3 --version")
    _, pip_ver = run("pip --version")
    _, git_ver = run("git --version")
    print(f"  Python: {py_ver}")
    print(f"  Pip: {pip_ver[:30]}")
    print(f"  Git: {git_ver}")

    # ── المكتبات المطلوبة ────────────────────────────
    print("\n📦 تثبيت المكتبات:")

    libraries = [
        ("httpx", "httpx"),
        ("python-dotenv", "dotenv"),
        ("rich", "rich"),
        ("nbformat", "nbformat"),
        ("watchdog", "watchdog"),
        ("schedule", "schedule"),
        ("websockets", "websockets"),
        ("aiofiles", "aiofiles"),
        ("pyflakes", "pyflakes"),
        ("plyer", "plyer"),
        ("beautifulsoup4", "bs4"),
    ]

    installed = []
    failed = []

    for pkg_name, import_name in libraries:
        if check_installed(import_name):
            print(f"  ✅ {pkg_name} (مثبت مسبقاً)")
            installed.append(pkg_name)
        else:
            if pip_install(pkg_name):
                installed.append(pkg_name)
            else:
                failed.append(pkg_name)

    # MCP SDK — يحاول طريقتين
    print("\n📡 تثبيت MCP SDK:")
    if check_installed("mcp"):
        print("  ✅ mcp (مثبت مسبقاً)")
        installed.append("mcp")
    else:
        code, out = run("pip install mcp --break-system-packages -q")
        if code == 0:
            print("  ✅ mcp")
            installed.append("mcp")
        else:
            # محاولة من GitHub
            code2, out2 = run(
                "pip install git+https://github.com/modelcontextprotocol/python-sdk.git"
                " --break-system-packages -q"
            )
            if code2 == 0:
                print("  ✅ mcp (من GitHub)")
                installed.append("mcp")
            else:
                print(f"  ⚠️  mcp — تعذّر التثبيت (سيعمل بدونه)")
                failed.append("mcp")

    # ── إضافة الأدوات الناقصة للـ registry ──────────
    print("\n🔧 إضافة الأدوات الناقصة لـ registry.py:")

    registry_path = ROOT / "core" / "tools" / "registry.py"
    content = registry_path.read_text(encoding="utf-8")

    # الأدوات الجديدة للإضافة
    new_tools_registration = '''
        # ── الأدوات الجديدة v1.1 ────────────────────────────────────────────

        self._add(Tool(
            name="Agent",
            description="تشغيل وكيل فرعي مستقل بسياق منفصل لإنجاز مهمة محددة",
            parameters={
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "المهمة للوكيل الفرعي"},
                    "tools": {"type": "array", "items": {"type": "string"}},
                    "background": {"type": "boolean", "default": False},
                },
                "required": ["task"],
            },
            fn=self._agent_spawn,
        ))

        self._add(Tool(
            name="Monitor",
            description="مراقبة أمر أو ملف في الخلفية والتفاعل مع الأحداث",
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "duration": {"type": "integer", "default": 30},
                    "trigger": {"type": "string"},
                },
                "required": ["command"],
            },
            fn=self._monitor,
            requires_permission=True,
        ))

        self._add(Tool(
            name="CronCreate",
            description="جدولة مهمة متكررة داخل الجلسة",
            parameters={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "interval_seconds": {"type": "integer"},
                    "label": {"type": "string"},
                },
                "required": ["prompt", "interval_seconds"],
            },
            fn=self._cron_create,
        ))

        self._add(Tool(
            name="CronList",
            description="عرض المهام المجدولة الحالية",
            parameters={"type": "object", "properties": {}, "required": []},
            fn=self._cron_list,
        ))

        self._add(Tool(
            name="CronDelete",
            description="إلغاء مهمة مجدولة بمعرّفها",
            parameters={
                "type": "object",
                "properties": {"cron_id": {"type": "string"}},
                "required": ["cron_id"],
            },
            fn=self._cron_delete,
        ))

        self._add(Tool(
            name="NotebookEdit",
            description="تعديل خلية في Jupyter notebook (.ipynb)",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "cell_index": {"type": "integer"},
                    "new_source": {"type": "string"},
                    "mode": {"type": "string", "enum": ["replace", "insert", "delete"], "default": "replace"},
                    "cell_type": {"type": "string", "enum": ["code", "markdown"], "default": "code"},
                },
                "required": ["path"],
            },
            fn=self._notebook_edit,
            requires_permission=True,
        ))

        self._add(Tool(
            name="EnterPlanMode",
            description="الدخول لوضع التخطيط — فكّر قبل التنفيذ",
            parameters={
                "type": "object",
                "properties": {"task": {"type": "string"}},
                "required": ["task"],
            },
            fn=self._enter_plan_mode,
        ))

        self._add(Tool(
            name="ExitPlanMode",
            description="عرض الخطة للموافقة ثم التنفيذ",
            parameters={
                "type": "object",
                "properties": {"plan": {"type": "string"}},
                "required": ["plan"],
            },
            fn=self._exit_plan_mode,
            requires_permission=True,
        ))

        self._add(Tool(
            name="ReportFindings",
            description="تقديم نتائج مراجعة الكود بشكل منظم ومصنّف",
            parameters={
                "type": "object",
                "properties": {
                    "findings": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "file": {"type": "string"},
                                "line": {"type": "integer"},
                                "severity": {"type": "string", "enum": ["critical", "warning", "info"]},
                                "summary": {"type": "string"},
                                "category": {"type": "string"},
                            },
                        },
                    },
                },
                "required": ["findings"],
            },
            fn=self._report_findings,
        ))

        self._add(Tool(
            name="SendUserFile",
            description="إرسال ملف للمستخدم مع وصف",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "caption": {"type": "string"},
                },
                "required": ["path"],
            },
            fn=self._send_user_file,
        ))

        self._add(Tool(
            name="PushNotification",
            description="إشعار سطح المكتب عند انتهاء مهمة",
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "message": {"type": "string"},
                },
                "required": ["title", "message"],
            },
            fn=self._push_notification,
        ))

        self._add(Tool(
            name="ToolSearch",
            description="البحث عن أداة متاحة بالاسم أو الوظيفة",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            fn=self._tool_search,
        ))

        self._add(Tool(
            name="LSP",
            description="تحليل الكود: أخطاء، رموز، تشخيص. يستخدم pyflakes و ast.",
            parameters={
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["diagnostics", "definition", "references", "symbols"],
                    },
                    "file": {"type": "string"},
                    "line": {"type": "integer"},
                    "character": {"type": "integer"},
                },
                "required": ["action", "file"],
            },
            fn=self._lsp_action,
        ))

        self._add(Tool(
            name="EnterWorktree",
            description="إنشاء git worktree معزول للتجريب الآمن",
            parameters={
                "type": "object",
                "properties": {
                    "branch": {"type": "string"},
                    "path": {"type": "string"},
                },
                "required": ["branch"],
            },
            fn=self._enter_worktree,
            requires_permission=True,
        ))

        self._add(Tool(
            name="ExitWorktree",
            description="الخروج من worktree والعودة للمجلد الأصلي",
            parameters={"type": "object", "properties": {}, "required": []},
            fn=self._exit_worktree,
        ))
'''

    new_tools_implementation = '''
    # ── تنفيذ الأدوات الجديدة v1.1 ──────────────────────────────────────────

    async def _agent_spawn(self, task: str, tools: Optional[List[str]] = None,
                            background: bool = False) -> str:
        try:
            from ..engine.query_engine import QueryEngine
            from ..engine.provider import get_provider
            sub_registry = ToolRegistry(self.work_dir)
            if tools:
                sub_registry._tools = {
                    k: v for k, v in sub_registry._tools.items() if k in tools
                }
            engine = QueryEngine(
                provider=get_provider(),
                tool_registry=sub_registry,
                system_prompt="أنت وكيل فرعي. أنجز المهمة المحددة فقط.",
                max_turns=10,
            )
            result = await engine.run(task)
            return f"[وكيل فرعي]\\n{result.text}"
        except Exception as e:
            return f"خطأ في الوكيل الفرعي: {e}"

    def _monitor(self, command: str, duration: int = 30,
                  trigger: Optional[str] = None) -> str:
        import threading, queue as q_module
        output_q: q_module.Queue = q_module.Queue()
        def runner():
            try:
                proc = subprocess.Popen(
                    command, shell=True, stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, text=True,
                )
                import time
                end = time.time() + duration
                while time.time() < end:
                    line = proc.stdout.readline()
                    if not line:
                        break
                    output_q.put(line.rstrip())
                    if trigger and trigger in line:
                        output_q.put(f"[تنبيه] تم اكتشاف: {trigger}")
                proc.terminate()
            except Exception as e:
                output_q.put(f"خطأ: {e}")
        t = threading.Thread(target=runner, daemon=True)
        t.start()
        t.join(timeout=duration + 2)
        lines = []
        while not output_q.empty():
            lines.append(output_q.get())
        return "\\n".join(lines[:100]) if lines else "(لا مخرجات)"

    def _cron_create(self, prompt: str, interval_seconds: int,
                      label: str = "") -> str:
        import time, uuid
        cron_file = Path.home() / ".weaver" / "crons.json"
        cron_file.parent.mkdir(exist_ok=True)
        try:
            crons = json.loads(cron_file.read_text()) if cron_file.exists() else []
        except Exception:
            crons = []
        cron_id = str(uuid.uuid4())[:8]
        crons.append({
            "id": cron_id, "prompt": prompt,
            "interval": interval_seconds, "label": label or prompt[:30],
            "created_at": time.time(), "active": True,
        })
        cron_file.write_text(json.dumps(crons, ensure_ascii=False, indent=2))
        return f"✅ مهمة #{cron_id} مجدولة كل {interval_seconds}ث"

    def _cron_list(self) -> str:
        cron_file = Path.home() / ".weaver" / "crons.json"
        if not cron_file.exists():
            return "لا توجد مهام مجدولة"
        crons = json.loads(cron_file.read_text())
        lines = []
        for c in crons:
            st = "✅" if c.get("active") else "⏹"
            lines.append(f"{st} [{c['id']}] كل {c['interval']}ث — {c['label']}")
        return "\\n".join(lines) if lines else "لا توجد مهام مجدولة"

    def _cron_delete(self, cron_id: str) -> str:
        cron_file = Path.home() / ".weaver" / "crons.json"
        if not cron_file.exists():
            return "لا توجد مهام"
        crons = json.loads(cron_file.read_text())
        before = len(crons)
        crons = [c for c in crons if c["id"] != cron_id]
        if len(crons) == before:
            return f"المهمة #{cron_id} غير موجودة"
        cron_file.write_text(json.dumps(crons, ensure_ascii=False, indent=2))
        return f"✅ تم إلغاء #{cron_id}"

    def _notebook_edit(self, path: str, cell_index: int = 0,
                        new_source: str = "", mode: str = "replace",
                        cell_type: str = "code") -> str:
        try:
            import nbformat
            nb = nbformat.read(path, as_version=4)
            if mode == "replace":
                nb.cells[cell_index]["source"] = new_source
            elif mode == "insert":
                cell = nbformat.v4.new_code_cell(new_source) if cell_type == "code" \\
                    else nbformat.v4.new_markdown_cell(new_source)
                nb.cells.insert(cell_index + 1, cell)
            elif mode == "delete":
                nb.cells.pop(cell_index)
            nbformat.write(nb, path)
            return f"✅ notebook محدَّث: {path}"
        except ImportError:
            return "❌ pip install nbformat --break-system-packages"
        except Exception as e:
            return f"خطأ: {e}"

    def _enter_plan_mode(self, task: str) -> str:
        (Path.home() / ".weaver").mkdir(exist_ok=True)
        (Path.home() / ".weaver" / "plan_mode.txt").write_text(task)
        return f"🗺️  وضع التخطيط — المهمة: {task}\\nفكّر ثم استخدم ExitPlanMode"

    def _exit_plan_mode(self, plan: str) -> str:
        plan_file = Path.home() / ".weaver" / "plan_mode.txt"
        if plan_file.exists():
            plan_file.unlink()
        print(f"\\n📋 الخطة:\\n{plan}\\n")
        try:
            ans = input("موافق على التنفيذ؟ (نعم/لا): ").strip()
        except Exception:
            ans = "نعم"
        return "✅ موافق — سأبدأ" if ans in ("نعم", "yes", "y") else "⏹ ملغى"

    def _report_findings(self, findings: List[Dict]) -> str:
        if not findings:
            return "✅ لا مشاكل"
        icons = {"critical": "🔴", "warning": "🟡", "info": "🔵"}
        lines = ["## تقرير المراجعة"]
        for sev in ["critical", "warning", "info"]:
            items = [f for f in findings if f.get("severity") == sev]
            if items:
                lines.append(f"\\n{icons[sev]} {sev.upper()} ({len(items)})")
                for item in items:
                    loc = f"{item.get('file','?')}:{item.get('line','?')}"
                    lines.append(f"  [{loc}] {item.get('summary','')}")
        report = "\\n".join(lines)
        (Path.home() / ".weaver" / "last_review.md").write_text(report)
        return report

    def _send_user_file(self, path: str, caption: str = "") -> str:
        p = Path(path)
        if not p.exists():
            return f"❌ الملف غير موجود: {path}"
        size = p.stat().st_size
        print(f"\\n📎 {path} ({size:,} بايت)\\n   {caption}")
        return f"✅ {path} ({size:,} بايت)"

    def _push_notification(self, title: str, message: str) -> str:
        try:
            from plyer import notification
            notification.notify(title=title, message=message, timeout=5)
        except Exception:
            pass
        print(f"\\n🔔 [{title}] {message}")
        return f"🔔 {title}: {message}"

    def _tool_search(self, query: str) -> str:
        q = query.lower()
        results = [
            f"• **{n}**: {t.description[:80]}"
            for n, t in self._tools.items()
            if q in n.lower() or q in t.description.lower()
        ]
        return f"نتائج '{query}':\\n" + "\\n".join(results) if results else f"لا نتائج لـ '{query}'"

    def _lsp_action(self, action: str, file: str,
                     line: int = 0, character: int = 0) -> str:
        if action == "diagnostics":
            r = self._bash(f"python3 -m pyflakes {file} 2>&1 || true")
            return f"✅ لا أخطاء" if not r.strip() else f"تشخيص {file}:\\n{r}"
        elif action == "symbols":
            script = (
                f"import ast\\n"
                f"tree = ast.parse(open('{file}').read())\\n"
                f"[print(f'{{type(n).__name__}}: {{n.name}} L{{n.lineno}}')"
                f" for n in ast.walk(tree)"
                f" if isinstance(n, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef))]"
            )
            return self._bash(f"python3 -c \"{script}\"") or "لا رموز"
        return f"يتطلب LSP server كامل: {action} في {file}:{line}"

    def _enter_worktree(self, branch: str, path: Optional[str] = None) -> str:
        wt_path = path or f".claude/worktrees/{branch}"
        r = self._bash(f"git worktree add -b {branch} {wt_path} 2>&1 || git worktree add {wt_path} {branch} 2>&1")
        if "fatal" in r.lower():
            return f"❌ {r}"
        self.work_dir = str(Path(self.work_dir) / wt_path)
        return f"✅ Worktree: {wt_path} | فرع: {branch}"

    def _exit_worktree(self) -> str:
        self.work_dir = str(Path(self.work_dir).parent.parent)
        return f"✅ عُدت إلى: {self.work_dir}"
'''

    # التحقق من وجود الأدوات مسبقاً
    if "# ── الأدوات الجديدة v1.1" in content:
        print("  ℹ️  الأدوات الجديدة موجودة مسبقاً")
    else:
        # إضافة التسجيل قبل نهاية _register_all
        insert_point = "    # ── تنفيذ الأدوات ───"
        if insert_point in content:
            content = content.replace(
                insert_point,
                new_tools_registration + "\n" + insert_point
            )
            print("  ✅ تسجيل الأدوات الجديدة")
        else:
            print("  ⚠️  لم يُعثر على نقطة الإدراج في _register_all")

        # إضافة التنفيذ قبل نهاية الملف
        if "_ask_user" in content and "_exit_worktree" not in content:
            # أضف التنفيذ في نهاية الكلاس
            last_def_pos = content.rfind("\n    def _ask_user")
            ask_user_end = content.find("\n    def ", last_def_pos + 1)
            if ask_user_end == -1:
                ask_user_end = len(content)
            content = content[:ask_user_end] + "\n" + new_tools_implementation + content[ask_user_end:]
            print("  ✅ إضافة دوال التنفيذ")

        registry_path.write_text(content, encoding="utf-8")

    # ── تحديث requirements.txt ───────────────────────
    print("\n📝 تحديث requirements.txt:")
    req_path = ROOT / "config" / "requirements.txt"
    req_content = req_path.read_text()
    new_reqs = [
        "nbformat>=5.9.0",
        "watchdog>=4.0.0",
        "schedule>=1.2.0",
        "websockets>=12.0",
        "aiofiles>=23.0.0",
        "plyer>=2.1.0",
        "pyflakes>=3.0.0",
    ]
    added = 0
    for req in new_reqs:
        pkg = req.split(">=")[0]
        if pkg not in req_content:
            req_content += f"\n{req}"
            added += 1
    req_path.write_text(req_content)
    print(f"  ✅ أُضيف {added} حزمة جديدة")

    # ── اختبار ──────────────────────────────────────
    print("\n🧪 اختبار الأدوات:")
    code, out = run(
        f"cd {ROOT} && python3 -c \""
        "import sys; sys.path.insert(0,'.');"
        "from core.tools.registry import ToolRegistry;"
        "r=ToolRegistry();"
        "tools=list(r._tools.keys());"
        "print(f'إجمالي الأدوات: {len(tools)}');"
        "[print(f\\\"  ✅ {t}\\\") for t in sorted(tools)]"
        "\""
    )
    print(out if out else f"خطأ: code={code}")

    # ── التقرير النهائي ──────────────────────────────
    print("\n" + "=" * 50)
    print("📊 التقرير النهائي:")
    print(f"  ✅ مكتبات مثبتة: {len(installed)}")
    if failed:
        print(f"  ⚠️  مكتبات فشلت: {', '.join(failed)}")
    print("\n✅ اكتمل التوسيع!")
    print("\nالخطوات التالية:")
    print("  python3 weaver.py --interactive")


if __name__ == "__main__":
    main()
