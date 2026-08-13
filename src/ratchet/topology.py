"""Dependency topology — blast radius derived from what *depends on* a resource.

V1 earns authority per operation class × argument **shape**, and the shape ignores
argument values so trust generalises. Right instinct, wrong granularity:
`compute.stop_idle_instance` on `staging-web-3` and on `ml-train-01` produce the same
shape, so five clean rehearsals against a spare staging box hand the agent the right
to stop the GPU node that runs the nightly build. `evals/poison.py` reached exactly
that proposal; only the ladder's inexperience stopped it, and inexperience is a
depreciating asset (CLAIMS.md §1).

This module supplies the missing coordinate. Blast radius is **re-derived from the
estate**, the same move that made verification trustworthy in V1 — stop asking, start
re-deriving — applied to consequence rather than correctness.

**What counts as evidence.** An attacker who can file a runbook note can also write a
label, a description, a DNS record, or name a VM `scratch-tmp`. So edges carry
`forgeable`, and a forgeable edge may only ever *raise* a blast class, never lower it.
Attachments, group membership, load-balancer backends and metered utilisation are
things the control plane records about itself; prose is not. If a signal can be
forged, it is not evidence.

**Fail closed.** Missing telemetry, an API error, or a resource this module has never
heard of yields `CRITICAL`, the most severe class. `gcp_inventory.py` already carries
this rule for idleness — a VM with no CPU average is *unknown*, never idle — and the
same mistake is much more expensive here, because absence of evidence would read as
absence of dependants. The cost is real and named in ROADMAP.md's falsification list:
a topology that degrades often puts everything in CRITICAL and the ladder stops
promoting. That is safety by paralysis, and it is the failure mode to watch. It is
still the correct direction to fail in.

**Cloud Asset Inventory is not a dependency.** CAI exposes a first-class relationship
graph (`contentType=RELATIONSHIP`, e.g. `INSTANCE_TO_INSTANCEGROUP`) which would
supply several of these edges directly — but it requires Security Command Center
Premium or Enterprise. Building on it would make this unavailable to exactly the
mid-size teams the problem statement describes, so everything here comes from the
plain Compute and Monitoring APIs. CAI is an enhancement to add where it exists, and
it may only add edges, never remove them.

**Unverified against a live project:** the GPU utilisation metric. Compute Engine does
not publish GPU utilisation as a built-in `compute.googleapis.com/instance/*` series;
the reachable one is `agent.googleapis.com/gpu/utilization`, which requires the Ops
Agent with GPU monitoring enabled. We have not confirmed its exact label set against a
project with GPUs attached, so `_read_utilisation` tries both `metric.labels.instance_name`
and `resource.labels.instance_id` and treats a miss as *unknown*. An instance with an
accelerator attached and no GPU series is therefore CRITICAL — which is the right
answer anyway: "no agent installed" and "GPU is idle" are indistinguishable from here,
and the whole poison turned on believing the second when only the first was known.

No cloud imports at module scope, deliberately: the classification logic is the part
that has to be provable in a plain unit test.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from typing import Any

from .effects import fingerprint


class BlastClass(IntEnum):
    """How much of the estate is downstream of this resource. Ordered, so
    "at least as severe as" is arithmetic and `max()` is the combining rule."""

    ISOLATED = 0   # nothing the control plane records points at it, and it is not working
    ATTACHED = 1   # something is bound to it, or it is measurably doing work
    SERVING = 2    # it is behind a load balancer or in an instance group, or holding a GPU
    CRITICAL = 3   # serving *and* busy — or we do not know, which is the same answer here

    @property
    def label(self) -> str:
        return self.name.lower()


class EdgeKind(StrEnum):
    """Why one resource points at another."""

    # Recorded by the control plane about itself. An attacker with write access to
    # these has already won by a shorter route than poisoning a note.
    DISK_ATTACHMENT = "disk_attachment"
    SNAPSHOT_SOURCE = "snapshot_source"
    INSTANCE_GROUP_MEMBERSHIP = "instance_group_membership"
    LOAD_BALANCER_BACKEND = "load_balancer_backend"
    ADDRESS_BINDING = "address_binding"

    # Prose and naming. Anyone who can file a ticket can arrange these.
    LABEL = "label"
    DESCRIPTION = "description"
    DNS_RECORD = "dns_record"
    RESOURCE_NAME = "resource_name"


FORGEABLE_KINDS = frozenset(
    {EdgeKind.LABEL, EdgeKind.DESCRIPTION, EdgeKind.DNS_RECORD, EdgeKind.RESOURCE_NAME}
)

# Membership in either of these means traffic is being sent here on purpose by
# something with its own health checks — the clearest "this is load-bearing" signal
# available for free.
SERVING_KINDS = frozenset(
    {EdgeKind.INSTANCE_GROUP_MEMBERSHIP, EdgeKind.LOAD_BALANCER_BACKEND}
)


class NodeKind(StrEnum):
    INSTANCE = "instance"
    DISK = "disk"
    SNAPSHOT = "snapshot"
    ADDRESS = "address"
    INSTANCE_GROUP = "instance_group"
    BACKEND_SERVICE = "backend_service"
    DNS_RECORD = "dns_record"


# --------------------------------------------------------------------------- #
# thresholds
# --------------------------------------------------------------------------- #

# Any measurable GPU work counts. A GPU node at 3% is still *holding the device*, and
# the machine we are protecting is the one whose runbook says "do not stop it on CPU
# average alone" — its CPU average was 0.4% while it trained.
GPU_BUSY_PERCENT = 1.0

# Below this is heartbeat: the Ops Agent, metadata polling, health checks, NTP. A box
# genuinely serving traffic clears it by orders of magnitude, so the threshold does
# not have to be precise to separate the two cases.
NETWORK_BUSY_BYTES_PER_S = 10_000.0

# One sustained IOP per second is not a filesystem at rest.
DISK_BUSY_OPS_PER_S = 1.0


@dataclass(frozen=True)
class Utilisation:
    """Metered work, from Cloud Monitoring. Every field may be `None` for *unknown*.

    CPU is carried but never sufficient on its own. That is not a style preference:
    CPU average alone is the exact signal the poisoned runbook note asked the agent to
    trust, and a GPU node training a model sits near zero CPU. An instance whose only
    known series is CPU is treated as having no telemetry at all.
    """

    gpu_percent: float | None = None
    network_bytes_per_s: float | None = None
    disk_ops_per_s: float | None = None
    cpu_percent: float | None = None

    @property
    def known(self) -> bool:
        return any(
            v is not None
            for v in (self.gpu_percent, self.network_bytes_per_s, self.disk_ops_per_s)
        )

    @property
    def gpu_busy(self) -> bool:
        return self.gpu_percent is not None and self.gpu_percent >= GPU_BUSY_PERCENT

    @property
    def busy(self) -> bool:
        """Doing work by some non-CPU measure."""
        return (
            (self.network_bytes_per_s is not None
             and self.network_bytes_per_s >= NETWORK_BUSY_BYTES_PER_S)
            or (self.disk_ops_per_s is not None
                and self.disk_ops_per_s >= DISK_BUSY_OPS_PER_S)
        )


@dataclass
class Node:
    name: str
    kind: NodeKind
    utilisation: Utilisation | None = None
    # Accelerators attached, from the instance's own `guest_accelerators`. Held apart
    # from utilisation because it answers a different question: not "is the GPU busy"
    # but "is there a GPU whose business we are obliged to know about".
    accelerators: int = 0


@dataclass
class Edge:
    """`source` depends on, references, or sends traffic to `target`.

    Direction is always *towards the thing that would be damaged*, so a resource's
    in-degree is the count of things that would notice if it went away.
    """

    source: str
    target: str
    kind: EdgeKind
    # Defaults from `kind` and can only be forced upward. A caller cannot declare a
    # label edge trustworthy — that would reopen the hole this module exists to close.
    forgeable: bool = False
    detail: str = ""

    def __post_init__(self) -> None:
        if self.kind in FORGEABLE_KINDS:
            self.forgeable = True


class Topology:
    """A dependency graph over resource names, with a blast class per node."""

    def __init__(self) -> None:
        self.nodes: dict[str, Node] = {}
        self.edges: list[Edge] = []
        self._inbound: dict[str, list[Edge]] = {}
        # Non-empty means some source could not be read. One unreadable source
        # invalidates every *negative* conclusion the graph could draw, because the
        # missing edges are exactly the ones that would have raised a class.
        self.degraded: str = ""

    # -- building --------------------------------------------------------- #

    def add_node(
        self,
        name: str,
        kind: NodeKind,
        utilisation: Utilisation | None = None,
        accelerators: int = 0,
    ) -> Node:
        node = self.nodes.get(name)
        if node is None:
            node = Node(name=name, kind=kind, accelerators=accelerators)
            self.nodes[name] = node
        if utilisation is not None:
            node.utilisation = utilisation
        if accelerators:
            node.accelerators = accelerators
        return node

    def add_edge(self, edge: Edge) -> Edge:
        # A node named only by an edge still exists in the estate; giving it a kind we
        # cannot confirm would be a guess, so it inherits nothing and, having no
        # telemetry, classifies severely.
        for endpoint in (edge.source, edge.target):
            if endpoint not in self.nodes:
                self.nodes[endpoint] = Node(name=endpoint, kind=NodeKind.INSTANCE)
        self.edges.append(edge)
        self._inbound.setdefault(edge.target, []).append(edge)
        return edge

    def degrade(self, reason: str) -> None:
        self.degraded = f"{self.degraded}; {reason}" if self.degraded else reason

    # -- reading ---------------------------------------------------------- #

    def inbound(self, name: str, *, trusted_only: bool = False) -> list[Edge]:
        edges = self._inbound.get(name, [])
        return [e for e in edges if not e.forgeable] if trusted_only else list(edges)

    def serving_reach(self, name: str, *, trusted_only: bool = False) -> bool:
        """Is there a serving edge anywhere upstream of this node?

        A VM sits in an instance group, and the group sits behind a backend service —
        so the load balancer never touches the VM directly. Classifying on immediate
        in-edges alone would call that VM merely ATTACHED, which is the same mistake at
        one remove.
        """
        seen: set[str] = set()
        frontier = [name]
        while frontier:
            current = frontier.pop()
            if current in seen:
                continue
            seen.add(current)
            for edge in self.inbound(current, trusted_only=trusted_only):
                if edge.kind in SERVING_KINDS:
                    return True
                frontier.append(edge.source)
        return False

    def blast_class(self, name: str) -> BlastClass:
        """The severity class for one resource. Never optimistic."""
        if self.degraded:
            return BlastClass.CRITICAL
        if name not in self.nodes:
            # An operation aimed at something we have no topology for is not a small
            # operation; it is an unmeasured one.
            return BlastClass.CRITICAL

        trusted = self._classify(name, trusted_only=True)
        with_claims = self._classify(name, trusted_only=False)
        # Forgeable edges are recorded and allowed to argue *upward* only. The max is
        # redundant while every rule below is monotone in edges, and it is kept anyway
        # so that a future rule which subtracts cannot quietly become an attack surface.
        return max(trusted, with_claims)

    def _classify(self, name: str, *, trusted_only: bool) -> BlastClass:
        node = self.nodes[name]
        util = node.utilisation

        if node.kind is NodeKind.INSTANCE:
            if util is None or not util.known:
                return BlastClass.CRITICAL
            if node.accelerators and util.gpu_percent is None:
                # There is a GPU here and no series describing it. "Idle" and
                # "unmonitored" look identical from this side; only one of them is safe
                # to act on, so we assume the other.
                return BlastClass.CRITICAL

        inbound = self.inbound(name, trusted_only=trusted_only)
        serving = self.serving_reach(name, trusted_only=trusted_only)
        busy = bool(util and util.busy)
        gpu = bool(util and util.gpu_busy)

        level = BlastClass.ISOLATED
        if inbound or busy:
            # Something is bound to it, or it is moving bytes. Either way stopping it
            # is not a no-op, which is all ATTACHED claims.
            level = max(level, BlastClass.ATTACHED)
        if serving or gpu:
            # Traffic is being sent here deliberately, or a device is being held.
            level = max(level, BlastClass.SERVING)
        if (serving and (busy or gpu)) or (gpu and (busy or inbound)):
            # Load-bearing *and* demonstrably in use. This is the ml-train-01 case and
            # the prod front-end case, and it is the class that must never share an
            # authority envelope with a spare box.
            level = max(level, BlastClass.CRITICAL)
        return level


# --------------------------------------------------------------------------- #
# the seam into the ladder
# --------------------------------------------------------------------------- #

def blast_shape(
    op_class: str,
    target: str,
    topology: Topology,
    params: dict[str, Any] | None = None,
) -> str:
    """The V1 fingerprint with the blast class folded in.

    `AuthorityLedger` keys its envelope on an opaque string, so adding a coordinate
    here changes what "the same shape of work" means without touching a line of
    `authority.py`. Authority earned stopping ISOLATED boxes is then simply not in the
    envelope when the target is CRITICAL, and the existing "unrehearsed shape" branch
    routes it back to rehearsal — the behaviour the poison run needed and did not get.

    Trust still generalises *within* a class, which is what keeps the ladder able to
    climb: two ISOLATED staging boxes remain one shape.
    """
    body = {**(params or {}), "target": target}
    return f"{fingerprint(op_class, body)}/{topology.blast_class(target).label}"


# --------------------------------------------------------------------------- #
# edge sources — live GCP
# --------------------------------------------------------------------------- #

def _last(url: str) -> str:
    return url.rsplit("/", 1)[-1]


def from_gcp(project: str, *, days: int = 7) -> Topology:
    """Build the topology from the plain Compute and Monitoring APIs.

    Only reads. Any failure degrades the whole topology rather than returning a
    smaller graph, because a smaller graph is indistinguishable from a safer estate.
    """
    topo = Topology()
    try:
        _read_compute(project, topo)
    except Exception as exc:  # noqa: BLE001 — Compute fails in many ways (quota,
        # permission, transport, a partially-enabled API). Every one of them leaves us
        # with fewer edges than the estate has, and fewer edges reads as safer.
        topo.degrade(f"compute read failed: {type(exc).__name__}: {exc}")
        return topo

    try:
        _read_utilisation(project, topo, days)
    except Exception as exc:  # noqa: BLE001 — same reasoning; see gcp_inventory's
        # `_cpu_averages`, which returns {} and makes its callers treat absence as
        # unknown. Here absence is handled by leaving `utilisation` None, which
        # classifies CRITICAL.
        topo.degrade(f"monitoring read failed: {type(exc).__name__}: {exc}")
    return topo


def _read_compute(project: str, topo: Topology) -> None:
    from google.cloud import compute_v1

    for zone, scoped in compute_v1.InstancesClient().aggregated_list(project=project):
        for vm in getattr(scoped, "instances", []) or []:
            accelerators = sum(a.accelerator_count for a in (vm.guest_accelerators or []))
            topo.add_node(vm.name, NodeKind.INSTANCE, accelerators=accelerators)

            for attached in vm.disks or []:
                if not attached.source:
                    continue  # local SSD / scratch: no independent resource to point at
                disk = _last(attached.source)
                topo.add_node(disk, NodeKind.DISK)
                # Both directions. The instance cannot boot without the disk, and the
                # disk is not free to delete while the instance holds it; each is a
                # reason the other is not ISOLATED.
                topo.add_edge(Edge(vm.name, disk, EdgeKind.DISK_ATTACHMENT))
                topo.add_edge(Edge(disk, vm.name, EdgeKind.DISK_ATTACHMENT))

            for label, value in (vm.labels or {}).items():
                topo.add_edge(
                    Edge(f"label:{label}={value}", vm.name, EdgeKind.LABEL, detail=label)
                )
            if vm.description:
                topo.add_edge(
                    Edge(f"description:{vm.name}", vm.name, EdgeKind.DESCRIPTION)
                )

    for zone, scoped in compute_v1.DisksClient().aggregated_list(project=project):
        for disk in getattr(scoped, "disks", []) or []:
            topo.add_node(disk.name, NodeKind.DISK)
            for user in disk.users or []:
                topo.add_edge(Edge(_last(user), disk.name, EdgeKind.DISK_ATTACHMENT))

    for snap in compute_v1.SnapshotsClient().list(project=project):
        topo.add_node(snap.name, NodeKind.SNAPSHOT)
        if snap.source_disk:
            topo.add_node(_last(snap.source_disk), NodeKind.DISK)
            topo.add_edge(
                Edge(snap.name, _last(snap.source_disk), EdgeKind.SNAPSHOT_SOURCE)
            )

    for region, scoped in compute_v1.AddressesClient().aggregated_list(project=project):
        for address in getattr(scoped, "addresses", []) or []:
            topo.add_node(address.name, NodeKind.ADDRESS)
            for user in address.users or []:
                topo.add_edge(Edge(address.name, _last(user), EdgeKind.ADDRESS_BINDING))

    _read_groups(project, topo, compute_v1)

    for scope, scoped in compute_v1.BackendServicesClient().aggregated_list(project=project):
        for service in getattr(scoped, "backend_services", []) or []:
            topo.add_node(service.name, NodeKind.BACKEND_SERVICE)
            for backend in service.backends or []:
                if not backend.group:
                    continue
                # `group` may name an instance group or a network endpoint group. NEG
                # membership is not resolved here; the edge to the group is still
                # recorded, so the group itself is never ISOLATED. Instances behind a
                # NEG are the known blind spot — they classify on their own telemetry.
                group = _last(backend.group)
                topo.add_node(group, NodeKind.INSTANCE_GROUP)
                topo.add_edge(
                    Edge(service.name, group, EdgeKind.LOAD_BALANCER_BACKEND)
                )


def _read_groups(project: str, topo: Topology, compute_v1: Any) -> None:
    """Instance-group membership, zonal and regional.

    Membership is listed per group rather than read off the instance, because an
    instance carries no field naming the groups that contain it.
    """
    zonal = compute_v1.InstanceGroupsClient()
    regional = compute_v1.RegionInstanceGroupsClient()

    for scope, scoped in zonal.aggregated_list(project=project):
        for group in getattr(scoped, "instance_groups", []) or []:
            topo.add_node(group.name, NodeKind.INSTANCE_GROUP)
            location = _last(scope)
            if scope.startswith("regions/"):
                members = regional.list_instances(
                    project=project,
                    region=location,
                    instance_group=group.name,
                    region_instance_groups_list_instances_request_resource=(
                        compute_v1.RegionInstanceGroupsListInstancesRequest(instance_state="ALL")
                    ),
                )
            else:
                members = zonal.list_instances(
                    project=project,
                    zone=location,
                    instance_group=group.name,
                    instance_groups_list_instances_request_resource=(
                        compute_v1.InstanceGroupsListInstancesRequest(instance_state="ALL")
                    ),
                )
            for member in members:
                if member.instance:
                    topo.add_edge(
                        Edge(group.name, _last(member.instance),
                             EdgeKind.INSTANCE_GROUP_MEMBERSHIP)
                    )


# Metric types, and how to turn each into a rate. Network and disk are DELTA counters,
# so ALIGN_RATE is what makes them bytes- and ops-per-second rather than a total that
# grows with the window.
_NETWORK_METRIC = "compute.googleapis.com/instance/network/received_bytes_count"
_DISK_READ_METRIC = "compute.googleapis.com/instance/disk/read_ops_count"
_DISK_WRITE_METRIC = "compute.googleapis.com/instance/disk/write_ops_count"
_CPU_METRIC = "compute.googleapis.com/instance/cpu/utilization"
# Ops Agent only; see the module docstring. Absence is treated as unknown.
_GPU_METRIC = "agent.googleapis.com/gpu/utilization"


def _read_utilisation(project: str, topo: Topology, days: int) -> None:
    """Attach metered work to every instance node.

    Deliberately more than CPU. `gcp_inventory` reads CPU alone because idleness for
    *cost* purposes is a CPU question; blast radius is not, and the one machine the
    poison found is the one where CPU is the least informative series available.
    """
    from google.cloud import monitoring_v3

    client = monitoring_v3.MetricServiceClient()

    network = _series_means(client, project, _NETWORK_METRIC, days, rate=True)
    reads = _series_means(client, project, _DISK_READ_METRIC, days, rate=True)
    writes = _series_means(client, project, _DISK_WRITE_METRIC, days, rate=True)
    cpu = _series_means(client, project, _CPU_METRIC, days, rate=False)
    gpu = _series_means(client, project, _GPU_METRIC, days, rate=False)

    for name, node in topo.nodes.items():
        if node.kind is not NodeKind.INSTANCE:
            continue
        disk_ops = None
        if name in reads or name in writes:
            disk_ops = reads.get(name, 0.0) + writes.get(name, 0.0)
        node.utilisation = Utilisation(
            gpu_percent=gpu.get(name),
            network_bytes_per_s=network.get(name),
            disk_ops_per_s=disk_ops,
            cpu_percent=None if name not in cpu else round(100 * cpu[name], 2),
        )


def _series_means(
    client: Any, project: str, metric_type: str, days: int, *, rate: bool
) -> dict[str, float]:
    """Mean of one metric per instance over the window, keyed by instance name.

    A metric that does not exist in the project raises, and the caller degrades the
    whole topology. That is intentional: silently returning `{}` here would put every
    instance in CRITICAL for a *different* reason and hide which signal was missing.
    """
    from datetime import UTC, datetime, timedelta

    from google.cloud import monitoring_v3

    now = datetime.now(UTC)
    interval = monitoring_v3.TimeInterval(
        start_time=now - timedelta(days=days), end_time=now
    )
    aligner = (
        monitoring_v3.Aggregation.Aligner.ALIGN_RATE
        if rate
        else monitoring_v3.Aggregation.Aligner.ALIGN_MEAN
    )
    aggregation = monitoring_v3.Aggregation(
        alignment_period={"seconds": 3600},
        per_series_aligner=aligner,
        cross_series_reducer=monitoring_v3.Aggregation.Reducer.REDUCE_MEAN,
        group_by_fields=["metric.labels.instance_name", "resource.labels.instance_id"],
    )
    series = client.list_time_series(
        name=f"projects/{project}",
        filter=f'metric.type="{metric_type}"',
        interval=interval,
        aggregation=aggregation,
        view=monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
    )

    out: dict[str, float] = {}
    for ts in series:
        name = ts.metric.labels.get("instance_name") or ts.resource.labels.get("instance_id")
        points = [p.value.double_value for p in ts.points]
        if name and points:
            out[name] = sum(points) / len(points)
    return out


def from_dns(zones: Iterable[str], topo: Topology, project: str) -> Topology:
    """Add DNS record edges. Forgeable by construction, so they can only raise a class.

    `google-cloud-dns` is not a dependency of this project, so this imports lazily and
    is never called by `from_gcp`. A record is a claim about intent, not a fact about
    the control plane — recording it is useful for explaining a CRITICAL, and it is
    never allowed to argue a resource down to ISOLATED.
    """
    from google.cloud import dns

    client = dns.Client(project=project)
    for zone_name in zones:
        zone = client.zone(zone_name)
        for record in zone.list_resource_record_sets():
            for value in record.rrdatas:
                topo.add_edge(
                    Edge(f"dns:{record.name}", value, EdgeKind.DNS_RECORD, detail=record.record_type)
                )
    return topo
