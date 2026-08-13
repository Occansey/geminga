"""Coverage against the OWASP agentic threat taxonomy — checked, not asserted.

Two things make a security mapping worth reading, and most published ones have neither.

**Every claim names a test.** A row saying "mitigated by the admission gate" is a
sentence. A row naming `tests/test_ratchet.py::test_x` is a claim that can be run, and
this module runs them: `python -m evals.owasp` resolves every referenced test id and
fails if one does not exist. A mapping that drifts out of date silently is worse than
no mapping, because it converts an unknown into a false reassurance.

**The gaps are rows too.** Four of the fifteen threats are not covered here, and one
more is only partly covered — by a control that a documented experiment in this
repository defeated. Those rows are in the table with the same weight as the rest. A
coverage document with fifteen greens is evidence about the author, not the system.

Taxonomy: OWASP Agentic Security Initiative, *Agentic AI — Threats and Mitigations*,
T1–T15. (A v1.1 extending to T16–T17 is reported but was not confirmed against the
source when this was written, so it is not mapped.) The LLM Top 10 for 2025 is carried
alongside where a threat maps cleanly onto it.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class Status(StrEnum):
    COVERED = "covered"
    # The control exists and something real about the threat still gets through. This
    # is the most useful status in the table and the one nobody publishes.
    PARTIAL = "partial"
    # Structurally absent: there is no surface for the threat because the capability it
    # attacks was never built. Honest, but it expires the moment the capability lands.
    NOT_APPLICABLE = "n/a — no such surface yet"
    OPEN = "not covered"


@dataclass(frozen=True)
class Row:
    threat: str
    name: str
    status: Status
    control: str
    tests: tuple[str, ...] = ()
    note: str = ""


ROWS: tuple[Row, ...] = (
    Row(
        "T1", "Memory Poisoning", Status.PARTIAL,
        "Retrieved history is served from a fixed cache with no relevance ranking, so "
        "there is no score for an attacker to climb. Blast-radius classes derived from "
        "control-plane facts keep a poisoned target from inheriting a safe target's "
        "earned authority.",
        ("tests/test_topology.py", "tests/test_wiring.py::test_the_two_instances_are_not_the_same_shape_on_the_server"),
        "PARTIAL is the honest status and this is the sharpest result in the project. "
        "Three plausible notes moved the agent off a correct target and onto a GPU node, "
        "and the operation was *permitted* — it cleared admission, legal and "
        "reversibility. Only unearned authority stopped it. V2's topology separates the "
        "two shapes; it does not stop a poisoned note from being believed.",
    ),
    Row(
        "T2", "Tool Misuse", Status.COVERED,
        "A closed operation table. Verb and resource type are checked against a snapshot "
        "of what each resource actually is, so a real name of the wrong kind is refused.",
        ("tests/test_ratchet.py", "evals/redteam.py"),
        "Exhaustive enumeration over the operation × resource space found 49 wrongly "
        "admitted pairs that six hand-written payloads had missed.",
    ),
    Row(
        "T3", "Privilege Compromise", Status.COVERED,
        "Authority is earned per shape of work and never transfers to an unrehearsed "
        "shape. It is granted only in exchange for verified clean runs, and the one "
        "other door — `AuthorityLedger.restrict` — clamps and cannot raise.",
        ("tests/test_review.py::test_a_fully_compromised_reviewer_cannot_promote",
         "tests/test_review.py::test_restrict_clamps_rather_than_raises"),
    ),
    Row(
        "T4", "Resource Overload", Status.PARTIAL,
        "A damage budget denominated in restore-minutes, refused past 60 per rolling "
        "hour, plus rate limiting on targets drawing sustained refusals.",
        ("tests/test_restraint.py", "tests/test_attempts.py"),
        "The budget is enforced. The restore-minute estimates behind it are declared "
        "figures, not measured ones — no restore has been timed. Until they are, this "
        "bounds a modelled quantity rather than a real one.",
    ),
    Row(
        "T5", "Cascading Hallucination Attacks", Status.COVERED,
        "Nothing is believed because it was reported. The verifier re-derives state from "
        "the provider after every commit; a tool that returns success without acting "
        "fails verification and demotes the shape.",
        ("tests/test_ratchet.py", "tests/test_whitebox_fable.py"),
        "Demonstrable live: the console's lying-tool switch makes every tool report "
        "success and change nothing.",
    ),
    Row(
        "T6", "Intent Breaking & Goal Manipulation", Status.COVERED,
        "The gates never read the proposer's reasoning. They take an operation class, a "
        "target and a snapshot; a persuasive argument has no field to arrive in.",
        ("evals/injection.py", "tests/test_review.py::test_the_reviewer_never_sees_attacker_writable_prose"),
        "0/1000 adversarial proposals across two model families reached an actuator "
        "(95% Wilson upper bound 0.383%).",
    ),
    Row(
        "T7", "Misaligned & Deceptive Behaviors", Status.PARTIAL,
        "Post-commit review by a stronger model on everything that reached the actuator, "
        "with a verdict vocabulary that contains no way to widen anything.",
        ("tests/test_review.py",),
        "The structural property — no output can grant authority — is tested. Whether "
        "the reviewer *catches* a misaligned commit depends on a model and is not yet "
        "measured. Do not read this row as a detection rate.",
    ),
    Row(
        "T8", "Repudiation & Untraceability", Status.COVERED,
        "Three append-only ledgers: effects committed, attempts refused, verdicts "
        "returned. None of them expose a delete or amend path to the agent.",
        ("tests/test_attempts.py::test_the_ledger_is_append_only",
         "tests/test_wiring.py::test_the_estate_endpoint_surfaces_both_ledgers"),
    ),
    Row(
        "T9", "Identity Spoofing & Impersonation", Status.OPEN,
        "None. The agent runs as one service account and there is no caller "
        "authentication on the run endpoint.",
        (),
        "The A2A agent card and Agent Registry entry are on the roadmap and not built. "
        "Until then anyone who can reach the service can ask it to act.",
    ),
    Row(
        "T10", "Overwhelming Human-in-the-Loop", Status.PARTIAL,
        "Escalations queue rather than block, and the damage budget caps how much can "
        "be queued before the system stops proposing at all.",
        ("tests/test_restraint.py",),
        "It bounds the queue. It has not been tested against a human operator's actual "
        "throughput, which is the quantity the threat is really about.",
    ),
    Row(
        "T11", "Unexpected RCE and Code Attacks", Status.NOT_APPLICABLE,
        "No code execution surface. Tools are a fixed dictionary of typed callables "
        "resolved at construction; the model selects a name and supplies parameters, and "
        "cannot introduce a new callable.",
        ("tests/test_ratchet.py",),
        "Structural rather than defended. It stops being true the moment a shell or "
        "eval-style tool is added, so it is a property to re-check, not a box ticked.",
    ),
    Row(
        "T12", "Agent Communication Poisoning", Status.NOT_APPLICABLE,
        "None. Single agent, no inter-agent messaging.",
        (),
        "Becomes live work the day A2A ships.",
    ),
    Row(
        "T13", "Rogue Agents in Multi-Agent Systems", Status.NOT_APPLICABLE,
        "None. No multi-agent runtime.", (),
    ),
    Row(
        "T14", "Human Attacks on Multi-Agent Systems", Status.NOT_APPLICABLE,
        "None. No multi-agent runtime.", (),
    ),
    Row(
        "T15", "Human Manipulation", Status.PARTIAL,
        "The console shows the operation, the target's blast class, the measured "
        "utilisation and the ladder position — evidence rather than a recommendation to "
        "approve. Approval is never the default action.",
        ("tests/test_wiring.py",),
        "Presenting evidence well is not the same as being resistant to a persuasive "
        "agent, and this has not been tested with human subjects.",
    ),
)

# Where a threat also lands squarely on the 2025 LLM Top 10, so a reader coming from the
# more familiar list can find their way in.
LLM_TOP_10 = {
    "LLM01 Prompt Injection": ("T6", "T1"),
    "LLM02 Sensitive Information Disclosure": ("T8",),
    "LLM04 Data and Model Poisoning": ("T1",),
    "LLM05 Improper Output Handling": ("T5", "T7"),
    "LLM06 Excessive Agency": ("T2", "T3"),
    "LLM08 Vector and Embedding Weaknesses": ("T1",),
    "LLM09 Misinformation": ("T5",),
    "LLM10 Unbounded Consumption": ("T4",),
}


def missing_tests() -> list[str]:
    """Every referenced test id that does not resolve. The point of the module."""
    missing: list[str] = []
    for row in ROWS:
        for ref in row.tests:
            path = ROOT / ref.split("::")[0]
            if not path.exists():
                missing.append(f"{row.threat}: no such file {ref}")
                continue
            if "::" in ref:
                name = ref.split("::")[1]
                if name not in path.read_text(encoding="utf-8"):
                    missing.append(f"{row.threat}: {path.name} has no {name}")
    return missing


def collect_ok() -> tuple[bool, str]:
    """Ask pytest to collect the referenced ids, so 'it exists' means pytest agrees."""
    ids = sorted({t for row in ROWS for t in row.tests if t.startswith("tests/")})
    if not ids:
        return True, "nothing to collect"
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", *ids],
        cwd=ROOT, capture_output=True, text=True,
    )
    return proc.returncode == 0, (proc.stdout + proc.stderr).strip().splitlines()[-1]


def table() -> str:
    width = max(len(r.name) for r in ROWS)
    lines = [f"{'':<4}{'threat':<{width}}  status", "-" * (width + 26)]
    for r in ROWS:
        lines.append(f"{r.threat:<4}{r.name:<{width}}  {r.status}")
    return "\n".join(lines)


def summary() -> dict:
    counts: dict[str, int] = {}
    for r in ROWS:
        counts[str(r.status)] = counts.get(str(r.status), 0) + 1
    return counts


def main() -> int:
    print(table())
    print()
    print("summary:", summary())

    gaps = missing_tests()
    if gaps:
        print("\nBROKEN REFERENCES — a mapping that names a test that does not exist is worse")
        print("than one that names nothing, because it reads as reassurance:")
        for g in gaps:
            print("  ✗", g)
        return 1

    ok, last = collect_ok()
    print("\nevery referenced test resolves under pytest:", "yes" if ok else f"NO — {last}")
    print(f"\n{sum(1 for r in ROWS if r.status is Status.COVERED)}/15 covered, "
          f"{sum(1 for r in ROWS if r.status is Status.PARTIAL)} partial, "
          f"{sum(1 for r in ROWS if r.status is Status.OPEN)} open, "
          f"{sum(1 for r in ROWS if r.status is Status.NOT_APPLICABLE)} no surface yet.")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
