---
name: estate
description: Inspect, provision or tear down the GCP demo estate that Geminga acts on, with the cost consequences stated up front. Use when asked what the demo is costing, to create resources for the agent to reclaim, to clean up afterwards, or when the run rate looks wrong.
---

# The demo estate

The estate is the *subject matter*, not the app. Geminga reclaims wasted cloud spend,
so there has to be real waste for it to find. Reads are free; existence is not.

Project: `nightshift-agentic-2026`. Billing: the "Hackathon" EUR account, €50 budget
alerting at 50/90/100%. Budgets **alert, they do not cap** — there is no hard stop.

## Inspect — always do this first

```bash
cd /Users/maxwell/hackathon/02-all-things-agentic
PYTHONPATH=src ./.venv/bin/python -c "
from ratchet.domains import gcp_inventory as inv
e = inv.read_estate('nightshift-agentic-2026')
for s, r in sorted(e.items(), key=lambda kv: -kv[1]['monthly_cost_usd']):
    op, t = s.split(':', 1)
    print(f\"{t:<22}{op.split('.')[1]:<26}\${r['monthly_cost_usd']:>6.2f}  \"
          f\"{'RECLAIMABLE' if r['idle_candidate'] else 'in use':<12}\"
          f\"{'free tier' if r.get('free_tier') else ''}\")
print(f\"run rate \${inv.monthly_spend(e)}/mo\")"
```

Costs are **list-price estimates** minus known free-tier allowances, not the bill.
The authoritative figure is the billing console. Never present an estimate as a bill —
the whole product argues for verifying claims against reality.

## Keep it free

The steady state costs **$0/mo** and should stay there between demos:

- one `e2-micro` in `us-central1` — always-free covers exactly one
- ≤30GB of `pd-standard` total — the free disk allowance
- **no reserved IPs** — every external IPv4 is billed since Feb 2024, in use or not
- no snapshots, no second VM

Anything beyond that is real money. An `e2-small` is ~$12/mo; a reserved unused IP is
~$7.30/mo. Both are easy to leave running by accident.

## Provision waste for a recording

A $0 estate reclaims $0, which weakens the demo. Spin up something legible shortly
before recording and remove it after — roughly ten cents for a couple of hours.

```bash
P=nightshift-agentic-2026
gcloud compute addresses create demo-orphan-ip --project=$P --region=us-central1
gcloud compute disks create demo-orphan-disk-big --project=$P --zone=us-central1-a \
  --size=200GB --type=pd-standard --labels=purpose=demo,owner=geminga
```

Zones run out of capacity. If a create fails with *"does not have enough resources"*,
try another zone — and **verify the resource exists afterwards** rather than trusting
the command's exit status. A retry loop that swallows stderr has already reported
success for a VM that was never created.

## Tear down

```bash
P=nightshift-agentic-2026
gcloud compute addresses delete demo-orphan-ip --region=us-central1 --project=$P --quiet
gcloud compute disks delete demo-orphan-disk-big --zone=us-central1-a --project=$P --quiet
gcloud compute instances list --project=$P   # confirm what remains
```

Leave `demo-idle-web` and one small `demo-orphan-disk` in place — they are free and
they keep the board non-empty.
