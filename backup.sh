#!/usr/bin/env bash
# Bookmarks: online database backup with rotation.
#
# Usage:
#   ./backup.sh                      # default data dir: ./data
#   BOOKMARKS_DATA=/var/bookmarks ./backup.sh
#   KEEP=14 ./backup.sh              # keep 14 most recent backups
#
# Backups land in $BACKUP_DIR (default: <data dir>/backups) as
# bookmarks-YYYYmmdd-HHMMSS.sqlite3; older copies beyond KEEP are removed.
#
# The copy is made with sqlite3's online backup API (python manage.py backup),
# so it is consistent even while the server is writing. Run it from cron,
# e.g. daily at 03:00:
#   0 3 * * * /path/to/bookmarks/backup.sh >> /var/log/bookmarks-backup.log 2>&1

set -euo pipefail

cd "$(dirname "$0")"

DATA_DIR="${BOOKMARKS_DATA:-./data}"
KEEP="${KEEP:-7}"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_DIR="${BACKUP_DIR:-$DATA_DIR/backups}"
TARGET="$BACKUP_DIR/bookmarks-$STAMP.sqlite3"

mkdir -p "$BACKUP_DIR"

PYTHON="${PYTHON:-python3}"
if [ -x ./.venv/bin/python ]; then
  PYTHON=./.venv/bin/python
fi

"$PYTHON" manage.py --data "$DATA_DIR" backup "$TARGET"

# Rotation: keep the KEEP newest copies.
cd "$BACKUP_DIR"
ls -1t bookmarks-*.sqlite3 2>/dev/null | tail -n "+$((KEEP + 1))" | while read -r old; do
  rm -f -- "$old"
done

echo "  Ротация: сохранено не более $KEEP копий в $BACKUP_DIR"
