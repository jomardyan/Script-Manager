#!/usr/bin/env bash
# Script Manager - Quick Start Script

if [ -z "${BASH_VERSION:-}" ]; then
    if command -v bash >/dev/null 2>&1; then
        exec bash "$0" "$@"
    fi
    echo "Error: bash is required to run this script."
    exit 1
fi

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=================================================="
echo "  Script Manager - Starting Application"
echo "=================================================="
echo ""

PYTHON_CMD=""
NODE_CMD=""
BACKEND_PID=""
FRONTEND_PID=""

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

hash_file() {
    local target_file="$1"
    if command_exists sha256sum; then
        sha256sum "$target_file" | awk '{print $1}'
    else
        shasum -a 256 "$target_file" | awk '{print $1}'
    fi
}

port_in_use() {
    local port="$1"
    if command_exists lsof; then
        lsof -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
    else
        ss -ltn "sport = :$port" 2>/dev/null | grep -q LISTEN
    fi
}

kill_port_listeners() {
    local port="$1"
    local label="$2"
    local pids=""

    if command_exists lsof; then
        pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
    elif command_exists fuser; then
        pids="$(fuser -n tcp "$port" 2>/dev/null || true)"
    fi

    pids="$(echo "$pids" | tr '\n' ' ' | xargs 2>/dev/null || true)"

    if [ -n "${pids// }" ]; then
        echo "Port $port is in use. Stopping existing $label process(es): $pids"
        kill $pids 2>/dev/null || true
        sleep 1
        if port_in_use "$port"; then
            echo "Force killing remaining process(es) on port $port..."
            kill -9 $pids 2>/dev/null || true
            sleep 1
        fi
    fi

    if port_in_use "$port"; then
        echo "Error: Port $port is still in use and could not be released automatically."
        exit 1
    fi

    return 0
}

cleanup() {
    echo ""
    echo "Stopping services..."
    [ -n "$BACKEND_PID" ] && kill "$BACKEND_PID" 2>/dev/null || true
    [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null || true
}

trap cleanup INT TERM

find_python() {
    if command_exists python3; then
        PYTHON_CMD="python3"
        return
    fi

    if command_exists python && python --version 2>&1 | grep -q "Python 3"; then
        PYTHON_CMD="python"
        return
    fi

    if command_exists py; then
        PYTHON_CMD="py -3"
        return
    fi
}

install_python() {
    echo "Python 3 not found. Attempting automatic installation..."
    if command_exists apt-get; then
        sudo apt-get update
        sudo apt-get install -y python3 python3-venv python3-pip
    elif command_exists dnf; then
        sudo dnf install -y python3 python3-pip
    elif command_exists yum; then
        sudo yum install -y python3 python3-pip
    elif command_exists pacman; then
        sudo pacman -S --noconfirm python python-pip
    elif [[ "$OSTYPE" == "darwin"* ]] && command_exists brew; then
        brew install python3
    else
        echo "Error: Could not auto-install Python 3 on this system."
        exit 1
    fi
}

find_node() {
    if command_exists node; then
        NODE_CMD="node"
        return
    fi
}

install_node() {
    echo "Node.js not found. Attempting automatic installation..."
    if command_exists apt-get; then
        curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
        sudo apt-get install -y nodejs
    elif command_exists dnf; then
        curl -fsSL https://rpm.nodesource.com/setup_lts.x | sudo bash -
        sudo dnf install -y nodejs
    elif command_exists yum; then
        curl -fsSL https://rpm.nodesource.com/setup_lts.x | sudo bash -
        sudo yum install -y nodejs
    elif command_exists pacman; then
        sudo pacman -S --noconfirm nodejs npm
    elif [[ "$OSTYPE" == "darwin"* ]] && command_exists brew; then
        brew install node
    else
        echo "Error: Could not auto-install Node.js on this system."
        exit 1
    fi
}

find_python
if [ -z "$PYTHON_CMD" ]; then
    install_python
    find_python
fi

if [ -z "$PYTHON_CMD" ]; then
    echo "Error: Python 3 is still unavailable after installation attempt."
    exit 1
fi

find_node
if [ -z "$NODE_CMD" ]; then
    install_node
    find_node
fi

if [ -z "$NODE_CMD" ]; then
    echo "Error: Node.js is still unavailable after installation attempt."
    exit 1
fi

echo "✓ Python found: $PYTHON_CMD"
eval "$PYTHON_CMD --version"
echo "✓ Node.js found: $NODE_CMD"
$NODE_CMD --version
echo ""

kill_port_listeners 8000 "backend"
kill_port_listeners 3000 "frontend"

echo "Checking backend environment..."
if [ ! -d "backend/venv" ]; then
    eval "$PYTHON_CMD -m venv backend/venv"
fi

BACKEND_REQUIREMENTS_HASH="$(hash_file backend/requirements.txt)"
BACKEND_HASH_FILE="backend/venv/.requirements.sha256"
INSTALLED_BACKEND_HASH=""

if [ -f "$BACKEND_HASH_FILE" ]; then
    INSTALLED_BACKEND_HASH="$(cat "$BACKEND_HASH_FILE")"
fi

if [ "$BACKEND_REQUIREMENTS_HASH" != "$INSTALLED_BACKEND_HASH" ]; then
    echo "Installing/updating backend dependencies..."
    backend/venv/bin/python -m pip install --upgrade pip
    backend/venv/bin/pip install -r backend/requirements.txt
    echo "$BACKEND_REQUIREMENTS_HASH" > "$BACKEND_HASH_FILE"
    echo "✓ Backend dependencies synced"
else
    echo "✓ Backend dependencies already up to date"
fi

echo "Validating backend password-hash backend..."
backend/venv/bin/python -c "from passlib.context import CryptContext; CryptContext(schemes=['argon2'], deprecated='auto').hash('admin')" >/dev/null
echo "✓ Backend crypto dependencies are healthy"

echo "Checking frontend dependencies..."
FRONTEND_SOURCE_HASH="$(hash_file frontend/package.json):$(hash_file frontend/package-lock.json 2>/dev/null || echo no-lock)"
FRONTEND_HASH_FILE="frontend/node_modules/.deps.sha256"
INSTALLED_FRONTEND_HASH=""

if [ -f "$FRONTEND_HASH_FILE" ]; then
    INSTALLED_FRONTEND_HASH="$(cat "$FRONTEND_HASH_FILE")"
fi

if [ ! -d "frontend/node_modules" ] || [ "$FRONTEND_SOURCE_HASH" != "$INSTALLED_FRONTEND_HASH" ]; then
    echo "Installing/updating frontend dependencies..."
    (cd frontend && npm install)
    mkdir -p frontend/node_modules
    echo "$FRONTEND_SOURCE_HASH" > "$FRONTEND_HASH_FILE"
    echo "✓ Frontend dependencies synced"
else
    echo "✓ Frontend dependencies already up to date"
fi

echo ""
echo "Starting services..."
echo ""

(cd backend && venv/bin/python main.py > ../backend.log 2>&1) &
BACKEND_PID=$!

echo "Waiting for backend health check..."
for _ in {1..30}; do
    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo "Error: Backend process exited during startup."
        echo "--- backend.log (last 60 lines) ---"
        tail -n 60 backend.log || true
        exit 1
    fi
    if command_exists curl && curl -fsS http://localhost:8000/docs >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

if ! (command_exists curl && curl -fsS http://localhost:8000/docs >/dev/null 2>&1); then
    echo "Error: Backend health check failed (http://localhost:8000/docs)."
    echo "--- backend.log (last 60 lines) ---"
    tail -n 60 backend.log || true
    exit 1
fi

echo "✓ Backend is healthy on http://localhost:8000"

(cd frontend && npm run dev > ../frontend.log 2>&1) &
FRONTEND_PID=$!

sleep 3
if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
    echo "Error: Frontend process exited during startup."
    echo "--- frontend.log (last 60 lines) ---"
    tail -n 60 frontend.log || true
    exit 1
fi

echo "✓ Frontend started (see frontend.log for exact URL)"
echo ""
echo "=================================================="
echo "  Application is running!"
echo "=================================================="
echo ""
echo "  Frontend: http://localhost:3000"
echo "  Backend API: http://localhost:8000"
echo "  API Docs: http://localhost:8000/docs"
echo ""
echo "  Backend log:  $SCRIPT_DIR/backend.log"
echo "  Frontend log: $SCRIPT_DIR/frontend.log"
echo "  Press Ctrl+C to stop all services"
echo ""

wait "$BACKEND_PID" "$FRONTEND_PID"
