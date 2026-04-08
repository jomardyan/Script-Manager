# Docker Deployment Guide for Script Manager

## Overview

Script Manager includes complete Docker support for both development and production environments.

## Prerequisites

- Docker Desktop or Docker Engine (v20.10+)
- Docker Compose (v2.0+)
- At least 2GB of available RAM
- ~500MB of disk space for images

## Quick Start

### Development Deployment

```bash
# 1. Clone the repository
git clone <repository-url>
cd Script-Manager

# 2. Start the application
docker-compose up -d

# 3. Check status
docker-compose ps

# 4. View logs
docker-compose logs -f
```

Access the application:
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

### Production Deployment

```bash
# Start with production configuration (includes Nginx)
docker-compose -f docker-compose.prod.yml up -d

# Access via Nginx
# http://localhost
```

## Configuration

### Environment Variables

Create a `.env` file:

```bash
cp .env.example .env
```

Edit `.env` with your settings:

```env
API_PORT=8000
DATABASE_PATH=/app/data/scripts.db
VITE_API_URL=http://localhost:8000
```

### Volume Management

#### Persistent Database

The database is stored in the `script_data` volume. This persists data even if containers are removed:

```bash
# View volumes
docker volume ls

# Inspect volume
docker volume inspect script-manager_script_data

# Backup database
docker run --rm -v script-manager_script_data:/data -v $(pwd):/backup \
  alpine tar czf /backup/scripts.db.tar.gz -C /data scripts.db

# Restore database
docker run --rm -v script-manager_script_data:/data -v $(pwd):/backup \
  alpine tar xzf /backup/scripts.db.tar.gz -C /data
```

#### Mounting Script Directories

Edit `docker-compose.yml` and add volumes to the `backend` service:

```yaml
backend:
  volumes:
    - script_data:/app/data
    - /home/user/scripts:/scripts:ro
    - /mnt/shared:/shared:ro
```

Then in the Script Manager UI, create folder roots pointing to `/scripts`, `/shared`, etc.

## Common Tasks

### Build Images

```bash
# Build all images
docker-compose build

# Build specific service
docker-compose build backend
docker-compose build frontend

# Build with no cache
docker-compose build --no-cache
```

### View Logs

```bash
# All services
docker-compose logs

# Specific service
docker-compose logs backend
docker-compose logs frontend
docker-compose logs nginx

# Follow logs
docker-compose logs -f

# Last 100 lines
docker-compose logs --tail=100
```

### Stop and Start

```bash
# Stop running containers
docker-compose stop

# Start stopped containers
docker-compose start

# Restart containers
docker-compose restart

# Remove containers and networks
docker-compose down

# Remove everything including volumes
docker-compose down -v
```

### Execute Commands

```bash
# Execute command in running container
docker-compose exec backend bash

# Run one-off command
docker-compose run backend python -c "import app; print('OK')"
```

### View Resource Usage

```bash
# See memory and CPU usage
docker stats

# See container details
docker inspect script-manager-backend
```

## Troubleshooting

### Port Already in Use

If ports 3000 or 8000 are already in use:

```bash
# Change ports in docker-compose.yml
# Or kill the process using the port

# On Linux/Mac
lsof -i :3000
kill -9 <PID>

# On Windows
netstat -ano | findstr :3000
taskkill /PID <PID> /F
```

### Database Issues

```bash
# Access SQLite database inside container
docker-compose exec backend sqlite3 /app/data/scripts.db

# Remove and recreate database
docker-compose exec backend rm /app/data/scripts.db
docker-compose restart backend
```

### Memory Issues

Increase Docker memory allocation:

1. **Windows**: Docker Desktop → Settings → Resources → Memory
2. **Mac**: Docker → Preferences → Resources → Memory
3. **Linux**: Edit `/etc/docker/daemon.json`:

```json
{
  "memory": 4294967296,
  "memswap": 4294967296
}
```

### Frontend Not Loading

```bash
# Check frontend logs
docker-compose logs frontend

# Clear cache and rebuild
docker-compose down -v
docker-compose build --no-cache
docker-compose up -d
```

### Backend Connection Issues

```bash
# Check backend logs
docker-compose logs backend

# Test backend connectivity
docker-compose exec frontend curl http://backend:8000/health

# Restart backend
docker-compose restart backend
```

### API CORS Issues

Check that `VITE_API_URL` in `.env` matches the backend service name or external URL:

```env
# For docker-compose
VITE_API_URL=http://localhost:8000

# For production with Nginx
VITE_API_URL=http://localhost/api
```

## Performance Optimization

### Enable BuildKit

Faster builds using Docker BuildKit:

```bash
# Linux
export DOCKER_BUILDKIT=1
docker-compose build

# Windows PowerShell
$env:DOCKER_BUILDKIT=1
docker-compose build

# macOS
export DOCKER_BUILDKIT=1
docker-compose build
```

### Reduce Image Size

Built images are optimized with:
- Alpine Linux base where possible
- Multi-stage builds for frontend
- .dockerignore to exclude unnecessary files

### Scale Backend (Production)

```bash
# Scale backend to 3 instances with Nginx load balancing
docker-compose -f docker-compose.prod.yml up -d --scale backend=3
```

Modify `nginx.conf` to use upstream load balancing:

```nginx
upstream backend {
    server backend:8000;
    server backend:8001;
    server backend:8002;
}
```

## Security Best Practices

1. **Environment Variables**: Use `.env` file, never commit secrets
2. **Volume Permissions**: Use read-only mounts (`ro`) for script directories
3. **Network Isolation**: Services communicate via Docker network, not exposed to host
4. **Health Checks**: Containers include health checks for automatic restart
5. **Resource Limits**: Consider adding memory/CPU limits in docker-compose.yml:

```yaml
backend:
  deploy:
    resources:
      limits:
        cpus: '1'
        memory: 1G
      reservations:
        cpus: '0.5'
        memory: 512M
```

## Advanced Configurations

### Using External Database

Modify Dockerfile.backend to connect to external PostgreSQL or MySQL instead of SQLite.

### Using External Nginx

Don't use the Nginx service in docker-compose.yml. Instead:

```bash
# Run only backend and frontend
docker-compose up -d backend frontend

# Configure your external Nginx to proxy to:
# Backend: http://localhost:8000
# Frontend: http://localhost:3000
```

### Multi-Machine Deployment

Use Docker Swarm or Kubernetes for multi-machine deployments:

```bash
# Docker Swarm
docker swarm init
docker stack deploy -c docker-compose.yml script-manager

# Kubernetes (requires docker-compose to k8s conversion)
# Consider using helm charts for production deployments
```

## Monitoring

### View Container Status

```bash
# Detailed status
docker-compose ps -a

# Service health
docker-compose ps

# Container resource usage
docker stats script-manager-backend
docker stats script-manager-frontend
```

### Check Application Health

```bash
# Backend health
curl http://localhost:8000/health

# Frontend
curl http://localhost:3000

# Via Nginx (production)
curl http://localhost/
```

## Backup and Recovery

### Backup Database

```bash
# Backup to tar.gz
docker run --rm -v script-manager_script_data:/data \
  -v $(pwd):/backup alpine tar czf /backup/scripts.db.tar.gz -C /data .

# Backup to SQL dump
docker-compose exec backend sqlite3 /app/data/scripts.db \
  ".mode insert" ".tables" > scripts.sql
```

### Recovery

```bash
# Stop services
docker-compose stop

# Restore volume
docker run --rm -v script-manager_script_data:/data \
  -v $(pwd):/backup alpine tar xzf /backup/scripts.db.tar.gz -C /data

# Start services
docker-compose up -d
```

## Additional Resources

- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose Documentation](https://docs.docker.com/compose/)
- [FastAPI Deployment](https://fastapi.tiangolo.com/deployment/)
- [React Production Build](https://vitejs.dev/guide/build.html)

## Support

For issues:
1. Check logs: `docker-compose logs`
2. Verify configuration in `docker-compose.yml`
3. Ensure all prerequisites are met
4. Check Docker and Docker Compose versions
