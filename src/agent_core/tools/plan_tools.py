"""Plan tools — the spine of the agent.

ADK reads these signatures and docstrings to build the tool schema the model
sees, so the wording here is prompt surface, not just documentation. Keep it
plain and imperative.
"""

from __future__ import annotations

from google.adk.tools import ToolContext

from ..ports import Plan, Step
from ..stores import make_plan_store

_store = None


def _plans():
    global _store
    if _store is None:
        _store = make_plan_store()
    return _store


def _session_id(tool_context: ToolContext) -> str:
    return getattr(tool_context, "session_id", None) or tool_context.state.get("session_id", "local")


def save_plan(goal: str, steps: list[dict], tool_context: ToolContext) -> dict:
    """Store an ordered plan for the current session, replacing any existing one.

    Args:
        goal: The user's goal, restated in one sentence.
        steps: Ordered list of {"description": str, "side_effecting": bool}.

    Returns:
        The stored plan, including the generated step ids.
    """
    plan = Plan(
        session_id=_session_id(tool_context),
        goal=goal,
        state="executing",
        steps=[
            Step(
                id=f"s{i + 1}",
                description=str(s.get("description", "")).strip(),
                side_effecting=bool(s.get("side_effecting", False)),
            )
            for i, s in enumerate(steps)
        ],
    )
    _plans().save(plan)
    return plan.to_dict()


def get_plan(tool_context: ToolContext) -> dict:
    """Return the current plan for this session, or an empty plan if none exists."""
    plan = _plans().load(_session_id(tool_context))
    return plan.to_dict() if plan else {"goal": "", "state": "planning", "steps": []}


def get_next_step(tool_context: ToolContext) -> dict:
    """Return the next pending step, or {"done": true} when the plan is finished."""
    plan = _plans().load(_session_id(tool_context))
    if not plan:
        return {"error": "No plan for this session. Delegate to the planner first."}
    step = plan.next_step
    if step is None:
        plan.state = "done"
        _plans().save(plan)
        return {"done": True}
    step.state = "running"
    _plans().save(plan)
    return step.to_dict()


def complete_step(step_id: str, result: str, tool_context: ToolContext) -> dict:
    """Mark a step done.

    Args:
        step_id: The id returned by get_next_step.
        result: One sentence on what actually happened — this is the evidence
            the verifier reads, so state the outcome, not the intention.
    """
    return _transition(tool_context, step_id, "done", result=result)


def fail_step(step_id: str, error: str, tool_context: ToolContext) -> dict:
    """Mark a step failed, with the reason. Never use this to hide a partial result."""
    return _transition(tool_context, step_id, "failed", error=error)


def _transition(tool_context: ToolContext, step_id: str, state: str, **fields) -> dict:
    plan = _plans().load(_session_id(tool_context))
    if not plan:
        return {"error": "No plan for this session."}
    for step in plan.steps:
        if step.id == step_id:
            step.state = state  # type: ignore[assignment]
            for k, v in fields.items():
                setattr(step, k, v)
            break
    else:
        return {"error": f"No step {step_id!r} in this plan."}

    if plan.is_complete:
        plan.state = "done"
    _plans().save(plan)
    return plan.to_dict()
