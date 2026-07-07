#!/usr/bin/env bash
# Creates Cloud Logging log-based metrics and the Cloud Monitoring dashboard.
# Run once from the repo root:  bash monitoring/setup_monitoring.sh
#
# Prerequisites:
#   gcloud auth login && gcloud config set project YOUR_PROJECT_ID

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> Creating log-based metric: events_fetched"
gcloud logging metrics create events_fetched \
  --config-from-file="${SCRIPT_DIR}/events_fetched_metric.yaml" \
  || gcloud logging metrics update events_fetched \
       --config-from-file="${SCRIPT_DIR}/events_fetched_metric.yaml"

echo "==> Creating log-based metric: events_sync_result"
gcloud logging metrics create events_sync_result \
  --config-from-file="${SCRIPT_DIR}/events_sync_result_metric.yaml" \
  || gcloud logging metrics update events_sync_result \
       --config-from-file="${SCRIPT_DIR}/events_sync_result_metric.yaml"

echo "==> Creating Cloud Monitoring dashboard"
gcloud monitoring dashboards create \
  --config-from-file="${SCRIPT_DIR}/dashboard.json"

echo ""
echo "Done. Open Cloud Monitoring > Dashboards to see 'Stuff To Do – Event Sync'."
echo "Note: metrics populate only after the next scheduled job run."
echo ""
echo "To get an email whenever a run has sync errors, run:"
echo "  ./setup_error_alert.sh you@example.com"
