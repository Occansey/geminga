"""The world: how we observe it, rehearse against it, and check what we did to it.

Three jobs, deliberately in one place because they must agree on what "state" means:

1. **Observe** — read the real environment. Plain reads, no model involved.
2. **Rehearse** — run an effect against a virtualized copy and record the delta it
   predicts. This is Google's own Agent Simulation pattern (GEAP, 22 Apr 2026):
   synthetic environment, virtualized tools, nothing committed.
3. **Verify** — after a real commit, observe again and check the delta that actually
   happened against the one that was predicted.

Verification re-derives environment state. It does not ask a model whether things
went well. A static LLM judge is reward-hackable, and here the thing being judged is
authored by the same system that would be judging it.
"""

from __future__ import annotations

import copy
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Protocol

from .effects import Effect


class WorldReader(Protocol):
    """Reads the slice of the world an operation class touches."""

    def observe(self, op_class: str, params: dict[str, Any]) -> dict[str, Any]: ...


@dataclass
class Delta:
    before: dict[str, Any]
    after: dict[str, Any]

    @property
    def changed(self) -> dict[str, tuple[Any, Any]]:
        keys = set(self.before) | set(self.after)
        return {
            k: (self.before.get(k), self.after.get(k))
            for k in sorted(keys)
            if self.before.get(k) != self.after.get(k)
        }

    def to_dict(self) -> dict:
        return {"before": self.before, "after": self.after, "changed": self.changed}


@dataclass
class Verdict:
    passed: bool
    reason: str
    expected: dict[str, Any] = field(default_factory=dict)
    observed: dict[str, Any] = field(default_factory=dict)
    mismatches: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "reason": self.reason,
            "expected": self.expected,
            "observed": self.observed,
            "mismatches": self.mismatches,
        }


# --------------------------------------------------------------------------- #
# rehearsal
# --------------------------------------------------------------------------- #

@dataclass
class FaultProfile:
    """Deliberate unreliability, for rehearsal and for the demo.

    ADK ships `tools.environment_simulation` which injects latency and HTTP errors by
    probability. This is the same idea kept local so it also works in a unit test:
    an operation class that only ever rehearsed against a perfect world has not
    earned anything.
    """

    error_rate: float = 0.0
    error: type[Exception] = RuntimeError
    seed: int | None = None

    def maybe_fail(self, rng: random.Random) -> None:
        if self.error_rate and rng.random() < self.error_rate:
            raise self.error("injected fault")


class DictReader:
    """A `WorldReader` over a plain dict. Used by tests and the local demo."""

    def __init__(self, state: dict[str, dict[str, Any]]) -> None:
        self.state = state

    def observe(self, op_class: str, params: dict[str, Any]) -> dict[str, Any]:
        return copy.deepcopy(self.state.get(scope_of(op_class, params), {}))


def scope_of(op_class: str, params: dict[str, Any]) -> str:
    """Which slice of the world an operation touches."""
    return f"{op_class}:{params.get('target', params.get('name', '*'))}"


class VirtualWorld:
    """A per-run copy of the world that effects may be applied to without consequence.

    Scoped by `run_id`, and that scoping is load-bearing. A multi-step plan must see
    its own earlier rehearsals — step three has to be simulated against the world
    step two would have produced. But the *next* run must start from the real world
    again, or the second rehearsal of the same operation sees its own leftovers,
    reads as a no-op, and the operation can never earn anything.

    (That bug was live in the first draft and only surfaced on an end-to-end run:
    the streak reset on every run and nothing ever left shadow. Unit tests on a single
    rehearsal would not have caught it.)
    """

    def __init__(
        self,
        reader: WorldReader,
        simulators: dict[str, Callable[[dict, dict], dict]],
        faults: FaultProfile | None = None,
    ) -> None:
        self._reader = reader
        self._simulators = simulators
        self._faults = faults or FaultProfile()
        self._rng = random.Random(self._faults.seed)
        self._runs: dict[str, dict[str, dict[str, Any]]] = {}

    def _slice(self, run_id: str, op_class: str, params: dict[str, Any]) -> tuple[str, dict]:
        scope = scope_of(op_class, params)
        run = self._runs.setdefault(run_id, {})
        if scope not in run:
            run[scope] = copy.deepcopy(self._reader.observe(op_class, params))
        return scope, run

    def observe(self, op_class: str, params: dict[str, Any], run_id: str = "") -> dict[str, Any]:
        scope, run = self._slice(run_id, op_class, params)
        return copy.deepcopy(run[scope])

    def rehearse(self, effect: Effect) -> tuple[Delta, str]:
        """Apply the effect to this run's copy. Returns the predicted delta, or an error."""
        simulate = self._simulators.get(effect.op_class)
        if simulate is None:
            return Delta({}, {}), f"no simulator for {effect.op_class!r}"

        scope, run = self._slice(effect.run_id, effect.op_class, effect.params)
        before = copy.deepcopy(run[scope])
        try:
            self._faults.maybe_fail(self._rng)
            after = simulate(copy.deepcopy(before), dict(effect.params))
        except Exception as exc:  # noqa: BLE001 — a simulator is domain code and may
            # raise anything, including the deliberately injected FaultProfile error.
            # A rehearsal that blows up is a *failed rehearsal*, which the ladder must
            # see as evidence; letting it propagate would skip the ratchet entirely.
            return Delta(before, before), f"{type(exc).__name__}: {exc}"

        run[scope] = after
        return Delta(before, after), ""

    def discard(self, run_id: str) -> None:
        self._runs.pop(run_id, None)


# --------------------------------------------------------------------------- #
# verification
# --------------------------------------------------------------------------- #

def verify(effect: Effect, before: dict[str, Any], after: dict[str, Any]) -> Verdict:
    """Did the world actually change the way the effect said it would?

    Every key in `effect.expect` must hold in the observed after-state. Silence is not
    success: an effect that predicts nothing cannot pass, because an operation whose
    outcome is unspecified is one we can never earn authority for.
    """
    if not effect.expect:
        return Verdict(
            passed=False,
            reason="effect declared no expected post-conditions — nothing to verify",
            expected={},
            observed=after,
        )

    mismatches = [
        f"{key}: expected {value!r}, observed {after.get(key)!r}"
        for key, value in effect.expect.items()
        if after.get(key) != value
    ]

    if mismatches:
        return Verdict(
            passed=False,
            reason=f"{len(mismatches)} post-condition(s) did not hold",
            expected=effect.expect,
            observed=after,
            mismatches=mismatches,
        )

    if before == after:
        return Verdict(
            passed=False,
            reason="post-conditions matched but nothing changed — the effect was a no-op",
            expected=effect.expect,
            observed=after,
        )

    return Verdict(
        passed=True,
        reason="all post-conditions hold and the world changed",
        expected=effect.expect,
        observed=after,
    )
