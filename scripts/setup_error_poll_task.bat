@echo off
REM Setup Windows Scheduled Task to poll for production errors
REM Run this script once to create the scheduled task

set SCRIPT_PATH=%~dp0poll_errors.py

echo ===============================================
echo SDLL Error Poll - Scheduled Task Setup
echo ===============================================
echo.

echo Script path: %SCRIPT_PATH%
echo.

REM Check if task already exists
schtasks /query /tn "SDLL Error Poll" >nul 2>&1
if %errorlevel% equ 0 (
    echo Task "SDLL Error Poll" already exists.
    echo.
    choice /C YN /M "Delete and recreate"
    if errorlevel 2 (
        echo Keeping existing task.
        goto :status
    )
    schtasks /delete /tn "SDLL Error Poll" /f
    echo Deleted existing task.
)

echo Creating scheduled task "SDLL Error Poll"...
echo.

REM Create task that runs every 5 minutes
REM Uses pythonw to run silently without console window
schtasks /create /tn "SDLL Error Poll" ^
    /tr "pythonw \"%SCRIPT_PATH%\"" ^
    /sc minute /mo 5 ^
    /ru %USERNAME% ^
    /f

if %errorlevel% equ 0 (
    echo.
    echo ===============================================
    echo SUCCESS: Task created!
    echo ===============================================
    echo.
    echo Task runs silently in background using pythonw.
) else (
    echo.
    echo ERROR: Failed to create task.
    echo Try running this script as Administrator.
    goto :end
)

:status
echo.
echo Current task status:
schtasks /query /tn "SDLL Error Poll" /v /fo list | findstr /i "Status Next"
echo.
echo ===============================================
echo Commands:
echo ===============================================
echo   Check status:   schtasks /query /tn "SDLL Error Poll"
echo   Run now:        schtasks /run /tn "SDLL Error Poll"
echo   Stop:           schtasks /end /tn "SDLL Error Poll"
echo   Delete:         schtasks /delete /tn "SDLL Error Poll" /f
echo   Manual poll:    python scripts\poll_errors.py
echo   View status:    python scripts\poll_errors.py --status
echo.

:end
pause
