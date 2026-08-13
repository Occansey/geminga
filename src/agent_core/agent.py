"""The agent itself: a planner → executor → verifier loop built on Google ADK.

Shape of the thing
------------------
A root `LlmAgent` owns the conversation and delegates to three sub-agents.
The plan is *data* (see ports.Plan) held in Firestore rather than state hidden
in the model's context, which is what makes the run resumable, auditable, and
demoable — you can show the plan mutating step by step on screen.

Track framing (rules require you pick exactly one):
  Taskmaster            — AGENT_REQUIRE_APPROVAL=false, agent runs to completion
  Collaborative Partner — AGENT_REQUIRE_APPROVAL=true, pauses on side-effecting steps
The code path is the same; only the gate differs. Decide before the demo video
and say the track name out loud in it.
"""

from __future__ import annotations

from google.adk.agents import LlmAgent

from .config import settings
from .tools import approval, plan_tools, research, workspace

PLANNER_INSTRUCTION = """\
You turn a goal into a short, ordered plan.

Rules:
- 3 to 8 steps. Fewer, larger steps beat many trivial ones.
- Each step must be independently checkable — a reader should be able to tell
  whether it succeeded without running the whole plan.
- Mark a step side_effecting=true if it writes to the world: sends, publishes,
  pays, deletes, or changes anything outside this session.
- Do not execute anything. Call save_plan exactly once, then stop.
"""

EXECUTOR_INSTRUCTION = """\
You execute one step of an existing plan at a time.

Loop: call get_next_step. If it returns nothing, say the plan is complete and stop.
Otherwise do that step using the tools available, then call complete_step with a
one-sentence result, then stop and return control. Never run two steps in one turn —
the caller re-invokes you, and that boundary is what makes the run interruptible.

If a step is blocked, call fail_step with the reason. Do not invent a result.
If a step needs approval you do not have, call request_approval and stop.
"""

VERIFIER_INSTRUCTION = """\
You check finished work against the original goal. You are the last thing between
a plausible-looking demo and a wrong one, so be concrete.

For each completed step, state whether its recorded result actually supports the
goal. Name what is missing rather than hedging. If the plan claims success but the
evidence is thin, say so plainly and list what would need to be true.
Return a short verdict: COMPLETE, PARTIAL, or FAILED, then the reasoning.
"""

ROOT_INSTRUCTION = """\
You are {name}, an agent that carries multi-step goals through to a finished result.

Route the work:
- A new goal, or a materially changed one -> delegate to planner.
- An existing plan with pending steps -> delegate to executor, once per turn.
- A plan whose steps are all done -> delegate to verifier, then report.

Report in the user's terms, not the system's: what got done, what it means for
them, and what still needs a decision. Never claim a step succeeded unless the
plan records it as done.
"""


def build_planner() -> LlmAgent:
    return LlmAgent(
        name="planner",
        model=settings().agent_model,
        description="Turns a goal into an ordered, checkable plan.",
        instruction=PLANNER_INSTRUCTION,
        tools=[plan_tools.save_plan],
    )


def build_executor() -> LlmAgent:
    tools = [
        plan_tools.get_next_step,
        plan_tools.complete_step,
        plan_tools.fail_step,
        workspace.write_artifact,
        workspace.read_artifact,
        research.web_search,
    ]
    if settings().agent_require_approval:
        tools.append(approval.request_approval)
    return LlmAgent(
        name="executor",
        model=settings().agent_model,
        description="Executes exactly one pending step per turn.",
        instruction=EXECUTOR_INSTRUCTION,
        tools=tools,
    )


def build_verifier() -> LlmAgent:
    # The fast model is deliberate: verification is cheap and runs often.
    return LlmAgent(
        name="verifier",
        model=settings().agent_fast_model,
        description="Checks completed work against the original goal.",
        instruction=VERIFIER_INSTRUCTION,
        tools=[plan_tools.get_plan],
    )


def build_root_agent() -> LlmAgent:
    cfg = settings()
    return LlmAgent(
        name=cfg.agent_name,
        model=cfg.agent_model,
        description="Root agent: routes between planning, execution and verification.",
        instruction=ROOT_INSTRUCTION.format(name=cfg.agent_name),
        sub_agents=[build_planner(), build_executor(), build_verifier()],
        tools=[plan_tools.get_plan],
    )


# ADK's `adk web` / `adk run` discover this symbol by convention.
root_agent = build_root_agent()
