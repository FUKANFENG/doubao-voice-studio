@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto project_python
py -3.11 -I -c "import sys" >nul 2>&1
if errorlevel 1 goto path_python
py -3.11 -I -X utf8 export_auth.py %*
goto finished
:project_python
".venv\Scripts\python.exe" -I -X utf8 export_auth.py %*
goto finished
:path_python
python -I -X utf8 export_auth.py %*
:finished
set "EXPORT_RESULT=%ERRORLEVEL%"
if not "%EXPORT_RESULT%"=="0" echo Export failed. See the message above.
pause
exit /b %EXPORT_RESULT%
