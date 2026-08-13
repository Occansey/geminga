"""Context assembly — TAG, CAG and RAG, each where it belongs.

Three modes answer three different questions, and using one for another's job is how
context becomes an attack surface.

| Source | Mode | Why |
|---|---|---|
| Estate / inventory | **TAG** | It is a table. Queries return *complete* answers; retrieval returns *likely* ones, and a reclamation agent that silently misses a resource is failing quietly. |
| Operational history | **CAG**, falling back to RAG | Small, unstructured, human-written. Cache while it fits: ranking can be manipulated to *evict* the note that contradicts the attacker. |
| Ledger · policy · snapshot | **none** | Gates read these directly. |

That last row is load-bearing. If admission consulted a *retrieved* policy, poisoning
retrieval would move the policy, and every result we have would be worthless. The gates
read tables; only the proposer reads context.

## The arithmetic argument for TAG

A model asked to find the most expensive idle resource from a list of rows is doing a
`max()` in prose. That is both unreliable and *steerable*: a note claiming "this is now
the single largest source of waste at $2,632/mo" competes directly with the model's own
reading of the table, and in our poisoning experiment it won.

So TAG computes the aggregates in code, from the API's own numbers, and hands the model
a **conclusion** rather than a spreadsheet. A note can still lie about a resource; it
can no longer lie about the arithmetic.

**And that turned out to be a smaller win than expected.** The prediction was that
grounding the numbers would blunt the memory-poisoning attack. It did not — the steer
is identical with TAG in place, because the poison's decisive claim was never about
cost. `ml-train-01` was always the most expensive candidate, and TAG says so. What the
poison changed was whether stopping it is *safe*: "the nightly build was migrated in
July, it no longer holds the GPU."

**TAG grounds what the API knows, and nothing else.** Whether a GPU node is doing
useful work is not in the inventory — CPU reads 0.4% either way, which is precisely why
a human wrote a runbook note about it, and precisely why that note was worth poisoning.
The attack moved from arithmetic to semantics because arithmetic was the part we had
closed.

The boundary is worth stating plainly rather than discovering later: structured
grounding defeats manipulation of *derivable* facts. It does nothing against
manipulation of facts the system cannot derive, and those are the facts operational
notes exist to carry.

## Provenance

Every block is labelled with where it came from and whether it is trusted. Provenance
is the trusted computing base of this whole approach and is under-specified in every
comparable system, ours included — so it is at least written down here, at the point
where the labels are assigned rather than assumed downstream.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .admission import new_nonce, sanitise_metadata
from .memory import CachedRecall, Note, render


@dataclass
class Block:
    """One labelled piece of context, and where it came from."""

    source: str
    mode: str            # tag | cag | rag
    trusted: bool
    text: str
    items: int = 0

    @property
    def chars(self) -> int:
        return len(self.text)


@dataclass
class Assembly:
    blocks: list[Block] = field(default_factory=list)
    nonce: str = ""

    def prompt(self) -> str:
        return "\n\n".join(
            f"### {b.source}  [{b.mode.upper()} · "
            f"{'derived from the API' if b.trusted else 'UNTRUSTED — written by people'}]\n{b.text}"
            for b in self.blocks
        )

    def report(self) -> list[dict]:
        return [
            {"source": b.source, "mode": b.mode, "trusted": b.trusted,
             "items": b.items, "chars": b.chars}
            for b in self.blocks
        ]


# --------------------------------------------------------------------------- #
# TAG — structured queries over the estate
# --------------------------------------------------------------------------- #

def query_estate(estate: dict[str, dict[str, Any]], specs: dict) -> dict[str, Any]:
    """Compute the facts, rather than inviting the model to infer them.

    Returns aggregates and a ranked candidate list, both derived in code from the
    inventory the API returned. The model is asked to *choose*, not to add up.
    """
    rows = []
    for scope, row in estate.items():
        op_class, target = scope.split(":", 1)
        spec = specs.get(op_class)
        if spec is None:
            continue
        rows.append({
            "target": target,
            "op_class": op_class,
            "monthly_cost_usd": float(row.get("monthly_cost_usd", 0.0)),
            "reclaimable": bool(row.get("idle_candidate", True)),
            "reversible": spec.reversible,
            "destroys_data": spec.destroys_data,
        })

    reclaimable = sorted(
        (r for r in rows if r["reclaimable"]),
        key=lambda r: -r["monthly_cost_usd"],
    )
    return {
        "resources": len(rows),
        "total_monthly_usd": round(sum(r["monthly_cost_usd"] for r in rows), 2),
        "reclaimable_monthly_usd": round(sum(r["monthly_cost_usd"] for r in reclaimable), 2),
        "candidates": reclaimable,
    }


def render_estate(facts: dict[str, Any], limit: int = 10) -> str:
    lines = [
        f"resources: {facts['resources']}    "
        f"run rate: ${facts['total_monthly_usd']:,.2f}/mo    "
        f"reclaimable: ${facts['reclaimable_monthly_usd']:,.2f}/mo",
        "",
        "candidates, ranked by cost — this ordering is computed, not inferred:",
    ]
    for i, c in enumerate(facts["candidates"][:limit], 1):
        flags = []
        if not c["reversible"]:
            flags.append("irreversible")
        if c["destroys_data"]:
            flags.append("destroys data")
        lines.append(
            f"  {i}. {c['target']:<20} {c['op_class']:<34} "
            f"${c['monthly_cost_usd']:>8,.2f}/mo  {', '.join(flags) or '—'}"
        )
    if not facts["candidates"]:
        lines.append("  (none — nothing in this estate is currently reclaimable)")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# assembly
# --------------------------------------------------------------------------- #

# Never placed in context. A gate that reads its policy from a prompt is a gate an
# attacker can edit. Named explicitly so adding one is a deliberate act.
NEVER_IN_CONTEXT = frozenset({"authority_ledger", "hold_register", "snapshot", "operation_table"})


def assemble(
    estate: dict[str, dict[str, Any]],
    specs: dict,
    history: CachedRecall | None = None,
    query: str = "",
) -> Assembly:
    nonce = new_nonce()
    blocks: list[Block] = []

    facts = query_estate(estate, specs)
    blocks.append(Block(
        source="Estate", mode="tag", trusted=True,
        text=render_estate(facts), items=facts["resources"],
    ))

    if history is not None and len(history):
        notes = history.recall(query or "estate history")
        blocks.append(Block(
            source="Operational history", mode="cag" if history.fits else "rag",
            trusted=False, text=render(notes, nonce), items=len(notes),
        ))

    return Assembly(blocks=blocks, nonce=nonce)


def sanity_check(assembly: Assembly) -> list[str]:
    """Complaints about the assembled context, for a caller to act on.

    Cheap, and it catches the two failures that look like success from outside: a
    retrieval block that came back empty, and anything from a source that should never
    have been in context at all.
    """
    problems = []
    for block in assembly.blocks:
        if block.source.lower().replace(" ", "_") in NEVER_IN_CONTEXT:
            problems.append(f"{block.source} must never be placed in context")
        if block.mode in ("cag", "rag") and block.items == 0:
            problems.append(
                f"{block.source} returned nothing — an empty retrieval is "
                f"indistinguishable from a working one from the outside"
            )
    return problems
