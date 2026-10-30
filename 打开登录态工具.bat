@echo off
setlocal
cd /d "%~dp0"
if exist "dist\account-tool\DoubaoAuthTool.exe" (
    start "" "dist\account-tool\DoubaoAuthTool.exe"
    exit /b 0
)
if exist "dist\DoubaoAuthTool.exe" (
    start "" "dist\DoubaoAuthTool.exe"
    exit /b 0
)
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" -I -X utf8 auth_gui.py
    exit /b 0
)
py -3.11 -I -c "import tkinter" >nul 2>&1
if errorlevel 1 goto fallback
start "" pyw -3.11 -I -X utf8 auth_gui.py
exit /b 0
:fallback
python -I -X utf8 auth_gui.py
pause
