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

        return [r for r in registered if r]

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

    async def stop_all(self) -> None:
        for server in self.servers.values():
            await server.stop()
        self.servers.clear()
