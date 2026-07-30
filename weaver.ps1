# WeaverCode launcher (Windows / PowerShell)
# Usage: .\weaver.ps1 <command>   e.g.  .\weaver.ps1 start
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = (Get-Command python -ErrorAction SilentlyContinue) ?? (Get-Command py -ErrorAction SilentlyContinue)
if (-not $py) { Write-Error "Python not found. Install Python 3.8+."; exit 1 }
& $py.Source (Join-Path $root "weaver-cli.py") @args
