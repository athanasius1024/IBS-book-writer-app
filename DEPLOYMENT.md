# Terran Society Book Manager - Deployment Guide

## Overview

The Terran Society Book Manager is a Flask-based web application for managing organizational structure documentation and generating professional books in PDF and HTML formats.

## System Requirements

- **Python**: 3.8 or higher
- **PostgreSQL**: 13 or higher
- **Operating System**: Linux (Ubuntu/Debian recommended) or macOS
- **Memory**: 2GB RAM minimum
- **Disk Space**: 500MB minimum

## Installation

### 1. Install System Dependencies

#### Ubuntu/Debian:
```bash
# Update package list
sudo apt update

# Install Python 3 and pip
sudo apt install python3 python3-pip python3-venv

# Install PostgreSQL
sudo apt install postgresql postgresql-contrib

# Install Pandoc (for document conversion)
sudo apt install pandoc

# Install WeasyPrint dependencies
sudo apt install python3-cffi python3-brotli libpango-1.0-0 libpangoft2-1.0-0
```

#### macOS:
```bash
# Install Homebrew if not installed
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Install Python and PostgreSQL
brew install python postgresql pandoc

# Start PostgreSQL service
brew services start postgresql
```

### 2. Clone or Extract Application

```bash
cd /path/to/installation/directory
# If from git:
git clone <repository-url> terran-society

# Or extract from archive:
tar -xzf terran-society.tar.gz
cd terran-society
```

### 3. Set Up Python Virtual Environment

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. Set Up PostgreSQL Database

#### Option A: Automated Setup (Recommended)

Use the interactive setup script:

```bash
./setup_database.sh
```

The script will:
- Prompt you for PostgreSQL admin credentials
- Ask for database configuration (name, user, password, schema)
- Create the database and user
- Create all tables and schema
- Populate initial data
- Save configuration for the application

#### Option B: Manual Setup

##### Create Database and User:
```bash
# Switch to postgres user
sudo -u postgres psql

# In PostgreSQL prompt:
CREATE DATABASE db_terran_society;
CREATE USER rock WITH PASSWORD 'your_secure_password_here';
GRANT ALL PRIVILEGES ON DATABASE db_terran_society TO rock;
\q
```

##### Create Schema and Tables:
```bash
# Run schema creation script
PGPASSWORD=your_secure_password_here psql -h localhost -U rock -d db_terran_society -f scripts/pg_schema.sql
```

##### Populate Initial Data:
```bash
# From the application directory
cd scripts
python3 populate_db.py
python3 populate_roles.py
cd ..
```

### 5. Configure Database Connection

You can configure the database connection in two ways:

#### Option A: Using the Web Interface (Recommended)
1. Start the application (see "Running the Application" below)
2. Navigate to http://localhost:5000
3. Click "Database" in the top navigation
4. Enter your database connection details
5. Click "Test Connection" to verify
6. Click "Save Configuration"
7. Restart the application

#### Option B: Manual Configuration
Create `config/db_config.json`:
```json
{
  "host": "localhost",
  "port": 5432,
  "database": "db_terran_society",
  "user": "rock",
  "password": "your_secure_password_here"
}
```

## Running the Application

### Quick Start (Recommended)

```bash
./start.sh
```

The startup script will:
- Create virtual environment if it doesn't exist
- Install dependencies
- Load database configuration
- Start the Flask application

Access the application at: **http://localhost:5000**

### Manual Start

```bash
# Activate virtual environment
source .venv/bin/activate

# Change to app directory
cd app

# Start Flask
python3 tsbook.py
```

### Production Deployment with Gunicorn

For production, use a production-grade WSGI server:

```bash
# Install gunicorn
pip install gunicorn

# Run with gunicorn
cd app
gunicorn -w 4 -b 0.0.0.0:5000 tsbook:app
```

## Features

### 1. Data Management
- **Tiers**: District, Region, World levels
- **Branches**: Executive, Legislative, Judicial, Fair Witness, Military
- **Institutions**: Organizational bodies at each tier/branch
- **Roles**: Positions within institutions
- **Duties**: Responsibilities for each role
- **Processes**: Organizational procedures

### 2. Book Generation
- **Markdown**: Source format for book manuscript
- **PDF**: Professional book output with:
  - Custom cover page
  - Table of contents with page numbers
  - Headers and footers
  - Glossary with hyperlinks
  - Proper pagination
- **HTML**: Web-optimized version with:
  - Responsive design
  - Interactive navigation
  - Glossary term hyperlinking
  - Sidebar navigation

### 3. Database Settings
- Web-based database configuration
- Connection testing
- Secure credential storage

## Directory Structure

```
terran-society/
├── app/                    # Flask application
│   ├── tsbook.py          # Main application
│   ├── models.py          # Database models
│   ├── config.py          # Configuration
│   ├── templates/         # HTML templates
│   └── static/            # CSS, JS, images
├── book/                  # Generated book outputs
│   ├── manuscript.md      # Source markdown
│   ├── TerranSocietyBook.pdf
│   └── TerranSocietyBook.html
├── config/                # Configuration files
│   └── db_config.json     # Database credentials
├── scripts/               # Utility scripts
│   ├── generate_book.py   # Generate manuscript
│   ├── generate_pdf.py    # Generate PDF
│   ├── generate_html.py   # Generate HTML
│   ├── pg_schema.sql      # Database schema
│   ├── populate_db.py     # Populate data
│   └── populate_roles.py  # Populate roles
├── templates/             # Book templates
│   ├── book.css          # PDF styling
│   └── book_html.css     # HTML styling
├── requirements.txt       # Python dependencies
├── start.sh              # Startup script
└── DEPLOYMENT.md         # This file
```

## Security Considerations

1. **Change Default Passwords**: Replace the default password ('river') with a strong password
2. **Secret Key**: Set a secure SECRET_KEY in production:
   ```bash
   export SECRET_KEY='your-random-secret-key-here'
   ```
3. **Database Access**: Restrict PostgreSQL to localhost or use firewall rules
4. **HTTPS**: Use a reverse proxy (nginx, Apache) with SSL/TLS in production
5. **File Permissions**: Ensure config files are not world-readable:
   ```bash
   chmod 600 config/db_config.json
   ```

## Troubleshooting

### Database Connection Errors
```bash
# Check PostgreSQL is running
sudo systemctl status postgresql

# Test connection manually
psql -h localhost -U rock -d db_terran_society

# Check logs
sudo tail -f /var/log/postgresql/postgresql-*.log
```

### PDF Generation Issues
```bash
# Verify Pandoc is installed
pandoc --version

# Verify WeasyPrint dependencies
python3 -c "import weasyprint; print(weasyprint.__version__)"

# Check book generation manually
cd scripts
python3 generate_pdf.py
```

### Port Already in Use
```bash
# Find process using port 5000
lsof -i :5000

# Kill the process (replace PID with actual process ID)
kill -9 PID

# Or use a different port
export FLASK_RUN_PORT=5001
```

## Backup and Restore

### Backup Database
```bash
pg_dump -h localhost -U rock db_terran_society > backup_$(date +%Y%m%d).sql
```

### Restore Database
```bash
psql -h localhost -U rock -d db_terran_society < backup_20250101.sql
```

### Backup Generated Books
```bash
tar -czf books_backup_$(date +%Y%m%d).tar.gz book/
```

## Updating the Application

```bash
# Backup database first (see above)

# Pull latest code
git pull

# Update dependencies
source .venv/bin/activate
pip install -r requirements.txt --upgrade

# Run any database migrations if provided
# (Follow specific upgrade instructions)

# Restart application
pkill -f tsbook.py
./start.sh
```

## Support

For issues, questions, or contributions:
- Check the logs in the application terminal
- Review database connection settings
- Verify all dependencies are installed
- Ensure PostgreSQL is running and accessible

## License

Copyright © 2025 Terran Society. All rights reserved.
