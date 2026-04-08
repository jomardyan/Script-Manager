# Script Manager User Guide

## Getting Started

### Installation

1. **Clone the repository:**
   ```bash
   git clone https://github.com/jomardyan/Script-Manager.git
   cd Script-Manager
   ```

2. **Install backend dependencies:**
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

3. **Install frontend dependencies:**
   ```bash
   cd ../frontend
   npm install
   ```

### Running the Application

1. **Start the backend server:**
   ```bash
   cd backend
   python main.py
   ```
   The API will be available at http://localhost:8000

2. **Start the frontend (in a new terminal):**
   ```bash
   cd frontend
   npm run dev
   ```
   The web interface will be available at http://localhost:3000

## Using Script Manager

### 1. Add a Folder Root

1. Navigate to **Folder Roots** in the sidebar
2. Click **Add Folder Root**
3. Fill in the details:
   - **Name**: A friendly name for this folder (e.g., "Production Scripts")
   - **Path**: Absolute path to the folder (e.g., "/home/user/scripts")
   - **Recursive**: Check to scan subfolders
   - **Include Patterns**: Optional comma-separated patterns (e.g., "*.py,*.sh")
   - **Exclude Patterns**: Optional patterns to skip (e.g., "*test*,*tmp*")
4. Click **Add**

### 2. Scan for Scripts

1. Go to **Folder Roots**
2. Click **Scan** next to a folder root
3. Wait for the scan to complete
4. Review the results showing new, updated, and deleted scripts

### 3. Browse Scripts

1. Navigate to **Scripts** in the sidebar
2. Use the search bar to find scripts by name or path
3. Use filters to narrow down by language or status
4. Click on a script name to view details

### 4. Manage Script Metadata

On the script detail page, you can:

- **Add Notes**: Document important information about the script
- **Add Tags**: Organize scripts with tags (create tags first in the Tags section)
- **Update Status**: Set status (active, draft, deprecated, archived)
- **Set Classification**: Add classification like "production" or "staging"
- **Assign Owner**: Record who owns or maintains the script
- **Set Environment**: Specify the deployment environment

### 5. Create and Use Tags

1. Navigate to **Tags** in the sidebar
2. Click **Create Tag**
3. Enter:
   - **Name**: Tag name (e.g., "production", "backup", "critical")
   - **Group**: Optional group name (e.g., "environment", "category")
   - **Color**: Pick a color for visual distinction
4. Use tags on scripts to organize your collection

### 6. Advanced Search

1. Navigate to **Search** in the sidebar
2. Enter search criteria:
   - **Query**: Search term for name or path
   - **Languages**: Filter by programming language
   - **Status**: Filter by script status
   - **Tags**: Filter by tags
   - **Folder Roots**: Filter by specific folders
3. Click **Search**

### 7. View Statistics

The **Dashboard** shows:
- Total number of scripts indexed
- Number of folder roots configured
- Total tags created
- Scripts grouped by language
- Recent folder roots and scan status

### Screenshots

#### Dashboard

![Dashboard](./screenshots/dashboard.png)

#### Folder Roots

![Folder Roots](./screenshots/folder-roots.png)

#### Scripts

![Scripts](./screenshots/scripts.png)

#### Tags

![Tags](./screenshots/tags.png)

#### Advanced Search

![Advanced Search](./screenshots/search.png)

## Tips and Best Practices

### Organizing Scripts

1. **Use meaningful tags**: Create tags for different purposes (environment, team, system)
2. **Add notes**: Document what scripts do, when to use them, and any dependencies
3. **Set status appropriately**: Mark deprecated scripts to avoid confusion
4. **Use classification**: Distinguish between production, staging, and development scripts

### Scanning Strategy

1. **Start with recursive scanning** to find all scripts
2. **Use exclude patterns** to skip temporary files and test directories
3. **Set appropriate max file size** to avoid indexing large data files
4. **Re-scan regularly** to keep the index up to date

### Performance Tips

1. **Use pagination** when browsing large script collections
2. **Apply filters** to narrow down search results
3. **Exclude unnecessary directories** to speed up scans
4. **Use tags** for quick categorization instead of relying solely on search

## Supported Script Types

Script Manager automatically detects the following file types:

- **Python**: .py
- **PowerShell**: .ps1, .psm1
- **Bash**: .sh
- **Batch**: .bat, .cmd
- **SQL**: .sql
- **JavaScript**: .js
- **TypeScript**: .ts
- **YAML**: .yml, .yaml
- **JSON**: .json
- **Terraform**: .tf
- **Ruby**: .rb
- **Perl**: .pl
- **PHP**: .php
- **Go**: .go
- **Rust**: .rs
- **Java**: .java
- **C#**: .cs
- **C++**: .cpp
- **C**: .c
- **R**: .r

## Troubleshooting

### Backend won't start
- Check that port 8000 is not in use
- Verify Python dependencies are installed: `pip install -r requirements.txt`
- Check for error messages in the console

### Frontend won't start
- Check that port 3000 is not in use
- Verify Node.js dependencies are installed: `npm install`
- Check for error messages in the console

### Scripts not showing up after scan
- Verify the folder path exists and is accessible
- Check exclude patterns aren't filtering out the scripts
- Ensure the file extensions are supported
- Check the max file size setting

### Database issues
- The database is automatically created at `backend/data/scripts.db`
- To reset the database, delete the file and restart the backend
- Regular backups of the database file are recommended

## Environment Variables

You can configure the application using environment variables:

```bash
# Backend configuration
export DATABASE_PATH="./data/scripts.db"
export API_PORT="8000"

# Start the backend
python main.py
```

## API Documentation

For developers integrating with the API, see [API.md](./API.md) for complete endpoint documentation.

Interactive API documentation is available at:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
