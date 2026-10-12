#!/bin/bash
# Terran Society Book Manager Startup Script

# Change to script directory
cd "$(dirname "$0")"

# Load environment variables if .env exists
if [ -f ".env" ]; then
    export $(cat .env | grep -v '#' | xargs)
fi

# Load database config if it exists
CONFIG_FILE="config/db_config.json"
if [ -f "$CONFIG_FILE" ]; then
    echo "Loading database configuration from $CONFIG_FILE..."
    export DB_HOST=$(cat $CONFIG_FILE | grep -o '"host": *"[^"]*"' | sed 's/"host": *"\(.*\)"/\1/')
    export DB_PORT=$(cat $CONFIG_FILE | grep -o '"port": *[0-9]*' | sed 's/"port": *\([0-9]*\)/\1/')
    export DB_NAME=$(cat $CONFIG_FILE | grep -o '"database": *"[^"]*"' | sed 's/"database": *"\(.*\)"/\1/')
    export DB_USER=$(cat $CONFIG_FILE | grep -o '"user": *"[^"]*"' | sed 's/"user": *"\(.*\)"/\1/')
    export DB_PASSWORD=$(cat $CONFIG_FILE | grep -o '"password": *"[^"]*"' | sed 's/"password": *"\(.*\)"/\1/')
fi

# Check if virtual environment exists
if [ ! -d ".venv" ]; then
    echo "Virtual environment not found. Creating..."
    python3 -m venv .venv
    echo "Installing dependencies..."
    .venv/bin/pip install -r requirements.txt
fi

# Activate virtual environment
source .venv/bin/activate

# Start the Flask application
echo "Starting Terran Society Book Manager..."
echo "Access the application at: http://localhost:5000"
cd app
python3 tsbook.py
