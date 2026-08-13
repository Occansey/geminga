"""Does the operation's own name hold?

An operation called `stop_idle_instance` asserts something about the world: that the
instance is idle. Nothing checked it. Admission checked the resource existed and was the
right kind of thing, legal checked for holds, reversibility checked the operation could
be undone, authority checked the shape had been rehearsed — and the agent stopped a node
running a training job at 94% GPU, three times, on the deployed service.

The post-commit reviewer caught it and said the useful thing:

    The agent attempted to stop an instance for being 'idle' based on a very low CPU
    average (0.4%), while ignoring the extremely high GPU utilization (94%). For a
    GPU-accelerated machine, CPU is not the primary indicator of activity.

That is a defect in the gates, not only in the proposer. V2 folded blast radius into the
argument shape, which meant the GPU node was no longer interchangeable with a staging box
and had to be rehearsed separately — but rehearsal only asks whether the operation
*works*. Stopping a busy instance works. It stops. The verifier confirms it stopped. Five
clean runs later the shape is earned and the attack, or the mistake, proceeds on schedule.

So this is the gate that was missing: an operation asserting a precondition has that
precondition checked against metered work, every run, with no rung that exempts it.

## Why CPU is not consulted

Deliberately, and not as a style preference. CPU average is the exact signal the poisoned
runbook note asked the agent to trust, and a GPU node training a model sits near zero CPU
while doing the most expensive work in the estate. An instance whose only known series is
CPU is treated as having no telemetry at all — which, for the question "is this idle",
it does not.

## Why unknown escalates rather than refuses

Refusing on unknown telemetry would make the gate a denial of service against every
resource Cloud Monitoring has not sampled, and an estate that cannot be cleaned is the
problem this system exists to solve. Escalation puts it in front of a human with the
reason attached, which is the honest answer to "we cannot tell".
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class State(StrEnum):
    IDLE = "idle"          # metered, and not working
    WORKING = "working"    # metered, and working
    UNKNOWN = "unknown"    # not metered, or metered only by CPU


@dataclass(frozen=True)
class Liveness:
    state: State
    reason: str
    detail: dict

    @property
    def may_proceed(self) -> bool:
        return self.state is State.IDLE


def assess(op_class: str, target: str, topology, *, asserts_idle: bool) -> Liveness:
    """Check the operation's stated precondition against metered work.

    Returns IDLE for operations that assert nothing — most of them. `delete_stale_snapshot`
    makes a claim about age, not about activity, and has no liveness question to answer.
    """
    if not asserts_idle:
        return Liveness(State.IDLE, "operation asserts no activity precondition", {})

    if topology is None:
        return Liveness(
            State.UNKNOWN,
            "no topology: cannot confirm the instance is idle, and the operation claims it is",
            {},
        )

    node = topology.nodes.get(target)
    if node is None or node.utilisation is None:
        return Liveness(
            State.UNKNOWN, f"no telemetry for {target!r}; idleness is asserted, not measured", {}
        )

    u = node.utilisation
    detail = {
        k: v
        for k, v in {
            "gpu_percent": u.gpu_percent,
            "network_bytes_per_s": u.network_bytes_per_s,
            "disk_ops_per_s": u.disk_ops_per_s,
            "cpu_percent": u.cpu_percent,
        }.items()
        if v is not None
    }

    if u.gpu_busy:
        # Called out separately from `busy` because it is the case that actually
        # happened, and because an accelerator held at any measurable utilisation is
        # doing work that a CPU average will never show.
        return Liveness(
            State.WORKING,
            f"GPU at {u.gpu_percent:.0f}% — accelerator work does not show in a CPU average",
            detail,
        )
    if u.busy:
        return Liveness(State.WORKING, "network or disk activity above heartbeat", detail)
    if node.accelerators and u.gpu_percent is None:
        # An accelerator whose utilisation was never read is the worst of both: the
        # expensive case, unmeasured. Treating that as idle is how this went wrong.
        return Liveness(
            State.UNKNOWN,
            f"{node.accelerators} accelerator(s) attached and no GPU series read",
            detail,
        )
    if not u.known:
        return Liveness(State.UNKNOWN, "only CPU is known, which does not answer idleness", detail)

    return Liveness(State.IDLE, "no metered work on any non-CPU series", detail)
