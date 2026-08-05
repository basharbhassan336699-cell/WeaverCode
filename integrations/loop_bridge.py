"""
loop_bridge.py — جسر WeaverCode إلى أدوات Loop Engineering المدمجة 🕸️
====================================================================
Thin bridge to the vendored Node tools in ``vendors/loop/tools``. WeaverCode
shells out to their prebuilt CLIs (``dist/cli.js``) as separate processes, so
Node and each tool's dependencies are only needed when a tool is actually run.
Every function degrades gracefully with a clear message when Node or a tool's
dependencies are missing, and never modifies anything under ``vendors/``.

Public API:
    audit_project(path=".") -> dict          # loop-audit  → readiness report
    check_gate(files, action="commit") -> dict   # loop-gate  → pass/fail
    check_context(ledger_path) -> dict       # loop-context → continue/escalate
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Union

_ROOT = Path(__file__).resolve().parent.parent
_LOOP_TOOLS = _ROOT / "vendors" / "loop" / "tools"
_DEFAULT_GATE = _ROOT / "vendors" / "loop" / "gate.yaml"


class LoopBridgeError(RuntimeError):
    """خطأ في تشغيل أداة Loop مدمجة (Node مفقود أو تبعيات/تنفيذ فشل)."""


# ── أدوات مساعدة ─────────────────────────────────────────────────────────────

def _node() -> str:
    node = shutil.which("node")
    if not node:
        raise LoopBridgeError(
            "Node.js غير مثبّت — أدوات loop تتطلّبه. ثبّت node ثم أعد المحاولة.")
    return node


def _cli(tool: str) -> str:
    """مسار cli.js لأداة loop، مع تحقّق من وجوده."""
    cli = _LOOP_TOOLS / tool / "dist" / "cli.js"
    if not cli.exists():
        raise LoopBridgeError(f"أداة {tool} غير موجودة: {cli}")
    return str(cli)


def _run_node(tool: str, args: List[str], cwd: Optional[str] = None,
              timeout: int = 300) -> subprocess.CompletedProcess:
    cmd = [_node(), _cli(tool), *args]
    try:
        return subprocess.run(cmd, cwd=cwd, capture_output=True,
                              text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise LoopBridgeError(f"انتهت مهلة {tool} بعد {timeout}s") from e


def _parse_json(proc: subprocess.CompletedProcess, tool: str) -> Dict:
    """يحلّل مخرجات JSON من الأداة (حتى مع رمز خروج غير صفري كـ escalate)."""
    out = (proc.stdout or "").strip()
    if not out:
        raise LoopBridgeError(
            f"{tool} لم يُخرِج شيئاً "
            f"(ربّما نقص تبعيات — جرّب: cd {_LOOP_TOOLS / tool} && npm install):\n"
            + (proc.stderr or "").strip()[:400])
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        # بعض الأدوات قد تطبع سطوراً قبل الـ JSON — خذ آخر كتلة JSON
        for line in reversed(out.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        raise LoopBridgeError(
            f"تعذّر تحليل مخرجات {tool} كـ JSON:\n{out[:400]}")


# ── loop-audit ───────────────────────────────────────────────────────────────

def audit_project(path: str = ".") -> Dict:
    """يشغّل loop-audit على مشروع ويُعيد تقرير «درجة جاهزية الحلقة».

    يُرجع dict: {tool, path, exit_code, report} حيث report هو مخرجات JSON للأداة.
    """
    target = str(Path(path).expanduser())
    proc = _run_node("loop-audit", [target, "--json"])
    report = _parse_json(proc, "loop-audit")
    return {"tool": "loop-audit", "path": target,
            "exit_code": proc.returncode, "report": report}


# ── loop-gate ────────────────────────────────────────────────────────────────

def check_gate(files: Union[List[str], str], action: str = "commit",
               gate_file: Optional[str] = None,
               cwd: Optional[str] = None) -> Dict:
    """يشغّل loop-gate لتقييم إجراء مقترح مقابل سياسة gate.yaml.

    files     : قائمة (أو نصّ مفصول بفواصل) بالملفات المتغيّرة.
    action    : نوع الإجراء (commit | merge | auto-merge).
    gate_file : ملف السياسة (افتراضي: gate.yaml المدمج).
    cwd       : مجلد التشغيل (افتراضي: جذر المشروع).

    يُرجع dict: {tool, action, passed(bool), verdict(pass|fail),
                 trigger, reason, exit_code, decision(raw)}.
    """
    if isinstance(files, str):
        paths = files
    else:
        paths = ",".join(str(f) for f in files if str(f).strip())
    if not paths:
        raise LoopBridgeError("check_gate يتطلّب ملفاً واحداً على الأقل.")

    gate = gate_file or (str(_DEFAULT_GATE) if _DEFAULT_GATE.exists() else "gate.yaml")
    args = ["check", "--action", action, "--paths", paths,
            "--gate-file", gate, "--json"]
    proc = _run_node("loop-gate", args, cwd=cwd or str(_ROOT))
    decision = _parse_json(proc, "loop-gate")
    allowed = bool(decision.get("allowed"))
    return {
        "tool": "loop-gate",
        "action": action,
        "passed": allowed,
        "verdict": "pass" if allowed else "fail",
        "trigger": decision.get("trigger"),
        "reason": decision.get("reason"),
        "exit_code": proc.returncode,
        "decision": decision,
    }


# ── loop-context ─────────────────────────────────────────────────────────────

def check_context(ledger_path: str) -> Dict:
    """يشغّل loop-context (قاطِع الدائرة) على سجلّ تشغيل ويُعيد القرار.

    ledger_path : مسار ملف السجلّ JSON ({goal, attempts}).

    يُرجع dict: {tool, decision("continue"|"escalate"), exit_code, result(raw)}.
    رمز الخروج: 0 = continue، 2 = escalate.
    """
    led = Path(ledger_path).expanduser()
    if not led.exists():
        raise LoopBridgeError(f"ملف السجلّ (ledger) غير موجود: {ledger_path}")
    proc = _run_node("loop-context", ["--check", "--ledger", str(led), "--json"])
    result = _parse_json(proc, "loop-context")
    # القرار من رمز الخروج (0 continue / 2 escalate)، مع تأكيد من الـ JSON إن توفّر
    decision = "escalate" if proc.returncode == 2 else "continue"
    for key in ("decision", "verdict", "action"):
        val = result.get(key)
        if isinstance(val, str) and val.lower() in ("continue", "escalate"):
            decision = val.lower()
            break
    return {"tool": "loop-context", "decision": decision,
            "exit_code": proc.returncode, "result": result}
