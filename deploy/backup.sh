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

echo "[backup] staging $DATA_DIR -> $STAGING"

# Consistent snapshots of the databases.
for db in ledger sim_broker; do
  src="$DATA_DIR/$db.sqlite"
  if [ -f "$src" ]; then
    sqlite3 "$src" ".backup '$STAGING/$db.sqlite'"
    echo "[backup] snapshotted $db.sqlite"
  fi
done

# Parquet bars are written whole, so a plain copy is safe here.
if [ -d "$DATA_DIR/bars" ]; then
  cp -r "$DATA_DIR/bars" "$STAGING/bars"
  echo "[backup] copied bars/"
fi

ARCHIVE="$STAGING/diyquant-$STAMP.tar.gz"
tar -czf "$ARCHIVE" -C "$STAGING" --exclude="$(basename "$ARCHIVE")" .

# Dated key, so a corrupted run cannot overwrite the last good backup. The IAM
# user has no DeleteObject, so history is append-only.
aws s3 cp "$ARCHIVE" "s3://$BUCKET/backups/diyquant-$STAMP.tar.gz"
echo "[backup] uploaded backups/diyquant-$STAMP.tar.gz ($(du -h "$ARCHIVE" | cut -f1))"
