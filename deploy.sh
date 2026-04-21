#!/usr/bin/env bash
# Deploy stuff-to-do as a Cloud Run Job scheduled every 6 hours.
#
# Prerequisites:
#   - gcloud CLI installed and authenticated (gcloud auth login)
#   - GOOGLE_CLOUD_PROJECT set, or pass it as the first argument
#   - client_secret.json and token.json present in the project root
#     (run `python -m app.main` locally first to generate token.json)
#
# Usage:
#   GOOGLE_CLOUD_PROJECT=my-project ./deploy.sh
#   ./deploy.sh my-project
set -euo pipefail

PROJECT_ID="${1:-${GOOGLE_CLOUD_PROJECT:?Set GOOGLE_CLOUD_PROJECT or pass it as argument}}"
REGION="${REGION:-us-west1}"
JOB_NAME="stuff-to-do"
IMAGE="gcr.io/$PROJECT_ID/$JOB_NAME"
BUCKET="$PROJECT_ID-push-history"
JOB_SA="$JOB_NAME-runner@$PROJECT_ID.iam.gserviceaccount.com"
SCHEDULER_SA="$JOB_NAME-scheduler@$PROJECT_ID.iam.gserviceaccount.com"

echo "==> Project:  $PROJECT_ID"
echo "==> Region:   $REGION"
echo "==> Image:    $IMAGE"
echo "==> GCS:      gs://$BUCKET"
echo ""

# ── Enable required APIs ──────────────────────────────────────────────────────
echo "==> Enabling APIs..."
gcloud services enable \
  run.googleapis.com \
  cloudscheduler.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com \
  cloudbuild.googleapis.com \
  --project "$PROJECT_ID"

# ── GCS bucket for push_history.json ─────────────────────────────────────────
echo "==> Creating GCS bucket gs://$BUCKET (if not exists)..."
gsutil mb -p "$PROJECT_ID" -l "$REGION" "gs://$BUCKET" 2>/dev/null || true

# ── Secret Manager secrets ────────────────────────────────────────────────────
echo "==> Creating/updating secrets..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

for SECRET in calendar-client-secret calendar-token; do
  gcloud secrets create "$SECRET" --project "$PROJECT_ID" 2>/dev/null || true
done

gcloud secrets versions add calendar-client-secret \
  --data-file="$SCRIPT_DIR/client_secret.json" \
  --project "$PROJECT_ID"

gcloud secrets versions add calendar-token \
  --data-file="$SCRIPT_DIR/token.json" \
  --project "$PROJECT_ID"

# ── Build and push container image ───────────────────────────────────────────
echo "==> Building and pushing image..."
gcloud builds submit --tag "$IMAGE" --project "$PROJECT_ID" "$SCRIPT_DIR"

# ── Service account for the Cloud Run Job ────────────────────────────────────
echo "==> Setting up job service account..."
gcloud iam service-accounts create "$JOB_NAME-runner" \
  --display-name="Stuff To Do Job Runner" \
  --project "$PROJECT_ID" 2>/dev/null || true

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$JOB_SA" \
  --role="roles/secretmanager.secretAccessor" \
  --condition=None

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:$JOB_SA" \
  --role="roles/storage.objectAdmin" \
  --condition=None

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
  --set-env-vars "GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GCS_BUCKET=$BUCKET" \
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
echo "To run it manually:"
echo "  gcloud run jobs execute $JOB_NAME --region $REGION --project $PROJECT_ID"
echo ""
echo "To view logs:"
echo "  gcloud logging read 'resource.type=cloud_run_job AND resource.labels.job_name=$JOB_NAME' --project $PROJECT_ID --limit 50"
