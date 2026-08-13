"""Attack memory — recorded, deliberately not learned from.

The distinction these tests defend: attempts are persisted for audit and for one
narrow, safe response, and there is no path from this module to a wider grant. A gate
that learns from attacks is a gate an attacker can train.
"""

from __future__ import annotations

from ratchet.attempts import PRESSURE_LIMIT, Attempt, AttemptLedger


def _ledger(now):
    return AttemptLedger(clock=lambda: now[0])


def test_a_refused_attempt_is_remembered() -> None:
    """The gap this closed: refusals used to write to per-run state and vanish, so the
    thousandth poison attempt was treated exactly like the first."""
    led = AttemptLedger()
    led.record(Attempt("compute.delete_unattached_disk", "pd-1", "admission", "not-in-snapshot"))
    assert len(led.all()) == 1
    assert led.pressure("pd-1") == 1
    assert led.pressure("something-else") == 0


def test_sustained_pressure_pushes_a_target_back_to_rehearsal() -> None:
    now = [1_000_000.0]
    led = _ledger(now)
    for _ in range(PRESSURE_LIMIT - 1):
        led.record(Attempt("op", "ml-train-01", "admission", "type-mismatch", at=now[0]))
    assert led.force_rehearsal("ml-train-01") is False

    led.record(Attempt("op", "ml-train-01", "admission", "type-mismatch", at=now[0]))
    assert led.force_rehearsal("ml-train-01") is True


def test_pressure_decays_so_an_old_campaign_does_not_freeze_the_estate() -> None:
    now = [1_000_000.0]
    led = _ledger(now)
    for _ in range(PRESSURE_LIMIT + 3):
        led.record(Attempt("op", "t", "legal", "unknown", at=now[0]))
    assert led.force_rehearsal("t") is True

    now[0] += 3601
    assert led.force_rehearsal("t") is False, "a tripwire that never resets is a broken estate"


def test_the_ledger_offers_no_way_to_widen_anything() -> None:
    """The load-bearing property. If a future change adds a method that lowers scrutiny,
    this fails — and it should, loudly, because that is the reward-hacking channel."""
    surface = {m for m in dir(AttemptLedger) if not m.startswith("_")}
    assert surface == {"record", "all", "since", "pressure", "under_pressure",
                       "force_rehearsal", "report"}


def test_the_ledger_is_append_only() -> None:
    """An audit trail the agent can edit is not an audit trail, and the agent is the
    thing being audited."""
    led = AttemptLedger()
    led.record(Attempt("op", "t", "admission", "x"))
    assert not any(m in dir(led) for m in ("delete", "remove", "clear", "amend", "purge"))
    assert len(led.all()) == 1


def test_the_gate_writes_refusals_to_the_ledger() -> None:
    """The wiring, not the module — the mistake this project has now made three times."""
    from ratchet.admission import Snapshot
    from ratchet.authority import AuthorityLedger
    from ratchet.domains import finops
    from ratchet.effects import Actuator, EffectLog
    from ratchet.graph import Deps
    from ratchet.world import DictReader, VirtualWorld

    estate = finops.sample_estate()
    reader = DictReader(estate)
    attempts = AttemptLedger()
    deps = Deps(AuthorityLedger(), Actuator(EffectLog(), {}),
                VirtualWorld(reader, finops.simulators()), reader,
                snapshot=Snapshot.of(estate), specs=finops.SPECS, attempts=attempts)
    assert deps.attempts is attempts
    assert attempts.report()["recorded"] == 0
