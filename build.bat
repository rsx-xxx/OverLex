@echo off
cd /d "%~dp0"

:: Ищем venv
set VENV_PY=
for %%d in (.venv312 .venv venv env .env) do (
    if exist "%%d\Scripts\python.exe" (
        set VENV_PY=%%d\Scripts\python.exe
        set VENV_PIP=%%d\Scripts\pip.exe
        echo [+] venv: %%d
        goto :found
    )
)
set VENV_PY=python
set VENV_PIP=pip
:found

:: Ставим PyInstaller в venv если нет
%VENV_PY% -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo [+] Устанавливаю PyInstaller в venv...
    %VENV_PY% -m pip install pyinstaller --quiet
)

%VENV_PY% build.py
pause
