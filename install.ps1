# ============================================================================
#  WeaverCode - one-command installer (Windows / PowerShell)
#  From a new PC to a running dashboard, in ONE command:
#
#     irm https://raw.githubusercontent.com/basharbhassan336699-cell/WeaverCode/main/install.ps1 | iex
#
#  Requires Git and Python 3.8+ installed (get them from git-scm.com and python.org).
# ============================================================================
$ErrorActionPreference = "Stop"
$repo   = if ($env:WEAVER_REPO) { $env:WEAVER_REPO } else { "https://github.com/basharbhassan336699-cell/WeaverCode" }
$dir    = if ($env:WEAVER_DIR)  { $env:WEAVER_DIR }  else { Join-Path $HOME "WeaverCode" }
$branch = if ($env:WEAVER_BRANCH) { $env:WEAVER_BRANCH } else { "main" }

function Say($m){ Write-Host "WeaverCode  $m" -ForegroundColor DarkYellow }

Say "Installing..."
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw "Git is not installed. Install it from https://git-scm.com then re-run." }
$py = (Get-Command python -ErrorAction SilentlyContinue) ?? (Get-Command py -ErrorAction SilentlyContinue)
if (-not $py) { throw "Python 3.8+ is not installed. Install it from https://python.org then re-run." }

if (Test-Path (Join-Path $dir ".git")) {
  Say "Updating existing install at $dir ..."
  git -C $dir pull --ff-only origin $branch 2>$null
} else {
  Say "Downloading WeaverCode to $dir ..."
  git clone --depth 1 -b $branch $repo $dir
}
Set-Location $dir

& $py.Source "weaver-cli.py" install
Say "Starting the dashboard..."
& $py.Source "weaver-cli.py" start

Write-Host ""
Say "Done! Installed at: $dir"
Write-Host "  Use it with:  weaver start | weaver stop | weaver restore | weaver key <API_KEY> | weaver help"
Write-Host "  Open the printed URL above in your browser, then set your API key in Settings."
