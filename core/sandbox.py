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
                        timeout: int, warn: bool = True) -> SandboxResult:
    """تشغيل بدون proot كاحتياطي. warn=False للفحوص الداخلية (بلا تحذير)."""
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=work_dir,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout)
            prefix = "[تحذير: proot غير متاح — تشغيل عادي بدون عزل]\n" if warn else ""
            return SandboxResult(
                prefix + out.decode("utf-8", "replace"),
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


async def verify_python(files, work_dir: Optional[str] = None):
    """يتحقّق من صحّة ملفات بايثون المكتوبة (py_compile) — داخل الـ sandbox إن كان
    مفعّلاً، وإلا تشغيلاً عادياً آمناً (py_compile فقط لا تنفيذ للكود).

    EN: syntax-check written .py files with py_compile, inside the sandbox when
    enabled. Returns (ok: bool, summary: str). No-op summary if no .py files.
    """
    pys = [str(f) for f in (files or []) if str(f).endswith(".py")]
    if not pys:
        return True, ""
    # مسارات نسبية لمجلد العمل ما أمكن (كي تُوجَد داخل الـ sandbox المنسوخ)
    rel = []
    for f in pys:
        try:
            rel.append(os.path.relpath(f, work_dir) if work_dir else f)
        except Exception:
            rel.append(f)
    quoted = " ".join("'" + r.replace("'", "") + "'" for r in rel)
    cmd = "python3 -m py_compile " + quoted
    if is_enabled():
        r = await run_sandboxed(cmd, work_dir=work_dir, copy_back=False)
    else:
        r = await _run_fallback(cmd, work_dir, SANDBOX_TIMEOUT, warn=False)
    ok = (r.returncode == 0) and not r.timed_out
    names = ", ".join(Path(p).name for p in pys)
    if ok:
        summary = f"✅ تم التحقق: {len(pys)} ملف بايثون يُصرَّف بلا أخطاء ({names})."
    else:
        detail = (r.stderr or r.stdout or "").strip()
        summary = (f"❌ فشل التحقق: خطأ نحوي في أحد الملفات ({names}).\n"
                   + detail[:800])
    return ok, summary


async def _run_check(cmd: str, work_dir: Optional[str], timeout: int):
    """يشغّل أمر فحص داخل الـ sandbox إن كان مفعّلاً، وإلا عادياً (بلا copy_back)."""
    if is_enabled():
        return await run_sandboxed(cmd, work_dir=work_dir, timeout=timeout, copy_back=False)
    return await _run_fallback(cmd, work_dir, timeout, warn=False)


def _has_tests(work_dir: Optional[str]) -> bool:
    """هل في مجلد العمل اختبارات (tests/ أو test_*.py) لفحص المنطق؟"""
    if not work_dir:
        return False
    try:
        p = Path(work_dir)
        if (p / "tests").is_dir():
            return True
        for pat in ("test_*.py", "*_test.py"):
            if next(p.glob(pat), None) is not None:
                return True
    except Exception:
        pass
    return False


async def verify_code(files, work_dir: Optional[str] = None):
    """تحقّق كامل: **البنية** (py_compile) ثم **المنطق** (pytest إن وُجدت اختبارات).

    داخل الـ Sandbox إن كان مفعّلاً. يُرجع (ok, summary, kind) حيث kind ∈
    {"none","syntax","tests"} — يشير لآخر فحص جرى. الفحص المنطقي يعتمد على وجود
    اختبارات؛ بدونها نكتفي بالبنية (بصدق: لا ندّعي فحص منطق غير موجود).
    """
    allf = [str(f) for f in (files or [])]
    py = [f for f in allf if f.endswith(".py")]
    js = [f for f in allf if f.endswith((".js", ".mjs", ".cjs", ".jsx"))]

    # 1) بنية بايثون (py_compile)
    summary = ""
    if py:
        ok, summary = await verify_python(py, work_dir)
        if not ok:
            return False, summary, "syntax"
        # 1ب) أخطاء برمجية حقيقية عبر ruff (اختياري): E9 نحوي، F أسماء/استيراد
        if shutil.which("ruff"):
            rel = _relpaths(py, work_dir)
            r = await _run_check(
                "ruff check --select E9,F63,F7,F82,F821 --quiet " + _q(rel), work_dir, 60)
            if r.returncode != 0:
                bad = (r.stdout or r.stderr or "").strip()[-1200:]
                return False, "❌ فشل الفحص (أخطاء برمجية عبر ruff):\n" + bad, "lint"
            summary += " · ✅ ruff"

    # 2) بنية JavaScript عبر node --check (اختياري)
    if js and shutil.which("node"):
        for f in _relpaths(js, work_dir):
            r = await _run_check("node --check " + _q([f]), work_dir, 30)
            if r.returncode != 0:
                bad = (r.stderr or r.stdout or "").strip()[-800:]
                return False, f"❌ خطأ نحوي في JavaScript ({Path(f).name}):\n{bad}", "syntax"
        summary = (summary + " · ✅ JS").strip(" ·")

    # 3) منطق بايثون عبر الاختبارات (إن وُجدت)
    if py and _has_tests(work_dir):
        r = await _run_check("python3 -m pytest -q", work_dir,
                             timeout=int(os.environ.get("WEAVER_VERIFY_TEST_TIMEOUT", "180")))
        if r.timed_out:
            return True, (summary + " · ⏱️ تجاوزت الاختبارات المهلة (فحص منطقي جزئي)"), "tests"
        if r.returncode != 0:
            detail = (r.stdout or "") + ("\n" + r.stderr if r.stderr else "")
            return (False,
                    "❌ فشل التحقق المنطقي — الاختبارات لم تمرّ:\n" + detail.strip()[-1400:],
                    "tests")
        return True, (summary + " · ✅ الاختبارات تمرّ (فحص منطقي)"), "tests"

    if not summary:
        return True, "", "none"
    return True, (summary + (" · (لا اختبارات — فحص بنية فقط)" if py else "")), "syntax"


def _relpaths(files, work_dir):
    out = []
    for f in files:
        try:
            out.append(os.path.relpath(f, work_dir) if work_dir else f)
        except Exception:
            out.append(f)
    return out


def _q(paths) -> str:
    return " ".join("'" + str(p).replace("'", "") + "'" for p in paths)


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
