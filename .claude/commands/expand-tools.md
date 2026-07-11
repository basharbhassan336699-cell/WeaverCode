---
name: expand-tools
description: تثبيت الأدوات والمكتبات الناقصة في WeaverCode وإضافتها للنظام تلقائياً
allowed-tools: Bash, Read, Write, Edit, Glob, Read, TaskCreate, TaskUpdate, TaskList, MemorySave
---

# توسيع أدوات WeaverCode — تثبيت الناقص

## الأدوات الناقصة مقارنة بـ Claude Code (19 أداة)
- `Agent` — تشغيل وكيل فرعي مستقل
- `LSP` — تحليل الكود (تعريفات، مراجع، أخطاء)
- `Monitor` — مراقبة ملفات/logs في الخلفية
- `Workflow` — تنسيق عدة وكلاء
- `CronCreate/CronList/CronDelete` — جدولة المهام
- `NotebookEdit` — تعديل Jupyter notebooks
- `PowerShell` — تنفيذ PowerShell (Windows)
- `SendMessage` — إرسال رسائل بين الوكلاء
- `PushNotification` — إشعارات سطح المكتب
- `SendUserFile` — إرسال ملفات للمستخدم
- `ReportFindings` — تقارير مراجعة الكود
- `ToolSearch` — اكتشاف أدوات MCP ديناميكياً
- `ListMcpResourcesTool` — عرض موارد MCP
- `ReadMcpResourceTool` — قراءة مورد MCP
- `EnterPlanMode/ExitPlanMode` — وضع التخطيط
- `EnterWorktree/ExitWorktree` — عزل git worktree

## الخطوة 1: فحص البيئة

نفّذ:
```bash
python3 --version
pip --version
git --version
node --version 2>/dev/null || echo "node: غير مثبت"
npm --version 2>/dev/null || echo "npm: غير مثبت"
```

## الخطوة 2: تثبيت المكتبات الناقصة

### مكتبات Python الجديدة
```bash
pip install \
    nbformat \
    nbconvert \
    pyinotify \
    plyer \
    pylsp-jsonrpc \
    python-lsp-server \
    schedule \
    websockets \
    aiofiles \
    watchdog \
    --break-system-packages
```

**إذا فشل أي منها** في Termux تخطاه وسجّله.

### مكتبة MCP Python
```bash
pip install mcp --break-system-packages
```
إذا فشل:
```bash
pip install git+https://github.com/modelcontextprotocol/python-sdk.git --break-system-packages
```

## الخطوة 3: إضافة الأدوات الناقصة لـ registry.py

اقرأ الملف الحالي:
```
core/tools/registry.py
```

ثم أضف الأدوات التالية داخل دالة `_register_all` **بعد آخر أداة موجودة**:

### أداة Agent (وكيل فرعي)
```python
self._add(Tool(
    name="Agent",
    description="تشغيل وكيل فرعي مستقل بسياق منفصل لإنجاز مهمة محددة",
    parameters={
        "type": "object",
        "properties": {
            "task": {"type": "string", "description": "المهمة للوكيل الفرعي"},
            "tools": {"type": "array", "items": {"type": "string"}, "description": "الأدوات المسموح بها"},
            "background": {"type": "boolean", "default": False},
        },
        "required": ["task"],
    },
    fn=self._agent_spawn,
))
```

### أداة Monitor (مراقبة)
```python
self._add(Tool(
    name="Monitor",
    description="مراقبة ملف أو أمر في الخلفية والتفاعل مع الأحداث",
    parameters={
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "الأمر أو الملف للمراقبة"},
            "duration": {"type": "integer", "default": 30, "description": "مدة المراقبة بالثواني"},
            "trigger": {"type": "string", "description": "نمط للتفاعل معه"},
        },
        "required": ["command"],
    },
    fn=self._monitor,
    requires_permission=True,
))
```

### أداة CronCreate (جدولة)
```python
self._add(Tool(
    name="CronCreate",
    description="جدولة مهمة متكررة داخل الجلسة",
    parameters={
        "type": "object",
        "properties": {
            "prompt": {"type": "string", "description": "المهمة المجدولة"},
            "interval_seconds": {"type": "integer", "description": "الفترة بالثواني"},
            "label": {"type": "string", "description": "اسم للمهمة"},
        },
        "required": ["prompt", "interval_seconds"],
    },
    fn=self._cron_create,
))
```

### أداة CronList
```python
self._add(Tool(
    name="CronList",
    description="عرض المهام المجدولة الحالية",
    parameters={"type": "object", "properties": {}, "required": []},
    fn=self._cron_list,
))
```

### أداة CronDelete
```python
self._add(Tool(
    name="CronDelete",
    description="إلغاء مهمة مجدولة",
    parameters={
        "type": "object",
        "properties": {"cron_id": {"type": "string"}},
        "required": ["cron_id"],
    },
    fn=self._cron_delete,
))
```

### أداة NotebookEdit (Jupyter)
```python
self._add(Tool(
    name="NotebookEdit",
    description="تعديل خلية في Jupyter notebook",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "مسار ملف .ipynb"},
            "cell_index": {"type": "integer", "description": "رقم الخلية (0-based)"},
            "new_source": {"type": "string", "description": "المحتوى الجديد"},
            "mode": {"type": "string", "enum": ["replace", "insert", "delete"], "default": "replace"},
            "cell_type": {"type": "string", "enum": ["code", "markdown"], "default": "code"},
        },
        "required": ["path"],
    },
    fn=self._notebook_edit,
    requires_permission=True,
))
```

### أداة EnterPlanMode
```python
self._add(Tool(
    name="EnterPlanMode",
    description="الدخول لوضع التخطيط — فكّر قبل التنفيذ",
    parameters={
        "type": "object",
        "properties": {"task": {"type": "string", "description": "المهمة للتخطيط لها"}},
        "required": ["task"],
    },
    fn=self._enter_plan_mode,
))
```

### أداة ExitPlanMode
```python
self._add(Tool(
    name="ExitPlanMode",
    description="عرض الخطة وطلب الموافقة ثم التنفيذ",
    parameters={
        "type": "object",
        "properties": {"plan": {"type": "string", "description": "الخطة المقترحة"}},
        "required": ["plan"],
    },
    fn=self._exit_plan_mode,
    requires_permission=True,
))
```

### أداة ReportFindings (تقارير المراجعة)
```python
self._add(Tool(
    name="ReportFindings",
    description="تقديم نتائج مراجعة الكود بشكل منظم",
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
```

### أداة SendUserFile
```python
self._add(Tool(
    name="SendUserFile",
    description="إرسال ملف للمستخدم مع رسالة توضيحية",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "caption": {"type": "string", "description": "وصف الملف"},
        },
        "required": ["path"],
    },
    fn=self._send_user_file,
))
```

### أداة PushNotification
```python
self._add(Tool(
    name="PushNotification",
    description="إرسال إشعار لسطح المكتب عند انتهاء مهمة طويلة",
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
```

### أداة ToolSearch (اكتشاف الأدوات)
```python
self._add(Tool(
    name="ToolSearch",
    description="البحث عن أداة متاحة بالاسم أو الوظيفة",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "ما تبحث عنه"},
        },
        "required": ["query"],
    },
    fn=self._tool_search,
))
```

### أداة LSP (تحليل الكود)
```python
self._add(Tool(
    name="LSP",
    description="تحليل الكود: أخطاء، تعريفات، مراجع. يتطلب python-lsp-server.",
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
```

### أداة EnterWorktree
```python
self._add(Tool(
    name="EnterWorktree",
    description="إنشاء git worktree معزول للتجريب الآمن",
    parameters={
        "type": "object",
        "properties": {
            "branch": {"type": "string", "description": "اسم الفرع الجديد"},
            "path": {"type": "string", "description": "مسار الـ worktree"},
        },
        "required": ["branch"],
    },
    fn=self._enter_worktree,
    requires_permission=True,
))
```

### أداة ExitWorktree
```python
self._add(Tool(
    name="ExitWorktree",
    description="الخروج من الـ worktree والعودة للمجلد الأصلي",
    parameters={"type": "object", "properties": {}, "required": []},
    fn=self._exit_worktree,
))
```

## الخطوة 4: إضافة دوال التنفيذ

أضف هذه الدوال في نهاية كلاس `ToolRegistry` **قبل آخر سطر**:

```python
    # ── أدوات جديدة ─────────────────────────────────────────────────────────

    async def _agent_spawn(self, task: str, tools: Optional[List[str]] = None,
                            background: bool = False) -> str:
        """تشغيل وكيل فرعي مستقل"""
        from ..engine.query_engine import QueryEngine
        from ..engine.provider import get_provider
        sub_registry = ToolRegistry(self.work_dir)
        if tools:
            sub_registry._tools = {k: v for k, v in sub_registry._tools.items() if k in tools}
        engine = QueryEngine(
            provider=get_provider(),
            tool_registry=sub_registry,
            system_prompt="أنت وكيل فرعي في WeaverCode. أنجز المهمة المحددة فقط.",
            max_turns=10,
        )
        result = await engine.run(task)
        return f"[وكيل فرعي]\n{result.text}"

    def _monitor(self, command: str, duration: int = 30, trigger: Optional[str] = None) -> str:
        """مراقبة أمر أو ملف"""
        import threading, queue
        output_q: queue.Queue = queue.Queue()
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
        return "\n".join(lines[:100]) if lines else "(لا مخرجات)"

    def _cron_create(self, prompt: str, interval_seconds: int, label: str = "") -> str:
        """جدولة مهمة"""
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
        return f"✅ جُدولت المهمة #{cron_id} كل {interval_seconds}ث: {label or prompt[:40]}"

    def _cron_list(self) -> str:
        """عرض المهام المجدولة"""
        cron_file = Path.home() / ".weaver" / "crons.json"
        if not cron_file.exists():
            return "لا توجد مهام مجدولة"
        crons = json.loads(cron_file.read_text())
        if not crons:
            return "لا توجد مهام مجدولة"
        lines = []
        for c in crons:
            status = "✅" if c.get("active") else "⏹"
            lines.append(f"{status} [{c['id']}] كل {c['interval']}ث — {c['label']}")
        return "\n".join(lines)

    def _cron_delete(self, cron_id: str) -> str:
        """إلغاء مهمة مجدولة"""
        cron_file = Path.home() / ".weaver" / "crons.json"
        if not cron_file.exists():
            return "لا توجد مهام مجدولة"
        crons = json.loads(cron_file.read_text())
        before = len(crons)
        crons = [c for c in crons if c["id"] != cron_id]
        if len(crons) == before:
            return f"المهمة #{cron_id} غير موجودة"
        cron_file.write_text(json.dumps(crons, ensure_ascii=False, indent=2))
        return f"✅ تم إلغاء المهمة #{cron_id}"

    def _notebook_edit(self, path: str, cell_index: int = 0, new_source: str = "",
                        mode: str = "replace", cell_type: str = "code") -> str:
        """تعديل Jupyter notebook"""
        try:
            import nbformat
            nb = nbformat.read(path, as_version=4)
            if mode == "replace":
                if cell_index >= len(nb.cells):
                    return f"الخلية {cell_index} غير موجودة (المجموع: {len(nb.cells)})"
                nb.cells[cell_index]["source"] = new_source
            elif mode == "insert":
                cell = nbformat.v4.new_code_cell(new_source) if cell_type == "code" \
                    else nbformat.v4.new_markdown_cell(new_source)
                nb.cells.insert(cell_index + 1, cell)
            elif mode == "delete":
                nb.cells.pop(cell_index)
            nbformat.write(nb, path)
            return f"✅ تم تعديل notebook: {path}"
        except ImportError:
            return "❌ nbformat غير مثبت. شغّل: pip install nbformat --break-system-packages"
        except Exception as e:
            return f"خطأ: {e}"

    def _enter_plan_mode(self, task: str) -> str:
        """وضع التخطيط"""
        plan_file = Path.home() / ".weaver" / "current_plan.txt"
        plan_file.parent.mkdir(exist_ok=True)
        plan_file.write_text(f"المهمة: {task}\nالحالة: تخطيط\n")
        return f"""
🗺️  وضع التخطيط مفعّل

المهمة: {task}

فكّر في:
1. ما الخطوات المطلوبة؟
2. ما الأدوات التي ستستخدمها؟
3. ما المخاطر المحتملة؟
4. ما ترتيب التنفيذ الأمثل؟

عند الجاهزية استخدم ExitPlanMode مع خطتك الكاملة.
"""

    def _exit_plan_mode(self, plan: str) -> str:
        """الخروج من وضع التخطيط"""
        plan_file = Path.home() / ".weaver" / "current_plan.txt"
        if plan_file.exists():
            plan_file.unlink()
        print(f"\n📋 الخطة المقترحة:\n{plan}\n")
        try:
            confirm = input("هل توافق على تنفيذ هذه الخطة؟ (نعم/لا): ").strip()
        except Exception:
            confirm = "نعم"
        if confirm in ("نعم", "yes", "y", "1"):
            return "✅ تمت الموافقة — سأبدأ التنفيذ"
        return "⏹ تم إلغاء الخطة"

    def _report_findings(self, findings: List[Dict]) -> str:
        """تقرير نتائج المراجعة"""
        if not findings:
            return "✅ لا توجد مشاكل"
        icons = {"critical": "🔴", "warning": "🟡", "info": "🔵"}
        lines = ["## تقرير المراجعة\n"]
        by_severity = {"critical": [], "warning": [], "info": []}
        for f in findings:
            sev = f.get("severity", "info")
            by_severity.get(sev, by_severity["info"]).append(f)
        for sev, items in by_severity.items():
            if items:
                lines.append(f"\n### {icons.get(sev, '•')} {sev.upper()} ({len(items)})")
                for item in items:
                    loc = f"{item.get('file', '?')}:{item.get('line', '?')}"
                    lines.append(f"  - [{loc}] {item.get('summary', '')}")
        total = len(findings)
        crits = len(by_severity["critical"])
        lines.append(f"\n**المجموع: {total} | حرج: {crits}**")
        report = "\n".join(lines)
        # حفظ التقرير
        report_file = Path.home() / ".weaver" / "last_review.md"
        report_file.write_text(report)
        return report

    def _send_user_file(self, path: str, caption: str = "") -> str:
        """إرسال ملف للمستخدم"""
        p = Path(path)
        if not p.exists():
            return f"❌ الملف غير موجود: {path}"
        size = p.stat().st_size
        print(f"\n📎 ملف جاهز للتحميل: {path}")
        if caption:
            print(f"   {caption}")
        print(f"   الحجم: {size:,} بايت")
        return f"✅ الملف متاح: {path} ({size:,} بايت)\n{caption}"

    def _push_notification(self, title: str, message: str) -> str:
        """إشعار سطح المكتب"""
        try:
            from plyer import notification
            notification.notify(title=title, message=message, timeout=5)
            return f"✅ إشعار أُرسل: {title}"
        except ImportError:
            # fallback: طباعة في الـ terminal
            print(f"\n🔔 [{title}] {message}")
            return f"🔔 {title}: {message}"
        except Exception as e:
            print(f"\n🔔 [{title}] {message}")
            return f"🔔 {title}: {message}"

    def _tool_search(self, query: str) -> str:
        """البحث عن أداة"""
        query_lower = query.lower()
        results = []
        for name, tool in self._tools.items():
            if (query_lower in name.lower() or
                    query_lower in tool.description.lower()):
                results.append(f"• **{name}**: {tool.description[:80]}")
        if not results:
            return f"لا توجد أدوات تطابق '{query}'"
        return f"نتائج البحث عن '{query}':\n" + "\n".join(results)

    def _lsp_action(self, action: str, file: str,
                     line: int = 0, character: int = 0) -> str:
        """تحليل الكود عبر python-lsp-server"""
        if action == "diagnostics":
            # استخدام pyflakes بشكل مباشر
            result = self._bash(f"python3 -m pyflakes {file} 2>&1 || true")
            if not result.strip():
                return f"✅ {file}: لا أخطاء"
            return f"تشخيص {file}:\n{result}"
        elif action == "symbols":
            result = self._bash(f"python3 -c \"\nimport ast, sys\ntry:\n    tree = ast.parse(open('{file}').read())\n    for node in ast.walk(tree):\n        if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):\n            print(f'{{type(node).__name__}}: {{node.name}} (سطر {{node.lineno}})')\nexcept Exception as e:\n    print(f'خطأ: {{e}}')\n\"")
            return result or "لا رموز"
        elif action == "definition":
            return f"البحث عن تعريف في {file}:{line}:{character} — يتطلب LSP server كامل"
        elif action == "references":
            return f"البحث عن مراجع في {file}:{line}:{character} — يتطلب LSP server كامل"
        return f"إجراء غير معروف: {action}"

    def _enter_worktree(self, branch: str, path: Optional[str] = None) -> str:
        """إنشاء git worktree"""
        worktree_path = path or f".claude/worktrees/{branch}"
        result = self._bash(
            f"git worktree add {worktree_path} -b {branch} 2>&1 || "
            f"git worktree add {worktree_path} {branch} 2>&1"
        )
        if "fatal" in result.lower():
            return f"❌ {result}"
        self.work_dir = str(Path(self.work_dir) / worktree_path)
        return f"✅ Worktree جاهز: {worktree_path}\nالفرع: {branch}"

    def _exit_worktree(self) -> str:
        """الخروج من worktree"""
        original = str(Path(self.work_dir).parent.parent)
        self.work_dir = original
        return f"✅ عُدت إلى: {original}"
```

## الخطوة 5: تحديث requirements.txt

افتح `config/requirements.txt` وأضف:
```
nbformat>=5.9.0
nbconvert>=7.0.0
watchdog>=4.0.0
schedule>=1.2.0
websockets>=12.0
aiofiles>=23.0.0
plyer>=2.1.0
pyflakes>=3.0.0
mcp>=1.0.0
```

## الخطوة 6: اختبار الأدوات الجديدة

```bash
python3 -c "
from core.tools.registry import ToolRegistry
r = ToolRegistry()
tools = list(r._tools.keys())
print(f'إجمالي الأدوات: {len(tools)}')
for t in sorted(tools):
    print(f'  ✅ {t}')
"
```

## الخطوة 7: تحديث CLAUDE.md

أضف في قسم "الأدوات المدمجة" في CLAUDE.md:
```
## الأدوات الجديدة (v1.1)
- Agent: وكيل فرعي مستقل
- LSP: تحليل الكود والأخطاء
- Monitor: مراقبة الملفات والأوامر
- CronCreate/CronList/CronDelete: الجدولة
- NotebookEdit: Jupyter notebooks
- EnterPlanMode/ExitPlanMode: وضع التخطيط
- ReportFindings: تقارير المراجعة
- SendUserFile: إرسال الملفات
- PushNotification: الإشعارات
- ToolSearch: اكتشاف الأدوات
- EnterWorktree/ExitWorktree: عزل Git
```

## الخطوة 8: حفظ في الذاكرة والتقرير

احفظ في الذاكرة:
- مفتاح: "weaver_tools_version" — قيمة: "v1.1 — 44 أداة"
- مفتاح: "last_expand_date" — قيمة: تاريخ اليوم

ثم قدم تقريراً نهائياً يشمل:
1. عدد الأدوات قبل وبعد
2. المكتبات التي ثُبِّتت بنجاح
3. أي مكتبات فشل تثبيتها ولماذا
4. الخطوات التالية المقترحة
