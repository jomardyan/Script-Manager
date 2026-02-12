@echo off
setlocal EnableExtensions EnableDelayedExpansion
REM Script Manager - Quick Start Script for Windows

cd /d "%~dp0"

echo ==================================================
echo   Script Manager - Starting Application
echo ==================================================
echo.

set "PYTHON_CMD="
set "NODE_CMD="

python --version >nul 2>&1 && set "PYTHON_CMD=python"
if not defined PYTHON_CMD py -3 --version >nul 2>&1 && set "PYTHON_CMD=py -3"
if not defined PYTHON_CMD python3 --version >nul 2>&1 && set "PYTHON_CMD=python3"

if not defined PYTHON_CMD (
    echo Python 3 not found. Attempting automatic installation...
    winget --version >nul 2>&1 && winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
    if errorlevel 1 choco --version >nul 2>&1 && choco install python -y

    python --version >nul 2>&1 && set "PYTHON_CMD=python"
    if not defined PYTHON_CMD py -3 --version >nul 2>&1 && set "PYTHON_CMD=py -3"
    if not defined PYTHON_CMD python3 --version >nul 2>&1 && set "PYTHON_CMD=python3"
)

if not defined PYTHON_CMD (
    echo Error: Python 3 is required but could not be installed automatically.
    pause
    exit /b 1
)

node --version >nul 2>&1 && set "NODE_CMD=node"
if not defined NODE_CMD if exist "C:\Program Files\nodejs\node.exe" (
    set "NODE_CMD=C:\Program Files\nodejs\node.exe"
    set "PATH=%PATH%;C:\Program Files\nodejs"
)

if not defined NODE_CMD (
    echo Node.js not found. Attempting automatic installation...
    winget --version >nul 2>&1 && winget install -e --id OpenJS.NodeJS.LTS --silent --accept-package-agreements --accept-source-agreements
    if errorlevel 1 choco --version >nul 2>&1 && choco install nodejs-lts -y
    node --version >nul 2>&1 && set "NODE_CMD=node"
)

if not defined NODE_CMD (
    echo Error: Node.js is required but could not be installed automatically.
    pause
    exit /b 1
)

echo [OK] Python found: %PYTHON_CMD%
%PYTHON_CMD% --version
echo [OK] Node.js found: %NODE_CMD%
%NODE_CMD% --version
echo.

netstat -ano | findstr /R /C:":8000 .*LISTENING" >nul && (
    echo Error: Port 8000 is already in use.
    pause
    exit /b 1
)

netstat -ano | findstr /R /C:":3000 .*LISTENING" >nul && (
    echo Error: Port 3000 is already in use.
    pause
    exit /b 1
)

if not exist "backend\venv\Scripts\python.exe" (
    echo Creating backend virtual environment...
    %PYTHON_CMD% -m venv backend\venv
)

for /f %%H in ('powershell -NoProfile -Command "(Get-FileHash 'backend\requirements.txt' -Algorithm SHA256).Hash"') do set "BACKEND_REQ_HASH=%%H"
set "BACKEND_HASH_FILE=backend\venv\.requirements.sha256"
set "BACKEND_INSTALLED_HASH="
if exist "%BACKEND_HASH_FILE%" set /p BACKEND_INSTALLED_HASH=<"%BACKEND_HASH_FILE%"

if /I not "%BACKEND_REQ_HASH%"=="%BACKEND_INSTALLED_HASH%" (
    echo Installing/updating backend dependencies...
    backend\venv\Scripts\python -m pip install --upgrade pip
    backend\venv\Scripts\pip install -r backend\requirements.txt
    > "%BACKEND_HASH_FILE%" echo %BACKEND_REQ_HASH%
    echo [OK] Backend dependencies synced
) else (
    echo [OK] Backend dependencies already up to date
)

echo Validating backend crypto dependencies...
backend\venv\Scripts\python -c "from passlib.context import CryptContext; CryptContext(schemes=['argon2'], deprecated='auto').hash('admin')" >nul 2>&1
if errorlevel 1 (
    echo Error: backend password hashing backend is not healthy.
    pause
    exit /b 1
)

for /f %%H in ('powershell -NoProfile -Command "$a=(Get-FileHash 'frontend\package.json' -Algorithm SHA256).Hash; if(Test-Path 'frontend\package-lock.json'){$b=(Get-FileHash 'frontend\package-lock.json' -Algorithm SHA256).Hash}else{$b='NOLOCK'}; Write-Output ($a + ':' + $b)"') do set "FRONTEND_REQ_HASH=%%H"
set "FRONTEND_HASH_FILE=frontend\node_modules\.deps.sha256"
set "FRONTEND_INSTALLED_HASH="
if exist "%FRONTEND_HASH_FILE%" set /p FRONTEND_INSTALLED_HASH=<"%FRONTEND_HASH_FILE%"

if not exist "frontend\node_modules" (
    set "FRONTEND_INSTALLED_HASH="
)

if /I not "%FRONTEND_REQ_HASH%"=="%FRONTEND_INSTALLED_HASH%" (
    echo Installing/updating frontend dependencies...
    pushd frontend
    call npm install
    popd
    if not exist "frontend\node_modules" mkdir "frontend\node_modules"
    > "%FRONTEND_HASH_FILE%" echo %FRONTEND_REQ_HASH%
    echo [OK] Frontend dependencies synced
) else (
    echo [OK] Frontend dependencies already up to date
)

echo.
echo Starting services...
echo.

del /q backend.log 2>nul
del /q frontend.log 2>nul

start "" /B cmd /c "cd /d backend && call venv\Scripts\activate && python main.py >> ..\backend.log 2>&1"

echo Waiting for backend health check...
set "BACKEND_OK=0"
for /L %%I in (1,1,30) do (
    powershell -NoProfile -Command "try { $r=Invoke-WebRequest -UseBasicParsing -Uri 'http://localhost:8000/docs' -TimeoutSec 2; if($r.StatusCode -ge 200){ exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
    if not errorlevel 1 (
        set "BACKEND_OK=1"
        goto :backend_ready
    )
    timeout /t 1 /nobreak >nul
)

:backend_ready
if "%BACKEND_OK%"=="0" (
    echo Error: backend failed health check.
    echo --- backend.log (last lines) ---
    powershell -NoProfile -Command "if(Test-Path 'backend.log'){Get-Content 'backend.log' -Tail 60}"
    pause
    exit /b 1
)

echo [OK] Backend is healthy on http://localhost:8000

start "" /B cmd /c "cd /d frontend && npm run dev >> ..\frontend.log 2>&1"
timeout /t 3 /nobreak >nul

echo [OK] Frontend started (see frontend.log for exact URL)
echo.
echo ==================================================
echo   Application is running!
echo ==================================================
echo.
echo   Frontend: http://localhost:3000
echo   Backend API: http://localhost:8000
echo   API Docs: http://localhost:8000/docs
echo.
echo   Backend log:  %CD%\backend.log
echo   Frontend log: %CD%\frontend.log
echo.

pause
