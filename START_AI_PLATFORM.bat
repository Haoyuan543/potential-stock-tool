@echo off
setlocal
cd /d "%~dp0"

set PORT=8011
set HOST=127.0.0.1

if not exist ".venv\Scripts\python.exe" (
  echo ERROR: .venv was not found.
  echo Please install Python dependencies first.
  pause
  exit /b 1
)

if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo Created .env from .env.example.
  echo Please run CONFIG_API_KEYS.bat and fill in OPENAI_API_KEY.
  pause
)

echo Starting AI Alpha Research Platform on http://%HOST%:%PORT%
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "$conns = Get-NetTCPConnection -LocalPort %PORT% -State Listen -ErrorAction SilentlyContinue; foreach ($conn in $conns) { Write-Host ('Stopping old port %PORT% PID ' + $conn.OwningProcess); Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue }"

start "AI Alpha Backend" cmd /k ".venv\Scripts\python.exe -m uvicorn backend.main:app --host %HOST% --port %PORT% 1>>uvicorn-%PORT%.out.log 2>>uvicorn-%PORT%.err.log"

timeout /t 5 /nobreak >nul
echo Health check:
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { (Invoke-WebRequest -UseBasicParsing http://%HOST%:%PORT%/health).Content } catch { $_.Exception.Message }"
start "" "http://%HOST%:%PORT%"

echo Browser should open at http://%HOST%:%PORT%
echo If the page does not open, copy the URL above into your browser.
echo.
pause

