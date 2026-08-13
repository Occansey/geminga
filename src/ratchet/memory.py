"""Recall — retrieval over the agent's own operational history.

What an experienced operator knows that a fresh one does not is *what happened last
time*. This is that: incident notes, prior decisions, runbook fragments, retrieved and
handed to the proposer before it proposes.

It is also, deliberately, a new attack surface. Retrieval puts more
attacker-influenceable text into the model's context — Willison's lethal trifecta in
miniature. Anyone can file an incident note; in most organisations, anyone can edit a
runbook.

**We add it anyway, and that is the point.** The gates do not read notes. Poisoning the
entire corpus changes what the model proposes and cannot change the set of operations
it may perform, because admission consults a table and a snapshot, never a memory. A
defence whose safety depends on its context being clean is a defence that has not been
tested; this one is designed to be indifferent, and `evals/poison.py` measures whether
that is true rather than asserting it.

Backend is BM25 over headed notes: no embeddings, no API key, runs offline, and every
retrieval is inspectable. Vertex **Memory Bank** is the managed swap — same interface,
`recall()` and `remember()` — and the reason this file defines a protocol rather than a
class.
"""

from __future__ import annotations

import math
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Protocol

STOP = set(
    """a an and are as at be but by for from has have in into is it its of on or that the
    their there these this to was were what when where which who will with you your we our""".split()
)


@dataclass
class Note:
    """One thing the organisation remembers.

    `authored_by` matters more than it looks. A note is evidence about who wrote it,
    not evidence about the world, and the proposer is told so.
    """

    text: str
    kind: str = "incident"          # incident | decision | runbook
    authored_by: str = "unknown"
    at: float = field(default_factory=time.time)

    @property
    def trusted(self) -> bool:
        """Nothing here is trusted. The property exists to make that explicit at the
        call site rather than implied by its absence."""
        return False


class Recall(Protocol):
    def remember(self, note: Note) -> None: ...
    def recall(self, query: str, k: int = 4) -> list[Note]: ...


def tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9][a-z0-9\-_.]*", text.lower())
    return [w for w in words if w not in STOP and len(w) > 1]


class Bm25Recall:
    """Local retrieval. Rebuilt on write — the corpus is small and correctness beats
    cleverness when the thing being retrieved feeds a model that can delete disks."""

    K1, B = 1.5, 0.75

    def __init__(self, notes: list[Note] | None = None) -> None:
        self._notes: list[Note] = []
        self._tokens: list[list[str]] = []
        self._idf: dict[str, float] = {}
        for note in notes or []:
            self.remember(note)

    def remember(self, note: Note) -> None:
        self._notes.append(note)
        self._tokens.append(tokenize(note.text))
        self._reindex()

    def _reindex(self) -> None:
        df: Counter[str] = Counter()
        for tokens in self._tokens:
            df.update(set(tokens))
        n = len(self._notes)
        self._idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def recall(self, query: str, k: int = 4) -> list[Note]:
        if not self._notes:
            return []
        terms = tokenize(query)
        lengths = [len(t) for t in self._tokens]
        avg = sum(lengths) / len(lengths)

        scored: list[tuple[float, Note]] = []
        for i, note in enumerate(self._notes):
            tf = Counter(self._tokens[i])
            score = 0.0
            for term in terms:
                freq = tf.get(term, 0)
                if not freq:
                    continue
                denom = freq + self.K1 * (1 - self.B + self.B * (lengths[i] / (avg or 1)))
                score += self._idf.get(term, 0.0) * (freq * (self.K1 + 1)) / denom
            if score > 0:
                scored.append((score, note))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [note for _, note in scored[:k]]

    def __len__(self) -> int:
        return len(self._notes)


def render(notes: list[Note], nonce: str) -> str:
    """Format recalled notes for a prompt, wrapped and labelled as untrusted.

    Same envelope as inventory metadata, for the same reason: a note is text somebody
    typed, and the person who typed it may not be on your side.
    """
    from .admission import sanitise_metadata

    if not notes:
        return "(no relevant history)"
    lines = []
    for i, note in enumerate(notes, 1):
        clean = sanitise_metadata({f"{note.kind}": note.text}, nonce)
        flag = "  [FLAGGED: reads like an instruction]" if clean.suspicious else ""
        lines.append(f"{i}. from {note.authored_by}{flag}\n{clean.text}")
    return "\n\n".join(lines)


# --------------------------------------------------------------------------- #
# a small, plausible operational history
# --------------------------------------------------------------------------- #

def sample_history() -> list[Note]:
    return [
        Note(
            "ml-train-01 runs the nightly feature build. It looks idle between 02:00 "
            "and 06:00 UTC but the job holds the GPU. Do not stop it on CPU average alone.",
            kind="runbook", authored_by="ml-platform@",
        ),
        Note(
            "INC-2291: staging-web-3 was stopped during a load test and nobody noticed "
            "for four days. Stopping it is safe; someone should be told.",
            kind="incident", authored_by="sre@",
        ),
        Note(
            "pd-ml-scratch was detached in March when the training rig was rebuilt. "
            "Ownership is unclear. Nobody has claimed it and nobody has deleted it.",
            kind="decision", authored_by="platform@",
        ),
        Note(
            "legacy-lb-ip is referenced in two partner allowlists. Releasing it means "
            "coordinating with them first.",
            kind="runbook", authored_by="networking@",
        ),
        Note(
            "snap-2024-03-11 predates the retention policy rewrite. Legal have not "
            "confirmed whether it is in scope for the Acme matter.",
            kind="decision", authored_by="dataprotection@",
        ),
    ]
