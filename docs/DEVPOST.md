# Devpost submission copy: Geminga

Paste-ready. Every claim below is checkable against the repo.

---

## About the project

## Inspiration

Monday morning, a billing alert. Something has been running since Friday. The engineer on call already knows what to delete. That was never the hard part.

The hard part is blast radius. Deleting the wrong resource at 9am costs more than the bill does. So the ticket gets parked, the resource stays up, and the same alert fires next month. Anyone who has held a pager knows this loop.

This is not only our experience. The FinOps Foundation's practitioner work puts *getting
engineers to act on cost recommendations* at the top of the field's challenges, named by around
40% of respondents, ahead of finding the waste in the first place; the reason given is that
engineers lack the confidence to delete a resource nobody owns. Meanwhile Flexera's State of the
Cloud reporting has enterprises wasting on the order of 30% of cloud spend. So the industry does
not have a detection problem. It has an *acting* problem, and that is the one we went after.

Every agent aimed at this problem lands on the same answer: never let the agent act. It drafts, a human approves, a human clicks. That does not fix anything. It just leaves the person as the one who has to be brave before coffee.

We wanted to work on the actual question. Not "how do we make the agent more confident," but "how does an agent earn the right to act, and how fast can we take that right away when it stops being correct."

The name comes from Geminga, a gamma ray pulsar with no counterpart at any other wavelength. In Milanese it reads *gh'è minga*, meaning "it's not there." The whole system is built on that instinct. A thing reported is not a thing confirmed.

## What it does

Geminga cleans up cloud waste. It stops idle VMs, deletes unattached disks, releases reserved static IPs, clears stale snapshots, and downsizes over provisioned instances. The interesting part is that it earns the authority to do each of those, one operation class at a time.

Autonomy here is not a flag you set at design time. It is a budget, measured, and continuously re-earned.

| Rung | What it does |
|---|---|
| **Shadow** | Rehearses against virtualised tools. Predicted delta recorded. Nothing is committed. |
| **Provisional** | Commits for real. Every single run is verified. One failure demotes it. |
| **Live** | Commits for real. Sampled verification, never zero, because a rung nobody watches cannot fall. |

A class climbs on evidence: *k* consecutive runs where a verifier that re-derives real environment state agrees with the prediction. One disagreement drops it a rung and resets the streak. The ratchet turns both ways, permanently.

Three design decisions make this more than a confidence score.

**Trust is scoped to the shape of the work, not to the tool.** Authority earned deleting scratch buckets does not carry over to production ones. An argument shape nobody has rehearsed goes back to shadow regardless of what the class has earned. This is least privilege applied to experience rather than to identity.

**Irreversibility is not a confidence level.** Deleting a disk sits behind a human at every rung, forever. The ladder governs doubt. It does not govern consequence. Those are different axes and collapsing them is how you get an outage.

**The model never writes its own success criteria.** It names an operation and a target. Post conditions come from the domain spec. Anything that grades its own homework passes every time.

## What it runs on

ADK 2's graph runtime (`google.adk.workflow`), which is a DAG scheduler rather than a tree walker.

```
START → propose → intake → gate ─┬─ shadow  → rehearse ─┐
                                 ├─ commit  → actuate  ─┼→ assess → report
                                 └─ consult → approve  ─┘    │
                                 ▲                            │
                                 └──── routed edge, next op ──┘
```

That choice does real work. Schemas are checked across edges at construction, so type errors fail before any model call, not in production at 3am. `retry_config` and `timeout` live on the node, so failure handling is declared in the topology instead of buried in a `try` block. Cycles are legal when they contain a routed edge, so "pick the next operation" is an edge in the graph rather than a Python `while` loop. You can draw it, replay it, and interrupt it.

| Module | Responsibility |
|---|---|
| `ratchet/authority.py` | The ladder. Promotion, demotion, the rehearsed shape envelope. |
| `ratchet/effects.py` | Typed effects with idempotency keys. A replay returns. It never re-fires. |
| `ratchet/world.py` | Observe, rehearse, verify by re-derivation. |
| `ratchet/graph.py` | The ADK 2 DAG. The only module that imports the framework. |
| `ratchet/domains/` | Operation specs and live GCP inventory. |
| `app/nightshift.py` | Cloud Run entrypoint and the SSE streamed console. |

`authority`, `effects` and `world` import neither ADK nor any cloud SDK. The code that decides whether the agent may act is provable in a plain unit test. That is why the ladder runs deterministically in CI with no credentials and no model in the loop.

On Google Cloud: Gemini 3.x on Vertex AI proposes, Compute and Monitoring APIs supply estate inventory, Cloud Run hosts the console.

One disclosure, because it is the kind of thing worth saying before a judge finds it: the hosted demo runs a fixture estate, not a live project. The live path is real and is the same code (`GEMINGA_PROJECT` points it at a project, and it then reads Compute and Monitoring directly), but the account we could point it at is empty, and a console showing $0.00 across the board demonstrates nothing. The fixture gives the ladder something to actually reclaim. The console states this on screen, and the ladder, the verification and the demotion logic are identical either way.

## Challenges we ran into

**Verification is the product, and it is the part that wants to lie to you.** The naive build asks the tool whether it worked. We caught ourselves doing exactly that, which is why the fault demo exists. From run 6 the tool reports success while changing nothing. Verification re-derives real state, spots the gap, and the operation demotes itself. If your verifier trusts the actuator's own report, the ladder is theatre and you have built a very confident way to cause an incident.

**Gemini 3.x serves from the `global` endpoint.** Regional endpoints like `us-central1` return 404 for every 3.x model, while Cloud Run still deploys to a real region. Two separate settings, easy to conflate, and it fails at deploy time rather than at review time. It cost us an afternoon and is now flagged in the README.

**Being honest about money.** Cost figures are list price estimates and are labelled as such everywhere they appear. The authoritative number is the BigQuery billing export. A system whose entire argument is "verify against the environment" does not get to fudge its own headline figure.

**Not making the flattering claim.** We do not say Geminga blocks prompt injection. Under a stated threat model, across 1,000 adaptive cases generated by two frontier model families that were handed the complete defence specification, zero reached an actuator. That is a true failure rate below 0.383% at 95% confidence (Wilson), with benign utility unchanged at 14 of 14 legitimate operations still admitted. Published defences have reported near zero attack rates and then been broken above 90% by adaptive attackers. The scope around a number is the work. The number on its own is worth very little. `CLAIMS.md` sets out what we do not claim, including the objection a good reviewer leads with: harm that is achievable inside the allowlist.

## Accomplishments that we're proud of

160 tests, no credentials required, and 20 of them are refusals. Cases where declining is the correct behaviour.

The rubric asks for undeniable proof of execution. It never asks what happens when the agent is wrong. For something with delete permissions on production infrastructure, that is the gap that matters, so `RESTRAINT.md` answers a question nobody asked: what is the worst thing this can do, how do we know, and what does recovery cost. The refusal count is CI enforced. A test asserts that the number printed in the document matches the number of traps in the suite, so the claim cannot quietly drift away from the code.

An agent that reclaims $50,000 a month and once drops a production database is worth less than nothing. Under a rubric that measures capability alone it scores higher than a careful one, because it acts more impressively on camera. We built the careful one and made the restraint demonstrable instead of asserted.

## What we learned

Autonomy is a control problem, not a prompting problem. The load bearing work ended up in a module that imports no framework and calls no model.

A graph runtime changes what you are able to promise. Because the loop is an edge, "the agent decides what to do next" becomes something you can inspect and interrupt, rather than a `while` nobody can see.

Design the failure demo first. The fault injection run taught us more about the architecture than any successful run did.

Scope beats magnitude in a claim. A small number with a stated threat model survives a hostile reader. A big number without one does not.

## What's next for Geminga

More domains behind the same ladder. The scaffold is domain neutral by construction and GCP compute is simply the first estate we pointed it at.

After that, two things we want. Authority that decays with disuse, because a class that has not run in three months should not still be sitting at Live. And per tenant authority, so trust earned in one project does not silently transfer to another.

---

## Built with (tags)

```
google-adk, adk-2, gemini, gemini-3, vertex-ai, google-cloud, cloud-run,
compute-engine, cloud-monitoring, python, fastapi, uvicorn, sse,
pytest, docker, agents, ai-agents, multi-agent, autonomous-agents,
finops, cloud-cost-optimization, devops, devsecops, ai-safety, prompt-injection
```

## "Try it out" links

1. **Live console (Cloud Run)**: deploy first with `./deploy/cloudrun.sh <project> us-central1`
2. **GitHub repo**: code, README setup, `RESTRAINT.md`, `CLAIMS.md`
3. **Architecture**: `ARCHITECTURE.md` (same folder as this file; from the repo root it is `docs/ARCHITECTURE.md`)

## Track

**Fortified Enterprise Fleet.** Scalable agent networks with security, compliance and governance.

Fifteen agents across three floors with a hard trust boundary between them: three untrusted
readers upstairs whose output is a proposal and never a decision, seven inspectors in the middle
that use no model at all, and five on the ground floor, the only ones able to change anything. Governance is the
product, not a wrapper on it: authority is earned per operation class, revoked on a single
disagreement, and the whole thing is evidenced by 20 refusal tests and a measured injection
result with its threat model stated.

## Media checklist

- **Cover and gallery**: `../brand/geminga-cover.png` (3:2 crop), `../brand/geminga-logo-tile.png`
- **Architecture diagram (required)**: export a PNG from `architecture-3d.html` (same folder as this file; full path `02-all-things-agentic/docs/architecture-3d.html`)
- **Demo video, roughly 4 minutes (required)**: must show live functionality and proof of Google Cloud deployment. Suggested cut:
  1. The estate. Real resources, real monthly spend, reclaimable figure, labelled list price.
  2. The ladder. Four rehearsals with the estate untouched, promotion on the fifth, first real commit on the sixth.
  3. The lie. From run 6 the tool reports success while changing nothing. Verification re-derives state, catches it, demotes.
  4. The Cloud Run URL on screen, live.

---

## Upload checklist (the parts that need a signed-in browser)

**Video** — `~/Desktop/geminga-final-v2.mp4`, 3:55, 2104x1972, narrated, **no embedded
subtitles** (turn on YouTube auto-captions and correct "Geminga", "Vertex", "ADK",
"provisional", "shadow").

Title:

    Geminga — an agent that earns the right to act

Description:

    Companies are starting to let AI agents delete things in their cloud. That should worry
    you slightly. Most teams handle it by never letting the agent actually do anything — it
    suggests, a human clicks. Which fixes nothing. It just means a person has to be the brave
    one at nine in the morning.

    Geminga does it the other way. It hunts down the stuff quietly burning money — machines
    nobody switched off, disks nobody deleted — and it has to earn the right to touch any of
    it.

    There are three levels:

    Shadow — it only pretends. Says what it would do, changes nothing.
    Provisional — it actually does it, and gets checked every single time.
    Live — it does it, checked on random spot-checks. Never zero, because a level nobody
    checks is a level that can never catch anything.

    Five correct runs in a row moves it up. One wrong answer drops it straight back down.

    Here's the part that matters. When the agent says "done", nothing believes it. Something
    else goes and looks.

    So in this video I break it on purpose. I make the delete tool lie — it reports "success"
    and does absolutely nothing. That's a hallucination: the agent thinks it worked, its own
    log says it worked, and anything trusting that log is now wrong without knowing it. The
    checker goes and looks anyway, finds the machine still sitting there, and takes the
    agent's permissions away on the spot. It ends at Live with 81 verified, 1 failed, 3
    demotions.

    There's also a machine sitting at 0.4% CPU. Every "find the idle servers" tool would kill
    it. Geminga won't touch it, because the GPU is at 94% — someone is training a model on
    that box. Deleting it would have ruined their week.

    Being straight with you: the cloud account in the demo is fake data, and nothing is really
    deleted. The agent, the three levels, the checker and the Gemini reviews are all real and
    running live at the link below — go click it.

    Gemini 3.6 Flash on Vertex AI · ADK 2 graph runtime · Cloud Run · FastAPI + SSE
    Live: https://agentic-core-468826425509.us-central1.run.app
    Code: https://github.com/Occansey/geminga

    Built by Maxwell Occansey for the All Things Agentic hackathon —
    Fortified Enterprise Fleet track.

Visibility: **Public or Unlisted** (rules require publicly visible). Not made for kids.

**Repo access** — public, or invite `testing@devpost.com` and `cloudhackathons@google.com`.

**Devpost fields** — the story above, the architecture diagram (`brand/geminga-architecture-3x2.png`),
the live URL, and the video link.
