@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo ERROR: .venv was not found.
  pause
  exit /b 1
)

echo [1/3] Compile check
".venv\Scripts\python.exe" -m compileall backend tests
if errorlevel 1 goto fail

echo.
echo [2/3] Unit tests
".venv\Scripts\python.exe" -m unittest discover -s tests -v
if errorlevel 1 goto fail

echo.
echo [3/3] API smoke test
".venv\Scripts\python.exe" tests\local_smoke.py
if errorlevel 1 goto fail

echo.
echo ALL LOCAL TESTS PASSED
pause
exit /b 0

:fail
echo.
echo LOCAL TESTS FAILED
pause
exit /b 1
