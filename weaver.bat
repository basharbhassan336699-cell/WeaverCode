@echo off
rem WeaverCode launcher (Windows / cmd.exe)
rem Usage: weaver <command>   e.g.  weaver start
setlocal
set "ROOT=%~dp0"
where python >nul 2>nul && (set "PY=python") || (set "PY=py")
"%PY%" "%ROOT%weaver-cli.py" %*
endlocal
