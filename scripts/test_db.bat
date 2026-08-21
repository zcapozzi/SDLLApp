@echo off
REM Test Database Management Script for SDLL CI/CD
REM Usage: test_db.bat [command]
REM
REM Commands:
REM   setup     - Create the test database
REM   reset     - Drop and recreate test database
REM   migrate   - Create tables in test database
REM   status    - Check if test database exists
REM   shell     - Open MySQL shell to test database
REM   full      - Run setup + migrate (full initialization)
REM   dump-prod - Download a MySQL dump from production
REM   restore   - Restore a dump file to local railway_replica database
REM   sync-prod - Download from prod and restore locally (dump-prod + restore)

setlocal

REM Database credentials (same as .env)
set DB_USER=lrp_master
set "DB_PASS=83jfd&fhd2340fjeSTdsfhdsa."
set DB_HOST=localhost
set DB_NAME=sdll_test
set DB_PROD=railway_replica
set DUMP_FILE=railway_backup.sql

REM Parse command
set CMD=%1
if "%CMD%"=="" set CMD=status

if "%CMD%"=="setup" goto setup
if "%CMD%"=="reset" goto reset
if "%CMD%"=="migrate" goto migrate
if "%CMD%"=="status" goto status
if "%CMD%"=="shell" goto shell
if "%CMD%"=="full" goto full
if "%CMD%"=="dump-prod" goto dump_prod
if "%CMD%"=="restore" goto restore
if "%CMD%"=="sync-prod" goto sync_prod
if "%CMD%"=="help" goto help

echo Unknown command: %CMD%
goto help

:setup
echo Creating test database %DB_NAME%...
mysql -u %DB_USER% -p"%DB_PASS%" -h %DB_HOST% -e "CREATE DATABASE IF NOT EXISTS %DB_NAME%; SHOW DATABASES LIKE '%DB_NAME%';"
if %ERRORLEVEL% EQU 0 (
    echo Test database created successfully.
) else (
    echo Failed to create test database.
    exit /b 1
)
goto end

:reset
echo Dropping and recreating test database %DB_NAME%...
mysql -u %DB_USER% -p"%DB_PASS%" -h %DB_HOST% -e "DROP DATABASE IF EXISTS %DB_NAME%; CREATE DATABASE %DB_NAME%;"
if %ERRORLEVEL% EQU 0 (
    echo Test database reset successfully.
) else (
    echo Failed to reset test database.
    exit /b 1
)
goto end

:migrate
echo Creating tables in test database...
python -c "from dotenv import load_dotenv; load_dotenv('.env'); from app import create_app, db; app = create_app('testing'); ctx = app.app_context(); ctx.push(); db.create_all(); print('Tables created successfully.')"
if %ERRORLEVEL% EQU 0 (
    echo Migration completed.
) else (
    echo Migration failed.
    exit /b 1
)
goto end

:full
echo Running full initialization (reset + migrate)...
call :reset
if %ERRORLEVEL% NEQ 0 exit /b 1
call :migrate
goto end

:status
echo Checking test database status...
mysql -u %DB_USER% -p"%DB_PASS%" -h %DB_HOST% -e "SHOW DATABASES LIKE '%DB_NAME%';" 2>nul
if %ERRORLEVEL% EQU 0 (
    echo Database connection successful.
    mysql -u %DB_USER% -p"%DB_PASS%" -h %DB_HOST% -e "SELECT COUNT(*) as table_count FROM information_schema.tables WHERE table_schema = '%DB_NAME%';"
) else (
    echo Failed to connect to database.
    exit /b 1
)
goto end

:shell
echo Opening MySQL shell to %DB_NAME%...
mysql -u %DB_USER% -p"%DB_PASS%" -h %DB_HOST% %DB_NAME%
goto end

:dump_prod
echo.
echo ============================================================
echo Downloading MySQL dump from production...
echo ============================================================
echo.
echo This reads credentials from .env.prod and creates %DUMP_FILE%
echo.
python -c "import os; from dotenv import load_dotenv; load_dotenv('.env.prod'); h=os.environ.get('MYSQL_HOST',''); p=os.environ.get('MYSQL_PORT','3306'); u=os.environ.get('MYSQL_USER',''); pw=os.environ.get('MYSQL_PASSWORD',''); db=os.environ.get('MYSQL_DB','railway'); print(f'Host: {h}:{p}'); print(f'Database: {db}'); import subprocess; cmd=f'mysqldump -h {h} -P {p} -u {u} -p{pw} --routines --triggers --single-transaction {db}'; result=subprocess.run(cmd, shell=True, capture_output=True, text=True); open('railway_backup.sql','w',encoding='utf-8').write(result.stdout); print(f'Dump saved to railway_backup.sql ({len(result.stdout)} bytes)') if result.returncode==0 else print(f'Error: {result.stderr}')"
if %ERRORLEVEL% EQU 0 (
    echo.
    echo Production dump completed: %DUMP_FILE%
    for %%A in (%DUMP_FILE%) do echo File size: %%~zA bytes
) else (
    echo.
    echo Failed to dump production database.
    echo Make sure .env.prod exists with valid credentials.
    exit /b 1
)
goto end

:restore
echo.
echo ============================================================
echo Restoring dump to local %DB_PROD% database...
echo ============================================================
echo.
if not exist %DUMP_FILE% (
    echo Error: %DUMP_FILE% not found.
    echo Run 'test_db.bat dump-prod' first to download from production.
    exit /b 1
)
echo Step 1: Dropping and recreating %DB_PROD%...
mysql -u %DB_USER% -p"%DB_PASS%" -h %DB_HOST% -e "DROP DATABASE IF EXISTS %DB_PROD%; CREATE DATABASE %DB_PROD%;"
if %ERRORLEVEL% NEQ 0 (
    echo Failed to recreate database.
    exit /b 1
)
echo Step 2: Restoring from %DUMP_FILE%...
mysql -u %DB_USER% -p"%DB_PASS%" -h %DB_HOST% %DB_PROD% < %DUMP_FILE%
if %ERRORLEVEL% EQU 0 (
    echo.
    echo Restore completed successfully!
    echo Database %DB_PROD% now mirrors production.
    echo.
    echo To use this database, set in .env:
    echo   MYSQL_DB=railway_replica
) else (
    echo.
    echo Restore failed.
    exit /b 1
)
goto end

:sync_prod
echo.
echo ============================================================
echo Syncing local database with production...
echo ============================================================
echo.
echo This will:
echo   1. Download a fresh dump from production
echo   2. Restore it to local %DB_PROD% database
echo.
call :dump_prod
if %ERRORLEVEL% NEQ 0 exit /b 1
call :restore
goto end

:help
echo.
echo Test Database Management Script
echo ================================
echo Usage: test_db.bat [command]
echo.
echo Test Database Commands:
echo   setup     - Create the test database (if not exists)
echo   reset     - Drop and recreate test database (WARNING: destroys data)
echo   migrate   - Create tables in test database
echo   full      - Reset + migrate (complete fresh setup)
echo   status    - Check database connection and table count
echo   shell     - Open MySQL shell to test database
echo.
echo Production Sync Commands:
echo   dump-prod - Download MySQL dump from production (requires .env.prod)
echo   restore   - Restore railway_backup.sql to local railway_replica database
echo   sync-prod - Download from prod + restore locally (combines both)
echo.
echo   help      - Show this help message
echo.
echo Examples:
echo   test_db.bat setup      # Create test database
echo   test_db.bat full       # Fresh reset with tables
echo   test_db.bat status     # Check connection
echo   test_db.bat sync-prod  # Mirror production locally for debugging
echo.
echo Production Sync Workflow:
echo   1. Ensure .env.prod has valid Railway credentials
echo   2. Run: test_db.bat sync-prod
echo   3. Set MYSQL_DB=railway_replica in .env to use local copy
echo   4. Debug with exact production data
echo.
goto end

:end
endlocal
