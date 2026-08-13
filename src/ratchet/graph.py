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

from google.adk.apps import App, ResumabilityConfig
from google.adk.events.request_input import RequestInput
from google.adk.workflow import START, Workflow, node
from pydantic import BaseModel, Field

from .admission import Snapshot, admit, resource_type_of
from .authority import AuthorityLedger, Decision
from .effects import Actuator, Effect
from .legal import EscalationQueue, HoldRegister, assess
from .restraint import DamageBudget, UndoLedger
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
        *,
        snapshot: Snapshot | None = None,
        holds: HoldRegister | None = None,
        budget: DamageBudget | None = None,
        escalations: EscalationQueue | None = None,
        undo: UndoLedger | None = None,
        specs: dict | None = None,
    ) -> None:
        self.ledger = ledger
        self.actuator = actuator
        self.virtual = virtual
        self.reader = reader
        # The five gates need five sources of truth. Defaulting them keeps the
        # constructor usable in tests, but an empty snapshot admits nothing — which
        # is the right failure direction for a gate.
        self.snapshot = snapshot or Snapshot(frozenset(), "empty")
        self.holds = holds or HoldRegister()
        self.budget = budget or DamageBudget()
        self.escalations = escalations or EscalationQueue()
        self.undo = undo or UndoLedger()
        self.specs = specs or {}

    def spec(self, op_class: str):
        return self.specs.get(op_class)


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
        """Five gates, in order of how absolute they are.

        Cheapest and most categorical first, so a refusal costs nothing and the reason
        returned is the most fundamental one true of this proposal. An operation that
        fails admission is never assessed for legal hold — there is no point asking
        whether we may delete something that was never a real proposal.
        """
        if cursor >= len(queue):
            ctx.route = "done"
            yield {"route": "done", "operations": len(queue)}
            return

        effect = Effect(**queue[cursor])
        spec = deps.spec(effect.op_class)
        target = str(effect.params.get("target", ""))
        record: dict = {"op_class": effect.op_class, "target": target}

        def settle(route: str, gate_name: str, reason: str, **extra):
            record.update({"route": route, "gate": gate_name, "reason": reason, **extra})
            ctx.state["decisions"] = list(ctx.state.get("decisions", [])) + [record]
            ctx.route = route
            return {"route": route, "gate": gate_name, **record}

        # 1 — admission. Assumes the proposer was hijacked.
        verdict = admit(
            effect.op_class, target, deps.snapshot,
            claimed_saving_usd=float(effect.params.get("claimed_saving_usd", 0.0)),
        )
        if not verdict.allowed:
            yield settle("refuse", "admission", verdict.reason, check=verdict.check)
            return

        # 2 — legal. Three-valued; hold and unknown both escalate, with a clock.
        row = deps.reader.observe(effect.op_class, effect.params) or {}
        resource_type = resource_type_of(effect.op_class)
        legal = assess(target, resource_type, row, deps.holds,
                       destroys_data=bool(spec and spec.destroys_data))
        if not legal.may_delete:
            deps.escalations.raise_for(target, legal)
            yield settle("escalate", "legal", legal.reason, state=legal.state.value)
            return

        # 3 — reversibility. A property of the operation, never of confidence.
        if not effect.reversible:
            yield settle("consult", "reversibility", "irreversible — a human decides, at every rung")
            return

        # 4 — authority. The only earned gate.
        decision: Decision = deps.ledger.decide(effect.op_class, effect.shape)
        if not decision.commits:
            yield settle(
                "shadow", "authority", decision.reason,
                authority=decision.authority.label, in_envelope=decision.in_envelope,
            )
            return

        # 5 — blast radius. Consumable, and it refuses when the window is spent.
        if spec is not None:
            allowed, why = deps.budget.admits(spec.damage)
            if not allowed:
                yield settle("refuse", "blast-radius", why)
                return

        yield settle(
            "commit", "admitted", decision.reason, authority=decision.authority.label
        )

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

        spec = deps.spec(effect.op_class)
        if result.committed and spec is not None:
            # Charge the budget and record how to undo it, in that order: a commit
            # that is not charged is a commit the ceiling cannot see.
            deps.budget.charge(effect.op_class, str(effect.params.get("target", "")), spec.damage)
            if spec.inverse_op:
                deps.undo.record(
                    effect.op_class, str(effect.params.get("target", "")),
                    spec.inverse_op, effect.params,
                )

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
    async def settle_ratchet(ctx, queue: list, cursor: int):
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
    async def refuse(ctx, decisions: list | None = None):
        """A refusal is an outcome, not an error. It is recorded and counted."""
        last = (decisions or [])[-1] if decisions else {}
        yield {"refused": last.get("op_class"), "gate": last.get("gate"), "reason": last.get("reason")}

    @node
    async def escalate(ctx, decisions: list | None = None):
        last = (decisions or [])[-1] if decisions else {}
        yield {
            "escalated": last.get("target"),
            "reason": last.get("reason"),
            "open": deps.escalations.report()["open"],
        }

    @node
    async def report(ctx, decisions: list | None = None, outcomes: list | None = None, run_id: str = ""):
        # Release this run's rehearsal slice. It lives in the graph rather than in the
        # caller because forgetting it is silent and poisonous: the next run with the
        # same id rehearses against leftovers, every effect scores as a no-op, and the
        # operation can never earn anything. That failure has now happened twice, at
        # two different layers, which is argument enough for it to live here.
        deps.virtual.discard(run_id)

        outcomes = outcomes or []
        decisions = decisions or []
        committed = sum(1 for o in outcomes if o.get("committed"))
        passed = sum(1 for o in outcomes if o.get("passed"))
        yield {
            "refusals": sum(1 for d in decisions if d.get("route") in ("refuse", "escalate")),
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

    @node
    async def advance(ctx, cursor: int):
        """Refusals and escalations still move the cursor — otherwise the graph
        re-proposes the operation it just declined, forever."""
        ctx.state["cursor"] = cursor + 1
        yield {"cursor": cursor + 1}

    return Workflow(
        name="ratchet",
        state_schema=RunState,
        edges=[
            *head,
            # The routed edge. It is also what legalises the cycle below.
            (gate, {
                "shadow": rehearse,
                "commit": actuate,
                "consult": approve,
                "refuse": refuse,
                "escalate": escalate,
                "done": report,
            }),
            (rehearse, settle_ratchet),
            (approve, actuate),
            (actuate, settle_ratchet),
            (refuse, advance),
            (escalate, advance),
            (settle_ratchet, gate),   # cycle: next operation
            (advance, gate),
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
