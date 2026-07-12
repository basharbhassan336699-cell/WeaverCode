# تشغيل WeaverCode Dashboard في الخلفية على Windows PowerShell
Set-Location "$PSScriptRoot\.."
$env:WEAVER_WEB_PORT = if ($env:WEAVER_WEB_PORT) { $env:WEAVER_WEB_PORT } else { "7878" }
Start-Process python -ArgumentList "web/server.py" -WindowStyle Hidden
Write-Host "🕸️ WeaverCode Dashboard: http://localhost:$($env:WEAVER_WEB_PORT)"
Start-Process "http://localhost:$($env:WEAVER_WEB_PORT)"
