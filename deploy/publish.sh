#!/usr/bin/env bash
# Regenerate the public dashboard and push it to S3 behind CloudFront.
# Invoked by cron a few minutes after the trading cycle; see docs/deploy.md.
#
# Publishes two files from one ledger read:
#   index.html   what people look at
#   state.json   the same data as a contract, for any future frontend
#
# The box only ever pushes outward. Nothing here opens an inbound port, which
# is what keeps the trading host unreachable from the internet.
set -euo pipefail

BUCKET="${DIYQUANT_SITE_BUCKET:?set DIYQUANT_SITE_BUCKET}"
DISTRIBUTION="${DIYQUANT_DISTRIBUTION_ID:?set DIYQUANT_DISTRIBUTION_ID}"
PROJECT_DIR="${DIYQUANT_DIR:-$HOME/DIYQuant}"
PY="$PROJECT_DIR/.venv/bin/python"
STAGING="$(mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT

cd "$PROJECT_DIR"
"$PY" scripts/report.py --out "$STAGING/index.html" --json-out "$STAGING/state.json"

# Short max-age rather than relying on invalidation alone: if an invalidation
# is ever skipped or fails, the page still goes stale for minutes rather than
# for a day. The invalidation below then makes the update near-immediate.
aws s3 cp "$STAGING/index.html" "s3://$BUCKET/index.html" \
  --content-type "text/html; charset=utf-8" --cache-control "public, max-age=300"
aws s3 cp "$STAGING/state.json" "s3://$BUCKET/state.json" \
  --content-type "application/json" --cache-control "public, max-age=300"

aws cloudfront create-invalidation --distribution-id "$DISTRIBUTION" \
  --paths "/index.html" "/state.json" --query 'Invalidation.Id' --output text

echo "[publish] live at the CloudFront domain for $DISTRIBUTION"
