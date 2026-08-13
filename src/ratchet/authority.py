"""Earned autonomy: authority as a measured, per-operation, revocable budget.

The field's answer to "may the agent act?" is almost unanimously *no* — the agent
prepares, a human sends. The prior hackathon's winners answered *yes, with a brake*.
Both fix autonomy at design time.

Here it is a control loop. Every operation class starts in SHADOW and climbs only on
evidence: k consecutive runs where a post-condition verifier that re-derives real
environment state agreed with the predicted delta. One disagreement drops it a rung
and resets the counter. The ratchet turns both ways, per operation class, forever.

The point is expansionary, not restrictive: this exists so the agent can be permitted
to do *more* over time than a human-gated design ever allows.

No ADK, no cloud imports here on purpose — this is the part that has to be provable
in a unit test.
"""

from __future__ import annotations

import random
import time
from dataclasses import asdict, dataclass, field
from enum import IntEnum


class Authority(IntEnum):
    """Rungs. Ordered so promotion/demotion is arithmetic."""

    SHADOW = 0       # simulate against virtualized tools; never commit
    PROVISIONAL = 1  # commit for real, verify every single run, one failure demotes
    LIVE = 2         # commit for real, verify a sample

    @property
    def commits(self) -> bool:
        return self >= Authority.PROVISIONAL

    @property
    def label(self) -> str:
        return self.name.lower()


# How many consecutive verified passes are required to leave a rung.
PROMOTION_THRESHOLD = {Authority.SHADOW: 5, Authority.PROVISIONAL: 10}

# Fraction of LIVE runs still verified. Never zero — an unwatched rung cannot demote,
# and a ratchet that cannot turn back is just a permission grant with extra steps.
LIVE_VERIFY_SAMPLE = 0.2


@dataclass
class OperationRecord:
    """The standing of one operation class, e.g. "gcs.delete_bucket"."""

    op_class: str
    authority: Authority = Authority.SHADOW
    streak: int = 0
    passes: int = 0
    failures: int = 0
    demotions: int = 0
    last_change: float = 0.0
    last_reason: str = "created in shadow"
    # Envelope of parameter fingerprints seen during shadow. An operation outside
    # everything it has rehearsed is not the operation it earned authority for.
    envelope: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["authority"] = int(self.authority)
        return d

    @classmethod
    def from_dict(cls, raw: dict) -> OperationRecord:
        raw = dict(raw)
        raw["authority"] = Authority(raw.get("authority", 0))
        return cls(**raw)


@dataclass
class Decision:
    """What the gate decided, and the evidence for it. This is what the UI renders."""

    op_class: str
    authority: Authority
    commits: bool
    verify: bool
    reason: str
    in_envelope: bool = True


class AuthorityLedger:
    """The ratchet itself. Pure logic over a pluggable store."""

    def __init__(self, store: LedgerStore | None = None, clock=time.time) -> None:
        self._store = store or MemoryLedgerStore()
        self._clock = clock

    # -- reading ---------------------------------------------------------- #

    def record(self, op_class: str) -> OperationRecord:
        existing = self._store.load(op_class)
        if existing:
            return existing
        fresh = OperationRecord(op_class=op_class, last_change=self._clock())
        self._store.save(fresh)
        return fresh

    def decide(self, op_class: str, fingerprint: str, sampler=None) -> Decision:
        """Decide how this specific attempt may run.

        `fingerprint` describes the *shape* of the arguments, not their values, so
        that "delete a bucket in the scratch project" and "delete a bucket in prod"
        are different operations even though the tool is the same.
        """
        rec = self.record(op_class)
        known = fingerprint in rec.envelope

        if rec.authority.commits and not known:
            # Earned authority does not transfer to a shape it never rehearsed.
            return Decision(
                op_class=op_class,
                authority=Authority.SHADOW,
                commits=False,
                verify=True,
                reason=f"authority is {rec.authority.label} but this argument shape is unrehearsed",
                in_envelope=False,
            )

        if rec.authority is Authority.LIVE:
            # The default used to be the constant LIVE_VERIFY_SAMPLE compared against
            # (1 - LIVE_VERIFY_SAMPLE) — 0.2 >= 0.8, false every time. A rung advertised
            # as 20% sampled was verified 0% of the time, and a rung that is never
            # watched can never fall.
            draw = sampler() if sampler else random.random()
            verify = draw < LIVE_VERIFY_SAMPLE
            return Decision(
                op_class, rec.authority, True, verify,
                f"live after {rec.passes} verified runs; "
                + ("sampled for verification" if verify else "not sampled this run"),
            )

        if rec.authority is Authority.PROVISIONAL:
            needed = PROMOTION_THRESHOLD[Authority.PROVISIONAL] - rec.streak
            return Decision(
                op_class, rec.authority, True, True,
                f"provisional — every run verified, {needed} more to promote",
            )

        needed = PROMOTION_THRESHOLD[Authority.SHADOW] - rec.streak
        return Decision(
            op_class, rec.authority, False, True,
            f"shadow — simulated only, {needed} more clean rehearsals to earn commit",
        )

    # -- writing ---------------------------------------------------------- #

    def observe(self, op_class: str, fingerprint: str, passed: bool, detail: str = "") -> OperationRecord:
        """Record a verified outcome and move the ratchet.

        Called after verification, never after mere execution — an operation that ran
        without being checked is not evidence of anything.
        """
        rec = self.record(op_class)

        if passed:
            rec.passes += 1
            rec.streak += 1
            if fingerprint not in rec.envelope:
                rec.envelope.append(fingerprint)
            threshold = PROMOTION_THRESHOLD.get(rec.authority)
            if threshold is not None and rec.streak >= threshold:
                rec.authority = Authority(rec.authority + 1)
                rec.streak = 0
                rec.last_change = self._clock()
                rec.last_reason = f"promoted to {rec.authority.label} after {threshold} clean runs"
            else:
                rec.last_reason = detail or f"pass ({rec.streak} in a row)"
        else:
            rec.failures += 1
            rec.streak = 0
            if rec.authority > Authority.SHADOW:
                rec.authority = Authority(rec.authority - 1)
                rec.demotions += 1
                rec.last_change = self._clock()
                rec.last_reason = f"demoted to {rec.authority.label}: {detail or 'verification failed'}"
            else:
                rec.last_reason = f"failed in shadow: {detail or 'verification failed'}"

        self._store.save(rec)
        return rec

    def restrict(self, op_class: str, to: Authority, reason: str = "") -> OperationRecord:
        """Lower an operation's standing. It is not possible to raise it through here.

        Authority is only ever granted by `observe`, and only in exchange for verified
        clean runs. This is the other door, and it opens one way. The clamp is the
        invariant: a caller asking for a *higher* rung gets the rung it already had,
        silently and safely, rather than an exception it might be tempted to catch.

        That matters because the caller is `ratchet.review`, which is driven by a
        language model. Everything a model can influence has to be incapable of
        widening anything by construction, not merely unlikely to.
        """
        rec = self.record(op_class)
        floor = Authority(min(int(to), int(rec.authority)))
        if floor != rec.authority:
            rec.authority = floor
            rec.demotions += 1
            rec.last_change = self._clock()
        rec.streak = 0
        rec.last_reason = reason or f"restricted to {rec.authority.label}"
        self._store.save(rec)
        return rec

    def board(self) -> list[OperationRecord]:
        """Every operation class and its standing — the thing the UI draws."""
        return sorted(self._store.all(), key=lambda r: (-int(r.authority), r.op_class))


# ------------------------------------------------------------------------- #
# stores
# ------------------------------------------------------------------------- #

class LedgerStore:
    def load(self, op_class: str) -> OperationRecord | None: ...
    def save(self, record: OperationRecord) -> None: ...
    def all(self) -> list[OperationRecord]: ...


class MemoryLedgerStore(LedgerStore):
    def __init__(self) -> None:
        self._rows: dict[str, dict] = {}

    def load(self, op_class: str) -> OperationRecord | None:
        raw = self._rows.get(op_class)
        return OperationRecord.from_dict(raw) if raw else None

    def save(self, record: OperationRecord) -> None:
        self._rows[record.op_class] = record.to_dict()

    def all(self) -> list[OperationRecord]:
        return [OperationRecord.from_dict(r) for r in self._rows.values()]


class FirestoreLedgerStore(LedgerStore):
    COLLECTION = "authority_ledger"

    def __init__(self, project: str | None = None) -> None:
        from google.cloud import firestore

        self._db = firestore.Client(project=project)

    def load(self, op_class: str) -> OperationRecord | None:
        snap = self._db.collection(self.COLLECTION).document(op_class).get()
        return OperationRecord.from_dict(snap.to_dict()) if snap.exists else None

    def save(self, record: OperationRecord) -> None:
        self._db.collection(self.COLLECTION).document(record.op_class).set(record.to_dict())

    def all(self) -> list[OperationRecord]:
        return [OperationRecord.from_dict(d.to_dict()) for d in self._db.collection(self.COLLECTION).stream()]
