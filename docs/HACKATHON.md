# All Things Agentic Hackathon

**Page:** https://allthingsagentichackathon.devpost.com/
**Status:** live — deadline **Aug 31, 2026 @ 5:00pm PDT** (18 days out)

## Prizes — $180,000
| | |
|---|---|
| Grand prize | $50,000 |
| Track winners (×3) | $20,000 each |
| Startup Excellence | $20,000 |
| Individual / hobbyist (×2) | $10,000 each |
| Architecture & UX awards | $5,000 each |
| Honorable mentions (×5) | $2,000 each |

## Tracks — pick one
1. **Taskmaster** — autonomous multi-step workflows, end to end
2. **Collaborative Partner** — guides the user, adapts to feedback
3. **Fortified Enterprise Fleet** — scalable agent networks with security, compliance, governance

## Hard requirements
- Gemini 3.5+ (API or Vertex AI)
- At least one Google agent framework (ADK, GenAI SDK, …)
- At least one Google Cloud infrastructure service
- Repo (public or private) with step-by-step README setup
- **System architecture diagram**
- ~4 min demo video showing live functionality *and* proof of Google Cloud deployment
- Hosted project URL if applicable

## Notes
- ~2,100 participants registered. Highest prize-per-effort of the near-term set.
- The "proof of Google Cloud deployment" clause means a local-only demo is disqualified — budget time for deploy.

## Register
Yours to do: Devpost → **Join hackathon**.

---

# The build

A planner → executor → verifier agent on Google ADK, with the plan stored as data in
Firestore rather than as state hidden in the model's context. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the diagram and the reasoning.

## Setup

```bash
python3 -m venv .venv && ./.venv/bin/pip install -e ".[dev]"
cp .env.example .env      # fill in GOOGLE_CLOUD_PROJECT
```

Run the tests — they need no credentials:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests -q
```

## The console

```bash
PYTHONPATH=src ./.venv/bin/python -m uvicorn app.nightshift:app --port 8137
```

Open http://localhost:8137. **Run the ladder** shows an operation earning the right to
act — four rehearsals with the estate untouched, promotion on the fifth, first real
commit on the sixth. **Make the tool lie from run 6** breaks the world: the tool
reports success while nothing changes, verification catches it by re-deriving real
state, and the operation demotes itself.

Or without the browser:

```bash
PYTHONPATH=src ./.venv/bin/python -m ratchet.demo --estate      # the Monday billing alert
PYTHONPATH=src ./.venv/bin/python -m ratchet.demo --fault 6     # the ladder, sabotaged
```

## v1 baseline

The planner→executor→verifier scaffold in `agent_core` is kept as the control, not the
submission — see [SCAFFOLD-COMPARISON.md](docs/SCAFFOLD-COMPARISON.md).

Talk to it locally:

```bash
PYTHONPATH=src ./.venv/bin/python -m agent_core.cli "Draft a launch checklist for a mobile app"
```

Or use ADK's own dev UI, which gives you a trace view worth recording:

```bash
PYTHONPATH=src ./.venv/bin/adk web src/agent_core
```

## Deploy to Google Cloud

```bash
./deploy/cloudrun.sh <your-gcp-project> us-central1
```

That enables Vertex AI, Firestore, Cloud Storage and Cloud Run, creates the artifact
bucket, and prints the service URL. **The URL is the deployment proof the rules
require** — a local-only demo is disqualified.

Then:

```bash
curl -X POST "$URL/chat" -H 'content-type: application/json' \
  -d '{"session_id":"demo","message":"Research X and write me a summary"}'
curl "$URL/plan/demo"
```

## Layout

| Path | What it is |
|---|---|
| `src/agent_core/agent.py` | The ADK agent graph and its instructions |
| `src/agent_core/ports.py` | Plan/Step model + the store protocols — the portability seam |
| `src/agent_core/stores.py` | Firestore + Cloud Storage; the only cloud imports in the package |
| `src/agent_core/tools/` | Plan tools, artifacts, search, approval gate |
| `src/agent_core/runtime.py` | ADK Runner wiring, one `AgentSession` per conversation |
| `src/app/main.py` | Cloud Run entrypoint: `/chat`, `/plan/{id}`, `/approve` |
| `deploy/cloudrun.sh` | One-shot deploy |

## Decisions still open

- **Track. DECIDED: Fortified Enterprise Fleet.** (Was: Taskmaster (`AGENT_REQUIRE_APPROVAL=false`) or Collaborative Partner
  (`=true`). The code path is identical; the rules require you name one category.
- **The actual goal domain.** The scaffold is domain-neutral on purpose. Pick a
  problem where multi-step autonomy is obviously the right shape, not a chatbot.
- **Model.** Defaults to `gemini-3.5-flash` (GA since I/O, 19 May 2026).
  `gemini-3.5-pro` was still allowlist-only Vertex preview in late July 2026 —
  request access if you want it, but Flash satisfies the Gemini 3.5+ rule.

## Verified

- 7/7 tests pass on the plan state machine
- Agent graph constructs against real `google-adk` 2.6.3 — root + 3 sub-agents, 6 executor tools
- Not verified: any live Gemini or Google Cloud call. No GCP project configured and
  `gcloud` isn't installed on this machine.
