@echo off
REM Script Manager Docker Helper for Windows
REM Provides easy commands for Docker Compose operations

setlocal enabledelayedexpansion

REM Get script directory
for %%i in ("%~dp0.") do set "SCRIPT_DIR=%%~fi"
cd /d "%SCRIPT_DIR%"

REM Check for help
if "%1"=="" goto show_help
if "%1"=="help" goto show_help
if "%1"=="-h" goto show_help
if "%1"=="--help" goto show_help

REM Check Docker installation
where docker >nul 2>nul
if errorlevel 1 (
    echo Error: Docker is not installed
    exit /b 1
)

where docker-compose >nul 2>nul
if errorlevel 1 (
    echo Error: Docker Compose is not installed
    exit /b 1
)

REM Command routing
if "%1"=="up" goto cmd_up
if "%1"=="down" goto cmd_down
if "%1"=="restart" goto cmd_restart
if "%1"=="build" goto cmd_build
if "%1"=="logs" goto cmd_logs
if "%1"=="logs-backend" goto cmd_logs_backend
if "%1"=="logs-frontend" goto cmd_logs_frontend
if "%1"=="shell-backend" goto cmd_shell_backend
if "%1"=="shell-frontend" goto cmd_shell_frontend
if "%1"=="status" goto cmd_status
if "%1"=="health" goto cmd_health
if "%1"=="clean" goto cmd_clean
if "%1"=="prod" goto cmd_prod
if "%1"=="prod-down" goto cmd_prod_down
if "%1"=="--compose" goto cmd_compose

echo Error: Unknown command: %1
echo.
goto show_help

:show_help
echo.
echo Script Manager Docker Helper
echo.
echo Usage:
echo   docker.bat ^<command^> [options]
echo.
echo Commands:
echo   up              Start the application (development^)
echo   down            Stop the application
echo   restart         Restart the application
echo   build           Build Docker images
echo   logs            View application logs
echo   logs-backend    View backend logs only
echo   logs-frontend   View frontend logs only
echo   shell-backend   Access backend shell
echo   shell-frontend  Access frontend shell
echo   clean           Remove containers and volumes
echo   status          Show container status
echo   health          Check application health
echo   prod            Start with production config (includes Nginx^)
echo   prod-down       Stop production environment
echo.
echo Examples:
echo   docker.bat up
echo   docker.bat logs -f
echo   docker.bat shell-backend
echo   docker.bat prod
echo   docker.bat down
echo.
exit /b 0

:cmd_up
echo Starting Script Manager (development^)...
docker-compose up -d
if errorlevel 1 goto error
echo.
echo Application started
echo Frontend:    http://localhost:3000
echo Backend API: http://localhost:8000
echo API Docs:    http://localhost:8000/docs
echo.
timeout /t 2 /nobreak
call :cmd_health
exit /b 0

:cmd_down
echo Stopping Script Manager...
docker-compose down
if errorlevel 1 goto error
echo Application stopped
exit /b 0

:cmd_restart
call :cmd_down
call :cmd_up
exit /b 0

:cmd_build
echo Building Docker images...
docker-compose build
if errorlevel 1 goto error
echo Images built successfully
exit /b 0

:cmd_logs
shift
docker-compose logs %*
exit /b %errorlevel%

:cmd_logs_backend
shift
docker-compose logs %* backend
exit /b %errorlevel%

:cmd_logs_frontend
shift
docker-compose logs %* frontend
exit /b %errorlevel%

:cmd_shell_backend
echo Accessing backend shell...
docker-compose exec backend bash
exit /b %errorlevel%

:cmd_shell_frontend
echo Accessing frontend shell...
docker-compose exec frontend sh
exit /b %errorlevel%

:cmd_status
echo Container status:
docker-compose ps
exit /b %errorlevel%

:cmd_health
echo Checking application health...
echo.
REM Check backend
for /f "tokens=*" %%i in ('curl -s http://localhost:8000/health 2^>nul') do set "response=%%i"
if defined response (
    echo [OK] Backend is healthy (http://localhost:8000)
) else (
    echo [!] Backend is starting... (check logs with 'docker.bat logs-backend')
)

REM Check frontend
for /f "tokens=*" %%i in ('curl -s http://localhost:3000 2^>nul') do set "response=%%i"
if defined response (
    echo [OK] Frontend is healthy (http://localhost:3000)
) else (
    echo [!] Frontend is starting... (check logs with 'docker.bat logs-frontend')
)
exit /b 0

:cmd_clean
setlocal
set /p confirm="This will remove containers and data volumes. Are you sure? (y/N) "
if /i not "%confirm%"=="y" (
    echo Cleanup cancelled
    exit /b 0
)
echo Cleaning up Docker resources...
docker-compose down -v
if errorlevel 1 goto error
echo Cleanup complete
exit /b 0

:cmd_prod
echo Starting Script Manager (production with Nginx^)...
docker-compose -f docker-compose.prod.yml up -d
if errorlevel 1 goto error
echo.
echo Application started
echo Frontend: http://localhost
echo API:      http://localhost/api
echo.
timeout /t 2 /nobreak
call :cmd_health
exit /b 0

:cmd_prod_down
echo Stopping Script Manager (production^)...
docker-compose -f docker-compose.prod.yml down
if errorlevel 1 goto error
echo Application stopped
exit /b 0

:cmd_compose
setlocal enabledelayedexpansion
shift
docker-compose %*
exit /b %errorlevel%

:error
echo.
echo Error: Command failed with exit code !errorlevel!
exit /b 1
