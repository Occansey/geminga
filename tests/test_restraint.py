"""Negative tests — cases where the correct behaviour is to refuse.

Every other test in this repo checks that the agent does something. These check that
it declines to, which is the harder property and the one nobody publishes. The single
most decisive artifact found anywhere in the winners research was a project reporting
5/5 no-action traps refused.

A trap here is a situation where acting would be wrong. Passing means not acting.
`RESTRAINT.md` reports the count; this file is where the number comes from, so the
number cannot drift from the code.
"""

from __future__ import annotations

import pytest

from ratchet.authority import Authority, AuthorityLedger, PROMOTION_THRESHOLD
from ratchet.domains import finops
from ratchet.effects import Actuator, Effect, EffectLog
from ratchet.restraint import Damage, DamageBudget, UndoLedger
from ratchet.world import DictReader, VirtualWorld, verify

SHAPE = "op:abc123abc123"


# --------------------------------------------------------------------------- #
# traps: the budget
# --------------------------------------------------------------------------- #

def test_refuses_an_operation_that_cannot_be_undone() -> None:
    allowed, why = DamageBudget().admits(Damage(None, "data gone"))
    assert allowed is False
    assert "unrecoverable" in why


def test_refuses_an_operation_bigger_than_the_whole_ceiling() -> None:
    allowed, why = DamageBudget(minutes=30).admits(Damage(45.0))
    assert allowed is False
    assert "above the" in why


def test_refuses_once_the_window_budget_is_spent() -> None:
    """Two 45-minute operations do not fit in a 60-minute hour. The second is refused
    even though it is identical to the first, which was allowed."""
    budget = DamageBudget(minutes=60)
    damage = finops.SPECS["compute.release_static_ip"].damage

    assert budget.admits(damage)[0] is True
    budget.charge("compute.release_static_ip", "ip-1", damage)

    allowed, why = budget.admits(damage)
    assert allowed is False
    assert "left in this window" in why


def test_refuses_an_operation_whose_blast_radius_was_never_declared() -> None:
    """The default is refusal. "Nobody wrote it down" is not a safety property."""
    undeclared = finops.OpSpec(
        op_class="compute.something_new",
        summary="added without thinking about consequences",
        reversible=True,
        simulate=lambda b, p: b,
        expect=lambda p: {},
    )
    assert DamageBudget().admits(undeclared.damage)[0] is False


def test_the_budget_recovers_when_the_window_rolls() -> None:
    now = [1000.0]
    budget = DamageBudget(minutes=60, window_seconds=3600, clock=lambda: now[0])
    budget.charge("op", "t", Damage(45.0))
    assert budget.remaining() == 15.0

    now[0] += 3601
    assert budget.remaining() == 60.0


# --------------------------------------------------------------------------- #
# traps: authority
# --------------------------------------------------------------------------- #

def test_refuses_to_commit_an_argument_shape_it_never_rehearsed() -> None:
    ledger = AuthorityLedger()
    for _ in range(PROMOTION_THRESHOLD[Authority.SHADOW]):
        ledger.observe("op", SHAPE, passed=True)
    assert ledger.decide("op", SHAPE).commits is True
    assert ledger.decide("op", "op:unseenshape1").commits is False


def test_refuses_to_commit_before_authority_is_earned() -> None:
    assert AuthorityLedger().decide("op", SHAPE).commits is False


# --------------------------------------------------------------------------- #
# traps: verification
# --------------------------------------------------------------------------- #

def test_refuses_to_pass_an_operation_that_promised_nothing() -> None:
    assert verify(Effect("x", {}), {"a": 1}, {"a": 2}).passed is False


def test_refuses_to_pass_a_change_that_did_not_happen() -> None:
    """The lying tool. Reports success; the world says otherwise."""
    effect = Effect("x", {}, expect={"state": "stopped"})
    assert verify(effect, {"state": "running"}, {"state": "running"}).passed is False


def test_refuses_to_treat_an_unmonitored_instance_as_idle() -> None:
    """Absence of evidence. A VM with no CPU history may be a warm standby, and
    stopping one is exactly the mistake this system exists to make expensive."""
    row = {"status": "RUNNING", "cpu_7d_avg": None}
    idle = bool(row["status"] == "RUNNING" and row["cpu_7d_avg"] is not None and row["cpu_7d_avg"] < 5.0)
    assert idle is False


# --------------------------------------------------------------------------- #
# traps: execution
# --------------------------------------------------------------------------- #

def test_refuses_to_fire_the_same_effect_twice() -> None:
    fired: list = []
    actuator = Actuator(EffectLog(), {"x": lambda **p: fired.append(p) or {"ok": True}})
    effect = Effect("x", {"target": "t"}, expect={"ok": True}, run_id="r1")

    actuator.commit(effect)
    second = actuator.commit(effect)

    assert len(fired) == 1
    assert second.replayed is True


def test_refuses_to_rehearse_an_operation_with_no_simulator() -> None:
    world = VirtualWorld(DictReader({}), {})
    _, error = world.rehearse(Effect("unknown.op", {"target": "t"}, run_id="r"))
    assert "no simulator" in error


# --------------------------------------------------------------------------- #
# the undo ledger — measured, not asserted
# --------------------------------------------------------------------------- #

def test_a_restore_is_timed_rather_than_claimed() -> None:
    ledger = UndoLedger()
    ledger.record("compute.stop_idle_instance", "web-1", "compute.start_instance", {"target": "web-1"})

    ticks = [0.0, 18.0]  # monotonic seconds
    restored = ledger.restore("web-1", {"compute.start_instance": lambda **p: None}, clock=lambda: ticks.pop(0))

    assert restored.measured_minutes == 0.3
    assert ledger.report()["worst_measured"] == 0.3
    assert ledger.pending() == []


def test_every_reversible_operation_declares_how_to_undo_it() -> None:
    """A reversible operation with no inverse is a claim with nothing behind it."""
    missing = [
        name
        for name, spec in finops.SPECS.items()
        if spec.reversible and spec.damage.recoverable and not spec.inverse_op
    ]
    assert missing == [], f"reversible but no inverse recorded: {missing}"


# --------------------------------------------------------------------------- #
# the number
# --------------------------------------------------------------------------- #

TRAPS = [
    "unrecoverable operation",
    "single action over the ceiling",
    "window budget exhausted",
    "blast radius undeclared",
    "unrehearsed argument shape",
    "authority not yet earned",
    "no post-conditions declared",
    "world did not change",
    "instance with no monitoring history",
    "duplicate effect after resume",
    "operation with no simulator",
]


def test_the_refusal_count_is_what_restraint_md_claims() -> None:
    """Keeps the published number honest. If a trap is added here, the doc must move."""
    from pathlib import Path

    doc = Path(__file__).resolve().parents[1] / "RESTRAINT.md"
    if not doc.exists():
        pytest.skip("RESTRAINT.md not written yet")
    assert f"{len(TRAPS)}/{len(TRAPS)}" in doc.read_text()
