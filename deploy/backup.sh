#!/usr/bin/env bash
# IBS Book Writer - back up the database and the uploads directory.
#
# Writes a timestamped folder under $BACKUP_DIR containing:
#   db.dump        pg_dump custom format (restore with pg_restore)
#   uploads.tar.gz the uploaded images (skipped if the directory is missing)
#   SHA256SUMS     checksums of the files above
# and deletes backup folders older than $KEEP_DAYS days.
#
# Settings come from the environment (all optional):
#   DB_HOST DB_PORT DB_NAME DB_USER  - PostgreSQL connection (default localhost:5432, db_ibs_bookwriter, rock)
#   PGPASSWORD or ~/.pgpass          - the password (never pass it on the command line)
#   UPLOAD_DIR                       - default <project>/uploads
#   BACKUP_DIR                       - default $HOME/backups/ibs-bookwriter
#   KEEP_DAYS                        - default 14
#
# Schedule it nightly, for example from root's or the service user's crontab:
#   15 2 * * *  /opt/ibs-bookwriter/deploy/backup.sh >> /var/log/ibs-backup.log 2>&1
# Then copy $BACKUP_DIR off the machine (rsync, rclone, object storage).
set -euo pipefail
umask 077

project="$(cd "$(dirname "$0")/.." && pwd)"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-db_ibs_bookwriter}"
DB_USER="${DB_USER:-rock}"
UPLOAD_DIR="${UPLOAD_DIR:-$project/uploads}"
BACKUP_DIR="${BACKUP_DIR:-$HOME/backups/ibs-bookwriter}"
KEEP_DAYS="${KEEP_DAYS:-14}"

command -v pg_dump >/dev/null || { echo "pg_dump is not installed (install postgresql-client)." >&2; exit 1; }

stamp="$(date +%Y%m%d-%H%M%S)"
dest="$BACKUP_DIR/$stamp"
mkdir -p "$dest"

echo "[$stamp] Dumping $DB_NAME from $DB_HOST:$DB_PORT as $DB_USER ..."
pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -Fc -f "$dest/db.dump" "$DB_NAME"
pg_restore --list "$dest/db.dump" >/dev/null     # fails if the dump is unreadable

if [ -d "$UPLOAD_DIR" ]; then
    echo "[$stamp] Archiving $UPLOAD_DIR ..."
    tar -czf "$dest/uploads.tar.gz" -C "$UPLOAD_DIR" .
else
    echo "[$stamp] No uploads directory at $UPLOAD_DIR - skipping."
fi

( cd "$dest" && sha256sum ./* > SHA256SUMS )

find "$BACKUP_DIR" -mindepth 1 -maxdepth 1 -type d -mtime +"$KEEP_DAYS" -exec rm -rf {} +

echo "[$stamp] Backup complete: $dest"
du -sh "$dest" | cut -f1
