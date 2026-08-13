"""Blast radius — what the worst case costs, and a budget that runs out.

The rubric asks for undeniable proof that the agent performs its task. It never asks
what happens when the agent is wrong. For something that deletes production
infrastructure, that is the omission that matters: an agent reclaiming $50k a month
which once destroys a production database is worth less than nothing, and it demos
*better* than a careful one, because it acts more impressively on camera.

So this module supplies the missing number.

**The unit is restore-minutes.** Not dollars, not bytes — how long it takes to get
back to where we were. It is the only currency in which a wrong deletion and a wrong
resize are commensurable, and it is measurable rather than asserted: for reversible
operations we record the inverse and actually time the restore.

**Unrecoverable operations have no finite restore time**, which is why they can never
fit inside any budget however large. That is not a separate rule bolted on; it falls
out of the arithmetic.

Two properties that look like one and are not:

- `reversible` — is there an exact inverse? Stopping an instance has one; releasing a
  static IP does not, because the address returns to the pool and someone else may
  take it.
- `restore_minutes` — what does reaching an equivalent working state cost? Finite even
  for some operations that have no inverse: reserve a different address, repoint DNS.

Conflating them let `release_static_ip` commit without a human, because it *felt*
undoable. It is recoverable at cost, which is a different and weaker thing.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# Restore-minutes the fleet may place at risk within a rolling window. Deliberately
# small: this is not a throughput target, it is a ceiling on how much undoing a bad
# hour can require. An operator raising it is making a decision they can be asked about.
DEFAULT_BUDGET_MINUTES = 60.0
DEFAULT_WINDOW_SECONDS = 3600.0


@dataclass(frozen=True)
class Damage:
    """The declared worst case for one operation class.

    `restore_minutes = None` means unrecoverable — no budget accommodates it, at any
    size. Declaring it is mandatory: an operation whose blast radius nobody wrote down
    is refused, because "we never thought about it" is not a safety property.
    """

    restore_minutes: float | None
    description: str = ""

    @property
    def recoverable(self) -> bool:
        return self.restore_minutes is not None

    def to_dict(self) -> dict:
        return {
            "restore_minutes": self.restore_minutes,
            "recoverable": self.recoverable,
            "description": self.description,
        }


@dataclass
class Spend:
    op_class: str
    target: str
    minutes: float
    at: float = field(default_factory=time.time)


class DamageBudget:
    """A rolling ceiling on recoverable damage in flight.

    Refusing when the budget is spent is a *feature being exercised*, not an outage.
    A fleet that never hits its ceiling has a ceiling set too high to mean anything.
    """

    def __init__(
        self,
        minutes: float = DEFAULT_BUDGET_MINUTES,
        window_seconds: float = DEFAULT_WINDOW_SECONDS,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.ceiling = minutes
        self.window = window_seconds
        self._clock = clock
        self._spends: list[Spend] = []

    def _live(self) -> list[Spend]:
        cutoff = self._clock() - self.window
        self._spends = [s for s in self._spends if s.at >= cutoff]
        return self._spends

    def spent(self) -> float:
        return round(sum(s.minutes for s in self._live()), 2)

    def remaining(self) -> float:
        return round(max(0.0, self.ceiling - self.spent()), 2)

    def admits(self, damage: Damage) -> tuple[bool, str]:
        """Would this operation fit? Returns (allowed, reason)."""
        if not damage.recoverable:
            return False, "unrecoverable — no budget admits an operation that cannot be undone"
        assert damage.restore_minutes is not None
        if damage.restore_minutes > self.ceiling:
            return False, (
                f"needs {damage.restore_minutes:g} restore-minutes, "
                f"above the {self.ceiling:g}-minute ceiling for any single action"
            )
        if damage.restore_minutes > self.remaining():
            return False, (
                f"needs {damage.restore_minutes:g} restore-minutes, "
                f"{self.remaining():g} left in this window"
            )
        return True, f"{damage.restore_minutes:g} of {self.remaining():g} restore-minutes"

    def charge(self, op_class: str, target: str, damage: Damage) -> None:
        if damage.recoverable:
            assert damage.restore_minutes is not None
            self._spends.append(
                Spend(op_class, target, damage.restore_minutes, self._clock())
            )

    def report(self) -> dict:
        return {
            "ceiling_minutes": self.ceiling,
            "window_seconds": self.window,
            "spent_minutes": self.spent(),
            "remaining_minutes": self.remaining(),
            "actions_in_window": len(self._live()),
        }


# --------------------------------------------------------------------------- #
# undo
# --------------------------------------------------------------------------- #

@dataclass
class Undo:
    """How to put a reversible operation back, and what it cost to do so."""

    op_class: str
    target: str
    inverse_op: str
    params: dict[str, Any]
    at: float = field(default_factory=time.time)
    restored_at: float | None = None
    measured_minutes: float | None = None

    def to_dict(self) -> dict:
        return {
            "op_class": self.op_class,
            "target": self.target,
            "inverse_op": self.inverse_op,
            "restored": self.restored_at is not None,
            "measured_minutes": self.measured_minutes,
        }


class UndoLedger:
    """Records the inverse of every reversible commit, and times real restores.

    The measured number is the point. "Reversible" as an adjective is a claim; a
    restore that ran in 0.4 minutes is evidence. Declared restore-minutes that never
    get checked against a measurement are just optimism with a unit attached.
    """

    def __init__(self) -> None:
        self._entries: list[Undo] = []

    def record(self, op_class: str, target: str, inverse_op: str, params: dict) -> Undo:
        entry = Undo(op_class, target, inverse_op, dict(params))
        self._entries.append(entry)
        return entry

    def restore(self, target: str, tools: dict[str, Callable], clock=time.monotonic) -> Undo | None:
        """Run the most recent inverse for a target and *measure* how long it took."""
        entry = next((e for e in reversed(self._entries) if e.target == target and not e.restored_at), None)
        if entry is None:
            return None
        tool = tools.get(entry.inverse_op)
        if tool is None:
            return entry
        start = clock()
        tool(**entry.params)
        entry.measured_minutes = round((clock() - start) / 60.0, 4)
        entry.restored_at = time.time()
        return entry

    def pending(self) -> list[Undo]:
        return [e for e in self._entries if e.restored_at is None]

    def measurements(self) -> list[float]:
        return [e.measured_minutes for e in self._entries if e.measured_minutes is not None]

    def report(self) -> dict:
        measured = self.measurements()
        return {
            "recorded": len(self._entries),
            "restored": len([e for e in self._entries if e.restored_at]),
            "measured_restore_minutes": measured,
            "worst_measured": max(measured) if measured else None,
        }
