@echo off
REM Wrapper so this fits alongside run.bat and can be double-clicked.
REM Delegates the real work to generate-join-token.ps1 (PowerShell handles
REM retries, parsing, and file editing far more reliably than pure batch).

setlocal

set SCRIPT_DIR=%~dp0
set PS1_PATH=%SCRIPT_DIR%generate-join-token.ps1

if not exist "%PS1_PATH%" (
    echo [ERROR] Could not find generate-join-token.ps1 next to this .bat file.
    echo Expected at: %PS1_PATH%
    exit /b 1
)

where powershell >nul 2>&1
if errorlevel 1 (
    echo [ERROR] powershell.exe not found in PATH. This wrapper requires PowerShell.
    exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1_PATH%" %*
set EXITCODE=%ERRORLEVEL%

if not "%EXITCODE%"=="0" (
    echo.
    echo [FAILED] generate-join-token.ps1 exited with code %EXITCODE%.
    exit /b %EXITCODE%
)

exit /b 0