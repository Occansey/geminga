"""Portability seam.

The hackathon core is Gemini + ADK, but the same plan/step model is worth
resubmitting to Agents for Humans on the AWS Strands SDK. Everything that
would otherwise hard-code a vendor lives behind these two protocols, so the
port is a new implementation of `PlanStore`, not a rewrite of the agent.

Concretely: `agent.py` and `tools/` import from here and from ADK. Nothing
else in the package imports a cloud SDK directly.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal, Protocol

StepState = Literal["pending", "running", "done", "failed", "blocked"]


@dataclass
class Step:
    id: str
    description: str
    state: StepState = "pending"
    # Steps that write to the world (send, publish, pay, delete) get gated
    # behind approval when AGENT_REQUIRE_APPROVAL is on.
    side_effecting: bool = False
    result: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Plan:
    session_id: str
    goal: str
    steps: list[Step] = field(default_factory=list)
    state: Literal["planning", "executing", "awaiting_approval", "done", "failed"] = "planning"

    @property
    def next_step(self) -> Step | None:
        return next((s for s in self.steps if s.state == "pending"), None)

    @property
    def is_complete(self) -> bool:
        return all(s.state in ("done", "failed") for s in self.steps) and bool(self.steps)

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "goal": self.goal,
            "state": self.state,
            "steps": [s.to_dict() for s in self.steps],
        }

    @classmethod
    def from_dict(cls, raw: dict) -> Plan:
        return cls(
            session_id=raw["session_id"],
            goal=raw["goal"],
            state=raw.get("state", "planning"),
            steps=[Step(**s) for s in raw.get("steps", [])],
        )


class PlanStore(Protocol):
    """Durable plan storage. Cloud Run recycles instances mid-run; a plan that
    only lives in process memory loses the demo."""

    def load(self, session_id: str) -> Plan | None: ...

    def save(self, plan: Plan) -> None: ...


class ArtifactStore(Protocol):
    """Files the agent produces — reports, diagrams, exports."""

    def put(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str: ...

    def get(self, key: str) -> bytes: ...
