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
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from ratchet.authority import AuthorityLedger
from ratchet.domains import finops
from ratchet.effects import Actuator, EffectLog
from ratchet.graph import Deps, build_app
from ratchet.world import DictReader, VirtualWorld, scope_of

BOARD = Path(__file__).parent / "board.html"
app = FastAPI(title="Nightshift", version="0.1.0")


class Estate:
    """The live environment. One per process; the demo resets it between runs."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.rows = finops.sample_estate()
        self.ledger = AuthorityLedger()
        self.log = EffectLog()
        self.lying = False
        reader = DictReader(self.rows)
        self.deps = Deps(
            ledger=self.ledger,
            actuator=Actuator(self.log, {name: self._tool(name) for name in finops.SPECS}),
            virtual=VirtualWorld(reader, finops.simulators()),
            reader=reader,
        )

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
    op_class: str = "compute.stop_idle_instance"
    target: str = "staging-web-3"
    runs: int = 8
    lie_from: int | None = None


@app.get("/", response_class=HTMLResponse)
def board() -> str:
    return BOARD.read_text(encoding="utf-8")


@app.get("/api/estate")
def estate() -> dict:
    return {
        "spend": ESTATE.spend,
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
            ctx.state["queue"] = [finops.propose_effect(req.op_class, {"target": req.target}, run_id)]
            ctx.state["cursor"] = 0
            yield {"proposed": 1, "goal": goal}

        adk_app = build_app(ESTATE.deps, propose, name="nightshift")
        scope = scope_of(req.op_class, {"target": req.target})
        pristine = dict(ESTATE.rows[scope])

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

            record = next(r for r in ESTATE.ledger.board() if r.op_class == req.op_class)
            payload = {
                "run": i,
                "op_class": req.op_class,
                "target": req.target,
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

        yield "data: {\"done\": true}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
