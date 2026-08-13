"""Real GCP mutations — the hands.

Separated from `gcp_inventory` (the eyes) on purpose. Everything in that module
only reads; everything here changes the world. Keeping them apart means "what can
this program destroy?" has a single file as its answer.

Mutations are **opt-in**. Without `allow_mutations=True` the actuator returns the
post-state it *would* have produced without calling anything, so the console can run
against a real project and a real inventory while touching nothing. That default is
not timidity — it is the difference between a demo you can run on a laptop in front
of people and one you can only run once.
"""

from __future__ import annotations

from typing import Any, Callable


def _zone_of(estate: dict, op_class: str, target: str, key: str = "zone") -> str:
    row = estate.get(f"{op_class}:{target}", {})
    return row.get(key, "")


def build_tools(
    project: str, estate: dict[str, dict[str, Any]], allow_mutations: bool = False
) -> dict[str, Callable]:
    """Return the actuator's tool table for a real project.

    Each tool returns the observed post-state. When mutations are disabled the tool
    writes that state into the in-memory mirror of the estate instead of calling the
    API — "mirror mode". That distinction matters: a tool that merely *claimed*
    success while the mirror stayed put would be indistinguishable from the lying
    tool the verifier exists to catch, and the ladder would demote forever. Mirror
    mode is a dry run against real inventory, not a fib.
    """

    def settle(op_class: str, target: str, after: dict) -> dict:
        if not allow_mutations:
            estate[f"{op_class}:{target}"] = {**estate.get(f"{op_class}:{target}", {}), **after}
        return after

    def stop_instance(**params):
        target = params["target"]
        zone = _zone_of(estate, "compute.stop_idle_instance", target)
        if allow_mutations:
            from google.cloud import compute_v1

            compute_v1.InstancesClient().stop(project=project, zone=zone, instance=target).result()
        return settle("compute.stop_idle_instance", target, {"status": "TERMINATED", "monthly_cost_usd": 0.0})

    def delete_disk(**params):
        target = params["target"]
        zone = _zone_of(estate, "compute.delete_unattached_disk", target)
        if allow_mutations:
            from google.cloud import compute_v1

            compute_v1.DisksClient().delete(project=project, zone=zone, disk=target).result()
        return settle("compute.delete_unattached_disk", target, {"exists": False, "monthly_cost_usd": 0.0})

    def release_ip(**params):
        target = params["target"]
        region = _zone_of(estate, "compute.release_static_ip", target, key="region")
        if allow_mutations:
            from google.cloud import compute_v1

            compute_v1.AddressesClient().delete(
                project=project, region=region, address=target
            ).result()
        return settle("compute.release_static_ip", target, {"status": "RELEASED", "monthly_cost_usd": 0.0})

    def delete_snapshot(**params):
        target = params["target"]
        if allow_mutations:
            from google.cloud import compute_v1

            compute_v1.SnapshotsClient().delete(project=project, snapshot=target).result()
        return settle("compute.delete_stale_snapshot", target, {"exists": False, "monthly_cost_usd": 0.0})

    def downsize_instance(**params):
        target = params["target"]
        zone = _zone_of(estate, "compute.downsize_instance", target)
        machine = params.get("machine_type", "e2-micro")
        if allow_mutations:
            from google.cloud import compute_v1

            client = compute_v1.InstancesClient()
            # A machine-type change requires the instance to be stopped first —
            # which is itself a side effect, and why this operation is not
            # reversible in one step. Kept explicit rather than hidden in a helper.
            client.stop(project=project, zone=zone, instance=target).result()
            client.set_machine_type(
                project=project,
                zone=zone,
                instance=target,
                instances_set_machine_type_request_resource={
                    "machine_type": f"zones/{zone}/machineTypes/{machine}"
                },
            ).result()
            client.start(project=project, zone=zone, instance=target).result()
        return settle("compute.downsize_instance", target, {"machine_type": machine})

    return {
        "compute.stop_idle_instance": stop_instance,
        "compute.delete_unattached_disk": delete_disk,
        "compute.release_static_ip": release_ip,
        "compute.delete_stale_snapshot": delete_snapshot,
        "compute.downsize_instance": downsize_instance,
    }
