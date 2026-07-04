@echo off
setlocal
REM ---------- LeadLens launcher (Windows) ----------
cd /d "%~dp0backend"

REM Find a working Python (py launcher first, then python)
set "PY=py -3"
%PY% -c "import sys" >nul 2>&1 || set "PY=python"
%PY% -c "import sys" >nul 2>&1 || (
    echo Could not find Python. Install Python 3 and re-run.
    pause
    exit /b 1
)

echo Installing Python dependencies (quick after first run)...
%PY% -m pip install -q -r requirements.txt

REM Kill any previous LeadLens server still holding port 8787
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8787 ^| findstr LISTENING') do taskkill /f /pid %%a >nul 2>&1

echo.
echo Starting LeadLens at http://127.0.0.1:8787
echo (Keep this window open. Press Ctrl+C to stop.)
echo.
start "" http://127.0.0.1:8787
%PY% -m uvicorn main:app --host 127.0.0.1 --port 8787
pause
