"""The execution graph, on ADK 2's `google.adk.workflow` DAG runtime.

Why a graph and not the planner→executor→verifier tree in `agent_core`:

- ADK 2 (GA 19 May 2026) made `BaseAgent` a subclass of `BaseNode`; the runtime is a
  graph scheduler, not a tree walker. The audit in `research/raw/04-adk-capabilities.md`
  rates this "extremely underused" — the sampled field ships `SequentialAgent` /
  `LoopAgent` trees and hand-rolled ReAct loops.
- Schemas are checked **across edges at construction**, so a type error fails before
  any model call — and before any money is spent.
- `retry_config` and `timeout` live on the node, so failure handling is declared in
  the topology rather than buried in try/except. (Which matters twice over: a broad
  `except` inside a node silently defeats both the retry machinery and the
  human-in-the-loop pause.)
- **Cycles are legal** when they contain a routed edge, so "next operation" is an
  edge back into the gate rather than a Python `while`. The loop is in the graph
  where it can be drawn, replayed and interrupted.

Shape:

    START → propose → gate ─┬─ "shadow"  → rehearse ─┐
                            ├─ "commit"  → actuate  ─┼→ assess → ledger ─┐
                            └─ "consult" → approve → actuate             │
                            ▲                                            │
                            └──────────── routed edge, next operation ───┘

`approve` is the only human-facing node, and it exists for operations that are
*irreversible*, not for operations we merely haven't measured yet — measurement is
what the shadow rung is for.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from google.adk.apps import App, ResumabilityConfig
from google.adk.events.request_input import RequestInput
from google.adk.workflow import START, Workflow, node

from .authority import AuthorityLedger, Decision
from .effects import Actuator, Effect, EffectLog
from .world import VirtualWorld, verify


class RunState(BaseModel):
    """Typed session state. `@node` parameters are auto-bound from these fields."""

    goal: str = ""
    queue: list[dict] = Field(default_factory=list)     # proposed effects, as dicts
    cursor: int = 0
    decisions: list[dict] = Field(default_factory=list)
    outcomes: list[dict] = Field(default_factory=list)
    run_id: str = "run"


class Approval(BaseModel):
    approved: bool
    note: str = ""


# The runtime collaborators are injected once at build time rather than constructed
# inside nodes, so the whole graph can run in a test with in-memory doubles.
class Deps:
    def __init__(
        self,
        ledger: AuthorityLedger,
        actuator: Actuator,
        virtual: VirtualWorld,
        reader,
    ) -> None:
        self.ledger = ledger
        self.actuator = actuator
        self.virtual = virtual
        self.reader = reader


class Proposal(BaseModel):
    """What a model is allowed to say. Note what is absent: no post-conditions.

    The proposer names an operation and a target. It does not get to declare what
    success looks like — those come from the domain spec via `to_effect`. A model
    that writes its own success criteria will pass its own exam, and the entire
    verification story depends on the two being authored separately.
    """

    op_class: str
    target: str
    rationale: str = ""


def build_workflow(deps: Deps, propose, to_effect=None) -> Workflow:
    """Assemble the graph.

    `propose` is any node that fills `state["queue"]` — or, when `to_effect` is
    supplied, any node (including an `LlmAgent`) that emits a `Proposal`. The
    adapter in between is what lets the brain be swapped for a model without the
    machinery that decides whether it may act knowing or caring.

    `to_effect(op_class, target, run_id) -> dict` belongs to the domain, so this
    module stays domain-agnostic.
    """

    @node
    async def gate(ctx, queue: list, cursor: int):
        """Route this operation by the authority its class has earned."""
        if cursor >= len(queue):
            ctx.route = "done"
            yield {"route": "done", "operations": len(queue)}
            return

        effect = Effect(**queue[cursor])
        decision: Decision = deps.ledger.decide(effect.op_class, effect.shape)

        route = "shadow"
        if decision.commits:
            route = "consult" if not effect.reversible else "commit"

        ctx.state["decisions"] = list(ctx.state.get("decisions", [])) + [
            {
                "op_class": effect.op_class,
                "authority": decision.authority.label,
                "route": route,
                "reason": decision.reason,
                "in_envelope": decision.in_envelope,
            }
        ]
        # The routed edge is taken from ctx.route; the yielded value is just the
        # record of why, which is what the board renders.
        ctx.route = route
        yield {"route": route, "op_class": effect.op_class, "reason": decision.reason}

    @node
    async def rehearse(ctx, queue: list, cursor: int):
        """Run it against the virtualized world. Nothing is committed."""
        effect = Effect(**queue[cursor])
        delta, error = deps.virtual.rehearse(effect)
        verdict = (
            verify(effect, delta.before, delta.after)
            if not error
            else type("V", (), {"passed": False, "reason": error, "to_dict": lambda s: {"passed": False, "reason": error}})()
        )
        _observe(ctx, effect, verdict, committed=False)
        yield {"rehearsed": effect.op_class, "passed": verdict.passed, "reason": verdict.reason}

    @node(rerun_on_resume=False)
    async def approve(ctx, queue: list, cursor: int, node_input=None):
        """Ask a human — only for irreversible operations.

        `rerun_on_resume=False` makes the human's answer *become* this node's output,
        so resuming does not re-ask.
        """
        effect = Effect(**queue[cursor])
        yield RequestInput(
            interrupt_id=f"approve:{effect.key}",
            message=f"{effect.op_class} is irreversible. Approve?",
            response_schema=Approval,
            payload={"op_class": effect.op_class, "params": effect.params, "expect": effect.expect},
        )

    @node
    async def actuate(ctx, queue: list, cursor: int, node_input=None):
        """Commit for real, exactly once.

        `before` is read *here* rather than passed in, so a resumed invocation
        re-derives it instead of trusting stale state.
        """
        effect = Effect(**queue[cursor])

        if isinstance(node_input, dict) and node_input.get("approved") is False:
            _observe(ctx, effect, _refused("declined by operator"), committed=False)
            yield {"skipped": effect.op_class, "reason": "declined"}
            return

        before = deps.reader.observe(effect.op_class, effect.params)
        result = deps.actuator.commit(effect)
        after = deps.reader.observe(effect.op_class, effect.params)

        verdict = (
            verify(effect, before, after)
            if result.committed
            else _refused(result.error or "commit failed")
        )
        _observe(ctx, effect, verdict, committed=result.committed, replayed=result.replayed)
        yield {
            "committed": result.committed,
            "replayed": result.replayed,
            "passed": verdict.passed,
            "op_class": effect.op_class,
        }

    @node
    async def assess(ctx, queue: list, cursor: int):
        """Move the ratchet, then advance the cursor."""
        outcomes = list(ctx.state.get("outcomes", []))
        last = outcomes[-1] if outcomes else {}
        effect = Effect(**queue[cursor])
        record = deps.ledger.observe(
            effect.op_class, effect.shape, bool(last.get("passed")), last.get("reason", "")
        )
        ctx.state["cursor"] = cursor + 1
        yield {
            "op_class": effect.op_class,
            "authority": record.authority.label,
            "streak": record.streak,
            "note": record.last_reason,
        }

    @node
    async def report(ctx, decisions: list, outcomes: list, run_id: str = ""):
        # Release this run's rehearsal slice. It lives in the graph rather than in the
        # caller because forgetting it is silent and poisonous: the next run with the
        # same id rehearses against leftovers, every effect scores as a no-op, and the
        # operation can never earn anything. That failure has now happened twice, at
        # two different layers, which is argument enough for it to live here.
        deps.virtual.discard(run_id)

        committed = sum(1 for o in outcomes if o.get("committed"))
        passed = sum(1 for o in outcomes if o.get("passed"))
        yield {
            "operations": len(outcomes),
            "committed": committed,
            "verified_pass": passed,
            "board": [r.to_dict() for r in deps.ledger.board()],
        }

    @node
    async def intake(ctx, run_id: str, node_input=None):
        """Turn whatever the proposer said into a queue the gate can act on.

        This is the only place a model's output crosses into the machinery, so it is
        the only place that has to be suspicious. An unknown operation class is
        dropped rather than guessed at — a proposer that hallucinates a tool should
        produce an empty queue, not an unrecognised commit.
        """
        raw = node_input
        if hasattr(raw, "model_dump"):
            raw = raw.model_dump()
        if isinstance(raw, str):
            raw = _parse_lines(raw)

        op_class = (raw or {}).get("op_class", "").strip()
        target = (raw or {}).get("target", "").strip()

        try:
            effect = to_effect(op_class, target, run_id)
        except (KeyError, TypeError):
            ctx.state["queue"] = []
            ctx.state["cursor"] = 0
            yield {"accepted": False, "reason": f"unknown operation {op_class!r}", "proposed": raw}
            return

        ctx.state["queue"] = [effect]
        ctx.state["cursor"] = 0
        yield {"accepted": True, "op_class": op_class, "target": target,
               "rationale": (raw or {}).get("rationale", "")}

    head = [(START, propose), (propose, intake), (intake, gate)] if to_effect else [
        (START, propose), (propose, gate)
    ]

    return Workflow(
        name="ratchet",
        state_schema=RunState,
        edges=[
            *head,
            # The routed edge. It is also what legalises the cycle below.
            (gate, {"shadow": rehearse, "commit": actuate, "consult": approve, "done": report}),
            (rehearse, assess),
            (approve, actuate),
            (actuate, assess),
            (assess, gate),  # cycle: next operation
        ],
    )


def build_app(deps: Deps, propose, name: str = "ratchet", to_effect=None) -> App:
    return App(
        name=name,
        root_agent=build_workflow(deps, propose, to_effect),
        # Without this the approval interrupt cannot be resumed in a later call.
        resumability_config=ResumabilityConfig(is_resumable=True),
    )


# --------------------------------------------------------------------------- #

def _parse_lines(text: str) -> dict:
    """Read `OP: x` / `TARGET: y` lines out of a plain-text reply.

    A fallback for proposers without a structured output schema. Deliberately
    strict — anything it cannot read becomes an empty dict, which intake rejects.
    """
    out: dict[str, str] = {}
    for line in (text or "").splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip().lower()
        if key in ("op", "op_class"):
            out["op_class"] = value.strip()
        elif key == "target":
            out["target"] = value.strip()
        elif key == "rationale":
            out["rationale"] = value.strip()
    return out


def _refused(reason: str):
    from .world import Verdict

    return Verdict(passed=False, reason=reason)


def _observe(ctx, effect: Effect, verdict, committed: bool, replayed: bool = False) -> None:
    ctx.state["outcomes"] = list(ctx.state.get("outcomes", [])) + [
        {
            "op_class": effect.op_class,
            "key": effect.key,
            "committed": committed,
            "replayed": replayed,
            "passed": bool(getattr(verdict, "passed", False)),
            "reason": getattr(verdict, "reason", ""),
        }
    ]
