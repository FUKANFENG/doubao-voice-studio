@echo off
setlocal
cd /d "%~dp0"
set "STUDIO_PYTHON=python"
if exist ".venv\Scripts\python.exe" set "STUDIO_PYTHON=.venv\Scripts\python.exe"
"%STUDIO_PYTHON%" -X utf8 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
endlocal
