@echo off
setlocal
cd /d "%~dp0"
py -3.11 -m PyInstaller --noconfirm --clean --onefile --windowed --name DoubaoAuthTool --distpath dist\account-tool --specpath build\auth-tool-spec --workpath build\auth-tool --hidden-import export_auth --hidden-import Crypto.Cipher.AES auth_gui.py
exit /b %ERRORLEVEL%
