"""The legal gate — three-valued, and timed.

My first design had this as an absolute, unappealable veto. That is wrong, and the
research says so in a way worth stating plainly, because the correction is the
interesting part.

**Blocking is also illegal.** GDPR Art. 5(1)(e) is storage limitation: keeping data
longer than necessary is itself a violation. CNIL fined Free and Free Mobile €42m in
January 2026 on exactly that ground, and the EDPB's February 2026 erasure report
(764 controllers) singles out backups. The ICO's "beyond use" tolerance for backups is
conditional on an *established rotation schedule* — an unrotated three-year-old
snapshot is not a backup, it is an unauthorised archive.

So a gate that answers "never delete" builds the opposite violation. **BLOCK must mean
"escalate to a named human, with an expiry"** — and an escalation nobody answers must
resurface as over-retention risk rather than sitting quietly in a queue forever.

**And absence of a hold signal proves nothing here.** Buckets have real primitives —
Bucket Lock, `temporaryHold`, `eventBasedHold`, retention lock, soft delete. **Disks
and snapshots have none of them**: no retention lock, no immutability, no per-resource
deletion protection. Those are precisely the resources this agent most wants to delete.
Nor is there a published tagging vocabulary for it: the AWS tagging whitepaper and
Azure CAF both canonise classification, owner, environment and cost-centre, and neither
names legal hold. A tag-based veto is therefore fail-open by construction.

Hence three values, not two. `UNKNOWN` is the honest default for a snapshot, and it
must never decay into `CLEAR` through silence.

Nothing here is legal advice; it is an engineering gate built from signals an agent can
actually read, and it says which signals it could not read.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# Resource types with real, readable hold primitives. Anything absent from this set
# yields UNKNOWN rather than CLEAR, however clean it looks.
TYPES_WITH_HOLD_PRIMITIVES = frozenset({"bucket", "object"})

# How long an escalation may sit before it becomes an over-retention concern in its
# own right. Deliberately short: the point is that indecision has a cost.
ESCALATION_EXPIRY_DAYS = 14


class Hold(Enum):
    CLEAR = "clear"       # positive evidence of no hold, and retention satisfied
    HOLD = "hold"         # evidence of a hold — escalate, never silently delete
    UNKNOWN = "unknown"   # no signal exists to read. The default for disks and snapshots

    @property
    def may_delete(self) -> bool:
        return self is Hold.CLEAR


@dataclass
class LegalVerdict:
    state: Hold
    reason: str
    signals_read: list[str] = field(default_factory=list)
    signals_unavailable: list[str] = field(default_factory=list)
    escalate_to: str = ""
    expires_at: float | None = None

    @property
    def may_delete(self) -> bool:
        return self.state.may_delete

    def to_dict(self) -> dict:
        return {
            "state": self.state.value,
            "reason": self.reason,
            "signals_read": self.signals_read,
            "signals_unavailable": self.signals_unavailable,
            "escalate_to": self.escalate_to,
            "expires_at": self.expires_at,
        }


class HoldRegister:
    """An external record of what is under hold.

    For disks and snapshots this is **the only real defence**, because the cloud
    provider offers no primitive to read. That is an uncomfortable design position and
    naming it is better than hiding it: the gate is exactly as good as whatever
    register the organisation actually maintains, and if there is none, every disk is
    UNKNOWN and every deletion is an escalation.
    """

    def __init__(self, entries: dict[str, str] | None = None) -> None:
        self._entries = dict(entries or {})

    def held(self, target: str) -> str | None:
        return self._entries.get(target)

    def place(self, target: str, matter: str) -> None:
        self._entries[target] = matter

    def release(self, target: str) -> None:
        self._entries.pop(target, None)


def assess(
    target: str,
    resource_type: str,
    row: dict[str, Any],
    register: HoldRegister,
    *,
    owner: str = "data-protection@example.com",
    clock=time.time,
) -> LegalVerdict:
    """Decide whether deletion is legally answerable, from readable signals only."""
    read: list[str] = []
    unavailable: list[str] = []

    # 1. The external register outranks everything — it is the only signal that exists
    #    for the resource types we most want to delete.
    matter = register.held(target)
    read.append("hold-register")
    if matter:
        return LegalVerdict(
            Hold.HOLD,
            f"under legal hold for matter {matter!r} — escalated, not deleted",
            read,
            unavailable,
            escalate_to=owner,
            expires_at=clock() + ESCALATION_EXPIRY_DAYS * 86400,
        )

    # 2. Provider primitives, where the resource type actually has any.
    if resource_type in TYPES_WITH_HOLD_PRIMITIVES:
        for key in ("temporaryHold", "eventBasedHold", "retentionPolicyLocked"):
            read.append(key)
            if row.get(key):
                return LegalVerdict(
                    Hold.HOLD,
                    f"{key} is set on this {resource_type}",
                    read,
                    unavailable,
                    escalate_to=owner,
                    expires_at=clock() + ESCALATION_EXPIRY_DAYS * 86400,
                )
    else:
        # Stated, not silently skipped. This is the finding that matters most.
        unavailable.extend(["retention-lock", "immutability", "deletion-protection"])

    # 3. Labels are weak evidence — no published vocabulary defines a hold key, and an
    #    untagged resource is invisible to tag policy. Honoured when present, never
    #    trusted when absent.
    read.append("labels")
    labels = {k.lower(): str(v).lower() for k, v in (row.get("labels") or {}).items()}
    if labels.get("legal-hold") in ("true", "yes", "1") or labels.get("retention") == "locked":
        return LegalVerdict(
            Hold.HOLD,
            "a legal-hold label is present",
            read,
            unavailable,
            escalate_to=owner,
            expires_at=clock() + ESCALATION_EXPIRY_DAYS * 86400,
        )

    if unavailable:
        return LegalVerdict(
            Hold.UNKNOWN,
            f"a {resource_type} exposes no hold primitive — absence of a signal is not "
            f"evidence of absence, so this is an escalation rather than a deletion",
            read,
            unavailable,
            escalate_to=owner,
            expires_at=clock() + ESCALATION_EXPIRY_DAYS * 86400,
        )

    return LegalVerdict(Hold.CLEAR, "no hold signal on a resource type that would carry one", read, unavailable)


# --------------------------------------------------------------------------- #
# escalations that expire
# --------------------------------------------------------------------------- #

@dataclass
class Escalation:
    target: str
    reason: str
    raised_at: float
    expires_at: float
    owner: str
    resolved: bool = False


class EscalationQueue:
    """Escalations with a shelf life.

    A queue that only grows is how "we blocked it for legal reasons" becomes an
    unauthorised archive. Overdue items are reported as an over-retention concern —
    the same class of finding as the deletion we declined to make.
    """

    def __init__(self, clock=time.time) -> None:
        self._items: list[Escalation] = []
        self._clock = clock

    def raise_for(self, target: str, verdict: LegalVerdict) -> Escalation:
        item = Escalation(
            target=target,
            reason=verdict.reason,
            raised_at=self._clock(),
            expires_at=verdict.expires_at or (self._clock() + ESCALATION_EXPIRY_DAYS * 86400),
            owner=verdict.escalate_to,
        )
        self._items.append(item)
        return item

    def resolve(self, target: str) -> None:
        for item in self._items:
            if item.target == target:
                item.resolved = True

    def overdue(self) -> list[Escalation]:
        now = self._clock()
        return [i for i in self._items if not i.resolved and i.expires_at < now]

    def report(self) -> dict:
        overdue = self.overdue()
        return {
            "open": len([i for i in self._items if not i.resolved]),
            "overdue": len(overdue),
            "over_retention_risk": [i.target for i in overdue],
        }


# --------------------------------------------------------------------------- #
# residency — a routing decision, not a veto
# --------------------------------------------------------------------------- #

def crosses_boundary(row: dict[str, Any], permitted_regions: frozenset[str]) -> bool:
    """Whether inspecting this resource would leave the permitted data boundary.

    Google's org-policy location constraints govern only where resources may be
    *created*, so residency never forbids a deletion. What it constrains is **the
    agent**: under Assured Workloads, reading a resource can breach the boundary
    before deleting it would. So this is checked at the top of the pipeline, and the
    resource is routed away rather than proposed and then vetoed.
    """
    where = str(row.get("region") or row.get("zone") or "")
    if not where:
        return False
    return not any(where.startswith(region) for region in permitted_regions)
