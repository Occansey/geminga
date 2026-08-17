# Devpost submission copy — Geminga

Paste-ready. Everything below is checkable against the repo.

---

## About the project

## Inspiration

A platform engineer opens a billing alert on Monday. Something was left running since Friday. They already know what to delete — that is not the hard part.

The hard part is that **deleting the wrong thing at 9am is worse than the bill.** So nothing gets deleted, and the same resource is still there next month.

Every agent built for this problem answers it the same way: *never let the agent act.* The agent prepares, a human sends. Which means the asymmetry is untouched — the human is still the one who has to be brave at 9am on a Monday.

We wanted to attack that directly. Not "how do we make the agent more confident?" but **"how does an agent earn the right to act, and how do we take it back the instant it stops being correct?"**

The name comes from Geminga, a gamma-ray pulsar with no counterpart at any other wavelength. In Milanese it reads *gh'è minga* — **"it's not there."** Everything here is built on that suspicion: a thing reported is not a thing confirmed.

## What it does

Geminga reclaims wasted cloud spend — stopping idle VMs, deleting unattached disks, releasing static IPs, clearing stale snapshots, downsizing over-provisioned instances — and it **earns the authority to do each of those, one operation class at a time.**

Autonomy is not a switch set at design time. It is a measured, per-operation budget that is continuously re-earned:

| Rung | What it does |
|---|---|
| **Shadow** | Rehearses against virtualized tools. Predicted delta recorded. Nothing committed. |
| **Provisional** | Commits for real. **Every** run verified. One failure demotes. |
| **Live** | Commits for real. Sampled verification — never zero, because a rung that cannot be watched cannot fall. |

An operation class climbs on evidence: *k* consecutive runs where a verifier that **re-derives real environment state** agrees with the prediction. One disagreement drops it a rung and resets the streak. The ratchet turns both ways, forever.

Three properties make this more than a confidence score:

- **Trust is per *shape of work*, not per tool.** Authority earned deleting scratch buckets does not transfer to deleting production ones. An unrehearsed argument shape routes back to shadow no matter what the class has earned.
- **Irreversibility is not a confidence level.** Deleting a disk stays behind a human at *every* rung. The ladder governs **doubt**, not **consequence**.
- **The model never writes its own success criteria.** It names an operation and a target; post-conditions come from the domain spec. A system that grades its own homework passes every time.

## How we built it

Built on **ADK 2's graph runtime** (`google.adk.workflow`) — a DAG scheduler, not a tree walker.

```
START → propose → intake → gate ─┬─ shadow  → rehearse ─┐
                                 ├─ commit  → actuate  ─┼→ assess → report
                                 └─ consult → approve  ─┘    │
                                 ▲                            │
                                 └──── routed edge, next op ──┘
```

Choosing the graph runtime was load-bearing, not decorative. Schemas are checked across edges at construction, so type errors fail **before any model call**. `retry_config` and `timeout` live on the node, so failure handling is declared in the topology rather than buried in a `try`. Cycles are legal when they contain a routed edge, so "next operation" is an **edge in the graph** rather than a Python `while` — it can be drawn, replayed, and interrupted.

| Module | Responsibility |
|---|---|
| `ratchet/authority.py` | The ladder. Promotion, demotion, the rehearsed-shape envelope. |
| `ratchet/effects.py` | Typed effects with idempotency keys. A replay returns; it never re-fires. |
| `ratchet/world.py` | Observe, rehearse, verify by re-derivation. |
| `ratchet/graph.py` | The ADK 2 DAG. The only module that imports the framework. |
| `ratchet/domains/` | Operation specs and live GCP inventory. |
| `app/nightshift.py` | Cloud Run entrypoint and the SSE-streamed console. |

**`authority`, `effects` and `world` import neither ADK nor any cloud SDK.** The logic that decides whether the agent may act is provable in a plain unit test — which is why the ladder runs deterministically in CI with no credentials and no model.

Google Cloud: **Gemini 3.x** on Vertex AI for proposal, **Compute + Monitoring APIs** for live estate inventory, **Cloud Run** for the deployed console.

## Challenges we ran into

**Verification is the whole product, and it is the part that wants to lie.** The naive design asks the tool whether it worked. Our fault demo exists because we caught ourselves doing exactly that: from run 6, the tool reports success while changing nothing. Verification re-derives real environment state, catches the discrepancy, and the operation **demotes itself**. If the verifier trusts the actuator's own report, the entire ladder is theatre.

**Gemini 3.x is served from the `global` endpoint.** Regional endpoints such as `us-central1` return 404 for every 3.x model — while Cloud Run still deploys to a real region. They are separate settings, and conflating them fails at deploy time. That cost us an afternoon and is now a call-out in the README.

**Being honest about money.** Cost figures are **list-price estimates**, labelled as such everywhere they surface; the authoritative number is the BigQuery billing export. A system arguing for verification against the environment does not get to fudge its own headline number.

**Resisting the flattering claim.** We do not claim "blocks prompt injection." Under a stated threat model, in **1,000 adaptive cases** generated by two frontier model families given the complete defence specification, **0 reached an actuator** — a true failure rate below **0.383%** at 95% confidence (Wilson), with benign utility unchanged at **14/14** legitimate operations still admitted. Published defences have reported near-zero attack rates and been broken above 90% by adaptive attackers; the scope around the number is the work, not the number. [`CLAIMS.md`](CLAIMS.md) states what we do **not** claim, including the strongest objection — harm achievable *inside* the allowlist.

## Accomplishments that we're proud of

**160 tests, no credentials required — and 20 of them are refusals.** Cases where the correct behaviour is to *decline*. The rubric asks for undeniable proof of execution; it never asks what happens when the agent is wrong. For something that deletes production infrastructure, that is the omission that matters, so [`RESTRAINT.md`](RESTRAINT.md) answers a question nobody asked: what is the worst thing Geminga can do, how do we know, and what does recovery cost? The refusal count is itself CI-enforced — a test asserts the number in the document matches the number of traps in the suite, so the claim cannot quietly drift from the code.

An agent reclaiming $50,000 a month that once destroys a production database is worth less than nothing — and under a rubric measuring only capability, it *scores higher* than a careful one, because it acts more impressively on camera. We built the careful one anyway, and made the restraint demonstrable.

## What we learned

- **Autonomy is a control problem, not a prompting problem.** The interesting work sat in a module that imports no framework and calls no model.
- **A graph runtime changes what you can promise.** Because the loop is an edge, "the agent decides what to do next" is inspectable and interruptible instead of a `while` nobody can see.
- **Design the demo of failure first.** The fault-injection run taught us more about the architecture than any successful run did.
- **Scope beats magnitude in a claim.** A small number with a stated threat model survives contact with a hostile reader; a big number without one does not.

## What's next for Geminga

More domains behind the same ladder — the scaffold is domain-neutral by construction, and GCP compute is simply the first estate we pointed it at. Beyond that: a longer-horizon ratchet where authority decays with disuse (a class that has not run in months should not still be Live), and per-tenant authority so trust earned in one project does not silently transfer to another.

---

## Built with (tags)

```
google-adk, adk-2, gemini, gemini-3, vertex-ai, google-cloud, cloud-run,
compute-engine, cloud-monitoring, python, fastapi, uvicorn, sse,
pytest, docker, agents, ai-agents, multi-agent, autonomous-agents,
finops, cloud-cost-optimization, devops, ai-safety, prompt-injection
```

## "Try it out" links

1. **Live console (Cloud Run)** — `<deploy first: ./deploy/cloudrun.sh <project> us-central1>`
2. **GitHub repo** — the code, README setup, `RESTRAINT.md`, `CLAIMS.md`
3. **Architecture** — `docs/ARCHITECTURE.md`

## Track

**Taskmaster** — autonomous multi-step workflows, end to end. (`AGENT_REQUIRE_APPROVAL=false`.)

## Media checklist

- **Cover / gallery:** `brand/geminga-cover.png` (3:2 crop for Devpost), `brand/geminga-logo-tile.png`
- **Architecture diagram (required):** `docs/architecture-3d.html` → export a PNG
- **Demo video (~4 min, required):** must show live functionality **and** proof of Google Cloud deployment. Suggested cut:
  1. The estate: real resources, real monthly spend, reclaimable figure (labelled list-price).
  2. The ladder: four rehearsals with the estate untouched, promotion on the fifth, first real commit on the sixth.
  3. **The lie:** from run 6 the tool reports success while changing nothing — verification re-derives state, catches it, demotes.
  4. Cloud Run URL on screen, live.
