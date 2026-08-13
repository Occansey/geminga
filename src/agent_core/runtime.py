"""Runner wiring: turns the agent into something you can call once and await."""

from __future__ import annotations

import os
from dataclasses import dataclass

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from .agent import build_root_agent
from .config import settings

APP_NAME = "all-things-agentic"


def _configure_genai() -> None:
    """ADK reads these from the environment, so set them from our one config object."""
    cfg = settings()
    os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "TRUE" if cfg.uses_vertex else "FALSE"
    if cfg.uses_vertex:
        os.environ["GOOGLE_CLOUD_PROJECT"] = cfg.google_cloud_project
        os.environ["GOOGLE_CLOUD_LOCATION"] = cfg.google_cloud_location
    elif cfg.google_api_key:
        os.environ["GOOGLE_API_KEY"] = cfg.google_api_key


@dataclass
class Turn:
    text: str
    events: list


class AgentSession:
    """One conversation. Hold this per user session; it is cheap to construct."""

    def __init__(self, user_id: str = "demo", session_id: str = "local") -> None:
        _configure_genai()
        self.user_id = user_id
        self.session_id = session_id
        self._sessions = InMemorySessionService()
        self._runner = Runner(
            agent=build_root_agent(),
            app_name=APP_NAME,
            session_service=self._sessions,
        )
        self._started = False

    async def _ensure_session(self) -> None:
        if not self._started:
            await self._sessions.create_session(
                app_name=APP_NAME,
                user_id=self.user_id,
                session_id=self.session_id,
                state={"session_id": self.session_id},
            )
            self._started = True

    async def send(self, message: str) -> Turn:
        await self._ensure_session()
        content = types.Content(role="user", parts=[types.Part(text=message)])
        events, reply = [], ""
        async for event in self._runner.run_async(
            user_id=self.user_id, session_id=self.session_id, new_message=content
        ):
            events.append(event)
            if event.is_final_response() and event.content and event.content.parts:
                reply = "".join(p.text or "" for p in event.content.parts)
        return Turn(text=reply, events=events)
