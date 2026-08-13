---
name: ship
description: Build, export and deploy the Geminga container, and capture the deployment proof the hackathon requires. Use when asked to build the image, export it, deploy to Cloud Run, or produce the live URL for the submission.
---

# Ship

The submission is disqualified without visible proof of Google Cloud deployment in
the video. The live URL is not a nice-to-have; treat it as a required artifact.

## Build and export locally

```bash
cd /Users/maxwell/hackathon/02-all-things-agentic
docker build -t geminga:local . && docker tag geminga:local geminga:0.1.0
mkdir -p dist && docker save geminga:0.1.0 | gzip > dist/geminga-0.1.0.tar.gz
```

~94MB. Reload elsewhere with `docker load < dist/geminga-0.1.0.tar.gz`.

## Run the image locally against real GCP

ADC is mounted read-only; the image never carries a credential.

```bash
docker rm -f geminga-test 2>/dev/null
docker run -d --name geminga-test -p 8138:8080 \
  -e GEMINGA_PROJECT=nightshift-agentic-2026 \
  -e GOOGLE_APPLICATION_CREDENTIALS=/adc/application_default_credentials.json \
  -v "$HOME/.config/gcloud:/adc:ro" geminga:0.1.0
sleep 10 && curl -s http://127.0.0.1:8138/healthz
```

Expect `{"ok":true,"project":"...","mutations":false}`. **Mutations are off in the
image by default** — an image that can delete things by default is one someone runs
by accident. Enabling them is a deliberate deployment-time decision.

## Deploy to Cloud Run

```bash
./deploy/cloudrun.sh nightshift-agentic-2026 us-central1
```

Enables the APIs, creates the artifact bucket, deploys from source, prints the URL.

Two settings that are easy to conflate and fail at different times: **`GOOGLE_CLOUD_LOCATION`
must be `global`** for Gemini 3.x model access, while the **Cloud Run region must be a
real region**. They are separate; a regional model endpoint 404s.

Cloud Run injects `PORT`; uvicorn must bind it or the revision never goes healthy.

## Capture the proof

For the video, on screen: the `*.run.app` URL in the address bar, `/healthz`
responding, and the Cloud Run console showing the revision serving. The rubric asks
for **unedited, live execution** of the agent performing its task — the ladder is
deterministic and LLM-free precisely so it survives an unbroken take.

## Before calling it shipped

- `curl $URL/healthz` from outside your machine
- the board renders and the ladder runs on the deployed URL, not just locally
- confirm whether the deployed instance has mutations on, and that this is intended
- record the URL in the submission and in TRACKER.md
