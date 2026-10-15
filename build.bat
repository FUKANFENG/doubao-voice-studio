@echo off
setlocal
cd /d "%~dp0"
call npm run build --prefix frontend
if errorlevel 1 exit /b 1
echo Frontend built in frontend\dist.
endlocal
