#!/usr/bin/env bash
# IBS Book Writer - create the PostgreSQL database and tables (safe to re-run).
#
# Interactive by default. To run unattended, export DB_HOST, DB_PORT, DB_NAME,
# DB_USER and DB_PASSWORD (or rely on ~/.pgpass / peer auth with an empty password).
set -euo pipefail
cd "$(dirname "$0")"
umask 077

command -v psql >/dev/null || { echo "psql is not installed. Install the PostgreSQL client first." >&2; exit 1; }

ask() {  # ask VAR "Prompt" default
    local var=$1 text=$2 default=$3 reply
    if [ -z "${!var:-}" ]; then
        read -r -p "$text [$default]: " reply
        printf -v "$var" '%s' "${reply:-$default}"
    fi
}

ask DB_HOST "PostgreSQL host" "localhost"
ask DB_PORT "PostgreSQL port" "5432"
ask DB_NAME "Database name" "db_ibs_bookwriter"
ask DB_USER "PostgreSQL user" "rock"
if [ -z "${DB_PASSWORD+x}" ]; then
    read -r -s -p "Password for $DB_USER (blank to use ~/.pgpass or peer auth): " DB_PASSWORD
    echo
fi

if ! [[ "$DB_NAME" =~ ^[A-Za-z0-9_]+$ ]]; then
    echo "Database name may only contain letters, digits and underscores." >&2
    exit 1
fi

if [ -n "$DB_PASSWORD" ]; then export PGPASSWORD="$DB_PASSWORD"; fi
PSQL=(psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -v ON_ERROR_STOP=1 -X -q)

echo "Checking connection to $DB_HOST:$DB_PORT as $DB_USER ..."
"${PSQL[@]}" -d postgres -tAc "SELECT 1" >/dev/null

if [ "$("${PSQL[@]}" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'")" = "1" ]; then
    echo "Database $DB_NAME already exists."
else
    echo "Creating database $DB_NAME ..."
    "${PSQL[@]}" -d postgres -c "CREATE DATABASE \"$DB_NAME\""
fi

echo "Applying sql/schema.sql ..."
"${PSQL[@]}" -d "$DB_NAME" -f sql/schema.sql

echo "Saving connection settings to .env (readable only by you) ..."
[ -f .env ] || cp .env.template .env
chmod 600 .env
python3 scripts/set_env.py DB_HOST "$DB_HOST"
python3 scripts/set_env.py DB_PORT "$DB_PORT"
python3 scripts/set_env.py DB_NAME "$DB_NAME"
python3 scripts/set_env.py DB_USER "$DB_USER"
if [ -n "$DB_PASSWORD" ]; then python3 scripts/set_env.py DB_PASSWORD "$DB_PASSWORD"; fi
python3 scripts/set_env.py SECRET_KEY "$(python3 -c 'import secrets; print(secrets.token_hex(32))')" --if-empty

echo
echo "Done. Start the app with ./start.sh and create your account at /register."
echo "(The first account created becomes the administrator.)"
