#!/usr/bin/env bash
# Manually trigger the stuff-to-do Cloud Run Job — useful for testing changes
# without waiting for the next scheduled run (every 6 hours).
#
# Usage:
#   ./trigger.sh <project_id>
#   GOOGLE_CLOUD_PROJECT=my-project ./trigger.sh
#   ./trigger.sh my-project -- --num_events_per_source 3 --source luma_tiat
set -euo pipefail

PROJECT_ID="${1:-${GOOGLE_CLOUD_PROJECT:-}}"
if [[ -z "$PROJECT_ID" ]]; then
  echo "Usage: ./trigger.sh <project_id> [-- extra app.main args]" >&2
  exit 1
fi
shift || true

REGION="${REGION:-us-west1}"
JOB_NAME="stuff-to-do"

if [[ "${1:-}" == "--" ]]; then
  shift
fi

if [[ $# -gt 0 ]]; then
  ARGS="$(IFS=,; echo "$*")"
  echo "==> Executing $JOB_NAME with args: $*"
  gcloud run jobs execute "$JOB_NAME" --region "$REGION" --project "$PROJECT_ID" --args="$ARGS"
else
  echo "==> Executing $JOB_NAME"
  gcloud run jobs execute "$JOB_NAME" --region "$REGION" --project "$PROJECT_ID"
fi
