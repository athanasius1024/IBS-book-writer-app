#!/bin/bash
# Terran Society Book Manager - Database Setup Script
# This script creates the PostgreSQL database, schema, and initial data

set -e  # Exit on error

echo "=========================================="
echo "Terran Society Book Manager"
echo "Database Setup Script"
echo "=========================================="
echo ""

# Check if PostgreSQL is installed
if ! command -v psql &> /dev/null; then
    echo "❌ Error: PostgreSQL is not installed."
    echo "Please install PostgreSQL first:"
    echo "  Ubuntu/Debian: sudo apt install postgresql postgresql-contrib"
    echo "  macOS: brew install postgresql"
    exit 1
fi

echo "✓ PostgreSQL is installed"
echo ""

# Prompt for PostgreSQL admin credentials
echo "Enter PostgreSQL admin credentials:"
echo "(Default credentials: username='dba', password='sql')"
echo ""
read -p "PostgreSQL admin username [default: dba]: " PG_ADMIN_USER
PG_ADMIN_USER=${PG_ADMIN_USER:-dba}

read -sp "PostgreSQL admin password [default: sql]: " PG_ADMIN_PASSWORD
PG_ADMIN_PASSWORD=${PG_ADMIN_PASSWORD:-sql}
echo ""
echo ""

# Prompt for new database details
echo "Enter database configuration:"
read -p "Database name [default: db_terran_society]: " DB_NAME
DB_NAME=${DB_NAME:-db_terran_society}

read -p "Database user [default: rock]: " DB_USER
DB_USER=${DB_USER:-rock}

read -sp "Database user password: " DB_PASSWORD
echo ""

read -p "Database schema [default: scm_terran_society]: " DB_SCHEMA
DB_SCHEMA=${DB_SCHEMA:-scm_terran_society}
echo ""

# Confirm settings
echo "=========================================="
echo "Configuration Summary:"
echo "=========================================="
echo "Database Name: $DB_NAME"
echo "Database User: $DB_USER"
echo "Database Schema: $DB_SCHEMA"
echo "=========================================="
read -p "Proceed with setup? (y/n): " CONFIRM

if [[ ! $CONFIRM =~ ^[Yy]$ ]]; then
    echo "Setup cancelled."
    exit 0
fi

echo ""
echo "Starting database setup..."
echo ""

# Set PostgreSQL password environment variable
export PGPASSWORD="$PG_ADMIN_PASSWORD"

# Step 1: Create database and user
echo "📦 Step 1: Creating database and user..."
psql -h localhost -U "$PG_ADMIN_USER" -c "CREATE DATABASE $DB_NAME;" 2>/dev/null || echo "  Database already exists"
psql -h localhost -U "$PG_ADMIN_USER" -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';" 2>/dev/null || echo "  User already exists"
psql -h localhost -U "$PG_ADMIN_USER" -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;"
psql -h localhost -U "$PG_ADMIN_USER" -c "ALTER DATABASE $DB_NAME OWNER TO $DB_USER;"
echo "✓ Database and user created"
echo ""

# Switch to new user credentials
export PGPASSWORD="$DB_PASSWORD"

# Step 2: Create schema
echo "📋 Step 2: Creating schema..."
psql -h localhost -U "$DB_USER" -d "$DB_NAME" -c "CREATE SCHEMA IF NOT EXISTS $DB_SCHEMA;"
psql -h localhost -U "$DB_USER" -d "$DB_NAME" -c "GRANT ALL ON SCHEMA $DB_SCHEMA TO $DB_USER;"
psql -h localhost -U "$DB_USER" -d "$DB_NAME" -c "ALTER DEFAULT PRIVILEGES IN SCHEMA $DB_SCHEMA GRANT ALL ON TABLES TO $DB_USER;"
echo "✓ Schema created"
echo ""

# Step 3: Create tables
echo "📊 Step 3: Creating database tables..."
SCHEMA_FILE="$(dirname "$0")/scripts/pg_schema.sql"

if [ ! -f "$SCHEMA_FILE" ]; then
    echo "❌ Error: Schema file not found at $SCHEMA_FILE"
    exit 1
fi

# Replace schema name in SQL file if different from default
if [ "$DB_SCHEMA" != "scm_terran_society" ]; then
    sed "s/scm_terran_society/$DB_SCHEMA/g" "$SCHEMA_FILE" | psql -h localhost -U "$DB_USER" -d "$DB_NAME"
else
    psql -h localhost -U "$DB_USER" -d "$DB_NAME" -f "$SCHEMA_FILE"
fi
echo "✓ Tables created"
echo ""

# Step 4: Add book metadata tables
echo "📚 Step 4: Creating book metadata tables..."
METADATA_FILE="$(dirname "$0")/scripts/add_book_metadata_tables.sql"

if [ -f "$METADATA_FILE" ]; then
    if [ "$DB_SCHEMA" != "scm_terran_society" ]; then
        sed "s/scm_terran_society/$DB_SCHEMA/g" "$METADATA_FILE" | psql -h localhost -U "$DB_USER" -d "$DB_NAME"
    else
        psql -h localhost -U "$DB_USER" -d "$DB_NAME" -f "$METADATA_FILE"
    fi
    echo "✓ Book metadata tables created"
else
    echo "⚠ Book metadata script not found, skipping"
fi
echo ""

# Step 5: Load sample data
echo "🌱 Step 5: Loading sample data..."
SAMPLE_DATA="$(dirname "$0")/scripts/sample_data.sql"

if [ -f "$SAMPLE_DATA" ]; then
    if [ "$DB_SCHEMA" != "scm_terran_society" ]; then
        sed "s/scm_terran_society/$DB_SCHEMA/g" "$SAMPLE_DATA" | psql -h localhost -U "$DB_USER" -d "$DB_NAME"
    else
        psql -h localhost -U "$DB_USER" -d "$DB_NAME" -f "$SAMPLE_DATA"
    fi
    echo "✓ Sample data loaded"
    echo "  (3 tiers, 3 branches, 2 institutions, 3 roles, 4 duties, 1 process)"
else
    echo "⚠ Sample data file not found, skipping"
fi
echo ""

# Step 6: Save configuration
echo "💾 Step 6: Saving database configuration..."
CONFIG_DIR="$(dirname "$0")/config"
mkdir -p "$CONFIG_DIR"
CONFIG_FILE="$CONFIG_DIR/db_config.json"

cat > "$CONFIG_FILE" << EOF
{
  "host": "localhost",
  "port": 5432,
  "database": "$DB_NAME",
  "user": "$DB_USER",
  "password": "$DB_PASSWORD"
}
EOF

chmod 600 "$CONFIG_FILE"
echo "✓ Configuration saved to $CONFIG_FILE"
echo ""

# Clear password from environment
unset PGPASSWORD

echo "=========================================="
echo "✅ Database setup complete!"
echo "=========================================="
echo ""
echo "Database Details:"
echo "  Host: localhost"
echo "  Port: 5432"
echo "  Database: $DB_NAME"
echo "  User: $DB_USER"
echo "  Schema: $DB_SCHEMA"
echo ""
echo "Next steps:"
echo "  1. Start the application: ./start.sh"
echo "  2. Open your browser to: http://localhost:5000"
echo "  3. Configure additional settings in the web interface"
echo ""
echo "The database configuration has been saved."
echo "You can also configure it later via the web interface (Database menu)."
echo ""
