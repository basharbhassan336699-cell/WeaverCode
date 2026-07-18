"""
mcp.py — عميل MCP (Model Context Protocol) لـ WeaverCode
=========================================================

يتصل بخوادم MCP عبر stdio (JSON-RPC 2.0)، يُهيّئ الاتصال، يجلب قائمة الأدوات،
ويعرضها كأدوات WeaverCode عادية (عبر registry.register_dynamic).

الإعداد من `config/mcp.json`:
{
  "mcpServers": {
    "filesystem": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path"],
      "env": {}
    }
  }
}

كل أداة MCP تُسجَّل باسم "mcp__<server>__<tool>" وتتطلب إذناً افتراضياً.
هذا التنفيذ يدعم النقل عبر stdio (الأكثر شيوعاً لخوادم MCP المحلية).
"""

import os
import json
import asyncio
from pathlib import Path
from typing import Dict, List, Any, Optional


def _extract_resource_text(result: Optional[Dict]) -> str:
    """يستخرج نص مورد من رد resources/read (contents=[{text|blob,...}])."""
    if not result:
        return ""
    parts: List[str] = []
    for item in result.get("contents", []):
        if "text" in item and item["text"] is not None:
            parts.append(item["text"])
        elif "blob" in item:
            mime = item.get("mimeType", "application/octet-stream")
            parts.append(f"[بيانات ثنائية {mime}: {len(item.get('blob',''))} حرف base64]")
    return "\n".join(parts) if parts else json.dumps(result, ensure_ascii=False)


def _extract_prompt_text(result: Optional[Dict]) -> str:
    """يستخرج نص برومبت من رد prompts/get (messages=[{role,content}])."""
    if not result:
        return ""
    parts: List[str] = []
    for msg in result.get("messages", []):
        role = msg.get("role", "user")
        content = msg.get("content", {})
        if isinstance(content, dict):
            text = content.get("text", "")
        elif isinstance(content, list):
            text = "\n".join(b.get("text", "") for b in content
                             if isinstance(b, dict) and b.get("type") == "text")
        else:
            text = str(content)
        if text:
            parts.append(f"[{role}] {text}")
    return "\n".join(parts) if parts else json.dumps(result, ensure_ascii=False)


class MCPServer:
    """اتصال بخادم MCP واحد عبر stdio + JSON-RPC 2.0"""

    def __init__(self, name: str, command: str, args: List[str],
                 env: Optional[Dict[str, str]] = None, cwd: Optional[str] = None):
        self.name = name
        self.command = command
        self.args = args or []
        self.env = env or {}
        self.cwd = cwd
        self.proc: Optional[asyncio.subprocess.Process] = None
        self._id = 0
        self._lock = asyncio.Lock()
        self.tools: List[Dict[str, Any]] = []
        self.resources: List[Dict[str, Any]] = []
        self.prompts: List[Dict[str, Any]] = []

    async def start(self) -> None:
        full_env = dict(os.environ)
        full_env.update(self.env)
        self.proc = await asyncio.create_subprocess_exec(
            self.command, *self.args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=full_env,
            cwd=self.cwd,
        )
        await self._initialize()
        await self._load_tools()
        # resources & prompts اختياريان — الخادم قد لا يدعمهما
        await self._load_resources()
        await self._load_prompts()

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    async def _send(self, method: str, params: Optional[Dict] = None,
                    notify: bool = False) -> Optional[Dict]:
        """إرسال طلب/إشعار JSON-RPC وقراءة الرد (للطلبات)."""
        if not self.proc or not self.proc.stdin:
            raise RuntimeError(f"خادم MCP '{self.name}' غير مشغّل")
        msg: Dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        if not notify:
            msg["id"] = self._next_id()
        data = (json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8")

        async with self._lock:
            self.proc.stdin.write(data)
            await self.proc.stdin.drain()
            if notify:
                return None
            # قراءة سطور حتى نجد رداً يحمل نفس id (مع تخطّي الإشعارات)
            want = msg["id"]
            while True:
                line = await asyncio.wait_for(self.proc.stdout.readline(), timeout=30)
                if not line:
                    raise RuntimeError(f"خادم MCP '{self.name}' أغلق الاتصال")
                line = line.decode("utf-8", "replace").strip()
                if not line:
                    continue
                try:
                    resp = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if resp.get("id") == want:
                    if "error" in resp:
                        raise RuntimeError(resp["error"].get("message", "خطأ MCP"))
                    return resp.get("result", {})

    async def _initialize(self) -> None:
        await self._send("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "WeaverCode", "version": "1.5.0"},
        })
        await self._send("notifications/initialized", {}, notify=True)

    async def _load_tools(self) -> None:
        result = await self._send("tools/list", {})
        self.tools = (result or {}).get("tools", [])

    async def _load_resources(self) -> None:
        """جلب قائمة الموارد (resources) إن دعمها الخادم — فشل صامت."""
        try:
            result = await self._send("resources/list", {})
            self.resources = (result or {}).get("resources", [])
        except Exception:
            self.resources = []

    async def _load_prompts(self) -> None:
        """جلب قائمة البرومبتات (prompts) إن دعمها الخادم — فشل صامت."""
        try:
            result = await self._send("prompts/list", {})
            self.prompts = (result or {}).get("prompts", [])
        except Exception:
            self.prompts = []

    async def read_resource(self, uri: str) -> str:
        """قراءة مورد MCP عبر resources/read وإرجاع نصّه."""
        result = await self._send("resources/read", {"uri": uri})
        return _extract_resource_text(result)

    async def get_prompt(self, name: str,
                         arguments: Optional[Dict[str, Any]] = None) -> str:
        """جلب برومبت MCP عبر prompts/get وإرجاع نصّه المدموج."""
        result = await self._send("prompts/get",
                                  {"name": name, "arguments": arguments or {}})
        return _extract_prompt_text(result)

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        result = await self._send("tools/call", {
            "name": tool_name, "arguments": arguments,
        })
        # صيغة رد MCP: content = [{type:text, text:...}]
        parts = []
        for block in (result or {}).get("content", []):
            if block.get("type") == "text":
                parts.append(block.get("text", ""))
            else:
                parts.append(json.dumps(block, ensure_ascii=False))
        return "\n".join(parts) if parts else json.dumps(result, ensure_ascii=False)

    async def stop(self) -> None:
        if self.proc:
            try:
                self.proc.terminate()
                await asyncio.wait_for(self.proc.wait(), timeout=5)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass


class MCPServerSSE:
    """
    اتصال بخادم MCP عبر Server-Sent Events (SSE).
    يدعم خوادم MCP البعيدة التي تعمل على HTTP.
    """

    def __init__(self, name: str, url: str,
                 headers: Optional[Dict[str, str]] = None):
        self.name = name
        self.url = url.rstrip("/")
        self.headers = headers or {}
        self.tools: List[Dict[str, Any]] = []
        self._session_url: Optional[str] = None

    async def start(self) -> None:
        """الاتصال بخادم SSE وتهيئة الجلسة."""
        init_payload = json.dumps({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "WeaverCode", "version": "2.0.0"},
            }
        })
        result = await self._post("/", init_payload)
        if result:
            tools_payload = json.dumps({
                "jsonrpc": "2.0", "id": 2,
                "method": "tools/list", "params": {}
            })
            tools_result = await self._post("/", tools_payload)
            if tools_result:
                self.tools = (tools_result.get("result", {})
                                          .get("tools", []))

    async def _post(self, path: str, body: str) -> Optional[Dict]:
        """إرسال طلب POST عبر curl."""
        url = self.url + path
        headers_args = []
        for k, v in {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **self.headers
        }.items():
            headers_args += ["-H", f"{k}: {v}"]

        args = ["curl", "-sS", "-X", "POST", url] + headers_args + \
               ["--data-binary", "@-", "--max-time", "30"]
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, _ = await proc.communicate(input=body.encode("utf-8"))
            raw = out.decode("utf-8", "replace").strip()
            # SSE قد يُرجع "data: {...}\n\n"
            if raw.startswith("data:"):
                raw = raw.split("data:", 1)[1].strip()
            return json.loads(raw)
        except Exception:
            return None

    async def call_tool(self, tool_name: str,
                        arguments: Dict[str, Any]) -> str:
        payload = json.dumps({
            "jsonrpc": "2.0", "id": 3,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments}
        })
        result = await self._post("/", payload)
        if not result:
            return f"خطأ: لم يُستقبل رد من خادم SSE '{self.name}'"
        parts = []
        for block in (result.get("result", {}).get("content", [])):
            if block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts) if parts else json.dumps(result)

    async def stop(self) -> None:
        pass  # SSE لا يحتاج إغلاق


class MCPServerHTTP:
    """
    اتصال بخادم MCP عبر HTTP streamable (بروتوكول 2025-03-26).
    يرسل طلبات POST لنقطة نهاية واحدة ويستقبل ردوداً JSON.
    """

    def __init__(self, name: str, url: str,
                 headers: Optional[Dict[str, str]] = None,
                 api_key: Optional[str] = None):
        self.name = name
        self.url = url.rstrip("/")
        self.tools: List[Dict[str, Any]] = []
        self.headers = headers or {}
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"

    async def start(self) -> None:
        await self._initialize()
        await self._load_tools()

    async def _rpc(self, method: str,
                   params: Optional[Dict] = None,
                   req_id: int = 1) -> Optional[Dict]:
        payload = json.dumps({
            "jsonrpc": "2.0", "id": req_id,
            "method": method, "params": params or {}
        })
        headers_args = []
        for k, v in {
            "Content-Type": "application/json",
            "Accept": "application/json",
            **self.headers
        }.items():
            headers_args += ["-H", f"{k}: {v}"]
        args = (["curl", "-sS", "-X", "POST", self.url + "/mcp"] +
                headers_args +
                ["--data-binary", "@-", "--max-time", "30"])
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out, _ = await proc.communicate(input=payload.encode("utf-8"))
            data = json.loads(out.decode("utf-8", "replace"))
            if "error" in data:
                raise RuntimeError(data["error"].get("message", "خطأ HTTP MCP"))
            return data.get("result")
        except Exception:
            return None

    async def _initialize(self) -> None:
        await self._rpc("initialize", {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "WeaverCode", "version": "2.0.0"},
        })

    async def _load_tools(self) -> None:
        result = await self._rpc("tools/list", {}, req_id=2)
        self.tools = (result or {}).get("tools", [])

    async def call_tool(self, tool_name: str,
                        arguments: Dict[str, Any]) -> str:
        result = await self._rpc("tools/call",
                                  {"name": tool_name, "arguments": arguments},
                                  req_id=3)
        parts = []
        for block in (result or {}).get("content", []):
            if block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "\n".join(parts) if parts else json.dumps(result)

    async def stop(self) -> None:
        pass


class MCPManager:
    """يدير كل خوادم MCP ويربط أدواتها بسجل WeaverCode"""

    def __init__(self, config_path: Optional[Path] = None):
        if config_path is None:
            config_path = Path(__file__).resolve().parent.parent / "config" / "mcp.json"
        self.config_path = Path(config_path)
        self.servers: Dict[str, MCPServer] = {}

    def _load_config(self) -> Dict[str, Any]:
        if not self.config_path.exists():
            return {}
        try:
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    async def start_all(self, registry) -> List[str]:
        """
        تشغيل كل الخوادم المُعرّفة وتسجيل أدواتها في السجل.
        يُرجع قائمة بأسماء الأدوات المُسجّلة.
        """
        config = self._load_config()
        servers = config.get("mcpServers", {})
        registered: List[str] = []

        for name, spec in servers.items():
            if spec.get("disabled"):
                continue

            transport = spec.get("transport", "stdio").lower()
            server = None

            if transport == "sse":
                url = spec.get("url")
                if not url:
                    continue
                server = MCPServerSSE(
                    name=name, url=url,
                    headers=spec.get("headers", {}),
                )
            elif transport == "http":
                url = spec.get("url")
                if not url:
                    continue
                server = MCPServerHTTP(
                    name=name, url=url,
                    headers=spec.get("headers", {}),
                    api_key=spec.get("api_key"),
                )
            else:  # stdio (الافتراضي)
                command = spec.get("command")
                if not command:
                    continue
                server = MCPServer(
                    name=name,
                    command=command,
                    args=spec.get("args", []),
                    env=spec.get("env", {}),
                    cwd=spec.get("cwd"),
                )

            try:
                await server.start()
            except Exception:
                # خادم فاشل لا يُسقط WeaverCode
                continue
            self.servers[name] = server
            for tool in server.tools:
                registered.append(self._register_tool(registry, server, tool))
            # سجّل أداتَي الوصول للموارد/البرومبتات إن دعمها هذا الخادم
            self._register_resource_tools(registry, server)

        return [r for r in registered if r]

    def _register_resource_tools(self, registry, server) -> None:
        """يسجّل mcp__<server>__read_resource و mcp__<server>__get_prompt
        إذا كان الخادم يعرض موارد/برومبتات."""
        sname = server.name
        if getattr(server, "resources", None):
            uris = ", ".join(str(r.get("uri", "")) for r in server.resources[:10])

            async def _read(uri: str, _srv=server):
                return await _srv.read_resource(uri)

            registry.register_dynamic(
                name=f"mcp__{sname}__read_resource",
                description=(f"قراءة مورد MCP من الخادم '{sname}'. "
                             f"الموارد المتاحة: {uris}"),
                parameters={
                    "type": "object",
                    "properties": {"uri": {"type": "string",
                                           "description": "معرّف المورد (uri)"}},
                    "required": ["uri"],
                },
                fn=_read,
                requires_permission=True,
            )
        if getattr(server, "prompts", None):
            names = ", ".join(str(p.get("name", "")) for p in server.prompts[:10])

            async def _getp(name: str, arguments: Optional[Dict] = None, _srv=server):
                return await _srv.get_prompt(name, arguments or {})

            registry.register_dynamic(
                name=f"mcp__{sname}__get_prompt",
                description=(f"جلب برومبت MCP من الخادم '{sname}'. "
                             f"البرومبتات المتاحة: {names}"),
                parameters={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "اسم البرومبت"},
                        "arguments": {"type": "object",
                                      "description": "وسائط البرومبت (اختياري)"},
                    },
                    "required": ["name"],
                },
                fn=_getp,
                requires_permission=True,
            )

    def _register_tool(self, registry, server: MCPServer, tool: Dict[str, Any]) -> str:
        tool_name = tool.get("name", "")
        if not tool_name:
            return ""
        full_name = f"mcp__{server.name}__{tool_name}"
        description = tool.get("description", f"أداة MCP من {server.name}")
        parameters = tool.get("inputSchema") or {"type": "object", "properties": {}}

        async def _fn(**kwargs):
            return await server.call_tool(tool_name, kwargs)

        registry.register_dynamic(
            name=full_name,
            description=description,
            parameters=parameters,
            fn=_fn,
            requires_permission=True,
        )
        return full_name

    # ── الموارد (resources) والبرومبتات (prompts) ────────────────────────────

    def list_resources(self) -> List[Dict[str, Any]]:
        """كل الموارد من كل الخوادم، مع إضافة اسم الخادم لكل مورد."""
        out: List[Dict[str, Any]] = []
        for name, server in self.servers.items():
            for res in getattr(server, "resources", []) or []:
                entry = dict(res)
                entry["_server"] = name
                out.append(entry)
        return out

    def list_prompts(self) -> List[Dict[str, Any]]:
        """كل البرومبتات من كل الخوادم، مع إضافة اسم الخادم لكل برومبت."""
        out: List[Dict[str, Any]] = []
        for name, server in self.servers.items():
            for pr in getattr(server, "prompts", []) or []:
                entry = dict(pr)
                entry["_server"] = name
                out.append(entry)
        return out

    async def read_resource(self, uri: str,
                            server_name: Optional[str] = None) -> str:
        """قراءة مورد بالـ uri. إن حُدّد الخادم استُخدم مباشرةً، وإلا بحثنا."""
        if server_name:
            if server_name not in self.servers:
                return f"خطأ: لا يوجد خادم MCP باسم '{server_name}'."
            srv = self.servers[server_name]
            if hasattr(srv, "read_resource"):
                return await srv.read_resource(uri)
            return f"خطأ: الخادم '{server_name}' لا يدعم الموارد."
        # ابحث عن الخادم الذي يملك هذا المورد
        for name, server in self.servers.items():
            uris = [r.get("uri") for r in getattr(server, "resources", []) or []]
            if uri in uris and hasattr(server, "read_resource"):
                return await server.read_resource(uri)
        # محاولة أخيرة: أول خادم يدعم القراءة
        for server in self.servers.values():
            if hasattr(server, "read_resource"):
                try:
                    return await server.read_resource(uri)
                except Exception:
                    continue
        return f"خطأ: لم يُعثر على مورد '{uri}'."

    async def get_prompt(self, name: str,
                         arguments: Optional[Dict[str, Any]] = None,
                         server_name: Optional[str] = None) -> str:
        """جلب برومبت بالاسم من الخادم المناسب."""
        if server_name:
            if server_name not in self.servers:
                return f"خطأ: لا يوجد خادم MCP باسم '{server_name}'."
            srv = self.servers[server_name]
            if hasattr(srv, "get_prompt"):
                return await srv.get_prompt(name, arguments)
            return f"خطأ: الخادم '{server_name}' لا يدعم البرومبتات."
        for _sname, server in self.servers.items():
            names = [p.get("name") for p in getattr(server, "prompts", []) or []]
            if name in names and hasattr(server, "get_prompt"):
                return await server.get_prompt(name, arguments)
        return f"خطأ: لم يُعثر على برومبت '{name}'."

    async def stop_all(self) -> None:
        for server in self.servers.values():
            await server.stop()
        self.servers.clear()
