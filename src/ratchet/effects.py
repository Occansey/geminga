"""Typed side effects with idempotency keys.

The distinction this module exists to enforce: **checkpointing is not durable
execution.** ADK's resumability is at-least-once — a resumed node may re-run. If the
node wires money, deletes a bucket, or posts a message, "at least once" is a bug with
a nice name.

So every effect carries a key derived from its own content. The executor consults the
effect log before acting and after acting, and a replay of a completed effect returns
the recorded result instead of firing again. That is the property people mean when
they say durable execution, and almost nobody at hackathon scale implements it.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any


def fingerprint(op_class: str, params: dict[str, Any]) -> str:
    """The *shape* of an operation: which keys, which types, which sensitive values.

    Deliberately not the full arguments. Authority is earned for a shape of work, and
    we want "delete a bucket named X" and "delete a bucket named Y" to share earned
    trust — while `project` and `environment` stay in the shape, because deleting in
    prod is not the operation that was rehearsed in scratch.
    """
    shape = {
        k: (params[k] if k in SHAPE_SIGNIFICANT else type(params[k]).__name__)
        for k in sorted(params)
    }
    digest = hashlib.sha256(json.dumps(shape, sort_keys=True, default=str).encode()).hexdigest()
    return f"{op_class}:{digest[:12]}"


# Values that change *which* operation this is, not merely its argument.
SHAPE_SIGNIFICANT = {"project", "environment", "region", "tier", "scope"}


@dataclass
class Effect:
    """One intended mutation of the world."""

    op_class: str
    params: dict[str, Any]
    # What we expect to be true afterwards. The verifier re-derives real state and
    # compares against this — no LLM judge, because a static judge is reward-hackable
    # and this one has to survive an adversary that is also the author.
    expect: dict[str, Any] = field(default_factory=dict)
    reversible: bool = True
    run_id: str = ""

    @property
    def key(self) -> str:
        """Idempotency key. Same effect in the same run = same key = fires once.

        `expect` and `reversible` are part of the identity: two effects with identical
        parameters but different declared contracts are different effects, and
        reversibility in particular is safety-critical metadata the log should not
        collapse.
        """
        body = json.dumps(
            {
                "op": self.op_class, "params": self.params, "run": self.run_id,
                "expect": self.expect, "reversible": self.reversible,
            },
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(body.encode()).hexdigest()[:32]

    @property
    def shape(self) -> str:
        return fingerprint(self.op_class, self.params)

    def to_dict(self) -> dict:
        return {**asdict(self), "key": self.key, "shape": self.shape}


@dataclass
class EffectResult:
    key: str
    op_class: str
    committed: bool
    replayed: bool = False
    observed: dict[str, Any] = field(default_factory=dict)
    error: str = ""
    at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)


class EffectLog:
    """Append-only record of what actually fired. Consulted before every commit."""

    def __init__(self) -> None:
        self._rows: dict[str, EffectResult] = {}

    def seen(self, key: str) -> EffectResult | None:
        return self._rows.get(key)

    def record(self, result: EffectResult) -> EffectResult:
        """A success is written once and never overwritten. A failure is recorded for
        the audit trail but does not claim the key, so a later attempt can supersede
        it."""
        prior = self._rows.get(result.key)
        if prior is not None and prior.committed:
            return prior
        self._rows[result.key] = result
        return result

    def all(self) -> list[EffectResult]:
        return sorted(self._rows.values(), key=lambda r: r.at)


class Actuator:
    """Executes effects exactly once.

    `commit` is the only place in the system permitted to change the world, which is
    what makes "did this fire twice?" a question with a single call site to inspect.
    """

    def __init__(self, log: EffectLog, tools: dict[str, Any]) -> None:
        self._log = log
        self._tools = tools

    def commit(self, effect: Effect) -> EffectResult:
        prior = self._log.seen(effect.key)
        # Only a *successful* commit short-circuits. A failed one never changed the
        # world, so replaying it is correct — and caching the failure as terminal meant
        # a single network blip permanently killed the operation while the module
        # advertised durable execution. Retry is safe here specifically because the
        # verifier re-derives real state afterwards: if the first attempt did land, the
        # observed post-state says so.
        if prior is not None and prior.committed:
            # This is the resume path. The node re-ran; the effect must not.
            return EffectResult(
                key=prior.key,
                op_class=prior.op_class,
                committed=prior.committed,
                replayed=True,
                observed=prior.observed,
                error=prior.error,
            )

        tool = self._tools.get(effect.op_class)
        if tool is None:
            return self._log.record(
                EffectResult(effect.key, effect.op_class, False, error=f"no tool for {effect.op_class!r}")
            )

        try:
            observed = tool(**effect.params) or {}
        except Exception as exc:  # noqa: BLE001 — a tool is arbitrary third-party code
            # and may raise anything. The contract is that a failure is *recorded*, not
            # propagated: an exception escaping here would bypass the effect log and
            # leave the ledger unable to say whether the world changed.
            return self._log.record(
                EffectResult(effect.key, effect.op_class, False, error=f"{type(exc).__name__}: {exc}")
            )

        return self._log.record(
            EffectResult(effect.key, effect.op_class, True, observed=dict(observed))
        )
