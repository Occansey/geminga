#!/usr/bin/env bash
# One-shot deploy to Cloud Run. Run from the project root.
#   ./deploy/cloudrun.sh my-gcp-project us-central1
set -euo pipefail

PROJECT="${1:?usage: cloudrun.sh <project-id> [region]}"
REGION="${2:-us-central1}"
SERVICE="agentic-core"
BUCKET="${PROJECT}-agent-artifacts"

gcloud config set project "$PROJECT"

echo "==> enabling APIs"
gcloud services enable \
  run.googleapis.com \
  aiplatform.googleapis.com \
  firestore.googleapis.com \
  storage.googleapis.com \
  cloudbuild.googleapis.com

echo "==> Firestore (skips if it already exists)"
gcloud firestore databases create --location="$REGION" 2>/dev/null || true

echo "==> artifact bucket"
gcloud storage buckets create "gs://${BUCKET}" --location="$REGION" 2>/dev/null || true

echo "==> deploy"
gcloud run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --allow-unauthenticated \
  --set-env-vars "GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=${PROJECT},GOOGLE_CLOUD_LOCATION=${REGION},AGENT_STORE=firestore,AGENT_BUCKET=${BUCKET}"

URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"
echo
echo "Service: $URL"
echo "Health:  curl $URL/healthz"
echo "Put that URL in the submission — it is the deployment proof the rules ask for."
