@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

rem ============================================================
rem  Restart the UAV inspection map server.
rem  Double-click this file: it kills whatever is listening on the
rem  port, then starts the server again.
rem
rem  Why: the Python code is loaded once at process start, so without
rem  a restart you get "new page, old API" (new endpoints return 404).
rem
rem  Optional first argument = port (default 8000):
rem      restart_server.bat 8123
rem ============================================================

set PORT=%~1
if "%PORT%"=="" set PORT=8000

echo ============================================================
echo   Restarting server on 127.0.0.1:%PORT%
echo ============================================================
echo.

set KILLED=0
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":%PORT%" ^| findstr "LISTENING"') do (
  echo [kill] old process on port %PORT%: PID=%%p
  taskkill /F /PID %%p >nul 2>&1
  if errorlevel 1 (
    echo [fail] could not stop PID=%%p  ^(Access denied^)
    echo        run this file as Administrator, or close it manually
  ) else (
    echo [ ok ] stopped PID=%%p
    set KILLED=1
  )
)

if "!KILLED!"=="0" echo [skip] nothing listening on port %PORT%

echo.
echo waiting for the port to be released ...
ping -n 3 127.0.0.1 >nul

echo.
echo starting server -- keep this window open, Ctrl+C to stop
echo.

cd /d "%~dp0Code"

set UAV_MAP_PORT=%PORT%

where python >nul 2>&1
if errorlevel 1 (
  echo [error] python not found in PATH. Install Python 3.10+ and tick "Add to PATH".
  pause
  exit /b 1
)

python -B project_manager.py

echo.
echo server exited.
pause
