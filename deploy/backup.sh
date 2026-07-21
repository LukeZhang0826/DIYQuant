#!/usr/bin/env bash
# Nightly backup of the local data dir to S3. Invoked by cron after the trading
# cycle; see docs/deploy.md.
#
# The SQLite files are copied with `sqlite3 .backup`, not `cp`. A plain copy of
# a live SQLite database can capture a half-written transaction and restore as
# a corrupt file, and a backup you cannot restore is worse than none because it
# reads as protection you do not have.
set -euo pipefail

BUCKET="${DIYQUANT_BACKUP_BUCKET:?set DIYQUANT_BACKUP_BUCKET}"
PROJECT_DIR="${DIYQUANT_DIR:-$HOME/DIYQuant}"
DATA_DIR="$PROJECT_DIR/data"
STAMP="$(date -u +%Y-%m-%d)"
STAGING="$(mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT

# The payload lives in its own subdirectory so the archive can be written
# alongside it rather than inside it. tar reading the directory it is currently
# writing into fails with "file changed as we read it", which under set -e
# aborts the backup entirely.
PAYLOAD="$STAGING/payload"
mkdir -p "$PAYLOAD"

echo "[backup] staging $DATA_DIR -> $PAYLOAD"

# Consistent snapshots of the databases.
for db in ledger sim_broker; do
  src="$DATA_DIR/$db.sqlite"
  if [ -f "$src" ]; then
    sqlite3 "$src" ".backup '$PAYLOAD/$db.sqlite'"
    echo "[backup] snapshotted $db.sqlite"
  fi
done

# Parquet bars are written whole, so a plain copy is safe here.
if [ -d "$DATA_DIR/bars" ]; then
  cp -r "$DATA_DIR/bars" "$PAYLOAD/bars"
  echo "[backup] copied bars/"
fi

# Refuse to upload an empty archive: it would look like a successful backup
# while preserving nothing, which is the failure mode worth avoiding most.
if [ -z "$(ls -A "$PAYLOAD")" ]; then
  echo "[backup] nothing to back up: $DATA_DIR is empty or absent" >&2
  exit 1
fi

ARCHIVE="$STAGING/diyquant-$STAMP.tar.gz"
tar -czf "$ARCHIVE" -C "$PAYLOAD" .

# Dated key, so a corrupted run cannot overwrite the last good backup. The IAM
# user has no DeleteObject, so history is append-only.
aws s3 cp "$ARCHIVE" "s3://$BUCKET/backups/diyquant-$STAMP.tar.gz"
echo "[backup] uploaded backups/diyquant-$STAMP.tar.gz ($(du -h "$ARCHIVE" | cut -f1))"
