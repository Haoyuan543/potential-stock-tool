@echo off
setlocal
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ports = @(8000,8010); foreach ($port in $ports) { $conns = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue; foreach ($conn in $conns) { Write-Host ('Stopping port ' + $port + ' PID ' + $conn.OwningProcess); Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue } }; Write-Host 'Done.'"

pause

