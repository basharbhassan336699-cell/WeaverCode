"""
loader.py — محمّل Plugins لـ WeaverCode
يكتشف مجلدات .claude-plugin/plugin.json ويحمّل hooks وcommands وagents وskills الخاصة بكل plugin.
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional


class PluginLoader:
    """
    يكتشف plugins في:
      - plugins/<name>/.claude-plugin/plugin.json
      - ~/.weaver/plugins/<name>/.claude-plugin/plugin.json

    كل plugin يمكنه أن يحتوي على:
      - hooks/hooks.json
      - commands/*.md
      - agents/*.md
      - skills/**/SKILL.md
    """

    def __init__(self, plugins_dirs: Optional[List[Path]] = None):
        root = Path(__file__).resolve().parent.parent.parent
        self.search_dirs = plugins_dirs or [
            root / "plugins",
            Path.home() / ".weaver" / "plugins",
        ]
        self._plugins: Dict[str, Dict[str, Any]] = {}
        self.reload()

    def reload(self) -> None:
        self._plugins.clear()
        for search_dir in self.search_dirs:
            if not search_dir.exists():
                continue
            for plugin_json in search_dir.rglob(".claude-plugin/plugin.json"):
                plugin_dir = plugin_json.parent.parent
                try:
                    meta = json.loads(plugin_json.read_text(encoding="utf-8"))
                    name = meta.get("name") or plugin_dir.name
                    if meta.get("disabled"):
                        continue
                    self._plugins[name] = {
                        "meta": meta,
                        "dir": plugin_dir,
                        "hooks_file": plugin_dir / "hooks" / "hooks.json",
                        "commands_dir": plugin_dir / "commands",
                        "agents_dir": plugin_dir / "agents",
                        "skills_dir": plugin_dir / "skills",
                    }
                except Exception:
                    continue

    def names(self) -> List[str]:
        return sorted(self._plugins.keys())

    def get_all_hooks(self) -> Dict[str, List[Dict]]:
        """
        دمج hooks من كل plugins في قاموس واحد.
        يُدمج مع hooks المستخدم الرئيسية.
        """
        merged: Dict[str, List[Dict]] = {}
        for name, plugin in self._plugins.items():
            hooks_file = plugin["hooks_file"]
            if not hooks_file.exists():
                continue
            try:
                data = json.loads(hooks_file.read_text(encoding="utf-8"))
                # صيغة plugin: {"hooks": {...}} أو {"description":..., "hooks":{...}}
                hooks_data = data.get("hooks", data)
                root = str(plugin["dir"])
                for event, entries in hooks_data.items():
                    if not isinstance(entries, list):
                        continue
                    merged.setdefault(event, [])
                    for entry in entries:
                        # صيغة WeaverCode المسطّحة: {command, matcher, timeout}
                        if isinstance(entry, dict) and "command" in entry:
                            merged[event].append(self._fix_entry(entry, root))
                            continue
                        # صيغة Claude Code المتداخلة: {matcher?, hooks:[{command}]}
                        if isinstance(entry, dict) and isinstance(entry.get("hooks"), list):
                            matcher = entry.get("matcher")
                            for inner in entry["hooks"]:
                                if isinstance(inner, dict) and inner.get("command"):
                                    fixed = self._fix_entry(inner, root)
                                    if matcher and "matcher" not in fixed:
                                        fixed["matcher"] = matcher
                                    merged[event].append(fixed)
            except Exception:
                continue
        return merged

    @staticmethod
    def _fix_entry(entry: Dict, root: str) -> Dict:
        """نسخ الإدخال (محتفظاً بمفاتيحه مثل if/asyncRewake/matcher) مع استبدال
        ${CLAUDE_PLUGIN_ROOT} و${WEAVER_PLUGIN_ROOT} بالمسار الفعلي."""
        fixed = dict(entry)
        if "command" in fixed and isinstance(fixed["command"], str):
            fixed["command"] = (fixed["command"]
                                .replace("${CLAUDE_PLUGIN_ROOT}", root)
                                .replace("${WEAVER_PLUGIN_ROOT}", root))
        return fixed

    def get_all_agents(self) -> Dict[str, Path]:
        """جمع كل agents من كل plugins (المفتاح: plugin/agent)."""
        agents: Dict[str, Path] = {}
        for name, plugin in self._plugins.items():
            agents_dir = plugin.get("agents_dir") or (plugin["dir"] / "agents")
            if not agents_dir.exists():
                continue
            for md in agents_dir.glob("*.md"):
                agents[f"{name}/{md.stem}"] = md
        return agents

    def get_all_commands(self) -> Dict[str, Path]:
        """جمع كل commands من كل plugins."""
        commands: Dict[str, Path] = {}
        for name, plugin in self._plugins.items():
            cmd_dir = plugin["commands_dir"]
            if not cmd_dir.exists():
                continue
            for md in cmd_dir.glob("*.md"):
                cmd_name = f"{name}/{md.stem}"
                commands[cmd_name] = md
        return commands

    def get_plugin(self, name: str) -> Optional[Dict[str, Any]]:
        return self._plugins.get(name)
