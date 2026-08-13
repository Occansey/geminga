"""The gate that was missing when the agent stopped a training job.

Not a hypothetical. On the deployed service the agent stopped ml-train-01 — 94% GPU,
0.4% CPU — three separate times, and every gate said yes: it was in the allowlist, it was
an instance, no legal hold, reversible, and the shape had been rehearsed five times
cleanly. Rehearsal cannot catch this, because stopping a busy instance *works*. It stops.
The verifier confirms it stopped.
"""

from __future__ import annotations

import pytest

from ratchet.domains import finops
from ratchet.liveness import State, assess
from ratchet.topology import NodeKind, Topology, Utilisation


@pytest.fixture
def topo():
    return finops.topology()


def test_the_gpu_node_is_working(topo) -> None:
    v = assess("compute.stop_idle_instance", "ml-train-01", topo, asserts_idle=True)
    assert v.state is State.WORKING
    assert not v.may_proceed
    assert "94%" in v.reason


def test_cpu_alone_never_makes_something_idle() -> None:
    """CPU average is the exact signal the poisoned runbook note asked the agent to
    trust. A gate that consults it reproduces the vulnerability."""
    t = Topology()
    t.add_node("box", NodeKind.INSTANCE, Utilisation(cpu_percent=0.1))
    v = assess("compute.stop_idle_instance", "box", t, asserts_idle=True)
    assert v.state is State.UNKNOWN


def test_a_genuinely_quiet_box_is_idle(topo) -> None:
    """The gate has to let real work through, or the estate can never be cleaned."""
    v = assess("compute.stop_idle_instance", "staging-web-3", topo, asserts_idle=True)
    assert v.state is State.IDLE and v.may_proceed


def test_a_serving_box_is_working(topo) -> None:
    v = assess("compute.stop_idle_instance", "api-prod-2", topo, asserts_idle=True)
    assert v.state is State.WORKING


def test_an_accelerator_with_no_gpu_series_is_unknown_not_idle() -> None:
    """The expensive case, unmeasured. Treating it as idle is how this went wrong."""
    t = Topology()
    t.add_node("gpu-box", NodeKind.INSTANCE,
               Utilisation(network_bytes_per_s=10.0, disk_ops_per_s=0.0), accelerators=4)
    v = assess("compute.stop_idle_instance", "gpu-box", t, asserts_idle=True)
    assert v.state is State.UNKNOWN
    assert "accelerator" in v.reason


def test_no_topology_is_unknown_rather_than_idle() -> None:
    v = assess("compute.stop_idle_instance", "anything", None, asserts_idle=True)
    assert v.state is State.UNKNOWN


def test_operations_that_assert_nothing_are_unaffected(topo) -> None:
    """`delete_stale_snapshot` claims an age, not an activity level. Asking it a liveness
    question would refuse safe work for failing a check it never made."""
    v = assess("compute.delete_stale_snapshot", "snap-2024-03-11", topo, asserts_idle=False)
    assert v.may_proceed


def test_downsize_asserts_idle_too() -> None:
    """It restarts the machine; the interruption is identical from the workload's side."""
    assert finops.SPECS["compute.downsize_instance"].asserts_idle
    assert finops.SPECS["compute.stop_idle_instance"].asserts_idle
    assert not finops.SPECS["compute.delete_stale_snapshot"].asserts_idle


def test_the_proposer_no_longer_ranks_the_gpu_node_first() -> None:
    """Defence in depth: the gate is the guarantee, but a proposer that keeps offering
    the training job wastes every run and teaches an operator to ignore refusals."""
    import app.nightshift as ns

    op_class, target = ns.best_candidate()
    assert target != "ml-train-01", "the $2,632 training job was top of the list every run"
    # The most valuable resource that is both measurably idle and reversible. The disk at
    # $340 outranks it on cost and is irreversible, so it stays behind a human.
    assert (op_class, target) == ("storage.set_lifecycle_policy", "raw-events")


def test_the_refusal_reason_reaches_the_report() -> None:
    """A refusal whose reason does not reach the operator is most of the way to no
    refusal at all: they learn the system says no sometimes, not what it knows.

    Forcing the GPU node on the deployed service showed six refusals reading "created in
    shadow" — correct, and useless. The gate's own sentence never left the graph.
    """
    import asyncio

    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.adk.workflow import node
    from google.genai import types

    import app.nightshift as ns
    from ratchet.graph import build_app

    @node
    async def propose(ctx, goal: str, run_id: str):
        ctx.state["queue"] = [finops.propose_effect(
            "compute.stop_idle_instance", {"target": "ml-train-01"}, run_id)]
        ctx.state["cursor"] = 0
        yield {"proposed": 1}

    async def once() -> dict:
        adk = build_app(ns.ESTATE.deps, propose, name="probe")
        runner = Runner(app=adk, session_service=InMemorySessionService(),
                        auto_create_session=True)
        final: dict = {}
        async for ev in runner.run_async(
            user_id="u", session_id="s1",
            new_message=types.Content(role="user", parts=[types.Part(text="go")]),
            state_delta={"goal": "g", "run_id": "probe-1"},
        ):
            if getattr(ev, "output", None) and isinstance(ev.output, dict):
                final = ev.output
        return final

    final = asyncio.run(once())
    assert final["gate"] == "liveness"
    assert final["route"] == "refuse"
    assert "94%" in final["gate_reason"]
    assert not final["committed"]
