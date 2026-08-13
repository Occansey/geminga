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
