#!/usr/bin/env bash
# Deploy the public stats API as an unauthenticated Cloud Run service.
#
# Two pages, both read straight from Firestore (no Calendar API calls at
# page-load time):
#   GET /             Single source of truth: every event currently on the
#                      calendar in the next 30 days (title, description,
#                      start/end, location, source calendar, manual/automatic),
#                      read from the Firestore snapshot that app/sync_engine.py
#                      rewrites at the end of every scheduler run
#                      (app/event_snapshot_store.py).
#   GET /sync-stats    Firestore sync-run history (app/stats_store.py), newest first.
#
# Prerequisites:
#   - Run ./deploy.sh first — it provisions the Firestore database and the
#     job that populates it.
#
# Usage:
#   GOOGLE_CLOUD_PROJECT=my-project ./deploy_api.sh
#   ./deploy_api.sh my-project
set -euo pipefail

PROJECT_ID="${1:-${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT or pass it as argument}}"
REGION="${REGION:-us-west1}"
SERVICE_NAME="stuff-to-do-stats-api"
IMAGE="gcr.io/$PROJECT_ID/$SERVICE_NAME"
JOB_SA="stuff-to-do-runner@$PROJECT_ID.iam.gserviceaccount.com"

echo "==> Project: $PROJECT_ID"
echo "==> Region:  $REGION"
echo ""

echo "==> Enabling APIs..."
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  firestore.googleapis.com \
  --project "$PROJECT_ID"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "==> Building and pushing image..."
gcloud builds submit --tag "$IMAGE" --project "$PROJECT_ID" "$SCRIPT_DIR/webapi"

echo "==> Deploying Cloud Run service (public, unauthenticated) as $JOB_SA..."
gcloud run deploy "$SERVICE_NAME" \
  --image "$IMAGE" \
  --service-account "$JOB_SA" \
  --allow-unauthenticated \
  --region "$REGION" \
  --project "$PROJECT_ID"

echo ""
echo "Done! Public stats API:"
URL="$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --project "$PROJECT_ID" --format='value(status.url)')"
echo "  $URL/"
echo "  $URL/sync-stats"
