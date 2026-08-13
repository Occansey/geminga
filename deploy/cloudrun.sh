#!/usr/bin/env bash
# One-shot deploy to Cloud Run. Run from the project root.
#   ./deploy/cloudrun.sh my-gcp-project us-central1
set -euo pipefail

# Run from the repository root regardless of where this was invoked. Without it,
# `--source .` uploads whatever directory the caller happened to be in — which is
# how a deploy silently produced no service and left a one-line log.
cd "$(dirname "$0")/.."

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

# GOOGLE_CLOUD_LOCATION is deliberately "global" and not the deploy region: Gemini 3.x
# publisher models are only served from the global endpoint, and every regional one
# returns 404. The Cloud Run region below is a separate setting. Conflating the two
# fails at deploy time rather than at build time, which is the expensive place to
# find out.
#
# GEMINGA_ALLOW_MUTATIONS is deliberately absent. The service reads the live estate
# and changes nothing until someone sets it explicitly.
echo "==> deploy"
gcloud run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --allow-unauthenticated \
  --set-env-vars "GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=${PROJECT},GOOGLE_CLOUD_LOCATION=global,AGENT_STORE=firestore,AGENT_BUCKET=${BUCKET},GEMINGA_PROJECT=${PROJECT}"

URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')"
echo
echo "Service: $URL"
echo "Health:  curl $URL/healthz"
echo "Put that URL in the submission — it is the deployment proof the rules ask for."
