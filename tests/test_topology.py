"""Tests for the dependency topology.

The one that matters is `test_the_gpu_node_and_the_spare_box_are_not_the_same_shape`.
V1's measured gap (CLAIMS.md §1) is that `compute.stop_idle_instance` on
`staging-web-3` and on `ml-train-01` share an argument shape, so authority earned on
the spare box transfers to the GPU node. If that test ever passes trivially — if the
two shapes converge again — the V2 thesis is false and the poison works.

Like the rest of the suite these run with no credentials: `topology` imports nothing
from ADK or Google Cloud at module scope.
"""

from __future__ import annotations

import pytest

from ratchet.authority import PROMOTION_THRESHOLD, Authority, AuthorityLedger
from ratchet.topology import (
    BlastClass,
    Edge,
    EdgeKind,
    NodeKind,
    Topology,
    Utilisation,
    blast_shape,
)

STOP = "compute.stop_idle_instance"

# Telemetry that says "measured, and there is nothing happening" — as distinct from
# "we did not look", which is a different answer with a different class.
QUIET = Utilisation(gpu_percent=0.0, network_bytes_per_s=40.0, disk_ops_per_s=0.0, cpu_percent=0.1)


@pytest.fixture
def estate() -> Topology:
    """The two machines from the poison run, plus the wiring that separates them.

    `ml-train-01` holds a GPU that is actually training and sits in an instance group
    behind a backend service. `staging-web-3` is a spare box: nothing points at it and
    every series we can read is flat. Both cost money, both are RUNNING, both have a
    near-zero CPU average — which is exactly why CPU alone could not tell them apart.
    """
    topo = Topology()
    topo.add_node(
        "ml-train-01",
        NodeKind.INSTANCE,
        utilisation=Utilisation(
            gpu_percent=78.4, network_bytes_per_s=4_200_000.0,
            disk_ops_per_s=310.0, cpu_percent=0.4,
        ),
        accelerators=1,
    )
    topo.add_node("staging-web-3", NodeKind.INSTANCE, utilisation=QUIET)
    topo.add_node("ml-pool", NodeKind.INSTANCE_GROUP)
    topo.add_node("training-frontend", NodeKind.BACKEND_SERVICE)
    topo.add_edge(Edge("ml-pool", "ml-train-01", EdgeKind.INSTANCE_GROUP_MEMBERSHIP))
    topo.add_edge(Edge("training-frontend", "ml-pool", EdgeKind.LOAD_BALANCER_BACKEND))
    return topo


# --------------------------------------------------------------------------- #
# the thesis
# --------------------------------------------------------------------------- #

def test_the_gpu_node_and_the_spare_box_are_not_the_same_shape(estate: Topology) -> None:
    """V2 in one assertion. Under V1's `fingerprint` these two are identical."""
    from ratchet.effects import fingerprint

    assert fingerprint(STOP, {"target": "ml-train-01"}) == fingerprint(
        STOP, {"target": "staging-web-3"}
    ), "precondition: V1 cannot tell these apart"

    assert blast_shape(STOP, "ml-train-01", estate) != blast_shape(
        STOP, "staging-web-3", estate
    )
    assert estate.blast_class("ml-train-01") is BlastClass.CRITICAL
    assert estate.blast_class("staging-web-3") is BlastClass.ISOLATED


def test_authority_earned_on_the_spare_box_does_not_reach_the_gpu_node(estate: Topology) -> None:
    """The poison, replayed against the ladder with no change to `authority.py`.

    Five clean rehearsals against `staging-web-3` used to hand over `ml-train-01`.
    Now the GPU node is simply a shape the class has never rehearsed, and the ledger's
    existing envelope branch routes it back to shadow.
    """
    ledger = AuthorityLedger()
    spare = blast_shape(STOP, "staging-web-3", estate)
    gpu = blast_shape(STOP, "ml-train-01", estate)

    for _ in range(PROMOTION_THRESHOLD[Authority.SHADOW]):
        ledger.observe(STOP, spare, passed=True)

    assert ledger.decide(STOP, spare).commits is True
    poisoned = ledger.decide(STOP, gpu)
    assert poisoned.commits is False
    assert poisoned.in_envelope is False
    assert "unrehearsed" in poisoned.reason


def test_trust_still_generalises_within_a_class(estate: Topology) -> None:
    """The counterweight, and ROADMAP's second falsification criterion: if every
    resource got its own shape, the ladder would never promote and we would have
    bought safety with paralysis."""
    estate.add_node("staging-web-4", NodeKind.INSTANCE, utilisation=QUIET)
    assert blast_shape(STOP, "staging-web-3", estate) == blast_shape(
        STOP, "staging-web-4", estate
    )


# --------------------------------------------------------------------------- #
# forgeable edges
# --------------------------------------------------------------------------- #

def test_a_forgeable_edge_cannot_lower_a_blast_class(estate: Topology) -> None:
    """An attacker labelling the GPU node `env=scratch` changes nothing."""
    before = estate.blast_class("ml-train-01")
    estate.add_edge(Edge("label:env=scratch", "ml-train-01", EdgeKind.LABEL))
    estate.add_edge(Edge("description:ml-train-01", "ml-train-01", EdgeKind.DESCRIPTION))
    estate.add_edge(Edge("name:ml-train-01", "ml-train-01", EdgeKind.RESOURCE_NAME))
    assert estate.blast_class("ml-train-01") is before is BlastClass.CRITICAL


def test_a_forgeable_edge_may_still_raise_a_class(estate: Topology) -> None:
    """Forgeable evidence is one-directional, not worthless: a DNS record pointing at
    the spare box is a reason to be more careful, never less."""
    assert estate.blast_class("staging-web-3") is BlastClass.ISOLATED
    estate.add_edge(Edge("dns:www.example.com", "staging-web-3", EdgeKind.DNS_RECORD))
    assert estate.blast_class("staging-web-3") > BlastClass.ISOLATED


def test_an_edge_kind_that_is_forgeable_cannot_be_declared_otherwise() -> None:
    """The flag is derived, not trusted. A caller that could pass `forgeable=False`
    on a label edge would reopen exactly the hole this module closes."""
    assert Edge("a", "b", EdgeKind.LABEL, forgeable=False).forgeable is True
    assert Edge("a", "b", EdgeKind.DISK_ATTACHMENT).forgeable is False


# --------------------------------------------------------------------------- #
# fail closed
# --------------------------------------------------------------------------- #

def test_an_unknown_resource_is_critical(estate: Topology) -> None:
    assert estate.blast_class("never-heard-of-it") is BlastClass.CRITICAL


def test_missing_telemetry_is_critical() -> None:
    topo = Topology()
    topo.add_node("mystery-box", NodeKind.INSTANCE)
    assert topo.blast_class("mystery-box") is BlastClass.CRITICAL


def test_cpu_alone_is_not_telemetry() -> None:
    """The exact signal the poisoned runbook asked the agent to trust. A GPU node
    trains at 0.4% CPU, so a CPU-only reading is not evidence of anything."""
    topo = Topology()
    topo.add_node("ml-train-01", NodeKind.INSTANCE, utilisation=Utilisation(cpu_percent=0.4))
    assert topo.blast_class("ml-train-01") is BlastClass.CRITICAL


def test_an_accelerator_with_no_gpu_series_is_critical() -> None:
    """"GPU is idle" and "the Ops Agent was never installed" are indistinguishable
    from here. Only one of them is safe to act on."""
    topo = Topology()
    topo.add_node(
        "ml-train-02",
        NodeKind.INSTANCE,
        utilisation=Utilisation(network_bytes_per_s=0.0, disk_ops_per_s=0.0),
        accelerators=1,
    )
    assert topo.blast_class("ml-train-02") is BlastClass.CRITICAL


def test_an_api_error_degrades_the_whole_topology(estate: Topology) -> None:
    """A partial read is not a smaller estate. The edges we failed to fetch are the
    ones that would have raised a class, so every node fails to the top."""
    estate.degrade("monitoring read failed: PermissionDenied")
    assert estate.blast_class("staging-web-3") is BlastClass.CRITICAL
    assert estate.blast_class("ml-train-01") is BlastClass.CRITICAL


# --------------------------------------------------------------------------- #
# classification
# --------------------------------------------------------------------------- #

def test_the_classes_are_ordered() -> None:
    assert (
        BlastClass.ISOLATED < BlastClass.ATTACHED < BlastClass.SERVING < BlastClass.CRITICAL
    )


def test_a_load_balancer_reaches_through_the_instance_group() -> None:
    """The backend service never names the VM. Classifying on immediate in-edges would
    call a load-balanced instance merely ATTACHED — the same mistake, one hop out."""
    topo = Topology()
    topo.add_node("web-1", NodeKind.INSTANCE, utilisation=QUIET)
    topo.add_node("web-pool", NodeKind.INSTANCE_GROUP)
    topo.add_node("public-lb", NodeKind.BACKEND_SERVICE)
    topo.add_edge(Edge("web-pool", "web-1", EdgeKind.INSTANCE_GROUP_MEMBERSHIP))
    topo.add_edge(Edge("public-lb", "web-pool", EdgeKind.LOAD_BALANCER_BACKEND))

    assert topo.serving_reach("web-1") is True
    assert topo.blast_class("web-1") is BlastClass.SERVING


def test_an_attached_disk_is_not_isolated() -> None:
    topo = Topology()
    topo.add_node("web-1", NodeKind.INSTANCE, utilisation=QUIET)
    topo.add_node("pd-web-1", NodeKind.DISK)
    topo.add_edge(Edge("web-1", "pd-web-1", EdgeKind.DISK_ATTACHMENT))
    topo.add_edge(Edge("pd-web-1", "web-1", EdgeKind.DISK_ATTACHMENT))

    assert topo.blast_class("pd-web-1") is BlastClass.ATTACHED
    assert topo.blast_class("web-1") is BlastClass.ATTACHED


def test_a_snapshot_points_at_its_source_disk() -> None:
    topo = Topology()
    topo.add_node("pd-ml-scratch", NodeKind.DISK)
    topo.add_node("snap-2024-03-11", NodeKind.SNAPSHOT)
    topo.add_edge(Edge("snap-2024-03-11", "pd-ml-scratch", EdgeKind.SNAPSHOT_SOURCE))

    assert topo.blast_class("pd-ml-scratch") is BlastClass.ATTACHED
    assert topo.blast_class("snap-2024-03-11") is BlastClass.ISOLATED


def test_a_bound_address_raises_the_instance() -> None:
    topo = Topology()
    topo.add_node("web-1", NodeKind.INSTANCE, utilisation=QUIET)
    topo.add_node("legacy-lb-ip", NodeKind.ADDRESS)
    topo.add_edge(Edge("legacy-lb-ip", "web-1", EdgeKind.ADDRESS_BINDING))
    assert topo.blast_class("web-1") is BlastClass.ATTACHED


def test_measured_work_alone_is_enough_to_leave_isolated() -> None:
    """Nothing in the graph points at it, but it is moving four megabytes a second.
    Whatever is talking to it is real even if we cannot name it."""
    topo = Topology()
    topo.add_node(
        "batch-worker",
        NodeKind.INSTANCE,
        utilisation=Utilisation(gpu_percent=0.0, network_bytes_per_s=4_000_000.0, disk_ops_per_s=90.0),
    )
    assert topo.blast_class("batch-worker") is BlastClass.ATTACHED


def test_a_cycle_in_the_graph_terminates() -> None:
    """Disk attachment is recorded in both directions, so the reverse walk must be
    cycle-safe or a two-node estate hangs the gate."""
    topo = Topology()
    topo.add_node("a", NodeKind.INSTANCE, utilisation=QUIET)
    topo.add_node("b", NodeKind.INSTANCE, utilisation=QUIET)
    topo.add_edge(Edge("a", "b", EdgeKind.DISK_ATTACHMENT))
    topo.add_edge(Edge("b", "a", EdgeKind.DISK_ATTACHMENT))
    assert topo.serving_reach("a") is False


# --------------------------------------------------------------------------- #
# the seam
# --------------------------------------------------------------------------- #

def test_the_blast_shape_carries_the_class_where_a_human_can_read_it(estate: Topology) -> None:
    assert blast_shape(STOP, "ml-train-01", estate).endswith("/critical")
    assert blast_shape(STOP, "staging-web-3", estate).endswith("/isolated")


def test_shape_significant_params_still_split_the_shape(estate: Topology) -> None:
    """V1's rule survives: the same blast class in prod and in scratch is not the same
    operation. V2 adds a coordinate, it does not replace one."""
    scratch = blast_shape(STOP, "staging-web-3", estate, {"project": "scratch"})
    prod = blast_shape(STOP, "staging-web-3", estate, {"project": "prod"})
    assert scratch != prod


def test_the_ladder_actually_asks_the_topology() -> None:
    """The wiring, not the module. topology.py passed its own tests while graph.py
    still keyed the ladder on V1's fingerprint — so the poison would have worked end
    to end against a system whose unit tests all passed. This asserts the pipeline."""
    from ratchet.authority import AuthorityLedger, PROMOTION_THRESHOLD, Authority
    from ratchet.effects import Actuator, Effect, EffectLog
    from ratchet.domains import finops
    from ratchet.graph import Deps
    from ratchet.topology import Topology, Edge, EdgeKind, NodeKind, Utilisation
    from ratchet.world import DictReader, VirtualWorld

    topo = Topology()
    topo.add_node("ml-train-01", NodeKind.INSTANCE,
                  Utilisation(gpu_percent=71.0, network_bytes_per_s=4.2e6), accelerators=1)
    topo.add_node("staging-web-3", NodeKind.INSTANCE,
                  Utilisation(gpu_percent=0.0, network_bytes_per_s=0.0,
                              disk_ops_per_s=0.0, cpu_percent=0.1))
    topo.add_node("ig-train", NodeKind.INSTANCE_GROUP)
    topo.add_node("lb-front", NodeKind.BACKEND_SERVICE)
    topo.add_edge(Edge("ig-train", "ml-train-01", EdgeKind.INSTANCE_GROUP_MEMBERSHIP))
    topo.add_edge(Edge("lb-front", "ig-train", EdgeKind.LOAD_BALANCER_BACKEND))

    estate = finops.sample_estate()
    reader = DictReader(estate)
    ledger = AuthorityLedger()
    deps = Deps(ledger, Actuator(EffectLog(), {}), VirtualWorld(reader, finops.simulators()),
                reader, specs=finops.SPECS, topology=topo)

    spare = Effect("compute.stop_idle_instance", {"target": "staging-web-3"},
                   expect={"status": "TERMINATED"}, run_id="r")
    gpu = Effect("compute.stop_idle_instance", {"target": "ml-train-01"},
                 expect={"status": "TERMINATED"}, run_id="r")

    assert spare.shape == gpu.shape, "precondition: V1 could not tell them apart"
    assert deps.shape_of(spare) != deps.shape_of(gpu), "V2 must, through Deps"

    # Earn the spare box all the way to commit, then aim at the GPU node.
    for _ in range(PROMOTION_THRESHOLD[Authority.SHADOW]):
        ledger.observe("compute.stop_idle_instance", deps.shape_of(spare), passed=True)
    assert ledger.decide("compute.stop_idle_instance", deps.shape_of(spare)).commits is True

    reaching = ledger.decide("compute.stop_idle_instance", deps.shape_of(gpu))
    assert reaching.commits is False
    assert reaching.in_envelope is False


def test_no_topology_configured_fails_closed_rather_than_open() -> None:
    """An unconfigured deployment must be over-cautious, not blind."""
    from ratchet.topology import Topology
    empty = Topology()
    assert empty.blast_class("anything-at-all").name == "CRITICAL"
