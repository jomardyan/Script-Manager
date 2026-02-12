@echo off
REM Script Manager - Quick Start Script for Windows

echo ==================================================
echo   Script Manager - Starting Application
echo ==================================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo Error: Python is not installed
    exit /b 1
)

REM Check if Node.js is installed
node --version >nul 2>&1
if errorlevel 1 (
    echo Error: Node.js is not installed
    exit /b 1
)

REM Install backend dependencies if needed
if not exist "backend\venv" (
    echo Installing backend dependencies...
    cd backend
    python -m venv venv
    call venv\Scripts\activate
    pip install -r requirements.txt
    cd ..
    echo √ Backend dependencies installed
) else (
    echo √ Backend dependencies already installed
)

REM Install frontend dependencies if needed
if not exist "frontend\node_modules" (
    echo Installing frontend dependencies...
    cd frontend
    call npm install
    cd ..
    echo √ Frontend dependencies installed
) else (
    echo √ Frontend dependencies already installed
)

echo.
echo Starting services...
echo.

REM Start backend
cd backend
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate
)
start "Script Manager Backend" python main.py
cd ..

echo √ Backend started on http://localhost:8000

REM Wait for backend
timeout /t 3 /nobreak >nul

REM Start frontend
cd frontend
start "Script Manager Frontend" npm run dev
cd ..

echo √ Frontend started on http://localhost:3000
echo.
echo ==================================================
echo   Application is running!
echo ==================================================
echo.
echo   Frontend: http://localhost:3000
echo   Backend API: http://localhost:8000
echo   API Docs: http://localhost:8000/docs
echo.
echo   Close the terminal windows to stop services
echo.

pause
