@echo off
cd /d "%~dp0"
set VENV_PY=
for %%d in (.venv312 .venv venv env) do (
    if exist "%%d\Scripts\python.exe" (
        set VENV_PY=%%d\Scripts\python.exe
        goto :found
    )
)
set VENV_PY=python
:found
%VENV_PY% -m PyInstaller --version >nul 2>&1 || %VENV_PY% -m pip install pyinstaller -q
%VENV_PY% build_win.py
pause
