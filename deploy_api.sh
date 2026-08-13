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
# Dedicated, minimally-privileged SA for this public/unauthenticated service —
# deliberately NOT the stuff-to-do-runner SA that deploy.sh sets up for the
# sync job, which holds Secret Manager access (Eventbrite token, Gmail app
# password, Google Places API key) and full Firestore read/write. This
# service only ever reads two Firestore collections, so it gets read-only
# Firestore access and nothing else — a bug here can't leak those secrets or
# let anyone tamper with synced data.
WEBAPI_SA_ID="stuff-to-do-webapi"
WEBAPI_SA="$WEBAPI_SA_ID@$PROJECT_ID.iam.gserviceaccount.com"

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

echo "==> Setting up webapi service account..."
gcloud iam service-accounts create "$WEBAPI_SA_ID" \
  --display-name="Stuff To Do Stats API" \
  --project "$PROJECT_ID" 2>/dev/null || true

echo "==> Granting $WEBAPI_SA read-only Firestore access..."
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$WEBAPI_SA" \
  --role="roles/datastore.viewer" \
  --condition=None >/dev/null

echo "==> Building and pushing image..."
# Submitted from the repo root (not webapi/) so the build can pull in
# config/settings.py — see webapi/Dockerfile and webapi/cloudbuild.yaml.
gcloud builds submit --config "$SCRIPT_DIR/webapi/cloudbuild.yaml" \
  --substitutions "_IMAGE=$IMAGE" --project "$PROJECT_ID" "$SCRIPT_DIR"

echo "==> Deploying Cloud Run service (public, unauthenticated) as $WEBAPI_SA..."
gcloud run deploy "$SERVICE_NAME" \
  --image "$IMAGE" \
  --service-account "$WEBAPI_SA" \
  --allow-unauthenticated \
  --region "$REGION" \
  --project "$PROJECT_ID"

echo ""
echo "Done! Public stats API:"
URL="$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --project "$PROJECT_ID" --format='value(status.url)')"
echo "  $URL/"
echo "  $URL/sync-stats"
