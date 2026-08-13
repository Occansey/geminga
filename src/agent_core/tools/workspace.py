"""Artifact tools — anything the agent produces that outlives the turn.

Backed by Cloud Storage. Writing real objects to a real bucket during the demo
is the cheapest way to show "proof of Google Cloud deployment" on screen.
"""

from __future__ import annotations

from google.adk.tools import ToolContext

from ..stores import make_artifact_store

_store = None


def _artifacts():
    global _store
    if _store is None:
        _store = make_artifact_store()
    return _store


def write_artifact(name: str, content: str, tool_context: ToolContext) -> dict:
    """Save a text artifact (report, summary, generated file) to the workspace.

    Args:
        name: Filename, e.g. "summary.md". Scoped to this session automatically.
        content: The full text to store.

    Returns:
        {"uri": "gs://..."} — quote this uri when reporting the result.
    """
    session = getattr(tool_context, "session_id", None) or "local"
    uri = _artifacts().put(f"{session}/{name}", content.encode("utf-8"), "text/plain; charset=utf-8")
    return {"uri": uri, "bytes": len(content)}


def read_artifact(name: str, tool_context: ToolContext) -> dict:
    """Read back an artifact this session previously wrote."""
    session = getattr(tool_context, "session_id", None) or "local"
    try:
        return {"content": _artifacts().get(f"{session}/{name}").decode("utf-8")}
    except Exception as exc:  # surfaced to the model so it can recover, not swallowed
        return {"error": f"Could not read {name!r}: {exc}"}
