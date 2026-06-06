@echo off
setlocal
cd /d "%~dp0"

if not exist ".env" (
  copy ".env.example" ".env" >nul
)

echo Opening .env in Notepad.
echo Paste your OPENAI_API_KEY / FINMIND_TOKEN, then save the file.
echo Do not share your API keys.
echo.
notepad ".env"

