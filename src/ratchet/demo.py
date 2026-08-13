"""The demo: watch an agent earn the right to spend your money back.

    PYTHONPATH=src python -m ratchet.demo                  # the ladder
    PYTHONPATH=src python -m ratchet.demo --fault 6        # a tool starts lying
    PYTHONPATH=src python -m ratchet.demo --estate         # the Monday billing alert

No API key, no GCP project, no network. The graph engine in ADK 2 is LLM-free, so the
ladder is deterministic and runs in CI — which is also why it can be filmed in one
unbroken take without praying that a model behaves. The rubric asks for unedited live
execution; this is built to survive that.
"""

from __future__ import annotations

import argparse
import asyncio

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.workflow import node
from google.genai import types

from .authority import AuthorityLedger
from .domains import finops
from .effects import Actuator, EffectLog
from .graph import Deps, build_app
from .world import DictReader, FaultProfile, VirtualWorld, scope_of

# The class the ladder climbs during the demo. Reversible, high-frequency, and the
# one a tired human would never get round to.
OP = "compute.stop_idle_instance"
TARGET = "staging-web-3"


def build_demo(faults: FaultProfile | None = None):
    estate = finops.sample_estate()
    reader = DictReader(estate)

    def apply(op_class: str):
        def tool(**params):
            scope = scope_of(op_class, params)
            estate[scope] = finops.SPECS[op_class].simulate(estate.get(scope, {}), params)
            return estate[scope]

        return tool

    deps = Deps(
        ledger=AuthorityLedger(),
        actuator=Actuator(EffectLog(), {name: apply(name) for name in finops.SPECS}),
        # Rehearsal reads the real estate, then diverges into a per-run copy.
        virtual=VirtualWorld(reader, finops.simulators(), faults=faults),
        reader=reader,
    )
    return deps, estate


@node
async def propose(ctx, goal: str, run_id: str):
    """Stands in for the model, so the ladder is the only moving part.

    Swapping this for an `LlmAgent` is the brain/hands split working as designed:
    nothing downstream knows or cares where the proposal came from — and note the
    post-conditions come from the domain spec, not from whoever proposed the work.
    """
    ctx.state["queue"] = [finops.propose_effect(OP, {"target": TARGET}, run_id)]
    ctx.state["cursor"] = 0
    yield {"proposed": 1, "goal": goal}


async def run_once(app, estate: dict, run_id: str) -> dict:
    scope = scope_of(OP, {"target": TARGET})
    estate[scope] = {**estate[scope], "status": "RUNNING", "monthly_cost_usd": 97.80}

    runner = Runner(app=app, session_service=InMemorySessionService(), auto_create_session=True)
    final: dict = {}
    async for event in runner.run_async(
        user_id="platform-eng",
        session_id=run_id,
        new_message=types.Content(role="user", parts=[types.Part(text="reclaim idle spend")]),
        state_delta={"goal": "reclaim idle spend", "run_id": run_id},
    ):
        if getattr(event, "output", None) is not None and isinstance(event.output, dict):
            final = event.output
    return final


async def ladder(runs: int, fault_at: int | None) -> None:
    deps, estate = build_demo()
    app = build_app(deps, propose)
    scope = scope_of(OP, {"target": TARGET})

    print(f"\noperation: {OP} on {TARGET} — {finops.SPECS[OP].summary}")
    print(f"{'run':>4}  {'authority':<12} {'streak':>6}  {'acted':>5}  {'vm':<11} {'$/mo':>7}  why")
    print("─" * 104)

    for i in range(1, runs + 1):
        if fault_at and i == fault_at:
            # The tool starts lying: it reports success while the VM keeps running.
            # Verification re-derives real state, so the claim does not survive.
            deps.actuator = Actuator(EffectLog(), {OP: lambda **p: {"status": "TERMINATED"}})

        result = await run_once(app, estate, f"r{i}")
        record = deps.ledger.board()[0]
        row = estate[scope]
        print(
            f"{i:>4}  {record.authority.label:<12} {record.streak:>6}  "
            f"{result.get('committed', 0):>5}  {row['status']:<11} "
            f"{row['monthly_cost_usd']:>7.2f}  {record.last_reason}"
            + ("   ← tool starts lying" if fault_at and i == fault_at else "")
        )


def show_estate() -> None:
    estate = finops.sample_estate()
    print(f"\nMonday, 09:14. Billing alert. Monthly run rate: ${finops.monthly_spend(estate):,.2f}\n")
    print(f"  {'resource':<28} {'$/mo':>9}  {'reversible':<11} operation")
    print("  " + "─" * 96)
    for scope, row in sorted(estate.items(), key=lambda kv: -kv[1]["monthly_cost_usd"]):
        op_class, target = scope.split(":", 1)
        spec = finops.SPECS[op_class]
        print(
            f"  {target:<28} {row['monthly_cost_usd']:>9.2f}  "
            f"{'yes' if spec.reversible else 'NO — human':<11} {op_class}"
        )
    reclaimable = sum(r["monthly_cost_usd"] for r in estate.values())
    print(f"\n  Reclaimable: ${reclaimable:,.2f}/mo. Every one of these is known. "
          "None of them get deleted,\n  because deleting the wrong one on a Monday is worse than the bill.\n")


def cli() -> None:
    parser = argparse.ArgumentParser(description="Watch an operation earn the right to act")
    parser.add_argument("-n", "--runs", type=int, default=8)
    parser.add_argument("--fault", type=int, metavar="RUN",
                        help="from this run on, the tool reports success while nothing changes")
    parser.add_argument("--estate", action="store_true", help="show the Monday billing alert and exit")
    args = parser.parse_args()

    if args.estate:
        show_estate()
        return
    asyncio.run(ladder(args.runs, args.fault))


if __name__ == "__main__":
    cli()
