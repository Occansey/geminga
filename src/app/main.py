"""Cloud Run entrypoint.

Kept thin on purpose: the demo video needs a URL that responds, and the judges
need to see the plan mutating. /plan is what you screen-record next to the chat.
"""

from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agent_core.config import settings
from agent_core.runtime import AgentSession
from agent_core.stores import make_plan_store
from agent_core.tools.approval import grant_approval

app = FastAPI(title="All Things Agentic — agent core", version="0.1.0")
_sessions: dict[str, AgentSession] = {}


class Message(BaseModel):
    session_id: str = "demo"
    message: str


class Approval(BaseModel):
    session_id: str
    step_id: str


@app.on_event("startup")
def _check_config() -> None:
    if settings().agent_store != "memory":
        settings().require_cloud()


@app.get("/healthz")
def healthz() -> dict:
    cfg = settings()
    return {"ok": True, "model": cfg.agent_model, "vertex": cfg.uses_vertex}


@app.post("/chat")
async def chat(body: Message) -> dict:
    session = _sessions.setdefault(body.session_id, AgentSession(session_id=body.session_id))
    turn = await session.send(body.message)
    return {"reply": turn.text, "events": len(turn.events)}


@app.get("/plan/{session_id}")
def plan(session_id: str) -> dict:
    stored = make_plan_store().load(session_id)
    if not stored:
        raise HTTPException(404, f"No plan for session {session_id!r}")
    return stored.to_dict()


@app.post("/approve")
def approve(body: Approval) -> dict:
    result = grant_approval(body.session_id, body.step_id)
    if "error" in result:
        raise HTTPException(404, result["error"])
    return result


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
