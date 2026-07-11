"""
registry.py — سجل الأدوات المدمجة في WeaverCode
يماثل الأدوات الـ 46 المدمجة في Claude Code لكن بشكل مستقل
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

    def to_schema(self) -> Dict:
        """تحويل لصيغة OpenAI tool schema"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class ToolRegistry:
    """سجل جميع الأدوات المتاحة"""

    def __init__(self, work_dir: Optional[str] = None):
        self.work_dir = work_dir or os.getcwd()
        self._tools: Dict[str, Tool] = {}
        self._register_all()

    def _register_all(self):
        """تسجيل جميع الأدوات المدمجة"""

        # ── الملفات ─────────────────────────────────────────────────────────

        self._add(Tool(
            name="Read",
            description="قراءة محتوى ملف مع أرقام الأسطر. استخدم مسارات مطلقة دائماً.",
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
                },
                "required": ["command"],
            },
            fn=self._bash,
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
            description="رفع التغييرات لـ GitHub",
            parameters={
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string"},
                    "branch": {"type": "string", "default": "main"},
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

    # ── تنفيذ الأدوات ────────────────────────────────────────────────────────

    def _add(self, tool: Tool):
        self._tools[tool.name] = tool

    def get_schema(self) -> List[Dict]:
        return [t.to_schema() for t in self._tools.values()]

    async def execute(self, name: str, args: Dict[str, Any]) -> Any:
        if name not in self._tools:
            return f"خطأ: الأداة '{name}' غير موجودة"
        tool = self._tools[name]
        result = tool.fn(**args)
        if asyncio.iscoroutine(result):
            return await result
        return result

    # ── تنفيذ كل أداة ────────────────────────────────────────────────────────

    def _read(self, path: str, offset: int = 0, limit: Optional[int] = None) -> str:
        try:
            p = Path(path)
            if not p.exists():
                return f"الملف غير موجود: {path}"
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
            if offset:
                lines = lines[offset:]
            if limit:
                lines = lines[:limit]
            return "\n".join(f"{i+offset+1}\t{l}" for i, l in enumerate(lines))
        except Exception as e:
            return f"خطأ في قراءة {path}: {e}"

    def _write(self, path: str, content: str) -> str:
        try:
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return f"✅ تم الكتابة إلى {path} ({len(content)} حرف)"
        except Exception as e:
            return f"خطأ في الكتابة: {e}"

    def _edit(self, path: str, old_string: str, new_string: str, replace_all: bool = False) -> str:
        try:
            p = Path(path)
            content = p.read_text(encoding="utf-8")
            if old_string not in content:
                return f"لم يُعثر على النص المطلوب في {path}"
            count = content.count(old_string)
            if count > 1 and not replace_all:
                return f"النص موجود {count} مرات. استخدم replace_all=true أو أضف سياقاً أكثر."
            new_content = content.replace(old_string, new_string)
            p.write_text(new_content, encoding="utf-8")
            return f"✅ تم التعديل في {path}"
        except Exception as e:
            return f"خطأ في التعديل: {e}"

    def _glob(self, pattern: str, base_dir: Optional[str] = None) -> str:
        try:
            base = base_dir or self.work_dir
            files = list(_glob.glob(os.path.join(base, pattern), recursive=True))
            files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
            if not files:
                return "لا توجد ملفات تطابق النمط"
            return "\n".join(files[:100])
        except Exception as e:
            return f"خطأ: {e}"

    def _grep(self, pattern: str, path: Optional[str] = None, file_glob: Optional[str] = None,
               output_mode: str = "content", ignore_case: bool = False) -> str:
        try:
            search_path = path or self.work_dir
            flags = re.IGNORECASE if ignore_case else 0
            results = []
            if os.path.isfile(search_path):
                files = [search_path]
            else:
                file_pattern = os.path.join(search_path, f"**/{file_glob or '*'}")
                files = _glob.glob(file_pattern, recursive=True)
                files = [f for f in files if os.path.isfile(f)]

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

    def _bash(self, command: str, timeout: int = 120, work_dir: Optional[str] = None) -> str:
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

    async def _web_fetch(self, url: str, extract_prompt: str = "") -> str:
        try:
            import httpx
            async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
                resp = await client.get(url, headers={"User-Agent": "WeaverCode/1.0"})
                text = resp.text[:50000]
                # إزالة HTML بسيطة
                text = re.sub(r"<[^>]+>", " ", text)
                text = re.sub(r"\s+", " ", text)
                return text[:10000]
        except Exception as e:
            return f"خطأ في جلب {url}: {e}"

    async def _web_search(self, query: str, max_results: int = 5) -> str:
        try:
            import httpx
            url = f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}"
            async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
                resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0"})
                text = resp.text
            results = re.findall(r'class="result__title"[^>]*>.*?<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', text, re.S)
            output = []
            for link, title in results[:max_results]:
                title_clean = re.sub(r"<[^>]+>", "", title).strip()
                output.append(f"• {title_clean}\n  {link}")
            return "\n".join(output) if output else "لا توجد نتائج"
        except Exception as e:
            return f"خطأ في البحث: {e}"

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

    def _git_commit(self, message: str, repo_path: Optional[str] = None, add_all: bool = True) -> str:
        cmds = []
        if add_all:
            cmds.append("git add -A")
        cmds.append(f'git commit -m "{message}"')
        return self._bash(" && ".join(cmds), work_dir=repo_path)

    def _git_push(self, repo_path: Optional[str] = None, branch: str = "main", remote: str = "origin") -> str:
        return self._bash(f"git push {remote} {branch}", work_dir=repo_path, timeout=60)

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
