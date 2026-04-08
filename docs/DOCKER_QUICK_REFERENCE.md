# Docker Quick Reference

## Quick Commands

### Start the Application

```bash
# Development setup
./docker.sh up
# or on Windows
docker.bat up

# Production setup with Nginx
./docker.sh prod
# or on Windows
docker.bat prod
```

### Stop the Application

```bash
./docker.sh down
# or
docker docker.bat down
```

### View Logs

```bash
# All services
./docker.sh logs -f

# Backend only
./docker.sh logs-backend -f

# Frontend only
./docker.sh logs-frontend -f
```

### Access Container Shell

```bash
# Backend (Python/FastAPI)
./docker.sh shell-backend

# Frontend (Node/React)
./docker.sh shell-frontend
```

### Check Application Status

```bash
# Container status
./docker.sh status

# Application health
./docker.sh health
```

### Rebuild Images

```bash
# After code changes
./docker.sh build
./docker.sh up
```

### Clean Everything

```bash
# Remove containers and database
./docker.sh clean
```

## Docker Compose Commands

If you prefer using `docker-compose` directly:

### Basic Operations

```bash
# Start services
docker-compose up

# Start in background
docker-compose up -d

# Stop services
docker-compose down

# Remove everything including volumes
docker-compose down -v

# Restart services
docker-compose restart

# View status
docker-compose ps
```

### Building

```bash
# Build images
docker-compose build

# Build without cache
docker-compose build --no-cache

# Build specific service
docker-compose build backend
```

### Logs

```bash
# View logs
docker-compose logs

# Follow logs
docker-compose logs -f

# View specific service logs
docker-compose logs backend
docker-compose logs frontend

# View recent logs
docker-compose logs --tail=50
```

### Executing Commands

```bash
# Run command in container
docker-compose exec backend python -c "import app; print('OK')"

# Access shell
docker-compose exec backend bash
docker-compose exec frontend sh

# Database operations
docker-compose exec backend sqlite3 /app/data/scripts.db
```

## Production Deployment

### Using docker-compose.prod.yml

```bash
# Start with production config (Nginx included)
docker-compose -f docker-compose.prod.yml up -d

# Stop production environment
docker-compose -f docker-compose.prod.yml down

# View production logs
docker-compose -f docker-compose.prod.yml logs -f
```

Or use the helper:

```bash
./docker.sh prod    # Start
./docker.sh prod-down  # Stop
```

## Volume and Data Management

### View Volumes

```bash
docker volume ls
docker volume inspect script-manager_script_data
```

### Backup Database

```bash
# Backup script_data volume
docker run --rm -v script-manager_script_data:/data \
  -v $(pwd):/backup alpine tar czf /backup/scripts.db.tar.gz -C /data .
```

### Mount Script Directories

Edit `docker-compose.yml`:

```yaml
backend:
  volumes:
    - script_data:/app/data
    - /path/to/scripts:/scripts:ro
```

Access in app: Create folder root with path `/scripts`

## Docker Compose Network

Services communicate via Docker network:
- `backend` service: accessible as `http://backend:8000` from other containers
- `frontend` service: accessible as `http://frontend:3000` from other containers
- Both services accessible from host: `http://localhost:8000` and `http://localhost:3000`

## Environment Variables

Create `.env` file or edit docker-compose.yml:

```env
API_PORT=8000
DATABASE_PATH=/app/data/scripts.db
VITE_API_URL=http://localhost:8000
```

## Troubleshooting

### Port Conflict

If ports 3000 or 8000 are in use:

```bash
# Find process using port
lsof -i :3000

# Kill process (Linux/Mac)
kill -9 <PID>

# Change ports in docker-compose.yml
# ports:
#   - "3001:3000"  # frontend on different port
#   - "8001:8000"  # backend on different port
```

### Container Won't Start

```bash
# Check logs
docker-compose logs backend
docker-compose logs frontend

# Restart
docker-compose restart

# Full rebuild
docker-compose down -v
docker-compose build --no-cache
docker-compose up -d
```

### Database Issues

```bash
# Reset database
docker-compose exec backend rm /app/data/scripts.db

# Recreate on restart
docker-compose restart backend
```

### Memory Issues

Increase Docker memory allocation:
- Windows/Mac: Docker Desktop → Settings → Resources
- Linux: Edit `/etc/docker/daemon.json`

### API Connection Issues

Verify `VITE_API_URL` environment variable matches backend address:

```bash
# Local development
VITE_API_URL=http://localhost:8000

# Through Nginx
VITE_API_URL=http://localhost/api
```

## Performance Tips

1. **Use docker-compose with BuildKit**:
   ```bash
   export DOCKER_BUILDKIT=1
   docker-compose build
   ```

2. **Limit resource usage**:
   Add to docker-compose.yml:
   ```yaml
   backend:
     deploy:
       resources:
         limits:
           cpus: '1'
           memory: 1G
   ```

3. **Use .dockerignore** to exclude unnecessary files from build context

4. **Build in parallel**: `docker-compose build --parallel`

## Useful Environment Variables

```bash
# Display compose file being used
COMPOSE_FILE=docker-compose.yml docker-compose ps

# Change project name
COMPOSE_PROJECT_NAME=myapp docker-compose up

# Run with specific env file
docker-compose --env-file .env.prod up
```

## More Information

See [docs/DOCKER.md](../docs/DOCKER.md) for comprehensive Docker documentation.
