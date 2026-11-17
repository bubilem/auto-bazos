@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Vytvarim virtualni prostredi...
    python -m venv .venv || goto :err
    ".venv\Scripts\python.exe" -m pip install --quiet -r requirements.txt || goto :err
)

".venv\Scripts\python.exe" server.py --open
goto :eof

:err
echo Chyba pri priprave prostredi. Je nainstalovan Python 3.11+?
pause
