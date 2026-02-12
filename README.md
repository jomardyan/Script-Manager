# Script Manager

A web application for managing large collections of script files. Index, search, tag, and organize scripts across multiple directories while keeping files on disk as the source of truth.

## Features

- **Script Indexing**: Multi-root scans with include/exclude patterns, incremental updates, and optional watch mode
- **Metadata Management**: Notes, tags, status, classification, owner, environment, and custom fields
- **Fast Search**: Name/path search, filters, saved searches, and optional FTS5 full-text search
- **Lifecycle Tracking**: Draft → active → deprecated → archived with audit history
- **Duplicate & Similarity Detection**: Content hashing and fuzzy matching for related scripts
- **Markdown Notes & Attachments**: Rendered notes with optional file uploads
- **Bulk Operations & Import/Export**: Apply tags/status in bulk and export/import metadata
- **Responsive UI + API**: React frontend with FastAPI REST endpoints

## Supported Script Types

- Python (.py)
- PowerShell (.ps1, .psm1)
- Bash (.sh)
- Batch (.bat, .cmd)
- SQL (.sql)
- JavaScript/TypeScript (.js, .ts)
- YAML (.yml, .yaml)
- JSON (.json)
- Terraform (.tf)
- Ruby (.rb)
- Perl (.pl)
- PHP (.php)
- Go (.go)
- Rust (.rs)
- Java (.java)
- C# (.cs)
- C/C++ (.c, .cpp)
- R (.r)

## Quick Start

### Easy Start (Recommended)

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

### Manual Start

#### Prerequisites

- Python 3.8 or higher
- Node.js 16 or higher
- npm or yarn

#### Backend Setup

```bash
cd backend
pip install -r requirements.txt
python main.py
```

The API will be available at http://localhost:8000

#### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

The web interface will be available at http://localhost:3000

## Architecture

- **Backend**: FastAPI with async services for scanning, search, and metadata
- **Database**: SQLite with indexes and optional FTS5 full-text search
- **Frontend**: React + Vite single-page application
- **File System**: Script files remain on disk; metadata lives in SQLite

See [docs/ARCHITECTURE.md](./docs/ARCHITECTURE.md) for the full developer architecture overview.

## Project Structure

```
Script-Manager/
├── backend/              # FastAPI backend and SQLite integration
├── frontend/             # React UI
├── docs/                 # Developer and user documentation
├── start.sh              # Linux/Mac startup script
└── start.bat             # Windows startup script
```

## Configuration

Configuration options can be set via environment variables:

- `DATABASE_PATH`: Path to SQLite database (default: `./data/scripts.db`)
- `API_PORT`: Backend API port (default: `8000`)

## Documentation

- [Architecture Guide](./docs/ARCHITECTURE.md)
- [API Documentation](./docs/API.md)
- [User Guide](./docs/USER_GUIDE.md)

## License

MIT License - see LICENSE file for details
