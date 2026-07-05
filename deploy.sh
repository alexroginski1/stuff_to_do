#!/usr/bin/env bash
# Deploy stuff-to-do as a Cloud Run Job scheduled every 6 hours.
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
  --project "$PROJECT_ID"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Build and push container image ───────────────────────────────────────────
echo "==> Building and pushing image..."
gcloud builds submit --tag "$IMAGE" --project "$PROJECT_ID" "$SCRIPT_DIR"

# ── Service account for the Cloud Run Job ────────────────────────────────────
echo "==> Setting up job service account..."
gcloud iam service-accounts create "$JOB_NAME-runner" \
  --display-name="Stuff To Do Job Runner" \
  --project "$PROJECT_ID" 2>/dev/null || true

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

# ── Cloud Scheduler: every 6 hours ───────────────────────────────────────────
echo "==> Creating/updating Cloud Scheduler job (every 6 hours)..."
JOB_URI="https://$REGION-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/$PROJECT_ID/jobs/$JOB_NAME:run"

if gcloud scheduler jobs describe "$JOB_NAME-every-6h" \
    --location "$REGION" --project "$PROJECT_ID" &>/dev/null; then
  SCHED_VERB=update
else
  SCHED_VERB=create
fi

gcloud scheduler jobs "$SCHED_VERB" http "$JOB_NAME-every-6h" \
  --schedule="0 */6 * * *" \
  --uri="$JOB_URI" \
  --message-body='{}' \
  --oauth-service-account-email="$SCHEDULER_SA" \
  --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform" \
  --location "$REGION" \
  --project "$PROJECT_ID"

echo ""
echo "Done! The job will run automatically every 6 hours."
echo ""
echo "If you haven't already, share each calendar in config/settings.py's"
echo "CALENDARS with $JOB_SA, granting 'Make changes to events'."
echo ""
echo "To run it manually for testing:"
echo "  ./trigger.sh $PROJECT_ID"
echo ""
echo "To view logs:"
echo "  gcloud logging read 'resource.type=cloud_run_job AND resource.labels.job_name=$JOB_NAME' --project $PROJECT_ID --limit 50"
