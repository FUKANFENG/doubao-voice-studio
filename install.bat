@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    python -m venv .venv
    if errorlevel 1 exit /b 1
)
".venv\Scripts\python.exe" -m pip install -r backend\requirements.txt
if errorlevel 1 exit /b 1
call npm ci --prefix frontend
if errorlevel 1 exit /b 1
echo Dependencies installed. Configure auth.json, then run build.bat and start.bat.
endlocal
