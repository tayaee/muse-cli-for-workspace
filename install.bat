@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo === Installing muse-cli-w from local repository ===

set "SCRIPT_DIR=%~dp0"
if "%SCRIPT_DIR:~-1%"=="\" set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"

:: Check if uv is installed
where uv >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Warning: 'uv' is not found in PATH.
    echo Attempting to install uv automatically via PowerShell...
    echo + powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    if %ERRORLEVEL% neq 0 (
        echo Error: Failed to install uv automatically.
        echo Please install uv manually: https://docs.astral.sh/uv/getting-started/installation/
        exit /b 1
    )
    set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;%PATH%"
)

where uv >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo Error: uv was installed but is not found in PATH for this session.
    echo Please restart your Command Prompt / PowerShell and rerun this script.
    exit /b 1
)

cd /d "%SCRIPT_DIR%"

echo Syncing dependencies into .venv...
echo + uv sync
uv sync
if %ERRORLEVEL% neq 0 (
    echo Error: uv sync failed.
    exit /b %ERRORLEVEL%
)

echo Installing muse-cli-w CLI tool (editable mode)...
echo + uv tool install -e . --force
uv tool install -e . --force
if %ERRORLEVEL% neq 0 (
    echo Error: uv tool install failed.
    exit /b %ERRORLEVEL%
)

:: Ensure current session has uv bin in PATH
set "PATH=%USERPROFILE%\.local\bin;%USERPROFILE%\.cargo\bin;%PATH%"
uv tool update-shell >nul 2>&1

where muse-cli >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo.
    echo Note: 'muse-cli' was not detected in PATH.
    echo       muse-cli-w requires muse-cli to communicate with Muse AI.
    echo       Please ensure muse-cli is installed and configured (muse-cli status).
)

echo.
echo ========================================
echo   muse-cli-w installation complete!
echo ========================================
echo.
echo Next steps:
echo   muse-cli-w --help
echo   muse-cli-w ls muse:
echo.

endlocal
