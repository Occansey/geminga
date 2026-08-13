"""Human-in-the-loop gate.

This is what separates the Collaborative Partner framing from Taskmaster, and
it is also the honest way to run anything side-effecting. Enabled by
AGENT_REQUIRE_APPROVAL; the tool is not even registered when it is off.
"""

from __future__ import annotations

from google.adk.tools import ToolContext

from ..ports import Plan
from ..stores import make_plan_store

_store = None


def _plans():
    global _store
    if _store is None:
        _store = make_plan_store()
    return _store


def request_approval(step_id: str, action: str, tool_context: ToolContext) -> dict:
    """Pause the run and ask the user to approve a side-effecting action.

    Args:
        step_id: The step awaiting approval.
        action: Exactly what will happen if approved, in the user's terms —
            what gets sent, changed, or spent. Vague requests get refused.
    """
    session = getattr(tool_context, "session_id", None) or "local"
    plan: Plan | None = _plans().load(session)
    if not plan:
        return {"error": "No plan for this session."}

    for step in plan.steps:
        if step.id == step_id:
            step.state = "blocked"
            step.result = f"Awaiting approval: {action}"
            break
    plan.state = "awaiting_approval"
    _plans().save(plan)
    return {"awaiting_approval": True, "step_id": step_id, "action": action}


def grant_approval(session_id: str, step_id: str) -> dict:
    """Called by the application layer (not the model) once the user says yes."""
    plan: Plan | None = _plans().load(session_id)
    if not plan:
        return {"error": "No plan for this session."}
    for step in plan.steps:
        if step.id == step_id:
            step.state = "pending"
            step.result = ""
    plan.state = "executing"
    _plans().save(plan)
    return plan.to_dict()
