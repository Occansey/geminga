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
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from pydantic import BaseModel

from ratchet.authority import PROMOTION_THRESHOLD, AuthorityLedger, OperationRecord
from ratchet.domains import finops
from ratchet.effects import Actuator, Effect, EffectLog
from ratchet.admission import Snapshot
from ratchet.attempts import AttemptLedger
from ratchet.graph import Deps, build_app
from ratchet.liveness import assess as assess_liveness
from ratchet.review import REVIEW_MODEL, Reviewer, vertex_model
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

    def restore_world(self) -> None:
        """Put the estate back to its starting state, keeping the ladder.

        The boundary is one *request*, not one run. Inside a run sequence the world has
        to persist or the precondition gate is meaningless — that was the bug where the
        agent reapplied the same policy three times and the reviewer called it a
        malfunctioning loop. Across requests it has to reset, or the first click does the
        work and every click after it correctly reports there is nothing left to do,
        which reads as a dead button.

        The ledger is deliberately untouched: authority is earned over time and should
        survive a fresh estate. Only `/api/reset` clears it.

        Mutated in place because the reader holds this dict by reference.
        """
        if LIVE_PROJECT:
            from ratchet.domains import gcp_inventory

            fresh = gcp_inventory.read_estate(LIVE_PROJECT)
        else:
            fresh = finops.sample_estate()
        self.rows.clear()
        self.rows.update(fresh)
        self.lying = False
        self.refresh_snapshot()

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
    """Most valuable row the agent has an operation for *and* can honestly call idle.

    The old version ranked by cost and consulted `cpu_7d_avg`, which put the $2,632 GPU
    node at the top of the list every time — it sits near zero CPU while training. The
    post-commit reviewer named this exactly: "CPU is not the primary indicator of
    activity for a GPU-accelerated machine; the agent's logic is fundamentally flawed
    for this workload type."

    It is fixed here *and* in a gate. Fixing only the proposer would leave a system whose
    safety depends on the component most exposed to a hijacked model getting its ranking
    right, which is the assumption this whole project argues against.
    """
    ranked = sorted(ESTATE.rows.items(), key=lambda kv: -kv[1].get("monthly_cost_usd", 0))
    for scope, row in ranked:
        op_class, target = scope.split(":", 1)
        spec = finops.SPECS.get(op_class)
        if spec is None or not row.get("idle_candidate", True):
            continue
        # Irreversible operations are not skipped because they are forbidden — they are
        # skipped because they sit behind a human at every rung, so they are never the
        # autonomous path's best *next* action. They stay in the estate view, tagged.
        if not spec.reversible:
            continue
        live = assess_liveness(op_class, target, ESTATE.deps.topology,
                               asserts_idle=spec.asserts_idle)
        if live.may_proceed:
            return op_class, target
    scope = ranked[0][0]
    return scope.split(":", 1)[0], scope.split(":", 1)[1]


@app.get("/", response_class=HTMLResponse)
def board() -> str:
    return BOARD.read_text(encoding="utf-8")


GSAP = Path(__file__).parent / "gsap.min.js"


INTRO = Path(__file__).parent / "intro.html"
MARK = Path(__file__).parent / "mark.png"


@app.get("/intro", response_class=HTMLResponse)
def intro() -> str:
    """The title card: who built this, what the name means, and why. Opens the presentation."""
    return INTRO.read_text(encoding="utf-8")


@app.get("/mark.png")
def mark() -> Response:
    return Response(MARK.read_bytes(), media_type="image/png")


ARCH = Path(__file__).parent / "architecture.html"


@app.get("/architecture", response_class=HTMLResponse)
def architecture() -> str:
    """The interactive cutaway, served from the same origin as the console so a presenter can
    open it mid-demo without leaving the deployment."""
    return ARCH.read_text(encoding="utf-8")


@app.get("/gsap.min.js")
def gsap() -> Response:
    # Self-hosted so the console's motion needs no third-party CDN and survives any CSP.
    return Response(GSAP.read_text(encoding="utf-8"), media_type="application/javascript")


# Cloud Run's frontend intercepts /healthz before it reaches the container: the
# deployed app's own route table contains it and the path still returns Google's 404.
# /api/health is the one to curl against a deployed service.
@app.get("/api/health")
@app.get("/healthz")
def healthz() -> dict:
    """Cloud Run's readiness probe. Reports the two switches, because "is it live?"
    and "can it delete things?" are the questions worth answering at a glance."""
    model = getattr(getattr(ESTATE.reviewer, "model", None), "used", {}) or {}
    return {"ok": True, "project": LIVE_PROJECT or "fixture", "mutations": ALLOW_MUTATIONS,
            # Which Gemini actually answered the last review. Asserted nowhere; measured here.
            "review_model": model.get("model") or REVIEW_MODEL}


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
        ESTATE.restore_world()
        scope = scope_of(op_class, {"target": target})
        pristine = dict(ESTATE.rows[scope])
        committed: list[dict] = []

        for i in range(1, req.runs + 1):
            ESTATE.lying = bool(req.lie_from and i >= req.lie_from)
            # The row used to be restored to `pristine` before every run so the ladder
            # could commit the same operation repeatedly. Rehearsals never needed it —
            # they run against the virtual world and touch nothing — so all it did was
            # undo real work and hand the agent the same job again. The post-commit
            # reviewer read the result exactly as it looked: "this redundant operation
            # confirms a malfunctioning loop", three freezes in a row.
            #
            # Now the estate stays as the agent left it. Once the policy is set there is
            # nothing to do, and the precondition gate says so.

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

            before_row = dict(ESTATE.rows[scope])
            if final.get("committed"):
                # Reviewed after the stream, not inside it. A commit that has happened
                # is not undone by a slow reviewer, and putting a model call in the
                # per-run path would make the console's latency depend on it.
                committed.append({
                    "op_class": op_class, "target": target, "run_id": f"r{i}",
                    "shape": ESTATE.deps.shape_of(
                        Effect(**finops.to_effect(op_class, target, f"r{i}"))),
                    "monthly_cost_usd": pristine.get("monthly_cost_usd"),
                    "before": before_row, "after": dict(ESTATE.rows[scope]),
                    # Whether the commit survived verification. Without it the reviewer
                    # sees `before == after` and cannot tell a redundant operation from a
                    # tool that claimed success and changed nothing — the two are
                    # identical in state and opposite in cause. Shown the sabotage run it
                    # blamed "a flaw in the agent's logic" when the agent was fine and the
                    # tool had lied. The verdict was right and the reason was not, and a
                    # reviewer that misattributes cause teaches an operator to discount it.
                    "verified": bool(final.get("verified_pass")),
                })

            # A refusal at admission never reaches the ladder, so no record exists — and
            # `next()` without a default raises StopIteration, which inside an async
            # generator becomes a RuntimeError that kills the stream. The console went
            # blank on exactly the behaviour the product exists to demonstrate. Refusing
            # is this system's normal day; it has to render.
            record = next(
                (r for r in ESTATE.ledger.board() if r.op_class == op_class),
                OperationRecord(op_class=op_class),
            )
            payload = {
                "run": i,
                "op_class": op_class,
                "target": target,
                "authority": record.authority.label,
                "refused": final.get("refused") or (not final.get("committed") and not record.passes),
                "gate": final.get("gate", ""),
                "route": final.get("route", ""),
                "streak": record.streak,
                # The console drew five pips at every rung, which is only right in shadow:
                # provisional needs ten. Send the real threshold so the meter cannot lie.
                "threshold": PROMOTION_THRESHOLD.get(record.authority, 0),
                "passes": record.passes,
                "failures": record.failures,
                "demotions": record.demotions,
                # Two different sentences, and which one is true depends on how far the run got.
                # A refusal never reaches an outcome, so the gate's reason is all there is.
                # A run that committed has a verified result, and that is the one worth
                # reading — surfacing the gate's pre-run decision instead replaced
                # "demoted to shadow: 2 post-conditions did not hold" with "provisional —
                # every run verified", which is the opposite of what had just happened.
                "reason": (
                    record.last_reason if final.get("operations")
                    else final.get("gate_reason") or "refused before the ladder"
                ),
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
        findings = ESTATE.reviewer.review(committed, ESTATE.deps.topology, finops.SPECS)
        if findings:
            yield f"data: {json.dumps({'review': [f.to_dict() for f in findings]})}\n\n"

        yield "data: {\"done\": true}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
