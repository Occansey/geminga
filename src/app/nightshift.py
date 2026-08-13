"""Nightshift — the operations console.

Serves the promotion board and streams the ladder as it moves. The board is not a
readout bolted onto the agent; it is the agent's state made visible, which is the
only honest way to show a judge what "earned autonomy" means in four minutes.

    PYTHONPATH=src python -m app.nightshift          # http://localhost:8080

Streams over SSE so the demo is genuinely live — the rubric asks for unedited
execution, and a page that fills in as the agent works survives that better than any
edit would.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from ratchet.authority import AuthorityLedger
from ratchet.domains import finops
from ratchet.effects import Actuator, Effect, EffectLog
from ratchet.admission import Snapshot
from ratchet.attempts import AttemptLedger
from ratchet.graph import Deps, build_app
from ratchet.review import Reviewer, vertex_model
from ratchet.world import DictReader, VirtualWorld, scope_of

log = logging.getLogger("nightshift")
BOARD = Path(__file__).parent / "board.html"
app = FastAPI(title="Nightshift", version="0.1.0")


# Point at a real project to read live inventory; leave unset for the fixture.
# Mutations are a *second*, separate opt-in — reading the real world and changing it
# are different decisions and should not share a switch.
LIVE_PROJECT = os.environ.get("GEMINGA_PROJECT", "")
ALLOW_MUTATIONS = os.environ.get("GEMINGA_ALLOW_MUTATIONS", "").lower() in ("1", "true", "yes")


def _live_topology():
    """The real project's dependency graph, or nothing.

    Reading it needs Compute and Monitoring permissions the demo project may not have.
    Returning None is the honest failure: `shape_of` falls back to the V1 fingerprint
    rather than to a topology we invented, and the console says which one it is using.
    """
    try:
        from ratchet import topology as topo

        return topo.from_gcp(LIVE_PROJECT)
    except Exception as exc:  # noqa: BLE001 - degraded is a state, not a crash
        log.warning("topology unavailable, falling back to V1 shapes: %s", exc)
        return None


class Estate:
    """The live environment. One per process; the demo resets it between runs."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        if LIVE_PROJECT:
            from ratchet.domains import gcp_inventory

            self.rows = gcp_inventory.read_estate(LIVE_PROJECT)
        else:
            self.rows = finops.sample_estate()
        self.ledger = AuthorityLedger()
        self.log = EffectLog()
        self.lying = False
        if LIVE_PROJECT and ALLOW_MUTATIONS:
            # Once deletes are real, verification must re-derive from the API.
            # Checking a cached snapshot would let a delete "succeed" against stale
            # data — exactly the failure this system exists to catch.
            from ratchet.domains.gcp_inventory import GcpReader

            reader = GcpReader(LIVE_PROJECT, self.rows)
        else:
            reader = DictReader(self.rows)

        if LIVE_PROJECT:
            from ratchet.domains import gcp_actions

            tools = gcp_actions.build_tools(LIVE_PROJECT, self.rows, ALLOW_MUTATIONS)
        else:
            tools = {name: self._tool(name) for name in finops.SPECS}
        self.attempts = AttemptLedger()
        # Post-commit second opinion. `vertex_model()` returns None without credentials,
        # and a reviewer with no model is inert rather than broken — the ladder simply
        # goes unreviewed, which is exactly where this system was before.
        self.reviewer = Reviewer(self.ledger, model=vertex_model())
        # Every one of these was previously left to default, and defaults here are not
        # neutral: an empty snapshot admits nothing and an empty spec table gives the
        # legal gate nothing to reason with. The unit tests passed throughout, because
        # they build their own Deps. This is the fourth time in this project that a
        # module has been correct and unreachable, which is why `test_wiring.py` now
        # asserts the *server's* dependencies rather than a fixture's.
        self.deps = Deps(
            ledger=self.ledger,
            actuator=Actuator(self.log, tools),
            virtual=VirtualWorld(reader, finops.simulators()),
            reader=reader,
            snapshot=Snapshot.of(self.rows),
            specs=finops.SPECS,
            topology=finops.topology() if not LIVE_PROJECT else _live_topology(),
            attempts=self.attempts,
        )

    def refresh_snapshot(self) -> None:
        """Re-derive admission's view of the world immediately before a run.

        The snapshot is the answer to "does this resource exist, and is it the kind of
        thing this operation acts on". Holding a stale one across runs would let a
        delete be admitted against a resource a previous run already removed.
        """
        self.deps.snapshot = Snapshot.of(self.rows)

    def _tool(self, op_class: str):
        def tool(**params):
            scope = scope_of(op_class, params)
            if self.lying:
                # Reports success, changes nothing. The verifier re-derives real
                # state, so the claim does not survive contact with the world.
                return {"status": "TERMINATED"}
            self.rows[scope] = finops.SPECS[op_class].simulate(self.rows.get(scope, {}), params)
            return self.rows[scope]

        return tool

    @property
    def spend(self) -> float:
        return finops.monthly_spend(self.rows)


ESTATE = Estate()


class RunRequest(BaseModel):
    # Unset means "pick the most valuable thing you are allowed to act on", which
    # is the only sensible default once the estate is real and changes under you.
    op_class: str | None = None
    target: str | None = None
    runs: int = 8
    lie_from: int | None = None


def best_candidate() -> tuple[str, str]:
    """Highest-cost row the domain has an operation for. Falls back to any row."""
    ranked = sorted(ESTATE.rows.items(), key=lambda kv: -kv[1].get("monthly_cost_usd", 0))
    for scope, row in ranked:
        op_class, target = scope.split(":", 1)
        if op_class in finops.SPECS and row.get("idle_candidate", True):
            return op_class, target
    scope = ranked[0][0]
    return scope.split(":", 1)[0], scope.split(":", 1)[1]


@app.get("/", response_class=HTMLResponse)
def board() -> str:
    return BOARD.read_text(encoding="utf-8")


# Cloud Run's frontend intercepts /healthz before it reaches the container: the
# deployed app's own route table contains it and the path still returns Google's 404.
# /api/health is the one to curl against a deployed service.
@app.get("/api/health")
@app.get("/healthz")
def healthz() -> dict:
    """Cloud Run's readiness probe. Reports the two switches, because "is it live?"
    and "can it delete things?" are the questions worth answering at a glance."""
    return {"ok": True, "project": LIVE_PROJECT or "fixture", "mutations": ALLOW_MUTATIONS}


@app.get("/api/estate")
def estate() -> dict:
    return {
        "spend": ESTATE.spend,
        "project": LIVE_PROJECT or "fixture",
        "mutations": ALLOW_MUTATIONS,
        "resources": [
            {
                "scope": scope,
                "target": scope.split(":", 1)[1],
                "op_class": scope.split(":", 1)[0],
                "reversible": finops.SPECS[scope.split(":", 1)[0]].reversible,
                "summary": finops.SPECS[scope.split(":", 1)[0]].summary,
                **row,
            }
            for scope, row in sorted(ESTATE.rows.items(), key=lambda kv: -kv[1]["monthly_cost_usd"])
        ],
        "board": [r.to_dict() for r in ESTATE.ledger.board()],
        "attempts": ESTATE.attempts.report(),
        "review": ESTATE.reviewer.log.report(),
    }


@app.post("/api/reset")
def reset() -> dict:
    ESTATE.reset()
    return {"ok": True, "spend": ESTATE.spend}


@app.post("/api/run")
async def run(req: RunRequest) -> StreamingResponse:
    """Run the ladder, streaming one event per run."""

    async def stream():
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        from google.adk.workflow import node
        from google.genai import types

        @node
        async def propose(ctx, goal: str, run_id: str):
            ctx.state["queue"] = [finops.propose_effect(op_class, {"target": target}, run_id)]
            ctx.state["cursor"] = 0
            yield {"proposed": 1, "goal": goal}

        op_class, target = (req.op_class, req.target) if req.op_class and req.target else best_candidate()
        adk_app = build_app(ESTATE.deps, propose, name="nightshift")
        ESTATE.refresh_snapshot()
        scope = scope_of(op_class, {"target": target})
        pristine = dict(ESTATE.rows[scope])
        committed: list[dict] = []

        for i in range(1, req.runs + 1):
            ESTATE.lying = bool(req.lie_from and i >= req.lie_from)
            ESTATE.rows[scope] = dict(pristine)

            runner = Runner(
                app=adk_app, session_service=InMemorySessionService(), auto_create_session=True
            )
            final: dict = {}
            async for event in runner.run_async(
                user_id="platform-eng",
                session_id=f"run-{i}",
                new_message=types.Content(role="user", parts=[types.Part(text="reclaim idle spend")]),
                state_delta={"goal": "reclaim idle spend", "run_id": f"r{i}"},
            ):
                if getattr(event, "output", None) is not None and isinstance(event.output, dict):
                    final = event.output

            if final.get("committed"):
                # Reviewed after the stream, not inside it. A commit that has happened
                # is not undone by a slow reviewer, and putting a model call in the
                # per-run path would make the console's latency depend on it.
                committed.append({
                    "op_class": op_class, "target": target, "run_id": f"r{i}",
                    "shape": ESTATE.deps.shape_of(
                        Effect(**finops.to_effect(op_class, target, f"r{i}"))),
                    "monthly_cost_usd": pristine.get("monthly_cost_usd"),
                    "before": pristine, "after": dict(ESTATE.rows[scope]),
                })

            record = next(r for r in ESTATE.ledger.board() if r.op_class == op_class)
            payload = {
                "run": i,
                "op_class": op_class,
                "target": target,
                "authority": record.authority.label,
                "streak": record.streak,
                "passes": record.passes,
                "failures": record.failures,
                "demotions": record.demotions,
                "reason": record.last_reason,
                "acted": bool(final.get("committed")),
                "lying": ESTATE.lying,
                "resource": ESTATE.rows[scope],
                "spend": ESTATE.spend,
            }
            yield f"data: {json.dumps(payload)}\n\n"
            await asyncio.sleep(0.45)  # paced so a viewer can follow it

        # The second opinion, on everything that actually reached the actuator. It can
        # only restrict, so a slow, absent or hostile reviewer costs caution, never
        # safety — which is why it is allowed to run at all.
        findings = ESTATE.reviewer.review(committed, ESTATE.deps.topology)
        if findings:
            yield f"data: {json.dumps({'review': [f.to_dict() for f in findings]})}\n\n"

        yield "data: {\"done\": true}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
