"""Local driver: `agent "goal"` or `agent` for an interactive session."""

from __future__ import annotations

import asyncio
import sys

from .config import settings
from .runtime import AgentSession


async def _run(goal: str | None) -> None:
    cfg = settings()
    session = AgentSession(session_id="cli")
    print(f"[{cfg.agent_name}] model={cfg.agent_model} store={cfg.agent_store} "
          f"approval={'on' if cfg.agent_require_approval else 'off'}\n")

    if goal:
        print((await session.send(goal)).text)
        return

    while True:
        try:
            message = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if message in {"exit", "quit"}:
            return
        if message:
            print((await session.send(message)).text, "\n")


def main() -> None:
    asyncio.run(_run(" ".join(sys.argv[1:]) or None))


if __name__ == "__main__":
    main()
