"""Domain: reclaiming abandoned cloud spend.

**The $4,000 weekend.** A platform engineer at a forty-person startup opens a billing
alert on Monday. Something was left running since Friday. They already know what to
delete — that is not the hard part. The hard part is that deleting the wrong thing at
9am on a Monday is far worse than the bill, so nothing gets deleted, and the same
resource is still there next month.

That asymmetry is the whole problem, and it is exactly what an authority ladder
dissolves. The agent does not need permission to delete; it needs to have *rehearsed
this class of delete enough times, against this shape of resource, that the question
stops being interesting.*

Why this domain and not another (see DECISIONS.md D-005):

- **Operations repeat.** A ratchet is meaningless where each task is unique. Every
  idle disk is another instance of the same operation class, so the ladder actually
  climbs during a demo rather than in theory.
- **Post-conditions are re-derivable from the environment**, twice over: the resource's
  real state from the API, and the spend from the billing export. The verifier never
  has to ask the agent whether it went well.
- **The substrate is unfakeable.** Billing data is real money in a real project, which
  the field scan lists as one of the axes separating winners from the median.
- **Reversibility varies across the operation set**, which is what makes the routing
  interesting: stopping an instance is reversible and can be earned outright;
  deleting a disk is not, and stays behind a human no matter how much authority the
  class accrues. Irreversibility is a property of the operation, not a confidence level.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ..restraint import Damage


@dataclass(frozen=True)
class OpSpec:
    """One operation class the agent can learn to perform."""

    op_class: str
    summary: str
    reversible: bool
    simulate: Callable[[dict, dict], dict]
    expect: Callable[[dict], dict]
    # Declared worst case, in restore-minutes. Mandatory: an operation whose blast
    # radius nobody wrote down is refused, because "we never thought about it" is
    # not a safety property. None means unrecoverable at any budget.
    damage: Damage = Damage(None, "undeclared")
    # The operation that puts it back, for the undo ledger.
    inverse_op: str = ""


def _stop_instance(before: dict, params: dict) -> dict:
    return {**before, "status": "TERMINATED", "monthly_cost_usd": 0.0}


def _delete_disk(before: dict, params: dict) -> dict:
    return {**before, "exists": False, "monthly_cost_usd": 0.0}


def _delete_snapshot(before: dict, params: dict) -> dict:
    return {**before, "exists": False, "monthly_cost_usd": 0.0}


def _release_ip(before: dict, params: dict) -> dict:
    # Releasing a reserved address deletes it. The API then reports absence, not a
    # "RELEASED" status — post-conditions must describe what can actually be
    # observed afterwards, or verification fails on a success.
    return {**before, "status": "RELEASED", "exists": False, "monthly_cost_usd": 0.0}


def _downsize(before: dict, params: dict) -> dict:
    target = params.get("machine_type", "e2-standard-2")
    ratio = {"e2-standard-2": 0.25, "e2-standard-4": 0.5}.get(target, 0.5)
    return {
        **before,
        "machine_type": target,
        "monthly_cost_usd": round(before.get("monthly_cost_usd", 0.0) * ratio, 2),
    }


def _set_lifecycle(before: dict, params: dict) -> dict:
    return {
        **before,
        "lifecycle_days": params.get("days", 30),
        "monthly_cost_usd": round(before.get("monthly_cost_usd", 0.0) * 0.4, 2),
    }


SPECS: dict[str, OpSpec] = {
    spec.op_class: spec
    for spec in [
        OpSpec(
            "compute.stop_idle_instance",
            "Stop a VM with no CPU activity and no active sessions",
            reversible=True,
            simulate=_stop_instance,
            expect=lambda p: {"status": "TERMINATED", "monthly_cost_usd": 0.0},
            damage=Damage(3.0, "restart the instance; boot disk and IP are untouched"),
            inverse_op="compute.start_instance",
        ),
        OpSpec(
            "compute.downsize_instance",
            "Move an over-provisioned VM to a smaller machine type",
            reversible=True,
            simulate=_downsize,
            expect=lambda p: {"machine_type": p.get("machine_type", "e2-standard-2")},
            damage=Damage(6.0, "stop, restore the previous machine type, start"),
            inverse_op="compute.resize_instance",
        ),
        OpSpec(
            "compute.release_static_ip",
            "Release a reserved external IP that is attached to nothing",
            # NOT reversible, despite first appearances. Releasing returns the address
            # to the pool; someone else may claim it, and you cannot get that specific
            # address back. Recovery means reserving a *different* one and repointing
            # everything that referred to the old — recoverable at cost, not undoable.
            # The two are different properties and conflating them let this operation
            # commit without a human when it should not have.
            reversible=False,
            simulate=_release_ip,
            expect=lambda p: {"exists": False, "monthly_cost_usd": 0.0},
            # A released address is gone; a *new* one can be reserved in minutes, but
            # the same numeric address is not recoverable. Anything pointing at it
            # stays broken until DNS and configuration are updated.
            damage=Damage(45.0, "reserve a new address and repoint DNS and config"),
            inverse_op="",
        ),
        OpSpec(
            "storage.set_lifecycle_policy",
            "Age objects in a bucket to colder storage after N days",
            reversible=True,
            simulate=_set_lifecycle,
            expect=lambda p: {"lifecycle_days": p.get("days", 30)},
            damage=Damage(2.0, "remove the lifecycle rule; already-transitioned objects stay cold"),
            inverse_op="storage.clear_lifecycle_policy",
        ),
        OpSpec(
            "compute.delete_unattached_disk",
            "Delete a persistent disk attached to no instance",
            # Irreversible, and it stays behind a human however much authority the
            # class earns. The ladder governs *confidence*, not consequence.
            reversible=False,
            simulate=_delete_disk,
            expect=lambda p: {"exists": False, "monthly_cost_usd": 0.0},
            damage=Damage(None, "the data is gone unless a snapshot predates the delete"),
        ),
        OpSpec(
            "compute.delete_stale_snapshot",
            "Delete a snapshot older than the retention window",
            reversible=False,
            simulate=_delete_snapshot,
            expect=lambda p: {"exists": False, "monthly_cost_usd": 0.0},
            damage=Damage(None, "a snapshot is the recovery path; deleting it removes one"),
        ),
    ]
}


def simulators() -> dict[str, Callable[[dict, dict], dict]]:
    return {name: spec.simulate for name, spec in SPECS.items()}


def propose_effect(op_class: str, params: dict[str, Any], run_id: str) -> dict:
    """Build the queue entry for one operation, with its post-conditions attached.

    Post-conditions are declared here rather than by the model. A model that writes
    its own success criteria will pass its own exam; the whole verification story
    depends on the two being authored separately.
    """
    spec = SPECS[op_class]
    return {
        "op_class": op_class,
        "params": params,
        "expect": spec.expect(params),
        "reversible": spec.reversible,
        "run_id": run_id,
    }


# --------------------------------------------------------------------------- #
# a small fixture estate — the Monday morning billing alert
# --------------------------------------------------------------------------- #

def sample_estate() -> dict[str, dict[str, Any]]:
    """Realistic wreckage. `target` keys match `ratchet.world.scope_of`."""
    return {
        "compute.stop_idle_instance:ml-train-01": {
            "status": "RUNNING", "machine_type": "a2-highgpu-1g",
            "cpu_7d_avg": 0.4, "monthly_cost_usd": 2632.00, "exists": True,
        },
        "compute.stop_idle_instance:staging-web-3": {
            "status": "RUNNING", "machine_type": "e2-standard-4",
            "cpu_7d_avg": 0.1, "monthly_cost_usd": 97.80, "exists": True,
        },
        "compute.downsize_instance:api-prod-2": {
            "status": "RUNNING", "machine_type": "e2-standard-8",
            "cpu_7d_avg": 6.2, "monthly_cost_usd": 195.60, "exists": True,
        },
        "compute.release_static_ip:legacy-lb-ip": {
            "status": "RESERVED", "attached_to": None, "monthly_cost_usd": 7.30, "exists": True,
        },
        "compute.delete_unattached_disk:pd-ml-scratch": {
            "attached_to": None, "size_gb": 2000, "monthly_cost_usd": 340.00, "exists": True,
        },
        "compute.delete_stale_snapshot:snap-2024-03-11": {
            "age_days": 517, "size_gb": 400, "monthly_cost_usd": 20.00, "exists": True,
        },
        "storage.set_lifecycle_policy:raw-events": {
            "lifecycle_days": None, "size_tb": 14.2, "monthly_cost_usd": 290.50, "exists": True,
        },
    }


def monthly_spend(estate: dict[str, dict[str, Any]]) -> float:
    """What the billing export would report. The number the demo lives or dies on."""
    return round(sum(row.get("monthly_cost_usd", 0.0) for row in estate.values()), 2)


def to_effect(op_class: str, target: str, run_id: str) -> dict:
    """Adapter for `ratchet.graph.build_workflow(to_effect=...)`.

    Raises KeyError for an operation the domain does not define, which is how a
    hallucinated tool name gets dropped instead of executed.
    """
    if op_class not in SPECS:
        raise KeyError(op_class)
    return propose_effect(op_class, {"target": target}, run_id)
