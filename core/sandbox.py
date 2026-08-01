"""
sandbox.py — بيئة تنفيذ معزولة لـ WeaverCode
===============================================

يستخدم proot (بدون root) لتشغيل الكود في بيئة معزولة:
- مجلد عمل منفصل محدود في /tmp/weaver_sandbox_<id>
- timeout إلزامي (افتراضي 30 ثانية)
- لا وصول لملفات WeaverCode أو المنزل
- يُفعَّل بـ WEAVER_SANDBOX=1 (معطّل افتراضياً — لا يتغيّر أي سلوك قائم)

EN: Optional proot-based isolated execution for code WeaverCode writes.
Disabled by default; enable with WEAVER_SANDBOX=1. Never touches provider auth.

الاستخدام:
    from core.sandbox import run_sandboxed
    result = await run_sandboxed("python3 test.py", work_dir="/tmp/proj")
"""

from __future__ import annotations
import asyncio
import os
import shutil
import subprocess  # noqa: F401 (يُستخدم في بعض المسارات/الاختبارات)
import tempfile
import uuid
from pathlib import Path
from typing import Optional


# ── إعدادات ───────────────────────────────────────────────────────────────────
SANDBOX_TIMEOUT   = int(os.environ.get("WEAVER_SANDBOX_TIMEOUT", "30"))
SANDBOX_MAX_OUT   = int(os.environ.get("WEAVER_SANDBOX_MAX_OUT", "50000"))


def _flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


def is_available() -> bool:
    """هل proot مثبت على الجهاز؟"""
    return shutil.which("proot") is not None


def is_enabled() -> bool:
    """هل وضع الـ sandbox مفعَّل؟ (يُقرأ من البيئة لحظياً + يتطلّب توفّر proot)."""
    return _flag("WEAVER_SANDBOX") and is_available()


class SandboxResult:
    """نتيجة تنفيذ أمر في الـ sandbox."""
    def __init__(self, stdout: str, stderr: str,
                 returncode: int, timed_out: bool = False):
        self.stdout    = stdout
        self.stderr    = stderr
        self.returncode = returncode
        self.timed_out  = timed_out

    @property
    def output(self) -> str:
        out = self.stdout
        if self.stderr:
            out += f"\n[STDERR]: {self.stderr}"
        if self.returncode != 0:
            out += f"\n[EXIT]: {self.returncode}"
        if self.timed_out:
            out += f"\n[TIMEOUT]: تجاوز {SANDBOX_TIMEOUT} ثانية"
        return out[:SANDBOX_MAX_OUT] or "(لا مخرجات)"


def _make_sandbox_dir(work_dir: Optional[str] = None) -> Path:
    """
    ينشئ مجلد sandbox مؤقت:
    - /tmp/weaver_sandbox_<uuid>/
      ├── home/       ← مجلد المستخدم داخل الـ sandbox
      └── work/       ← مجلد العمل (نسخة من work_dir إن أُعطي)
    """
    sandbox_id = uuid.uuid4().hex[:8]
    base = Path(tempfile.gettempdir()) / f"weaver_sandbox_{sandbox_id}"
    (base / "home").mkdir(parents=True, exist_ok=True)
    work = base / "work"
    work.mkdir(parents=True, exist_ok=True)

    # انسخ ملفات مجلد العمل إن أُعطي
    if work_dir and Path(work_dir).exists():
        try:
            shutil.copytree(work_dir, str(work), dirs_exist_ok=True)
        except Exception:
            pass

    return base


def _build_proot_cmd(command: str, sandbox_base: Path,
                     timeout: int) -> list:
    """
    يبني أمر proot الكامل (عزل بلا root).

    ملاحظة العزل: لا نربط مجلد WeaverCode ولا HOME الحقيقي — فقط الأدوات
    (/usr /bin /lib …) ومجلد العمل المنسوخ (→ /work) وهوم مؤقّت (→ /root).
    """
    proot = shutil.which("proot") or "proot"
    home  = str(sandbox_base / "home")
    work  = str(sandbox_base / "work")

    cmd = [
        "timeout", str(timeout),
        proot,
        "--kill-on-exit",
    ]
    # روابط النظام الأساسية إن وُجدت (لا نفشل إن غاب أحدها)
    for p in ("/proc", "/dev", "/sys", "/usr", "/bin", "/etc",
              "/lib", "/lib64", "/lib32",
              "/data/data/com.termux/files/usr",
              "/data/data/com.termux/files/usr/lib"):
        if Path(p).exists():
            cmd += ["-b", f"{p}:{p}"]

    # ربط قاعدة Python (إن كانت خارج ما رُبط)
    import sys as _sys
    py_base = Path(_sys.executable).resolve().parent.parent
    if py_base.exists() and str(py_base) not in ("/usr", "/bin", "/"):
        cmd += ["-b", f"{py_base}:{py_base}"]

    # ربط مجلد العمل والهوم المؤقّت + مجلد العمل الحالي
    cmd += [
        "-b", f"{work}:/work",
        "-b", f"{home}:/root",
        "-w", "/work",
        "--",
        "/bin/sh", "-c", command,
    ]
    return cmd


async def run_sandboxed(
    command: str,
    work_dir: Optional[str] = None,
    timeout: int = SANDBOX_TIMEOUT,
    copy_back: bool = True,
) -> SandboxResult:
    """
    يُشغّل الأمر في بيئة معزولة بـ proot (أو احتياطياً بلا عزل إن غاب proot).

    Args:
        command:   الأمر المراد تشغيله
        work_dir:  مجلد العمل (يُنسَخ للـ sandbox ثم تُنسَخ التغييرات للخلف)
        timeout:   الحد الأقصى للتشغيل بالثواني
        copy_back: انسخ التغييرات من sandbox لـ work_dir بعد الانتهاء
    """
    if not is_available():
        # proot غير متاح — احتياطي بلا عزل (مع تحذير واضح)
        return await _run_fallback(command, work_dir, timeout)

    sandbox_base = _make_sandbox_dir(work_dir)
    try:
        proot_cmd = _build_proot_cmd(command, sandbox_base, timeout)
        try:
            proc = await asyncio.create_subprocess_exec(
                *proot_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={
                    **os.environ,
                    "HOME": "/root",
                    "PWD":  "/work",
                    "PATH": "/usr/local/bin:/usr/bin:/bin"
                            + (":/data/data/com.termux/files/usr/bin"
                               if Path("/data/data/com.termux").exists() else ""),
                },
            )
            try:
                stdout_b, stderr_b = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout + 2
                )
                timed_out = proc.returncode == 124  # timeout(1) exit code
                result = SandboxResult(
                    stdout=stdout_b.decode("utf-8", "replace"),
                    stderr=stderr_b.decode("utf-8", "replace"),
                    returncode=proc.returncode or 0,
                    timed_out=timed_out,
                )
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except Exception:
                    pass
                result = SandboxResult("", "", -1, timed_out=True)
        except FileNotFoundError:
            result = await _run_fallback(command, work_dir, timeout)

        # انسخ التغييرات للخلف
        if copy_back and work_dir:
            _copy_back(sandbox_base / "work", Path(work_dir))
        return result
    finally:
        try:
            shutil.rmtree(str(sandbox_base), ignore_errors=True)
        except Exception:
            pass


async def _run_fallback(command: str, work_dir: Optional[str],
                        timeout: int) -> SandboxResult:
    """تشغيل بدون proot كاحتياطي (مع تحذير واضح)."""
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=work_dir,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout)
            return SandboxResult(
                "[تحذير: proot غير متاح — تشغيل عادي بدون عزل]\n"
                + out.decode("utf-8", "replace"),
                err.decode("utf-8", "replace"),
                proc.returncode or 0,
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except Exception:
                pass
            return SandboxResult("", "", -1, timed_out=True)
    except Exception as e:
        return SandboxResult("", str(e), 1)


def _copy_back(sandbox_work: Path, original: Path) -> None:
    """ينسخ الملفات الجديدة/المُعدَّلة من sandbox لمجلد العمل الأصلي."""
    try:
        for item in sandbox_work.rglob("*"):
            if item.is_file():
                rel = item.relative_to(sandbox_work)
                dest = original / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(str(item), str(dest))
    except Exception:
        pass
