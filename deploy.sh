#!/usr/bin/env bash
# Deploy stuff-to-do as a Cloud Run Job scheduled every 12 hours.
#
# Prerequisites:
#   - gcloud CLI installed and authenticated (gcloud auth login)
#   - GOOGLE_CLOUD_PROJECT set, or pass it as the first argument
#   - The target Google Calendar(s) (see config/settings.py CALENDARS) shared
#     with stuff-to-do-runner@<project>.iam.gserviceaccount.com, granting
#     "Make changes to events". The job authenticates as that service account
#     directly (Application Default Credentials) — no OAuth token to refresh
#     or re-generate, ever.
#
# Usage:
#   GOOGLE_CLOUD_PROJECT=my-project ./deploy.sh
#   ./deploy.sh my-project
set -euo pipefail

PROJECT_ID="${1:-${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT or pass it as argument}}"
REGION="${REGION:-us-west1}"
JOB_NAME="stuff-to-do"
IMAGE="gcr.io/$PROJECT_ID/$JOB_NAME"
JOB_SA="$JOB_NAME-runner@$PROJECT_ID.iam.gserviceaccount.com"
SCHEDULER_SA="$JOB_NAME-scheduler@$PROJECT_ID.iam.gserviceaccount.com"

echo "==> Project:  $PROJECT_ID"
echo "==> Region:   $REGION"
echo "==> Image:    $IMAGE"
echo ""

# ── Enable required APIs ──────────────────────────────────────────────────────
echo "==> Enabling APIs..."
gcloud services enable \
  run.googleapis.com \
  cloudscheduler.googleapis.com \
  cloudbuild.googleapis.com \
  secretmanager.googleapis.com \
  firestore.googleapis.com \
  --project "$PROJECT_ID"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Firestore (stats database) ────────────────────────────────────────────────
# Stores one document per (run, calendar, source) with insert/delete/skip/error
# counts — see app/stats_store.py. Read publicly via the webapi/ service
# (deploy_api.sh).
echo "==> Ensuring Firestore database exists (Native mode)..."
if ! gcloud firestore databases describe --database='(default)' --project "$PROJECT_ID" &>/dev/null; then
  gcloud firestore databases create --location="$REGION" --type=firestore-native --project "$PROJECT_ID"
fi

# ── Eventbrite token secret ───────────────────────────────────────────────────
# The Eventbrite API token is a static bearer token, unrelated to the job's
# service account / ADC. It lives in Secret Manager (never in the image or
# git) as SECRET_NAME below. Create it once with:
#   printf '%s' 'YOUR_EVENTBRITE_TOKEN' | gcloud secrets create eventbrite-api-token \
#     --data-file=- --project "$PROJECT_ID"
# and update it later with:
#   printf '%s' 'NEW_TOKEN' | gcloud secrets versions add eventbrite-api-token \
#     --data-file=- --project "$PROJECT_ID"
SECRET_NAME="eventbrite-api-token"

# ── Build and push container image ───────────────────────────────────────────
echo "==> Building and pushing image..."
gcloud builds submit --tag "$IMAGE" --project "$PROJECT_ID" "$SCRIPT_DIR"

# ── Service account for the Cloud Run Job ────────────────────────────────────
echo "==> Setting up job service account..."
gcloud iam service-accounts create "$JOB_NAME-runner" \
  --display-name="Stuff To Do Job Runner" \
  --project "$PROJECT_ID" 2>/dev/null || true

# Let the job's service account read the Eventbrite token secret.
echo "==> Granting $JOB_SA access to secret $SECRET_NAME..."
gcloud secrets add-iam-policy-binding "$SECRET_NAME" \
  --member="serviceAccount:$JOB_SA" \
  --role="roles/secretmanager.secretAccessor" \
  --project "$PROJECT_ID"

# Let the job's service account write run stats to Firestore.
echo "==> Granting $JOB_SA Firestore write access..."
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$JOB_SA" \
  --role="roles/datastore.user" \
  --condition=None >/dev/null

# ── Create or update Cloud Run Job ───────────────────────────────────────────
echo "==> Deploying Cloud Run Job..."
if gcloud run jobs describe "$JOB_NAME" --region "$REGION" --project "$PROJECT_ID" &>/dev/null; then
  VERB=update
else
  VERB=create
fi

gcloud run jobs "$VERB" "$JOB_NAME" \
  --image "$IMAGE" \
  --service-account "$JOB_SA" \
  --set-env-vars "GOOGLE_CLOUD_PROJECT=$PROJECT_ID" \
  --set-secrets "EVENTBRITE_API_TOKEN=$SECRET_NAME:latest" \
  --memory 512Mi \
  --task-timeout 600 \
  --region "$REGION" \
  --project "$PROJECT_ID"

# ── Service account for Cloud Scheduler ──────────────────────────────────────
echo "==> Setting up scheduler service account..."
gcloud iam service-accounts create "$JOB_NAME-scheduler" \
  --display-name="Stuff To Do Scheduler" \
  --project "$PROJECT_ID" 2>/dev/null || true

# Grant permission to execute the Cloud Run Job
gcloud run jobs add-iam-policy-binding "$JOB_NAME" \
  --member="serviceAccount:$SCHEDULER_SA" \
  --role="roles/run.developer" \
  --region "$REGION" \
  --project "$PROJECT_ID"

# ── Cloud Scheduler: every 12 hours ──────────────────────────────────────────
echo "==> Creating/updating Cloud Scheduler job (every 12 hours)..."
JOB_URI="https://$REGION-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$PROJECT_ID/jobs/$JOB_NAME:run"

if gcloud scheduler jobs describe "$JOB_NAME-every-6h" \
    --location "$REGION" --project "$PROJECT_ID" &>/dev/null; then
  SCHED_VERB=update
else
  SCHED_VERB=create
fi

gcloud scheduler jobs "$SCHED_VERB" http "$JOB_NAME-every-6h" \
  --schedule="0 */12 * * *" \
  --uri="$JOB_URI" \
  --message-body='{}' \
  --oauth-service-account-email="$SCHEDULER_SA" \
  --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform" \
  --location "$REGION" \
  --project "$PROJECT_ID"

# ── Kick off the first run immediately ───────────────────────────────────────
# Cloud Scheduler only fires at the next 12-hour boundary (00:00/12:00 UTC),
# which could be up to 12 hours away, so trigger the job directly here too.
echo "==> Executing $JOB_NAME now for the first run..."
gcloud run jobs execute "$JOB_NAME" --region "$REGION" --project "$PROJECT_ID"

echo ""
echo "Done! First run started now; subsequent runs happen automatically every 12 hours."
echo ""
echo "If you haven't already, share each calendar in config/settings.py's"
echo "CALENDARS with $JOB_SA, granting 'Make changes to events'."
echo ""
echo "To view logs:"
echo "  gcloud logging read 'resource.type=cloud_run_job AND resource.labels.job_name=$JOB_NAME' --project $PROJECT_ID --limit 50"
echo ""
echo "To publish the public stats API (reads what this job writes to Firestore):"
echo "  ./deploy_api.sh $PROJECT_ID"
