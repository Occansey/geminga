"""Single source of truth for configuration.

Everything the agent needs to run is read here and nowhere else, so that
swapping the deployment target (local, Cloud Run, Agent Engine) is a matter
of environment variables rather than code edits.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # Model. 3.6 Flash went GA 21 Jul 2026 — cheaper than 3.5 Flash, ~17% fewer
    # output tokens, better agentic planning. It satisfies the rules' "Gemini 3.5+"
    # requirement, and several visible entrants are already on it. 3.5 Pro was still
    # allowlist-only Vertex preview in late July, so it is not the default.
    agent_model: str = "gemini-3.6-flash"
    agent_fast_model: str = "gemini-3.6-flash"
    google_genai_use_vertexai: bool = True
    google_cloud_project: str = ""
    # Gemini 3.x publisher models are served from the global endpoint;
    # regional endpoints 404 for them. Cloud Run still deploys to a real region.
    google_cloud_location: str = "global"
    google_api_key: str = ""

    # Persistence
    agent_store: Literal["firestore", "memory"] = "firestore"
    agent_bucket: str = ""

    # Behaviour
    agent_name: str = "taskmaster"
    agent_max_steps: int = Field(default=12, ge=1, le=50)
    agent_require_approval: bool = False

    # Tool providers
    serpapi_key: str = ""

    @property
    def uses_vertex(self) -> bool:
        return self.google_genai_use_vertexai and bool(self.google_cloud_project)

    def require_cloud(self) -> None:
        """Fail loudly rather than silently degrading to a local-only demo.

        The hackathon disqualifies submissions that never touch Google Cloud,
        so a misconfigured deploy should stop the process, not run anyway.
        """
        if not self.google_cloud_project:
            raise RuntimeError(
                "GOOGLE_CLOUD_PROJECT is unset. The submission must run against "
                "Google Cloud — see .env.example."
            )


@lru_cache
def settings() -> Settings:
    return Settings()
