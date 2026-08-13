"""Action-side admission control — the defence that does not depend on detection.

**Why this exists rather than a content filter.** LogJack (arXiv 2604.15368, 2026)
benchmarked prompt-injection payloads embedded in cloud logs and operational text
against production guardrails: **Model Armor detected 0 of 32**, Azure Prompt Shield 1
of 32, and Bedrock does not inspect tool results at all. Every one of them catches the
*same* payloads presented as bare text — the operational formatting is the camouflage.
Reported hijack rates reached 54% on Gemini 2.5 Pro.

The conclusion is not "use a better filter". It is that **detection is the wrong layer**.
This module assumes injection succeeds and makes success useless: the model may propose
anything it likes, and only proposals that survive deterministic, non-LLM checks reach
an actuator.

That gives a claim which is true rather than hopeful: *a prompt injection cannot cause
an unplanned deletion.* Not because we spotted it — because the proposal did not appear
in the plan-time inventory, or its verb is not allowlisted, or the verb is one no
amount of persuasion unlocks.

Model Armor still ships, at the perception boundary. It is named in the track's toolkit
and costs nothing at our volume, and it will catch the naive payloads. It is a layer,
not the answer, and the submission says so.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import unicodedata
from dataclasses import dataclass, field
from typing import Any

# Verbs no persuasion unlocks. Not risk-tiered — absent from the vocabulary entirely,
# so there is no state of the system in which the agent performs them.
FORBIDDEN_VERBS = frozenset({
    "iam.setPolicy", "iam.grant", "iam.createServiceAccount", "iam.setIamPolicy",
    "compute.setMetadata", "compute.setServiceAccount",
    "projects.delete", "billing.update", "org.setPolicy",
})

# Every operation the agent knows, mapped explicitly to (resource type, verb).
# Explicit rather than parsed out of the name: substring-guessing silently failed to
# resolve `release_static_ip` to an address at all, and a security control that fails
# by returning "unknown" is a security control that fails open the moment someone
# renames something.
OPERATIONS: dict[str, tuple[str, str]] = {
    "compute.stop_idle_instance": ("instance", "stop"),
    "compute.start_instance": ("instance", "start"),
    "compute.downsize_instance": ("instance", "resize"),
    "compute.delete_unattached_disk": ("disk", "delete"),
    "compute.release_static_ip": ("address", "release"),
    "compute.delete_stale_snapshot": ("snapshot", "delete"),
    "storage.set_lifecycle_policy": ("bucket", "set_lifecycle"),
    "storage.clear_lifecycle_policy": ("bucket", "clear_lifecycle"),
}

# What each resource type may have done to it. An operation naming a resource type
# it was not written for is refused, however plausible it sounds.
VERB_ALLOWLIST: dict[str, frozenset[str]] = {
    "instance": frozenset({"stop", "start", "resize"}),
    "disk": frozenset({"delete", "snapshot"}),
    "address": frozenset({"release"}),
    "snapshot": frozenset({"delete"}),
    "bucket": frozenset({"set_lifecycle", "clear_lifecycle"}),
}

# Savings above this are treated as a hijack signature rather than a windfall. A
# genuine reclamation on a small estate does not save five figures a month; a payload
# talking the model into deleting the fleet does.
IMPLAUSIBLE_MONTHLY_SAVING_USD = 1000.0

_ZERO_WIDTH = dict.fromkeys(map(ord, "​‌‍⁠﻿"))
_INSTRUCTION_BAIT = re.compile(
    r"(ignore\s+(all\s+)?previous|disregard\s+(the\s+)?above|system\s*:|"
    r"you\s+are\s+now|new\s+instructions?|<\s*!--|curl\s+[^|]*\|\s*(ba)?sh)",
    re.IGNORECASE,
)


# --------------------------------------------------------------------------- #
# perception: untrusted metadata
# --------------------------------------------------------------------------- #

@dataclass
class Sanitised:
    text: str
    suspicious: bool
    dropped_fields: list[str] = field(default_factory=list)


def sanitise_metadata(fields: dict[str, Any], run_nonce: str) -> Sanitised:
    """Wrap attacker-influenceable resource metadata before a model ever sees it.

    Cloud metadata is not data the operator wrote — VM names, labels, descriptions and
    bucket names are all writable by whoever can create resources, and in many estates
    that is a wide set. Startup scripts are dropped entirely: nothing in a reclamation
    decision needs them, and they are the richest payload carrier on the machine.

    The per-run nonce delimiter means a payload cannot close the envelope it is in,
    because it cannot know the delimiter.
    """
    dropped: list[str] = []
    suspicious = False
    lines: list[str] = []

    for key, value in sorted(fields.items()):
        if key in ("startup-script", "user-data", "metadata", "shutdown-script"):
            dropped.append(key)
            continue

        text = unicodedata.normalize("NFKC", str(value)).translate(_ZERO_WIDTH)
        text = "".join(ch for ch in text if ch.isprintable() or ch in " \t")
        if _INSTRUCTION_BAIT.search(text):
            suspicious = True
        # Neutralise the delimiter shape and protocol-relative URLs.
        text = text.replace("<!--", "").replace("-->", "").replace("//", "/ /")
        lines.append(f"{key}={text[:200]}")

    body = "\n".join(lines)
    envelope = (
        f"<untrusted-inventory nonce={run_nonce}>\n{body}\n</untrusted-inventory nonce={run_nonce}>"
    )
    return Sanitised(envelope, suspicious, dropped)


# --------------------------------------------------------------------------- #
# action: the plan-time snapshot
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class Snapshot:
    """Inventory as it stood when planning began, and its digest.

    Admission checks the *snapshot*, not live inventory. A resource that appeared
    after planning cannot be acted on in this run — which closes the window in which
    an attacker creates bait mid-flight.
    """

    targets: frozenset[str]
    digest: str

    @classmethod
    def of(cls, estate: dict[str, dict[str, Any]]) -> "Snapshot":
        """Keyed by *resource*, not by operation.

        "Did this resource exist when we planned?" is a question about the resource.
        Keying by `op_class:target` conflated it with "is this operation known", and
        made every novel operation on a familiar resource look like an attacker
        conjuring bait mid-flight.
        """
        keys = sorted(estate)
        targets = {k.split(":", 1)[1] for k in keys if ":" in k}
        digest = hashlib.sha256("\n".join(keys).encode()).hexdigest()[:16]
        return cls(frozenset(targets), digest)


@dataclass
class Admission:
    allowed: bool
    reason: str
    check: str = ""

    def to_dict(self) -> dict:
        return {"allowed": self.allowed, "reason": self.reason, "check": self.check}


def admit(
    op_class: str,
    target: str,
    snapshot: Snapshot,
    *,
    resource_type: str = "",
    verb: str = "",
    claimed_saving_usd: float = 0.0,
) -> Admission:
    """Deterministic gate. No model, no probability, no prompt.

    Order is deliberate: the cheapest and most absolute checks run first, so a
    refusal costs nothing and the reason returned is the most fundamental one.
    """
    known = OPERATIONS.get(op_class)
    parsed_type = resource_type or (known[0] if known else "")
    parsed_verb = verb or (known[1] if known else op_class.split(".")[-1])

    if parsed_verb in FORBIDDEN_VERBS or op_class in FORBIDDEN_VERBS:
        return Admission(False, f"{op_class!r} is not in the agent's vocabulary", "forbidden-verb")

    if target not in snapshot.targets:
        return Admission(
            False,
            f"{target!r} was not in the inventory snapshot {snapshot.digest} taken at plan time",
            "not-in-snapshot",
        )

    allowed_verbs = VERB_ALLOWLIST.get(parsed_type)
    if allowed_verbs is None:
        return Admission(False, f"unknown resource type {parsed_type!r}", "unknown-type")
    if parsed_verb not in allowed_verbs:
        return Admission(
            False,
            f"{parsed_verb!r} is not permitted on a {parsed_type}",
            "verb-not-allowlisted",
        )

    if claimed_saving_usd > IMPLAUSIBLE_MONTHLY_SAVING_USD:
        return Admission(
            False,
            f"claimed saving ${claimed_saving_usd:,.2f}/mo exceeds the plausible ceiling "
            f"— treated as a hijack signature, not a windfall",
            "implausible-saving",
        )

    return Admission(True, f"admitted against snapshot {snapshot.digest}", "ok")


def new_nonce() -> str:
    return secrets.token_hex(8)
