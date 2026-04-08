# Production Deployment Guide

This guide covers best practices for deploying Script Manager in a production environment.

## Security Checklist

### 1. Environment Variables

**Critical**: Update these environment variables before deploying to production:

```bash
# Generate a secure SECRET_KEY (required!)
SECRET_KEY=$(openssl rand -hex 32)

# Configure allowed CORS origins (only your production domains)
ALLOWED_ORIGINS=https://yourdomain.com,https://app.yourdomain.com

# Database configuration
DATABASE_PATH=/app/data/scripts.db
```

Create a `.env` file from `.env.example` and update all values:

```bash
cp .env.example .env
# Edit .env with your production values
```

### 2. Secret Key Generation

The default `SECRET_KEY` in the codebase is **INSECURE** and must be changed for production:

```bash
# Generate a secure random key
openssl rand -hex 32

# Or use Python
python -c "import secrets; print(secrets.token_hex(32))"
```

Add this to your `.env` file or set as an environment variable.

### 3. CORS Configuration

Update `ALLOWED_ORIGINS` to only include your production domains:

```bash
# Development (default)
ALLOWED_ORIGINS=http://localhost:3000,http://localhost:5173

# Production (example)
ALLOWED_ORIGINS=https://app.example.com,https://example.com
```

### 4. Database Security

- **SQLite**: Ensure proper file permissions (600) on the database file
- **MySQL/PostgreSQL**: Use strong passwords and restrict network access
- Enable SSL/TLS for database connections when using external databases

### 5. HTTPS/TLS

**Always** use HTTPS in production. Configure your reverse proxy (Nginx, Traefik, Caddy) to:

- Redirect HTTP to HTTPS
- Use valid SSL certificates (Let's Encrypt recommended)
- Enable HTTP/2
- Configure proper TLS settings

### 6. Container Security

When deploying with Docker:

```yaml
# docker-compose.yml production settings
services:
  backend:
    restart: unless-stopped
    read_only: true  # Make container filesystem read-only
    tmpfs:
      - /tmp
    cap_drop:
      - ALL
    cap_add:
      - NET_BIND_SERVICE
    security_opt:
      - no-new-privileges:true
```

### 7. Authentication

- Change default admin credentials immediately after setup
- Enforce strong password policies (minimum 8 characters, letters + numbers)
- Regularly rotate API tokens
- Use role-based access control (RBAC) appropriately

### 8. Logging

Configure logging for production:

```python
# Set log level via environment
LOG_LEVEL=INFO  # or WARNING for production

# Configure log rotation
# Use docker logging drivers or external logging services
```

### 9. Backups

Set up regular database backups:

```bash
# SQLite backup script
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
sqlite3 /app/data/scripts.db ".backup /backups/scripts_$DATE.db"

# Keep only last 30 days
find /backups -name "scripts_*.db" -mtime +30 -delete
```

### 10. Network Security

- Use a reverse proxy (Nginx) in front of the application
- Configure firewall rules to restrict access
- Use private networks for service-to-service communication
- Implement rate limiting on the reverse proxy level

## Docker Production Setup

Use the production Docker Compose configuration:

```bash
# Start with production configuration
./docker.sh prod

# Or manually
docker-compose -f docker-compose.prod.yml up -d
```

### Production docker-compose.yml Example

```yaml
version: '3.8'

services:
  backend:
    build:
      context: .
      dockerfile: Dockerfile.backend
    container_name: script-manager-backend
    restart: unless-stopped
    environment:
      - API_PORT=8000
      - DATABASE_PATH=/app/data/scripts.db
      - SECRET_KEY=${SECRET_KEY}
      - ALLOWED_ORIGINS=${ALLOWED_ORIGINS}
    volumes:
      - script_data:/app/data:rw
      - /path/to/scripts:/scripts:ro
    networks:
      - script-manager-network
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: '1'

  frontend:
    build:
      context: .
      dockerfile: Dockerfile.frontend
    container_name: script-manager-frontend
    restart: unless-stopped
    environment:
      - VITE_API_URL=https://api.yourdomain.com
    networks:
      - script-manager-network
    depends_on:
      - backend

  nginx:
    image: nginx:alpine
    container_name: script-manager-nginx
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx-production.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
    depends_on:
      - backend
      - frontend
    networks:
      - script-manager-network

volumes:
  script_data:
    driver: local

networks:
  script-manager-network:
    driver: bridge
```

## Nginx Production Configuration

Example production Nginx configuration:

```nginx
# Rate limiting zones
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
limit_req_zone $binary_remote_addr zone=login_limit:10m rate=5r/m;

server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com www.yourdomain.com;

    # SSL Configuration
    ssl_certificate /etc/nginx/ssl/fullchain.pem;
    ssl_certificate_key /etc/nginx/ssl/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    # Security Headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;

    # API Backend
    location /api/ {
        limit_req zone=api_limit burst=20 nodelay;
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Login endpoint with stricter rate limiting
    location /api/auth/login {
        limit_req zone=login_limit burst=2 nodelay;
        proxy_pass http://backend:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Frontend
    location / {
        proxy_pass http://frontend:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

## Monitoring and Maintenance

### Health Checks

Monitor the application health endpoint:

```bash
curl -f https://yourdomain.com/health
```

### Log Monitoring

Set up log aggregation and monitoring:

```bash
# View Docker logs
docker logs -f script-manager-backend
docker logs -f script-manager-frontend

# Configure log shipping to external services
# (Datadog, Splunk, ELK stack, etc.)
```

### Performance Monitoring

- Monitor database size and performance
- Track API response times
- Monitor memory and CPU usage
- Set up alerting for service failures

## Scaling Considerations

### Horizontal Scaling

For high availability:

1. Use an external database (PostgreSQL recommended)
2. Deploy multiple backend instances behind a load balancer
3. Use shared storage for attachments (S3, NFS, etc.)
4. Implement Redis for session storage and caching

### Vertical Scaling

Adjust resource limits based on usage:

```yaml
deploy:
  resources:
    limits:
      memory: 2G
      cpus: '2'
    reservations:
      memory: 1G
      cpus: '1'
```

## Troubleshooting

### Common Issues

**Issue**: CORS errors in production
- Verify `ALLOWED_ORIGINS` includes your production domain
- Check Nginx proxy headers are set correctly

**Issue**: Authentication failures
- Verify `SECRET_KEY` is set and consistent across restarts
- Check JWT token expiration settings

**Issue**: Database locked errors (SQLite)
- Consider migrating to PostgreSQL for production
- Ensure only one backend instance with SQLite

**Issue**: High memory usage
- Review and optimize queries
- Enable query result caching
- Adjust resource limits

## Security Incident Response

If you suspect a security breach:

1. Immediately rotate `SECRET_KEY`
2. Force all users to re-authenticate
3. Review audit logs for suspicious activity
4. Update all passwords
5. Review and restrict access permissions

## Updates and Patching

Regular maintenance schedule:

- **Weekly**: Check for security updates in dependencies
- **Monthly**: Update base Docker images
- **Quarterly**: Review and update security configurations
- **Annually**: Security audit and penetration testing

To update the application:

```bash
# Pull latest changes
git pull

# Backup database
./backup.sh

# Rebuild and restart containers
docker-compose build --no-cache
docker-compose up -d

# Verify health
curl -f https://yourdomain.com/health
```

## Support

For production support and security issues:

- GitHub Issues: https://github.com/jomardyan/Script-Manager/issues
- Security Issues: Report privately via GitHub Security Advisories

## Compliance

Depending on your use case, consider:

- GDPR compliance for EU users
- SOC 2 requirements for enterprise
- HIPAA compliance for healthcare data
- PCI DSS for payment processing

Review your compliance requirements and adjust security controls accordingly.
