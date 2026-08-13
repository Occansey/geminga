---
name: demo
description: Run the Nightshift authority-ladder demo — start the console, drive the clean promotion path and the sabotage path, and capture what happened. Use when asked to "run the demo", "show the ladder", "demo Geminga", rehearse the submission video, or check that the end-to-end story still works after a change.
---

# Run the demo

Two paths matter. The clean one shows an operation earning the right to act; the
sabotage one shows it losing that right. Rehearse both — the second is the one
judges remember, and it is the one that breaks when something regresses.

## Start the console

Port 8080 is often taken on this machine; 8137 is the project's convention.

```bash
cd /Users/maxwell/hackathon/02-all-things-agentic
kill $(lsof -ti:8137) 2>/dev/null
GEMINGA_PROJECT=nightshift-agentic-2026 PYTHONPATH=src \
  nohup ./.venv/bin/python -m uvicorn app.nightshift:app --host 127.0.0.1 --port 8137 \
  > /tmp/nightshift.log 2>&1 &
sleep 8 && curl -s http://127.0.0.1:8137/healthz
```

`healthz` reports both switches. Confirm `mutations` is what you intend **before**
running anything — `true` means real deletes.

Drop `GEMINGA_PROJECT` to run against the fixture estate instead of live GCP. Do
that when there is no network, or when rehearsing without touching a project.

## Drive it

In the browser at <http://localhost:8137>: **Run the ladder**, then **Reset**, then
**Make the tool lie from run 6**.

Headless, when you want the transcript rather than the pictures:

```bash
PYTHONPATH=src ./.venv/bin/python -m ratchet.demo --estate
PYTHONPATH=src ./.venv/bin/python -m ratchet.demo -n 8
PYTHONPATH=src ./.venv/bin/python -m ratchet.demo -n 8 --fault 6
```

## What correct looks like

Clean path: four rehearsals with the estate untouched, **promotion on run 5**, first
commit on run 6.

Sabotage path: identical until run 6, then `demoted to shadow: N post-condition(s)
did not hold`, and the resource visibly unchanged.

If the ladder never leaves shadow, suspect stale rehearsal state — the virtual world
is scoped per `run_id` and released by the graph's report node. That bug has appeared
twice, at two different layers; check `discard` is still being called before assuming
anything subtler.

## Verifying against the browser, not the screenshot

Screenshots at reduced scale have twice made the rung indicator look wrong when it
was right. Check the DOM rather than trusting the image:

```javascript
[...document.querySelectorAll('.rung')].map(e => [e.dataset.key, e.dataset.on])
```
