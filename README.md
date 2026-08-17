# Geminga

**An agent earns the right to act, one operation at a time — and loses it the moment it stops being correct.**

> *Geminga* — a gamma-ray pulsar in Gemini, IAU-approved 2022. The name contracts
> "Gemini gamma-ray source" and, in Milanese, reads *gh'è minga*: **"it's not there."**
> The source had no counterpart at any other wavelength. Everything here is built on
> the same suspicion — that a thing reported is not a thing confirmed.

---

## The problem

A platform engineer opens a billing alert on Monday. Something was left running since
Friday. They already know what to delete — that is not the hard part.

The hard part is that deleting the wrong thing at 9am is worse than the bill. So
nothing gets deleted, and the same resource is still there next month.

Every agent built for this problem answers it the same way: **never let the agent
act.** The agent prepares, a human sends. Which means the asymmetry is untouched —
the human is still the one who has to be brave at 9am on a Monday.

## The idea

Autonomy is not a switch set at design time. It is a **measured, per-operation budget
that is continuously re-earned.**

| Rung | What it does |
|---|---|
| **Shadow** | Rehearses against virtualized tools. Predicted delta recorded. Nothing committed. |
| **Provisional** | Commits for real. **Every** run verified. One failure demotes. |
| **Live** | Commits for real. Sampled verification — never zero, because a rung that cannot be watched cannot fall. |

An operation class climbs on evidence: *k* consecutive runs where a verifier that
**re-derives real environment state** agrees with the prediction. One disagreement
drops it a rung and resets the streak. The ratchet turns both ways, forever.

Three properties make it more than a confidence score:

- **Trust is per *shape of work*, not per tool.** Authority earned deleting scratch
  buckets does not transfer to deleting production ones. An unrehearsed argument shape
  routes back to shadow no matter what the class has earned.
- **Irreversibility is not a confidence level.** Deleting a disk stays behind a human
  at every rung. The ladder governs *doubt*, not *consequence*.
- **The model never writes its own success criteria.** It names an operation and a
  target; post-conditions come from the domain spec. A system that grades its own
  homework passes every time.

## See it

```bash
python3 -m venv .venv && ./.venv/bin/pip install -e ".[dev]"
PYTHONPATH=src ./.venv/bin/python -m uvicorn app.nightshift:app --port 8137
```

Open <http://localhost:8137>.

- **Run the ladder** — four rehearsals with the estate untouched, promotion on the
  fifth, first real commit on the sixth.
- **Make the tool lie from run 6** — the tool reports success while changing nothing.
  Verification re-derives real state, catches it, and the operation demotes itself.

No credentials needed for either: the ADK 2 graph engine is LLM-free, so the ladder is
deterministic and runs in CI. Terminal equivalents:

```bash
PYTHONPATH=src ./.venv/bin/python -m ratchet.demo --estate
PYTHONPATH=src ./.venv/bin/python -m ratchet.demo --fault 6
```

## Run it against real infrastructure

```bash
gcloud auth application-default login
cp .env.example .env      # set GOOGLE_CLOUD_PROJECT
```

> **Gemini 3.x is served from the `global` endpoint.** Regional endpoints such as
> `us-central1` return 404 for every 3.x model. Cloud Run still deploys to a real
> region — they are separate settings, and conflating them fails at deploy time.

```bash
PYTHONPATH=src ./.venv/bin/python -c "
from ratchet.domains import gcp_inventory as inv
e = inv.read_estate('YOUR_PROJECT')
print(f'{len(e)} resources, \${inv.monthly_spend(e)}/mo, \${inv.monthly_spend(inv.reclaimable(e))} reclaimable')"
```

Reads live Compute and Monitoring APIs. Costs are **list-price estimates**, labelled
as such everywhere they surface; the authoritative figure is the BigQuery billing
export. A system arguing for verification against the environment does not get to
fudge its own headline number.

## Deploy

```bash
./deploy/cloudrun.sh <project> us-central1
```

## Architecture

[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · [RESTRAINT.md](RESTRAINT.md) · [CLAIMS.md](CLAIMS.md) · [docs/SCAFFOLD-COMPARISON.md](docs/SCAFFOLD-COMPARISON.md)

Built on **ADK 2**'s graph runtime (`google.adk.workflow`) — a DAG scheduler, not a
tree walker. Schemas are checked across edges at construction, so type errors fail
before any model call. `retry_config` and `timeout` live on the node, so failure
handling is declared in the topology. Cycles are legal when they contain a routed
edge, so "next operation" is an edge in the graph rather than a Python `while` — it
can be drawn, replayed, and interrupted.

```
START → propose → intake → gate ─┬─ shadow  → rehearse ─┐
                                 ├─ commit  → actuate  ─┼→ assess → report
                                 └─ consult → approve  ─┘    │
                                 ▲                            │
                                 └──── routed edge, next op ──┘
```

| Module | Responsibility |
|---|---|
| `ratchet/authority.py` | The ladder. Promotion, demotion, the rehearsed-shape envelope. |
| `ratchet/effects.py` | Typed effects with idempotency keys. A replay returns; it never re-fires. |
| `ratchet/world.py` | Observe, rehearse, verify by re-derivation. |
| `ratchet/graph.py` | The ADK 2 DAG. The only module that imports the framework. |
| `ratchet/domains/` | Operation specs and live GCP inventory. |
| `app/nightshift.py` | Cloud Run entrypoint and the SSE-streamed console. |

`authority`, `effects` and `world` import neither ADK nor any cloud SDK — the logic
that decides whether the agent may act is provable in a plain unit test.

## Tests

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest tests -q
```

160 tests, no credentials required (one live-model test skips without them). Twenty of
them are **refusals** — cases where the correct behaviour is to decline, reported in
[RESTRAINT.md](RESTRAINT.md). They cover the claims this README makes: that authority is earned, that it is revoked, that
an effect cannot fire twice across a resume, that verification refuses to pass an
operation which promised nothing, and that a real model's correct proposal is still
routed to shadow. If they fail, the pitch is false.

## Licence

Apache 2.0 — see [LICENSE](LICENSE).
