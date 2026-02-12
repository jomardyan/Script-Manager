#!/bin/bash
# Script Manager - Quick Start Script

set -e

echo "=================================================="
echo "  Script Manager - Starting Application"
echo "=================================================="
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed"
    exit 1
fi

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "Error: Node.js is not installed"
    exit 1
fi

# Install backend dependencies if needed
if [ ! -d "backend/venv" ]; then
    echo "Installing backend dependencies..."
    cd backend
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    cd ..
    echo "✓ Backend dependencies installed"
else
    echo "✓ Backend dependencies already installed"
fi

# Install frontend dependencies if needed
if [ ! -d "frontend/node_modules" ]; then
    echo "Installing frontend dependencies..."
    cd frontend
    npm install
    cd ..
    echo "✓ Frontend dependencies installed"
else
    echo "✓ Frontend dependencies already installed"
fi

echo ""
echo "Starting services..."
echo ""

# Start backend in background
cd backend
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
fi
python3 main.py &
BACKEND_PID=$!
cd ..

echo "✓ Backend started (PID: $BACKEND_PID) on http://localhost:8000"

# Wait for backend to be ready
sleep 3

# Start frontend in background
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

echo "✓ Frontend started (PID: $FRONTEND_PID) on http://localhost:3000"
echo ""
echo "=================================================="
echo "  Application is running!"
echo "=================================================="
echo ""
echo "  Frontend: http://localhost:3000"
echo "  Backend API: http://localhost:8000"
echo "  API Docs: http://localhost:8000/docs"
echo ""
echo "  Press Ctrl+C to stop all services"
echo ""

# Trap Ctrl+C and kill both processes
trap "echo ''; echo 'Stopping services...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT

# Wait for processes
wait
