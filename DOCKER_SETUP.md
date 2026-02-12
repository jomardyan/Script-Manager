# Docker Setup Summary

This document summarizes the Docker implementation for Script Manager.

## Files Created

### Docker Configuration Files

#### `Dockerfile.backend`
- Multi-stage Python application for FastAPI backend
- Uses Python 3.11-slim base image
- Installs dependencies from `backend/requirements.txt`
- Exposes port 8000
- Includes health check endpoint

#### `Dockerfile.frontend`
- Multi-stage Node.js build for React frontend
- Builds with Vite in builder stage
- Serves via http-server in production stage
- Exposes port 3000
- Includes health check

### Docker Compose Files

#### `docker-compose.yml`
Development configuration with:
- Backend service (FastAPI)
- Frontend service (React)
- Named volume for persistent database storage
- Private Docker network for service communication
- Health checks for both services
- Optional Nginx service (commented out)

#### `docker-compose.prod.yml`
Production configuration with:
- Backend service with Nginx integration
- Frontend service optimized for production
- Nginx reverse proxy with load balancing support
- SSL/TLS certificate support (optional)
- Docker network for inter-service communication

### Helper Scripts

#### `docker.sh` (Linux/macOS)
Bash helper script with commands:
- `up` - Start development environment
- `down` - Stop application
- `build` - Build Docker images
- `logs` - View container logs
- `logs-backend`/`logs-frontend` - View specific service logs
- `shell-backend`/`shell-frontend` - Access container shell
- `status` - Show container status
- `health` - Check application health
- `restart` - Restart application
- `prod` - Start production environment
- `prod-down` - Stop production environment
- `clean` - Remove containers and volumes

#### `docker.bat` (Windows)
Batch equivalent of docker.sh with same commands for Windows users.

### Configuration Files

#### `.dockerignore`
Excludes unnecessary files from Docker build context:
- node_modules, npm-debug.log, dist
- __pycache__, *.pyc files
- .git, .env, .vscode/.idea
- Reduces image size and build time

#### `.env.example`
Template for environment variables:
- `API_PORT` - Backend port (default: 8000)
- `DATABASE_PATH` - Database location
- `VITE_API_URL` - Frontend API endpoint
- Document with examples for custom volumes

#### `nginx.conf`
Nginx reverse proxy configuration:
- Frontend server on port 80
- API proxy to backend
- Static file caching
- React router support
- CORS headers
- Connection timeout configuration

### Documentation Files

#### `docs/DOCKER.md`
Comprehensive Docker deployment guide covering:
- Prerequisites and installation
- Quick start instructions
- Volume management and backups
- Common Docker tasks
- Troubleshooting guide
- Performance optimization
- Security best practices
- Multi-machine deployment options

#### `docs/DOCKER_QUICK_REFERENCE.md`
Quick reference guide with:
- Common Docker commands
- docker-compose commands
- Production deployment
- Volume management
- Troubleshooting tips
- Performance tips
- Environment variables

## Quick Start

### Development
```bash
./docker.sh up
# or
docker-compose up -d
```

### Production
```bash
./docker.sh prod
# or
docker-compose -f docker-compose.prod.yml up -d
```

### Stop
```bash
./docker.sh down
# or
docker-compose down
```

## Architecture

```
┌─────────────────────────────────────────────┐
│         Your Host Machine                   │
│                                             │
│  ┌─────────────────────────────────────┐   │
│  │  Docker Compose Network              │   │
│  │                                      │   │
│  │  ┌──────────┐    ┌──────────┐      │   │
│  │  │Frontend  │    │Backend   │      │   │
│  │  │(React)  │───►│(FastAPI) │      │   │
│  │  │:3000    │    │:8000     │      │   │
│  │  └──────────┘    └──────────┘      │   │
│  │        ▲               │            │   │
│  │        │               ▼            │   │
│  │        │        ┌────────────┐     │   │
│  │        │        │  Volume    │     │   │
│  │        │        │  Database  │     │   │
│  │        │        └────────────┘     │   │
│  │        │                            │   │
│  │  ┌─────┴────────────────────────┐  │   │
│  │  │    Nginx (Optional)           │  │   │
│  │  │    :80 /:443                  │  │   │
│  │  └──────────────────────────────┘  │   │
│  │                                      │   │
│  └─────────────────────────────────────┘   │
│         ▲              ▲                    │
│         │              │                    │
│         │ (Mounted)    │ (Local)            │
└─────────┼──────────────┼────────────────────┘
          │              │
          ▼              ▼
    /scripts/       sqlite.db
```

## Key Features

1. **Multi-stage Builds**: Optimized image sizes
2. **Health Checks**: Automatic container restart if unhealthy
3. **Volume Persistence**: Database survives container restarts
4. **Network Isolation**: Services communicate securely within Docker network
5. **Load Balancing**: Nginx can scale backend services
6. **Environment Flexibility**: Works for dev and production
7. **Cross-platform**: Helper scripts for both Linux/macOS and Windows

## Files Structure

```
Script-Manager/
├── Dockerfile.backend           # Backend container definition
├── Dockerfile.frontend          # Frontend container definition
├── docker-compose.yml           # Development orchestration
├── docker-compose.prod.yml      # Production orchestration
├── nginx.conf                   # Reverse proxy config
├── .dockerignore               # Build context exclusions
├── .env.example                # Environment template
├── docker.sh                    # Linux/macOS helper script
├── docker.bat                   # Windows helper script
├── docs/
│   ├── DOCKER.md               # Full deployment guide
│   └── DOCKER_QUICK_REFERENCE.md # Quick commands
└── README.md                    # Updated with Docker info
```

## Updated Documentation

The main README.md has been updated to include:
- Docker quick start section at the top
- Helper script usage examples
- Environment variable documentation
- Production deployment instructions
- Links to comprehensive Docker guides

## Next Steps

1. **Run the application**:
   ```bash
   ./docker.sh up
   ```

2. **Access the application**:
   - Frontend: http://localhost:3000
   - Backend: http://localhost:8000

3. **Configure script directories**:
   - Edit `docker-compose.yml` to mount your script folders
   - Create folder roots in the UI pointing to mounted paths

4. **Deploy to production**:
   - Use `docker-compose.prod.yml` with Nginx
   - Configure SSL certificates
   - Set proper environment variables

## Support

For detailed information:
- [Docker Deployment Guide](./docs/DOCKER.md) - Comprehensive setup and troubleshooting
- [Docker Quick Reference](./docs/DOCKER_QUICK_REFERENCE.md) - Common commands
- [Original README](./README.md) - Main documentation with Docker section

## System Requirements

- **Docker**: v20.10+
- **Docker Compose**: v2.0+
- **RAM**: 2GB minimum (4GB recommended)
- **Disk**: ~500MB for images + database storage

## Performance Notes

- First build takes 2-3 minutes (multi-stage optimization)
- Subsequent builds use cache (faster)
- Running containers use ~200-400MB RAM
- Database performance optimized with SQLite indexes

## Security Considerations

- Database volume is local only (not exposed)
- Services communicate via private Docker network
- Script directories mounted read-only (ro flag)
- Environment variables for sensitive data
- CORS configured for frontend origin
