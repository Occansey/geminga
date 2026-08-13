"""Tests for the plan state machine — the part that must not be wrong on stage.

These run without credentials: AGENT_STORE=memory swaps in the doubles.
"""

from __future__ import annotations

import os

os.environ.setdefault("AGENT_STORE", "memory")

import pytest

from agent_core.ports import Plan, Step
from agent_core.stores import MemoryPlanStore


@pytest.fixture
def plan() -> Plan:
    return Plan(
        session_id="t1",
        goal="Produce a summary",
        steps=[
            Step(id="s1", description="Gather sources"),
            Step(id="s2", description="Write summary"),
            Step(id="s3", description="Publish", side_effecting=True),
        ],
    )


def test_next_step_is_first_pending(plan: Plan) -> None:
    assert plan.next_step.id == "s1"
    plan.steps[0].state = "done"
    assert plan.next_step.id == "s2"


def test_running_steps_are_not_handed_out_again(plan: Plan) -> None:
    plan.steps[0].state = "running"
    assert plan.next_step.id == "s2"


def test_plan_incomplete_until_every_step_settles(plan: Plan) -> None:
    assert not plan.is_complete
    for step in plan.steps:
        step.state = "done"
    assert plan.is_complete


def test_failed_steps_still_count_as_settled(plan: Plan) -> None:
    plan.steps[0].state = "failed"
    plan.steps[1].state = "done"
    plan.steps[2].state = "done"
    assert plan.is_complete


def test_empty_plan_is_never_complete() -> None:
    assert not Plan(session_id="t2", goal="nothing").is_complete


def test_round_trip_through_store_preserves_state(plan: Plan) -> None:
    plan.steps[0].state = "done"
    plan.steps[0].result = "Found 4 sources"
    store = MemoryPlanStore()
    store.save(plan)

    loaded = store.load("t1")
    assert loaded.goal == "Produce a summary"
    assert loaded.steps[0].state == "done"
    assert loaded.steps[0].result == "Found 4 sources"
    assert loaded.steps[2].side_effecting is True


def test_side_effecting_flag_survives_serialisation(plan: Plan) -> None:
    assert Plan.from_dict(plan.to_dict()).steps[2].side_effecting is True
