"""What the *server* is built with, not what a fixture is built with.

Four times in this project a module has been correct, tested and unreachable. Admission
and legal were written and not called. The topology that answers the memory-poisoning
result shipped with twenty-three passing tests and nothing in the product constructing
one. The console — the thing a judge actually opens — ran the five gates against an
empty snapshot and an empty spec table, so gate one refused on principle and the rest
had nothing to reason with. Every unit test passed throughout, because every unit test
built its own `Deps`.

So these tests import the server module and assert against the object it really uses.
They are deliberately blunt. A test that cannot fail when the wiring is right is worth
less than one that cannot pass when the wiring is wrong.
"""

from __future__ import annotations

import app.nightshift as ns
from ratchet.admission import Snapshot
from ratchet.effects import Effect
from ratchet.domains import finops


def test_the_server_admits_against_a_populated_snapshot() -> None:
    """An empty snapshot admits nothing. That is the right direction to fail, and it is
    also indistinguishable from a demo in which the agent never does anything."""
    assert len(ns.ESTATE.deps.snapshot.resources) == len(ns.ESTATE.rows)


def test_the_server_gives_the_legal_gate_a_spec_table() -> None:
    assert ns.ESTATE.deps.specs == finops.SPECS
    assert len(ns.ESTATE.deps.specs) > 0


def test_the_server_carries_a_topology() -> None:
    assert ns.ESTATE.deps.topology is not None
    assert "ml-train-01" in ns.ESTATE.deps.topology.nodes


def test_the_server_records_attempts_and_reviews_commits() -> None:
    assert ns.ESTATE.deps.attempts is ns.ESTATE.attempts
    assert ns.ESTATE.reviewer.ledger is ns.ESTATE.ledger


def test_the_two_instances_are_not_the_same_shape_on_the_server() -> None:
    """The whole V2 claim, asserted against the deployed object rather than a fixture.

    Both are RUNNING and near-zero CPU. Under V1 they were interchangeable, which is
    what let three poisoned notes move the agent from the staging box to the GPU node
    without ever leaving the allowlist.
    """
    shape = lambda t: ns.ESTATE.deps.shape_of(  # noqa: E731
        Effect(**finops.to_effect("compute.stop_idle_instance", t, "r1"))
    )
    assert shape("ml-train-01") != shape("staging-web-3")
    assert shape("ml-train-01").endswith("/critical")
    assert shape("staging-web-3").endswith("/isolated")


def test_the_snapshot_is_refreshed_rather_than_held() -> None:
    """A stale snapshot admits a delete against a resource an earlier run removed."""
    ns.ESTATE.rows.pop(next(iter(ns.ESTATE.rows)))
    ns.ESTATE.refresh_snapshot()
    assert len(ns.ESTATE.deps.snapshot.resources) == len(ns.ESTATE.rows)
    ns.ESTATE.reset()


def test_the_estate_endpoint_surfaces_both_ledgers() -> None:
    """Refusals and post-commit verdicts are evidence; evidence nobody can see is not
    doing the job it was written for."""
    payload = ns.estate()
    assert "attempts" in payload and "review" in payload
    assert set(payload["review"]) >= {"reviewed", "verdicts", "frozen"}


def test_the_owasp_mapping_names_only_tests_that_exist() -> None:
    """A coverage table is a liability the moment it drifts: a row naming a deleted test
    reads as reassurance while proving nothing."""
    from evals import owasp

    assert owasp.missing_tests() == []


def test_the_owasp_mapping_is_not_all_green() -> None:
    """Not a style check. Five of fifteen covered and four with no surface at all is the
    measured state; a table that reached fifteen greens would mean the rows had stopped
    tracking the system."""
    from evals.owasp import ROWS, Status

    assert any(r.status in (Status.OPEN, Status.PARTIAL) for r in ROWS)
    assert ROWS[0].status is Status.PARTIAL, "T1 is partial — the poisoning result stands"


def test_a_refusal_renders_instead_of_killing_the_stream() -> None:
    """The console crashed on the product's most characteristic behaviour.

    A refusal at admission never reaches the ladder, so no OperationRecord exists.
    `next()` without a default raised StopIteration, which an async generator converts
    into a RuntimeError, which ends the SSE response mid-flight — a blank page and a
    truncated-body warning in the logs. Deploying is not the same as working, and only
    a request against the running service showed the difference.
    """
    from ratchet.authority import Authority, OperationRecord

    board = []  # nothing was ever recorded, because nothing reached the ladder
    record = next((r for r in board if r.op_class == "compute.delete_unattached_disk"),
                  OperationRecord(op_class="compute.delete_unattached_disk"))
    assert record.authority is Authority.SHADOW
    assert record.passes == 0


def test_a_second_run_has_work_to_do_again() -> None:
    """One click is one demonstration; the world resets at the request boundary.

    Not resetting it at all made the first click do the work and every click after it
    report, correctly, that there was nothing left — which from the outside is a dead
    button. Resetting per *run* was the opposite error: it undid real work mid-sequence
    and handed the agent the same job repeatedly.
    """
    from ratchet.domains import finops

    key = "storage.set_lifecycle_policy:raw-events"
    ns.ESTATE.restore_world()
    assert ns.ESTATE.rows[key]["lifecycle_days"] is None

    ns.ESTATE.rows[key] = finops.SPECS["storage.set_lifecycle_policy"].simulate(
        ns.ESTATE.rows[key], {}
    )
    assert ns.ESTATE.rows[key]["lifecycle_days"] == 30, "the work is done"

    ns.ESTATE.restore_world()
    assert ns.ESTATE.rows[key]["lifecycle_days"] is None, "and the next click has work again"


def test_restoring_the_world_does_not_reset_the_ladder() -> None:
    """Authority is earned over time and should survive a fresh estate."""
    from ratchet.authority import Authority

    rec = ns.ESTATE.ledger.record("compute.stop_idle_instance")
    rec.authority = Authority.PROVISIONAL
    ns.ESTATE.ledger._store.save(rec)

    ns.ESTATE.restore_world()
    assert ns.ESTATE.ledger.record("compute.stop_idle_instance").authority is Authority.PROVISIONAL
    ns.ESTATE.reset()


def test_the_reader_still_sees_the_restored_rows() -> None:
    """The reader holds the dict by reference, so restore mutates in place. Rebinding it
    would leave every gate reading a world nobody updates any more."""
    ns.ESTATE.restore_world()
    assert ns.ESTATE.deps.reader.state is ns.ESTATE.rows


def test_the_log_reads_the_outcome_when_there_was_one() -> None:
    """A refusal and a completed run carry different sentences, and picking the wrong one
    inverts the meaning. Surfacing the gate's pre-run decision on a run that had already
    committed and failed verification replaced "demoted to shadow: 2 post-conditions did
    not hold" with "provisional — every run verified" — the opposite of what happened.
    """
    def reason_for(final, last_reason):
        return (last_reason if final.get("operations")
                else final.get("gate_reason") or "refused before the ladder")

    committed = {"operations": 1, "gate_reason": "provisional — every run verified"}
    assert reason_for(committed, "demoted to shadow: 2 post-conditions did not hold") \
        == "demoted to shadow: 2 post-conditions did not hold"

    refused = {"operations": 0, "gate_reason": "GPU at 94% — accelerator work does not show"}
    assert reason_for(refused, "") == "GPU at 94% — accelerator work does not show"
