"""Real GCP inventory — the substrate the fixture was standing in for.

Reads live resources through the Compute and Monitoring APIs and returns them in
the shape `ratchet.world` expects, so the same graph that ran against the fixture
runs against an actual project with no changes above this line.

**On the cost figures.** These are list-price estimates, computed here from a small
published price table, and they are labelled as estimates everywhere they surface.
The authoritative number is the BigQuery billing export, which lags by hours and
needs to be configured per-project. Two reasons to have both: the estimate is what
makes an operation *proposable* in real time, and the export is what makes a
reclamation *provable* after the fact. Do not let the estimate masquerade as the
bill — a system whose whole argument is "verify against the environment" cannot
fudge its own headline number.

**On idleness.** `cpu_7d_avg` is a real 7-day mean from Cloud Monitoring, not a
guess. A VM with no CPU is not automatically idle — it may be a warm standby — which
is exactly why stopping one starts in shadow and has to earn its way out.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

# europe-west1 list prices, USD/month, rounded. Sourced from Google's public pricing
# pages; refresh if the demo project moves region. Deliberately a small explicit
# table rather than the Cloud Billing Catalog API — a wrong number here is visible
# and correctable, whereas a silently mis-parsed SKU is neither.
MACHINE_MONTHLY = {
    "e2-micro": 6.11, "e2-small": 12.23, "e2-medium": 24.46,
    "e2-standard-2": 48.92, "e2-standard-4": 97.84, "e2-standard-8": 195.68,
    "n1-standard-1": 24.27, "n1-standard-2": 48.55, "n1-standard-4": 97.09,
    "n2-standard-2": 56.86, "n2-standard-4": 113.72,
    "a2-highgpu-1g": 2632.00,
}
DISK_MONTHLY_PER_GB = {"pd-standard": 0.044, "pd-balanced": 0.114, "pd-ssd": 0.187}
SNAPSHOT_MONTHLY_PER_GB = 0.026
# Since 1 Feb 2024 Google bills *every* external IPv4 address, not just idle ones.
# An in-use address on a VM is ~$0.005/hr; an unattached reservation is dearer.
# Treating in-use as free — as the first draft did — understates the bill, which is
# the wrong direction for a tool whose job is to find money.
IN_USE_IP_MONTHLY = 3.65
UNUSED_IP_MONTHLY = 7.30
IDLE_CPU_THRESHOLD = 5.0          # percent, 7-day mean
STALE_SNAPSHOT_DAYS = 180


def _last(url: str) -> str:
    return url.rsplit("/", 1)[-1]


def read_estate(project: str, idle_days: int = 7) -> dict[str, dict[str, Any]]:
    """Return the live estate, keyed to match `ratchet.world.scope_of`.

    Only reads. Nothing in this module mutates anything.
    """
    from google.cloud import compute_v1

    estate: dict[str, dict[str, Any]] = {}
    cpu = _cpu_averages(project, idle_days)

    # --- instances ---------------------------------------------------------
    for zone, scoped in compute_v1.InstancesClient().aggregated_list(project=project):
        for vm in getattr(scoped, "instances", []) or []:
            machine = _last(vm.machine_type)
            cost = MACHINE_MONTHLY.get(machine, 0.0)
            usage = cpu.get(vm.name)
            estate[f"compute.stop_idle_instance:{vm.name}"] = {
                "status": vm.status,
                "machine_type": machine,
                "zone": _last(zone),
                "cpu_7d_avg": usage,
                "monthly_cost_usd": cost if vm.status == "RUNNING" else 0.0,
                "exists": True,
                "cost_is_estimate": True,
                # Only a running VM below the CPU threshold is a candidate. An
                # unknown CPU average is not treated as idle — absence of evidence.
                "idle_candidate": bool(
                    vm.status == "RUNNING" and usage is not None and usage < IDLE_CPU_THRESHOLD
                ),
            }

    # --- disks -------------------------------------------------------------
    for zone, scoped in compute_v1.DisksClient().aggregated_list(project=project):
        for disk in getattr(scoped, "disks", []) or []:
            attached = list(disk.users or [])
            estate[f"compute.delete_unattached_disk:{disk.name}"] = {
                "attached_to": _last(attached[0]) if attached else None,
                "size_gb": disk.size_gb,
                "disk_type": _last(disk.type_),
                "zone": _last(zone),
                "monthly_cost_usd": round(
                    disk.size_gb * DISK_MONTHLY_PER_GB.get(_last(disk.type_), 0.114), 2
                ),
                "exists": True,
                "cost_is_estimate": True,
                "idle_candidate": not attached,
            }

    # --- reserved addresses ------------------------------------------------
    for region, scoped in compute_v1.AddressesClient().aggregated_list(project=project):
        for address in getattr(scoped, "addresses", []) or []:
            in_use = str(address.status) == "IN_USE"
            estate[f"compute.release_static_ip:{address.name}"] = {
                "status": address.status,
                "attached_to": _last(address.users[0]) if address.users else None,
                "region": _last(region),
                "monthly_cost_usd": IN_USE_IP_MONTHLY if in_use else UNUSED_IP_MONTHLY,
                "exists": True,
                "cost_is_estimate": True,
                "idle_candidate": not in_use,
            }

    # --- snapshots ---------------------------------------------------------
    now = datetime.now(timezone.utc)
    for snap in compute_v1.SnapshotsClient().list(project=project):
        age = None
        if snap.creation_timestamp:
            try:
                age = (now - datetime.fromisoformat(snap.creation_timestamp)).days
            except ValueError:
                age = None
        size = snap.storage_bytes / 1e9 if snap.storage_bytes else 0.0
        estate[f"compute.delete_stale_snapshot:{snap.name}"] = {
            "age_days": age,
            "size_gb": round(size, 1),
            "monthly_cost_usd": round(size * SNAPSHOT_MONTHLY_PER_GB, 2),
            "exists": True,
            "cost_is_estimate": True,
            "idle_candidate": bool(age is not None and age > STALE_SNAPSHOT_DAYS),
        }

    return estate


def _cpu_averages(project: str, days: int) -> dict[str, float]:
    """Mean CPU utilisation per instance over the window, as a percentage.

    Returns an empty mapping if Monitoring is unavailable — callers must treat a
    missing value as *unknown*, never as idle.
    """
    try:
        from google.cloud import monitoring_v3
    except ImportError:
        return {}

    client = monitoring_v3.MetricServiceClient()
    now = datetime.now(timezone.utc)
    interval = monitoring_v3.TimeInterval(
        start_time=now - timedelta(days=days),
        end_time=now,
    )
    aggregation = monitoring_v3.Aggregation(
        alignment_period={"seconds": 3600},
        per_series_aligner=monitoring_v3.Aggregation.Aligner.ALIGN_MEAN,
        cross_series_reducer=monitoring_v3.Aggregation.Reducer.REDUCE_MEAN,
        group_by_fields=["metric.labels.instance_name"],
    )

    try:
        series = client.list_time_series(
            name=f"projects/{project}",
            filter='metric.type="compute.googleapis.com/instance/cpu/utilization"',
            interval=interval,
            aggregation=aggregation,
            view=monitoring_v3.ListTimeSeriesRequest.TimeSeriesView.FULL,
        )
    except Exception:
        return {}

    out: dict[str, float] = {}
    for ts in series:
        name = ts.metric.labels.get("instance_name")
        points = [p.value.double_value for p in ts.points]
        if name and points:
            out[name] = round(100 * sum(points) / len(points), 2)
    return out


def reclaimable(estate: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Just the rows an operation could actually act on."""
    return {k: v for k, v in estate.items() if v.get("idle_candidate")}


def monthly_spend(estate: dict[str, dict[str, Any]]) -> float:
    return round(sum(row.get("monthly_cost_usd", 0.0) for row in estate.values()), 2)
