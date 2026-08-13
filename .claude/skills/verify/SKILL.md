---
name: verify
description: Run everything that can be checked and report honestly what is verified versus merely written — tests, ADK graph construction, live inference, Firestore round-trip. Use before committing, before recording, when asked "does it still work", or when writing any claim about this project into a README, changelog or submission.
---

# Verify

The project's argument is that a thing reported is not a thing confirmed. That
applies to our own claims first. Every statement in the README, CHANGELOG or
submission should trace to something in this file that actually ran.

## The suite

```bash
cd /Users/maxwell/hackathon/02-all-things-agentic
PYTHONPATH=src GOOGLE_CLOUD_PROJECT=nightshift-agentic-2026 \
  ./.venv/bin/python -m pytest tests -q
```

Expect **30 passed, 1 skipped** without credentials, **31 passed** with ADC present.
The skipped one is the live-model test; a skip is not a pass, and if you are about to
claim the model path works, run it with credentials.

## Graph construction against real ADK

Catches topology and schema breakage without spending a token — ADK validates edges,
cross-edge schemas, terminals and the cycle rule at construction.

```bash
PYTHONPATH=src ./.venv/bin/python -c "
from google.adk.agents import LlmAgent
from ratchet.authority import AuthorityLedger
from ratchet.effects import Actuator, EffectLog
from ratchet.domains import finops
from ratchet.graph import Deps, build_workflow
from ratchet.world import DictReader, VirtualWorld
r = DictReader(finops.sample_estate())
d = Deps(AuthorityLedger(), Actuator(EffectLog(), {}), VirtualWorld(r, finops.simulators()), r)
w = build_workflow(d, LlmAgent(name='p', model='gemini-3.6-flash', instruction='x'), finops.to_effect)
print('graph ok:', w.name, len(w.edges), 'edges')"
```

## Live inference

Gemini 3.x is served from the **`global`** endpoint. Regional endpoints 404 for every
3.x model — this has bitten once and will again.

```bash
PYTHONPATH=src ./.venv/bin/python -c "
from google import genai
c = genai.Client(vertexai=True, project='nightshift-agentic-2026', location='global')
print(c.models.generate_content(model='gemini-3.6-flash', contents='Reply OK').text.strip())"
```

## Durable ledger

```bash
PYTHONPATH=src ./.venv/bin/python -c "
from ratchet.authority import AuthorityLedger, FirestoreLedgerStore
l = AuthorityLedger(FirestoreLedgerStore(project='nightshift-agentic-2026'))
print([(r.op_class, r.authority.label, r.passes) for r in l.board()])"
```

## Reporting

State what ran and what did not, separately. Currently unverified and worth saying so
whenever it comes up:

- no Cloud Run deployment yet, so no deployment proof
- `ResumabilityConfig` is marked experimental by ADK and warns at construction
- cost figures are list-price estimates, not billing data

If a check fails, report the failure with its output rather than the intent. "Tests
pass" when one was skipped is the same category of error the product exists to catch.
