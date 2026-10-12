# Terran Society Book Manager - Web Application

A Flask-based web GUI for managing the Terran Society organizational structure database with HTMX for dynamic interactions.

## Features

### Phase 1 (Complete)
- ✅ **Dashboard** - Statistics and recent activity overview
- ✅ **Institution Management** - Full CRUD operations with filtering
- ✅ **Role Management** - Create, edit, delete roles with institution filtering
- ✅ **Duty Management** - Inline HTMX-powered duty editing within role pages
- ✅ **Process Management** - Create and manage organizational processes
- ✅ **Book Generation** - One-click button to regenerate the book manuscript
- ✅ **Responsive Design** - Bootstrap 5 with mobile-friendly layout
- ✅ **Clean UI** - Modern card-based interface with icons

## Technology Stack

- **Backend**: Flask 3.0 + SQLAlchemy 2.0
- **Database**: PostgreSQL 17 (db_kirby/scm_kirby)
- **Frontend**: Bootstrap 5 + HTMX 1.9
- **Icons**: Bootstrap Icons
- **Python**: 3.13.5 (or compatible 3.x)

## Installation

### 1. Install Python Dependencies

```bash
cd /media/infodine/LaCie/z_stash/z-terran/TerranSocietyBook/infobuild/app
pip3 install -r requirements.txt
```

Or if using the project's virtual environment:

```bash
source ../.venv/bin/activate
pip install -r requirements.txt
```

### 2. Verify Database Connection

Make sure PostgreSQL is running and the database exists:

```bash
PGPASSWORD=river psql -h localhost -U rock -d db_kirby -c "SELECT COUNT(*) FROM scm_kirby.tier;"
```

If the database doesn't exist, create it:

```bash
# Create database and schema
PGPASSWORD=river psql -h localhost -U rock -d postgres -c "CREATE DATABASE db_kirby;"
PGPASSWORD=river psql -h localhost -U rock -d db_kirby -c "CREATE SCHEMA scm_kirby;"

# Run the schema creation script
PGPASSWORD=river psql -h localhost -U rock -d db_kirby -f ../scripts/pg_schema.sql

# Populate data
cd ..
python3 scripts/populate_db.py
python3 scripts/populate_roles.py
```

## Running the Application

### Development Mode

```bash
cd /media/infodine/LaCie/z_stash/z-terran/TerranSocietyBook/infobuild/app
python3 tsbook.py
```

The application will start on **http://localhost:5000**

### Production Mode (with Gunicorn)

```bash
pip3 install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

## Usage Guide

### Dashboard
- View statistics for all data types (tiers, branches, institutions, roles, duties, processes)
- See recently modified roles
- Check book generation status
- Quick action buttons for common tasks

### Managing Institutions
1. Navigate to **Institutions** from the menu
2. Filter by tier or branch using the dropdown filters
3. Click **New Institution** to create one
4. View institution details to see all associated roles
5. Edit or delete institutions as needed

### Managing Roles
1. Navigate to **Roles** from the menu
2. Filter by institution if needed
3. Click **New Role** to create one
4. View role details to see all duties and explanations
5. Add duties inline using HTMX (no page reload!)

### Managing Duties (HTMX Feature)
1. Open any role detail page
2. Scroll to the **Duties** section
3. Use the "Add New Duty" form at the bottom
4. Duties appear instantly without page reload
5. Delete duties with the trash icon

### Managing Processes
1. Navigate to **Processes** from the menu
2. Create, view, edit, or delete processes
3. Processes represent organizational procedures

### Generating the Book
1. Click the **Generate Book** button in the navigation bar
2. Or use the button on the dashboard
3. This runs the `scripts/generate_book.py` script
4. Check the book output in `book/manuscript.md`

## File Structure

```
app/
├── tsbook.py                      # Main Flask application
├── config.py                   # Configuration settings
├── models.py                   # SQLAlchemy models
├── requirements.txt            # Python dependencies
├── README.md                   # This file
├── templates/                  # Jinja2 HTML templates
│   ├── base.html              # Base layout with navigation
│   ├── index.html             # Dashboard
│   ├── institutions/
│   │   ├── list.html          # Institution list with filters
│   │   ├── detail.html        # Institution details + roles
│   │   └── form.html          # Create/edit institution
│   ├── roles/
│   │   ├── list.html          # Role list with filters
│   │   ├── detail.html        # Role details + duties (HTMX)
│   │   └── form.html          # Create/edit role
│   ├── duties/
│   │   └── _duty_item.html    # HTMX component for duties
│   └── processes/
│       ├── list.html          # Process list
│       ├── detail.html        # Process details
│       └── form.html          # Create/edit process
└── static/                     # Static assets
    ├── css/
    │   └── style.css          # Custom styles
    └── js/
        └── app.js             # Custom JavaScript
```

## Database Schema

The application uses the `scm_kirby` schema in the `db_kirby` PostgreSQL database with these main tables:

- **tier** - Organizational tiers (District, Region, World)
- **branch** - Government branches (Executive, Legislative, Judicial, etc.)
- **institution** - Specific institutions within tiers and branches
- **role** - Roles within institutions
- **role_duty** - Duties assigned to roles
- **role_explain** - Explanatory text for roles
- **institution_explain** - Explanatory text for institutions
- **tier_explain** - Explanatory text for tiers
- **process** - Organizational processes

## Configuration

Edit `config.py` to change:

- Database connection settings
- Secret key for sessions
- Book output directory
- Generation script path

For production, set environment variables:
```bash
export SECRET_KEY="your-secret-key-here"
export DB_PASSWORD="your-db-password"
```

## Troubleshooting

### Database Connection Errors

**Error**: `psycopg2.OperationalError: FATAL: database "db_kirby" does not exist`

**Solution**: Create the database first:
```bash
PGPASSWORD=river psql -h localhost -U rock -d postgres -c "CREATE DATABASE db_kirby;"
```

### Template Not Found Errors

**Error**: `TemplateNotFound: base.html`

**Solution**: Make sure you're running the app from the `app/` directory:
```bash
cd /media/infodine/LaCie/z_stash/z-terran/TerranSocietyBook/infobuild/app
python3 tsbook.py
```

### HTMX Not Working

**Error**: Duties don't add without page refresh

**Solution**: 
1. Check browser console for JavaScript errors
2. Make sure HTMX is loaded (check page source)
3. Verify the duty routes return proper HTML

### Book Generation Fails

**Error**: `FileNotFoundError: generate_book.py`

**Solution**: Make sure the scripts directory exists and contains `generate_book.py`:
```bash
ls -la ../scripts/generate_book.py
```

## Future Enhancements (Phase 2-4)

- [ ] Search functionality across all entities
- [ ] Drag-and-drop reordering of items
- [ ] Rich text editor with Markdown preview
- [ ] Version tracking and comparison
- [ ] Bulk import/export (CSV/JSON)
- [ ] Relationship visualization diagrams
- [ ] User authentication and permissions
- [ ] API endpoints for external access
- [ ] Real-time collaborative editing

## Support

For issues or questions:
1. Check the main project README: `../README.md`
2. Review the WARP.md guidance: `../WARP.md`
3. Check PostgreSQL setup: `../POSTGRESQL_SETUP.md`

## License

Part of the Terran Society Book project.
