# Script Manager

A web application for managing large collections of script files. Index, search, tag, and organize your Python, PowerShell, Bash, SQL, and other script files across multiple directories.

## Features

- **Script Indexing**: Recursively scan and index scripts from multiple folder roots
- **Metadata Management**: Add notes, tags, status, and classifications to scripts
- **Fast Search**: Search by filename, path, content, tags, and metadata
- **Lifecycle Tracking**: Manage script status (draft, active, deprecated, archived)
- **Duplicate Detection**: Find identical scripts across different locations
- **Bulk Operations**: Apply changes to multiple scripts at once
- **Audit Trail**: Track changes to metadata and script status

## Screenshots

### Dashboard

![Dashboard](./docs/screenshots/dashboard.png)

### Folder Roots

![Folder Roots](./docs/screenshots/folder-roots.png)

### Scripts

![Scripts](./docs/screenshots/scripts.png)

### Tags

![Tags](./docs/screenshots/tags.png)

### Advanced Search

![Advanced Search](./docs/screenshots/search.png)

## Supported Script Types

- Python (.py)
- PowerShell (.ps1, .psm1)
- Bash (.sh)
- Batch (.bat, .cmd)
- SQL (.sql)
- JavaScript (.js)
- YAML (.yml, .yaml)
- JSON (.json)
- Terraform (.tf)

## Quick Start

### Docker Setup (Recommended)

#### Prerequisites
- Docker and Docker Compose installed

#### Quick Start with Docker

```bash
# Clone the repository
git clone <repository-url>
cd Script-Manager

# Start the application
./docker.sh up
# or on Windows
docker.bat up
```

The application will be available at:
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

#### Stop the Application

```bash
./docker.sh down
# or on Windows
docker.bat down
```

#### Helper Commands

Use the convenient helper scripts for common tasks:

```bash
# View logs
./docker.sh logs -f

# Check health
./docker.sh health

# Access backend shell
./docker.sh shell-backend

# Production setup with Nginx
./docker.sh prod

# See all commands
./docker.sh help
```

**Windows users**: Replace `./docker.sh` with `docker.bat`

See [Docker Quick Reference](./docs/DOCKER_QUICK_REFERENCE.md) for more commands.

### Docker Configuration

**Mounting Script Directories**

To scan scripts from your host machine, edit `docker-compose.yml` and modify the `backend` service volumes:

```yaml
volumes:
  - script_data:/app/data
  - /path/to/your/scripts:/scripts:ro
```

Then in the UI, create a folder root with path `/scripts`.

**Environment Variables**

Copy `.env.example` to `.env` and customize:

```bash
cp .env.example .env
```

Available variables:
- `API_PORT`: Backend API port (default: 8000)
- `DATABASE_PATH`: SQLite database location (default: /app/data/scripts.db)
- `VITE_API_URL`: Frontend API URL (default: http://localhost:8000)

**Production Deployment with Nginx**

For a production-like setup with Nginx reverse proxy:

```bash
./docker.sh prod
# or on Windows
docker.bat prod
```

Then access the application at `http://localhost` (port 80).

See [Docker Deployment Guide](./docs/DOCKER.md) for detailed configuration and troubleshooting.

### Traditional Setup

#### Easy Start (Recommended)

**On Linux/Mac:**
```bash
./start.sh
```

**On Windows:**
```bash
start.bat
```

This will automatically:
1. Install dependencies if needed
2. Start both backend and frontend
3. Open the application in your browser

#### Manual Start

##### Prerequisites

- Python 3.8 or higher
- Node.js 16 or higher
- npm or yarn

##### Backend Setup

```bash
cd backend
pip install -r requirements.txt
python main.py
```

The API will be available at http://localhost:8000

##### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

The web interface will be available at http://localhost:3000

## Architecture

- **Backend**: Python with FastAPI
- **Database**: SQLite with indexes for fast queries
- **Frontend**: React with modern UI components
- **API**: RESTful API with JSON responses
- **Containerization**: Docker and Docker Compose for easy deployment

## Docker Architecture

When running with Docker Compose, the following services are orchestrated:

```
┌─────────────────────────────────────────────┐
│         Docker Compose Network              │
│                                             │
│  ┌──────────────┐      ┌──────────────┐   │
│  │  Frontend    │      │  Backend     │   │
│  │  React       │◄────►│  FastAPI     │   │
│  │  Port 3000   │      │  Port 8000   │   │
│  └──────────────┘      └──────────────┘   │
│         ▲                      ▲           │
│         │                      │           │
│         └──────┬───────────────┘           │
│                │                          │
│         ┌──────▼────────┐                 │
│         │  Volume       │                 │
│         │  script_data  │                 │
│         │  (Database)   │                 │
│         └───────────────┘                 │
│                                             │
└─────────────────────────────────────────────┘
```

### Services

- **backend**: FastAPI application with Python
- **frontend**: React application (built with Vite)
- **script_data volume**: Persistent storage for SQLite database
- **Optional nginx**: Reverse proxy for production deployments

## Configuration

Configuration options can be set via environment variables:

- `DATABASE_PATH`: Path to SQLite database (default: `./data/scripts.db`)
- `API_PORT`: Backend API port (default: `8000`)

## Documentation

- [Docker Deployment Guide](./docs/DOCKER.md) - Complete Docker setup and troubleshooting
- [Docker Quick Reference](./docs/DOCKER_QUICK_REFERENCE.md) - Quick command reference
- [API Documentation](./docs/API.md)
- [User Guide](./docs/USER_GUIDE.md)
- [Development Guide](./docs/DEVELOPMENT.md)

## License

MIT License - see LICENSE file for details
