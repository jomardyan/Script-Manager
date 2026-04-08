.PHONY: help install install-backend install-frontend clean test test-backend lint build build-backend build-frontend docker-up docker-down docker-prod docker-logs docker-clean dev-backend dev-frontend dev start check health validate

# Default target
.DEFAULT_GOAL := help

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
YELLOW := \033[0;33m
RED := \033[0;31m
NC := \033[0m # No Color

##@ General

help: ## Display this help message
	@echo "$(BLUE)Script Manager - Makefile Commands$(NC)"
	@echo ""
	@awk 'BEGIN {FS = ":.*##"; printf "Usage:\n  make $(GREEN)<target>$(NC)\n"} /^[a-zA-Z_0-9-]+:.*?##/ { printf "  $(GREEN)%-20s$(NC) %s\n", $$1, $$2 } /^##@/ { printf "\n$(BLUE)%s$(NC)\n", substr($$0, 5) } ' $(MAKEFILE_LIST)

##@ Installation

install: install-backend install-frontend ## Install all dependencies (backend + frontend)
	@echo "$(GREEN)✓ All dependencies installed successfully$(NC)"

install-backend: ## Install backend Python dependencies
	@echo "$(BLUE)Installing backend dependencies...$(NC)"
	cd backend && pip install -r requirements.txt
	pip install pytest pytest-asyncio httpx
	@echo "$(GREEN)✓ Backend dependencies installed$(NC)"

install-frontend: ## Install frontend Node.js dependencies
	@echo "$(BLUE)Installing frontend dependencies...$(NC)"
	cd frontend && npm install
	@echo "$(GREEN)✓ Frontend dependencies installed$(NC)"

##@ Development

dev-backend: ## Run backend development server
	@echo "$(BLUE)Starting backend development server...$(NC)"
	cd backend && python main.py

dev-frontend: ## Run frontend development server
	@echo "$(BLUE)Starting frontend development server...$(NC)"
	cd frontend && npm run dev

dev: ## Run both backend and frontend in development mode (requires tmux or run in separate terminals)
	@echo "$(YELLOW)Note: Run 'make dev-backend' and 'make dev-frontend' in separate terminals$(NC)"
	@echo "Or use the start.sh script for automated multi-process startup"

start: ## Quick start using existing start.sh script
	@echo "$(BLUE)Starting Script Manager...$(NC)"
	./start.sh

##@ Testing

test: test-backend ## Run all tests
	@echo "$(GREEN)✓ All tests completed$(NC)"

test-backend: ## Run backend tests with pytest
	@echo "$(BLUE)Running backend tests...$(NC)"
	cd backend && python -m pytest tests -v
	@echo "$(GREEN)✓ Backend tests passed$(NC)"

test-coverage: ## Run backend tests with coverage report
	@echo "$(BLUE)Running backend tests with coverage...$(NC)"
	cd backend && python -m pytest tests --cov=app --cov-report=html --cov-report=term
	@echo "$(GREEN)✓ Coverage report generated in backend/htmlcov/$(NC)"

##@ Code Quality

lint: ## Run code quality checks (Python syntax check)
	@echo "$(BLUE)Running Python syntax check...$(NC)"
	python -m compileall backend
	@echo "$(GREEN)✓ Python syntax check passed$(NC)"

format: ## Format Python code with black (if installed)
	@echo "$(BLUE)Formatting Python code...$(NC)"
	@which black > /dev/null && (cd backend && black .) || echo "$(YELLOW)black not installed, skipping$(NC)"

check: lint test ## Run all checks (lint + test)
	@echo "$(GREEN)✓ All checks passed$(NC)"

validate: lint test build ## Validate everything (lint + test + build)
	@echo "$(GREEN)✓ Full validation passed$(NC)"

##@ Building

build: build-frontend ## Build production assets
	@echo "$(GREEN)✓ Build completed$(NC)"

build-backend: ## Check backend syntax (Python doesn't need building)
	@echo "$(BLUE)Validating backend syntax...$(NC)"
	python -m compileall backend
	@echo "$(GREEN)✓ Backend validated$(NC)"

build-frontend: ## Build frontend for production
	@echo "$(BLUE)Building frontend...$(NC)"
	cd frontend && npm run build
	@echo "$(GREEN)✓ Frontend built successfully$(NC)"

##@ Docker

docker-up: ## Start Docker containers (development mode)
	@echo "$(BLUE)Starting Docker containers...$(NC)"
	docker-compose up -d
	@echo "$(GREEN)✓ Containers started$(NC)"
	@echo "Frontend: http://localhost:3000"
	@echo "Backend: http://localhost:8000"
	@echo "API Docs: http://localhost:8000/docs"

docker-down: ## Stop Docker containers
	@echo "$(BLUE)Stopping Docker containers...$(NC)"
	docker-compose down
	@echo "$(GREEN)✓ Containers stopped$(NC)"

docker-prod: ## Start Docker containers (production mode with Nginx)
	@echo "$(BLUE)Starting Docker containers in production mode...$(NC)"
	docker-compose -f docker-compose.prod.yml up -d
	@echo "$(GREEN)✓ Production containers started$(NC)"
	@echo "Application: http://localhost"

docker-logs: ## Show Docker container logs
	docker-compose logs -f

docker-logs-backend: ## Show backend container logs
	docker-compose logs -f backend

docker-logs-frontend: ## Show frontend container logs
	docker-compose logs -f frontend

docker-build: ## Build Docker images
	@echo "$(BLUE)Building Docker images...$(NC)"
	docker-compose build
	@echo "$(GREEN)✓ Images built$(NC)"

docker-clean: ## Remove Docker containers, volumes, and images
	@echo "$(YELLOW)Cleaning Docker resources...$(NC)"
	docker-compose down -v --rmi local
	@echo "$(GREEN)✓ Docker resources cleaned$(NC)"

docker-shell-backend: ## Open shell in backend container
	docker exec -it script-manager-backend /bin/sh

docker-shell-frontend: ## Open shell in frontend container
	docker exec -it script-manager-frontend /bin/sh

##@ Database

db-backup: ## Backup SQLite database
	@echo "$(BLUE)Backing up database...$(NC)"
	@mkdir -p backups
	@DATE=$$(date +%Y%m%d_%H%M%S); \
	if [ -f backend/data/scripts.db ]; then \
		cp backend/data/scripts.db backups/scripts_$$DATE.db; \
		echo "$(GREEN)✓ Database backed up to backups/scripts_$$DATE.db$(NC)"; \
	else \
		echo "$(YELLOW)⚠ Database file not found$(NC)"; \
	fi

db-restore: ## Restore database from backup (usage: make db-restore FILE=backups/scripts_20260407.db)
	@if [ -z "$(FILE)" ]; then \
		echo "$(RED)Error: Please specify FILE=path/to/backup.db$(NC)"; \
		exit 1; \
	fi
	@if [ ! -f "$(FILE)" ]; then \
		echo "$(RED)Error: File $(FILE) not found$(NC)"; \
		exit 1; \
	fi
	@echo "$(BLUE)Restoring database from $(FILE)...$(NC)"
	cp $(FILE) backend/data/scripts.db
	@echo "$(GREEN)✓ Database restored$(NC)"

##@ Utilities

clean: ## Clean build artifacts and cache files
	@echo "$(BLUE)Cleaning build artifacts...$(NC)"
	rm -rf frontend/dist
	rm -rf frontend/node_modules/.vite
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "$(GREEN)✓ Cleaned$(NC)"

clean-all: clean ## Clean everything including dependencies
	@echo "$(YELLOW)Cleaning all dependencies and artifacts...$(NC)"
	rm -rf frontend/node_modules
	rm -rf backend/data
	@echo "$(GREEN)✓ Full clean completed$(NC)"

health: ## Check application health
	@echo "$(BLUE)Checking application health...$(NC)"
	@curl -sf http://localhost:8000/health > /dev/null && \
		echo "$(GREEN)✓ Backend is healthy$(NC)" || \
		echo "$(RED)✗ Backend is not responding$(NC)"
	@curl -sf http://localhost:3000 > /dev/null && \
		echo "$(GREEN)✓ Frontend is healthy$(NC)" || \
		echo "$(YELLOW)⚠ Frontend is not responding (may be in production mode)$(NC)"

env: ## Create .env file from .env.example
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo "$(GREEN)✓ Created .env file from .env.example$(NC)"; \
		echo "$(YELLOW)⚠ Please update SECRET_KEY and other values in .env$(NC)"; \
	else \
		echo "$(YELLOW)⚠ .env file already exists$(NC)"; \
	fi

secret-key: ## Generate a secure SECRET_KEY
	@echo "$(BLUE)Generated SECRET_KEY:$(NC)"
	@openssl rand -hex 32

##@ Information

info: ## Display project information
	@echo "$(BLUE)Script Manager - Project Information$(NC)"
	@echo ""
	@echo "Python version: $$(python --version 2>&1)"
	@echo "Node version: $$(node --version 2>&1)"
	@echo "npm version: $$(npm --version 2>&1)"
	@echo "Docker version: $$(docker --version 2>&1 || echo 'Not installed')"
	@echo ""
	@echo "Backend dependencies:"
	@pip list 2>/dev/null | grep -E "(fastapi|uvicorn|pytest)" || echo "Not installed"
	@echo ""
	@echo "Project structure:"
	@tree -L 2 -d . 2>/dev/null || ls -la

version: ## Display application version
	@echo "Script Manager v1.0.0"

##@ CI/CD Simulation

ci: lint test build ## Simulate CI pipeline (lint, test, build)
	@echo "$(GREEN)✓ CI pipeline completed successfully$(NC)"

ci-local: ## Run full CI pipeline locally (matches GitHub Actions)
	@echo "$(BLUE)Running CI pipeline (matching GitHub Actions)...$(NC)"
	@echo ""
	@echo "$(BLUE)Step 1: Install frontend dependencies$(NC)"
	cd frontend && npm ci
	@echo ""
	@echo "$(BLUE)Step 2: Build frontend$(NC)"
	cd frontend && npm run build
	@echo ""
	@echo "$(BLUE)Step 3: Install backend dependencies$(NC)"
	pip install -r backend/requirements.txt
	@echo ""
	@echo "$(BLUE)Step 4: Backend syntax check$(NC)"
	python -m compileall backend
	@echo ""
	@echo "$(BLUE)Step 5: Install test dependencies$(NC)"
	pip install pytest pytest-asyncio httpx
	@echo ""
	@echo "$(BLUE)Step 6: Run backend tests$(NC)"
	python -m pytest backend/tests
	@echo ""
	@echo "$(GREEN)✓ CI pipeline completed successfully$(NC)"
