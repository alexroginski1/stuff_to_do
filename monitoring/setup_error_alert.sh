#!/usr/bin/env bash
# Creates an email notification channel and a Cloud Monitoring alert policy
# that fires whenever a stuff-to-do sync run reports errors (scraper
# failures, or Calendar insert/delete failures), using the events_sync_result
# log-based metric created by setup_monitoring.sh.
#
# Prerequisites:
#   - setup_monitoring.sh already run once (creates the events_sync_result metric)
#   - gcloud auth login && gcloud config set project YOUR_PROJECT_ID
#
# Usage:
#   ./setup_error_alert.sh you@example.com [project_id]
#   GOOGLE_CLOUD_PROJECT=my-project ./setup_error_alert.sh you@example.com
set -euo pipefail

EMAIL="${1:?Usage: setup_error_alert.sh <email> [project_id]}"
PROJECT_ID="${2:-${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT or pass it as second argument}}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Looking for an existing email notification channel for $EMAIL..."
CHANNEL_NAME="$(gcloud beta monitoring channels list \
  --project "$PROJECT_ID" \
  --filter="type=email AND labels.email_address=$EMAIL" \
  --format='value(name)' | head -n1)"

if [[ -z "$CHANNEL_NAME" ]]; then
  echo "==> Creating email notification channel for $EMAIL..."
  CHANNEL_NAME="$(gcloud beta monitoring channels create \
    --project "$PROJECT_ID" \
    --display-name="Stuff To Do Errors ($EMAIL)" \
    --type=email \
    --channel-labels="email_address=$EMAIL" \
    --format='value(name)')"
else
  echo "==> Reusing existing channel: $CHANNEL_NAME"
fi

echo "==> Rendering alert policy..."
TMP_POLICY="$(mktemp)"
trap 'rm -f "$TMP_POLICY"' EXIT
sed -e "s|NOTIFICATION_CHANNEL_PLACEHOLDER|$CHANNEL_NAME|g" \
    -e "s|PROJECT_ID_PLACEHOLDER|$PROJECT_ID|g" \
    "${SCRIPT_DIR}/error_alert_policy.json" > "$TMP_POLICY"

EXISTING_POLICY="$(gcloud alpha monitoring policies list \
  --project "$PROJECT_ID" \
  --filter='displayName="Stuff To Do - Sync Errors"' \
  --format='value(name)' | head -n1)"

if [[ -n "$EXISTING_POLICY" ]]; then
  echo "==> Updating existing alert policy $EXISTING_POLICY..."
  gcloud alpha monitoring policies update "$EXISTING_POLICY" \
    --project "$PROJECT_ID" \
    --policy-from-file="$TMP_POLICY"
else
  echo "==> Creating alert policy..."
  gcloud alpha monitoring policies create \
    --project "$PROJECT_ID" \
    --policy-from-file="$TMP_POLICY"
fi

echo ""
echo "Done. $EMAIL will get an email whenever a sync run reports errors."
echo "If this is a new notification channel, Google may send a verification"
echo "email first - check your inbox."
