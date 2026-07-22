#!/usr/bin/env bash
# Deploy the public stats API as an unauthenticated Cloud Run service.
#
# Two pages:
#   GET /            Firestore sync-run history (app/stats_store.py), newest first.
#   GET /by-source    Live count of upcoming events per calendar, broken down by
#                     event source (reads the Calendar API directly; events with
#                     no `source` extended property, e.g. manually added ones,
#                     are grouped under "Manually Added Events").
#
# Prerequisites:
#   - Run ./deploy.sh first — it provisions the Firestore database, the job
#     that populates it, and the stuff-to-do-runner service account (shared
#     on every calendar in config/settings.py's CALENDAR_IDS, with "Make
#     changes to events"). This service runs as that same account, so no
#     separate calendar-sharing step is needed for /by-source. Note this
#     means the public, unauthenticated /by-source endpoint executes with
#     write-capable calendar credentials (it only ever calls read methods,
#     but the credential itself isn't restricted to read).
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
echo "  $URL/by-source"
