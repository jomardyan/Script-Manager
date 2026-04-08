# Makefile Usage Guide

This Makefile provides convenient commands for common development and deployment tasks for Script Manager.

## Quick Start

```bash
# View all available commands
make help

# Install all dependencies
make install

# Run tests
make test

# Build for production
make build

# Full validation (lint + test + build)
make validate
```

## Command Categories

### General
- `make help` - Display all available commands with descriptions

### Installation
- `make install` - Install all dependencies (backend + frontend)
- `make install-backend` - Install Python backend dependencies
- `make install-frontend` - Install Node.js frontend dependencies

### Development
- `make dev-backend` - Run backend development server (port 8000)
- `make dev-frontend` - Run frontend development server (port 3000)
- `make dev` - Instructions for running both servers
- `make start` - Quick start using the existing start.sh script

### Testing
- `make test` - Run all tests
- `make test-backend` - Run backend tests with pytest
- `make test-coverage` - Run tests with coverage report (generates HTML report)

### Code Quality
- `make lint` - Run Python syntax check
- `make format` - Format Python code with black (if installed)
- `make check` - Run lint + test
- `make validate` - Run lint + test + build (full validation)

### Building
- `make build` - Build production assets (frontend)
- `make build-backend` - Validate backend Python syntax
- `make build-frontend` - Build frontend for production

### Docker Commands
- `make docker-up` - Start containers in development mode
- `make docker-down` - Stop containers
- `make docker-prod` - Start containers in production mode with Nginx
- `make docker-logs` - Show all container logs (live)
- `make docker-logs-backend` - Show backend logs only
- `make docker-logs-frontend` - Show frontend logs only
- `make docker-build` - Build Docker images
- `make docker-clean` - Remove containers, volumes, and images
- `make docker-shell-backend` - Open shell in backend container
- `make docker-shell-frontend` - Open shell in frontend container

### Database Management
- `make db-backup` - Backup SQLite database to backups/ directory
- `make db-restore FILE=path/to/backup.db` - Restore database from backup

### Utilities
- `make clean` - Clean build artifacts and cache files
- `make clean-all` - Clean everything including dependencies
- `make health` - Check if application is running and healthy
- `make env` - Create .env file from .env.example
- `make secret-key` - Generate a secure SECRET_KEY for production

### Information
- `make info` - Display project information (versions, dependencies)
- `make version` - Display application version

### CI/CD Simulation
- `make ci` - Run CI pipeline (lint, test, build)
- `make ci-local` - Run full CI pipeline matching GitHub Actions

## Common Workflows

### First Time Setup

```bash
# 1. Install dependencies
make install

# 2. Create environment file
make env

# 3. Generate secure key
make secret-key

# 4. Edit .env and add the generated key
nano .env

# 5. Run tests to verify setup
make test

# 6. Start development server
make start
```

### Development Workflow

```bash
# Run checks before committing
make check

# Full validation
make validate

# Clean and rebuild
make clean && make build
```

### Docker Development

```bash
# Start containers
make docker-up

# View logs
make docker-logs

# Stop containers
make docker-down
```

### Production Deployment

```bash
# 1. Build production assets
make build

# 2. Start production containers
make docker-prod

# 3. Check health
make health
```

### Database Backup

```bash
# Create backup
make db-backup

# Restore from backup
make db-restore FILE=backups/scripts_20260407_143000.db
```

## CI/CD Integration

The Makefile includes targets that match the GitHub Actions workflow:

```bash
# Run the same checks as CI
make ci-local
```

This runs:
1. Install frontend dependencies
2. Build frontend
3. Install backend dependencies
4. Backend syntax check
5. Install test dependencies
6. Run backend tests

## Tips

- Use `make help` anytime to see all available commands
- Commands with `✓` indicate successful completion
- Commands use colored output for better readability
- All commands should be run from the project root directory
- Dependencies should be installed before running most targets

## Requirements

- Python 3.8+
- Node.js 16+
- make (GNU Make)
- Docker (optional, for Docker commands)

## Troubleshooting

### "No module named X" error
```bash
make install-backend
```

### "command not found: vite"
```bash
make install-frontend
```

### Docker commands not working
Ensure Docker is installed and running:
```bash
docker --version
docker ps
```

### Tests failing
Check that all dependencies are installed:
```bash
make install
```

## Color Legend

- 🔵 Blue - Information/Progress
- 🟢 Green - Success
- 🟡 Yellow - Warning
- 🔴 Red - Error

## Contributing

When adding new targets:
1. Add target to appropriate section
2. Add `##` comment for help text
3. Test the target thoroughly
4. Update this documentation
