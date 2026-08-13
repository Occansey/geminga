"""What was tried and refused — recorded, deliberately not learned from.

Until now the system had no memory of being attacked. A refusal wrote to per-run state
and vanished; `ledger.observe()` only ever saw rehearsals and commits. The poison could
run a thousand times and the thousand-and-first attempt was treated exactly like the
first. That is a real gap, and this closes it.

## Why recording is not the same as learning

The obvious next step — feed refusals back so the gates get smarter — is a trap, and it
is worth being explicit about why we are not taking it.

**A gate that learns from attacks is a gate an attacker can train.** Every adaptive
component is a channel: generate refusals in a chosen pattern and you shape the policy
that judges you. The entire architectural bet is that the gates are deterministic, which
is what makes the defence indifferent to attacker query budget in a way a classifier
never is. Making them adaptive would hand back exactly the surface we removed, and it is
how twelve published defences that reported near-zero attack success ended up broken
above 90%.

So the rule here is the same one that governs forgeable edges in `topology.py`:

> **Attack history may raise scrutiny. It may never lower it.**

Concretely: sustained refusals against a target push its operations *back* toward
rehearsal. Nothing an attacker can do makes the system more permissive, because there is
no path from this module to a wider grant. The worst an attacker achieves by hammering
the gates is that the agent becomes more cautious — which is a denial-of-service against
their own goal.

## What it is actually for

Audit and forensics first: an organisation needs to be able to answer "did anyone try?"
Then rate limiting, which is cheap, deterministic and safe. And finally as a signal to
the *proposer's* context — advisory only, never binding, and it cannot reach a gate.
"""

from __future__ import annotations

import time
from collections import Counter
from dataclasses import asdict, dataclass, field

# Refusals against one target within the window before its operations are pushed back to
# rehearsal. Low on purpose: this is a tripwire, not a threshold to be tuned.
PRESSURE_LIMIT = 5
PRESSURE_WINDOW_S = 3600.0


@dataclass(frozen=True)
class Attempt:
    """One proposal that did not become an action, and the gate that stopped it."""

    op_class: str
    target: str
    gate: str
    check: str
    reason: str = ""
    run_id: str = ""
    at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)


class AttemptLedger:
    """Append-only. Nothing in this class removes or amends a record.

    An audit trail an agent can edit is an audit trail, and the agent is the thing being
    audited.
    """

    def __init__(self, clock=time.time) -> None:
        self._rows: list[Attempt] = []
        self._clock = clock

    def record(self, attempt: Attempt) -> Attempt:
        self._rows.append(attempt)
        return attempt

    def all(self) -> list[Attempt]:
        return list(self._rows)

    def since(self, seconds: float) -> list[Attempt]:
        cutoff = self._clock() - seconds
        return [a for a in self._rows if a.at >= cutoff]

    # -- signals ---------------------------------------------------------- #

    def pressure(self, target: str, window: float = PRESSURE_WINDOW_S) -> int:
        """How many refusals this target has drawn recently.

        A target nobody is pushing on has none. A target under sustained attempt has a
        number, and that number is evidence about the estate rather than about the agent.
        """
        return sum(1 for a in self.since(window) if a.target == target)

    def under_pressure(self, target: str, window: float = PRESSURE_WINDOW_S) -> bool:
        return self.pressure(target, window) >= PRESSURE_LIMIT

    def force_rehearsal(self, target: str) -> bool:
        """Should this target's operations be pushed back to shadow?

        The only response this module is permitted to produce. There is deliberately no
        counterpart that widens anything: an attacker who hammers the gates makes the
        agent more cautious, never less, so the effort is a denial-of-service against
        their own objective.
        """
        return self.under_pressure(target)

    def report(self) -> dict:
        recent = self.since(PRESSURE_WINDOW_S)
        return {
            "recorded": len(self._rows),
            "in_window": len(recent),
            "by_gate": dict(Counter(a.gate for a in recent)),
            "by_target": dict(Counter(a.target for a in recent).most_common(5)),
            "under_pressure": sorted(
                {a.target for a in recent if self.under_pressure(a.target)}
            ),
        }
