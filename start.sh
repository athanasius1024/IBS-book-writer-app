#!/usr/bin/env bash
# IBS Book Writer startup script.
set -euo pipefail
cd "$(dirname "$0")"
umask 077

if [ ! -d .venv ]; then
    echo "Creating virtual environment and installing dependencies..."
    python3 -m venv .venv
    .venv/bin/pip install --quiet -r requirements.txt
fi

# Make sure a .env exists and has a SECRET_KEY (never committed; mode 600).
[ -f .env ] || cp .env.template .env
chmod 600 .env
.venv/bin/python scripts/set_env.py SECRET_KEY "$(.venv/bin/python -c 'import secrets; print(secrets.token_hex(32))')" --if-empty

echo "Starting IBS Book Writer at http://${HOST:-127.0.0.1}:${PORT:-5000}"
cd app
exec ../.venv/bin/python ibsbook.py
