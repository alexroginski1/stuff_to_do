#!/usr/bin/env bash
# Deploy the public stats API as an unauthenticated Cloud Run service.
#
# Serves the Firestore data the main job writes on every scheduler run (see
# app/stats_store.py) as a single public HTML table, newest first:
#   GET /?limit=200
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
API_SA="$SERVICE_NAME@$PROJECT_ID.iam.gserviceaccount.com"

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

# ── Read-only service account ─────────────────────────────────────────────────
# This service is public and unauthenticated, so it only ever gets Firestore
# read access — never the write role the job's service account has.
echo "==> Setting up read-only service account..."
gcloud iam service-accounts create "$SERVICE_NAME" \
  --display-name="Stuff To Do Stats API (read-only)" \
  --project "$PROJECT_ID" 2>/dev/null || true

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$API_SA" \
  --role="roles/datastore.viewer" \
  --condition=None >/dev/null

echo "==> Deploying Cloud Run service (public, unauthenticated)..."
gcloud run deploy "$SERVICE_NAME" \
  --image "$IMAGE" \
  --service-account "$API_SA" \
  --allow-unauthenticated \
  --region "$REGION" \
  --project "$PROJECT_ID"

echo ""
echo "Done! Public stats API:"
URL="$(gcloud run services describe "$SERVICE_NAME" --region "$REGION" --project "$PROJECT_ID" --format='value(status.url)')"
echo "  $URL/"
