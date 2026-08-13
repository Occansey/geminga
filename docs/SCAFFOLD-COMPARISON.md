# Scaffold comparison — v1, v2, and what the field is shipping

Three designs judged against the actual rubric. The third column is not hypothetical:
it is reconstructed from 52 GitHub repos naming this hackathon and ~15 public demo
videos (`research/raw/05-field-scan.md`).

## The three

| | **Field median** | **v1 · `agent_core`** | **v2 · `ratchet`** |
|---|---|---|---|
| Shape | Linear 4-agent chain, prompt-chaining relabelled | Planner → executor → verifier tree | Typed DAG on `google.adk.workflow`, with a routed cycle |
| Runtime | `SequentialAgent` / ReAct loop | Sub-agent tree, one step per turn | Graph scheduler; retry, timeout and schema checks on the node |
| State | Firestore documents | Plan-as-data in Firestore | Typed `state_schema`, event-sourced resume |
| May the agent act? | **No** — human sends | Yes, gated by a flag | **Only once it has earned it, per operation** |
| Verification | LLM self-check, or none | LLM verifier reads recorded results | Re-derives real environment state; no model in the loop |
| Side effects | Mostly none to speak of | Unprotected | Idempotency key per effect; replay returns, never re-fires |
| Failure handling | try/except | try/except | Declared in topology; faults injectable |
| Evidence | Happy-path screen recording | 7 unit tests | 21 tests + a ladder that runs in CI |
| UI | Streamlit on `run.app` | **None** — FastAPI and curl | Board of operation classes (to build) |

## Scored against the rubric

| Criterion | Weight | Field median | v1 | v2 |
|---|---|---|---|---|
| Innovation & Operational Utility | 40% | Low — everyone independently built it | Low — the documented default pattern | **High — a third answer to the field's central question, and the only expansionary one** |
| Architectural Discipline & Tech Stack | 30% | Medium | Medium | **High — the 2.x graph surface the audit rates "extremely underused"** |
| Demo & Production Readiness | 30% | Medium — happy path | **Low — headless, and a judge said he penalizes that** | **High — unedited, deterministic, includes a failure** |

## Why v1 loses

It is competent and it is the median by definition. The 2026 taxonomy literature
describes ReAct + Reflexion as the single-agent default, plan-and-execute as the
standard escalation when planning is the bottleneck, and verifier-critic as the
standard fix when quality is. That is v1, feature for feature. Roughly half a
thousand people will submit its cousin.

Two further problems, both from the research rather than taste:

- **It is headless.** A named judge explicitly penalizes "extremely back-end heavy
  projects with minimal UI," and there is a Best Multimodal UX prize. v1 is FastAPI
  and `curl`.
- **Its verifier reads the agent's own recorded results.** A static LLM judge grading
  text produced by the same system is the reward-hacking setup that "The Verification
  Horizon" (arXiv 2606.26300) is about.

v1 stays in the repo. It is the honest baseline for the A/B, and being able to show
*"here is the obvious design, here is what it cannot tell you"* is worth more than
deleting it.

## Why v2 is the bet

**The field converged on refusing to act.** "The agent prepares, the human sends"
recurs across nearly every independent public entry; several state outright that they
gave the agent no execute endpoint. Meanwhile the winners of the most comparable
prior event *acted* — the GitLab winner converts risky merge requests to Draft to
physically disable the merge button, on the logic that warning comments get ignored.
Read-only insight generators did not place first.

So two thousand entrants are optimizing for a virtue the judges did not reward, and
they are all doing it the same way. v2 takes the third position: **autonomy as a
measured, per-operation, revocable budget**. It ends where 90% of the field begins.

It also lands on three of the four organizer workshops — long-running, self-evolving,
memory — which is the closest thing to a published answer key this contest has.

## What is verified, and what is not

Run `PYTHONPATH=src python -m pytest tests -q` — 28 tests across both scaffolds
(7 for v1, 21 for v2), no credentials needed.

**Verified by execution against `google-adk` 2.6.3:**

- The graph constructs, routes, and completes: `propose → gate → {shadow|commit|consult} → assess → gate` with a legal routed cycle.
- The ladder works across runs: four rehearsals with the real world untouched,
  promotion on the fifth, first real mutation on the sixth.
- Fault injection demotes: with a tool that reports success while the world stays
  put, verification catches it and the class drops back to shadow, mid-demo.
- An effect replayed after resume returns its recorded result rather than firing again.
- Earned authority does not transfer to an argument shape that was never rehearsed.

**Not verified:**

- No `LlmAgent` has been run *inside* the workflow — that needs an API key. The mixed
  deterministic + LLM graph is source-verified only, and is the first thing to confirm.
- No live Gemini call, no GCP deployment. `gcloud` is not installed here.
- `ResumabilityConfig` is marked experimental by ADK and warns at construction.

## Known gaps in v2

1. **No UI.** The promotion board is the interface and it does not exist yet. This is
   the largest remaining risk to 30% of the score.
2. **The ledger has no Firestore round-trip test**, only the in-memory store.
3. **`adk conformance` is not wired in.** Recording golden transcripts would turn the
   rehearsal history into a replayable regression suite checked into git — the
   strongest available answer to "how do we know it works," given seeds do not
   produce determinism.
4. **No `pass^k` reporting.** The eval story is currently unit tests, which is better
   than the field but short of what the research says is credible.
5. **Domain is a placeholder.** `vm.stop` is a stand-in. The real domain is still the
   biggest open decision.

## One bug worth recording

The first draft of `VirtualWorld` accumulated mutations across runs, so the second
rehearsal of an operation saw its own leftovers, scored as a no-op, and **nothing
could ever leave shadow**. Every unit test passed. It surfaced only on the
end-to-end run, and the fix — scoping the virtual world per `run_id`, so a multi-step
plan still sees its own earlier steps — is now pinned by two regression tests.

Worth stating plainly because it is the same class of error the whole design is
about: a system that reports success while nothing actually changed.
