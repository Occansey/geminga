"""Search tool.

Deliberately provider-agnostic: SerpApi when a key is present, otherwise ADK's
built-in Google Search. The SerpApi path is not decoration — the same code
satisfies the DevNetwork "SerpApi · best AI use case" challenge ($3,000) when
this core is resubmitted there.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request

from ..config import settings

_TIMEOUT = 15


def web_search(query: str, limit: int = 5) -> dict:
    """Search the web and return titles, links and snippets.

    Args:
        query: A specific search query. Prefer several narrow searches over one broad one.
        limit: Maximum results to return, 1–10.
    """
    limit = max(1, min(int(limit), 10))
    key = settings().serpapi_key
    if not key:
        return {
            "error": "No search provider configured. Set SERPAPI_KEY, or give the "
            "agent ADK's built-in google_search tool instead.",
            "results": [],
        }

    params = urllib.parse.urlencode({"q": query, "api_key": key, "num": limit, "engine": "google"})
    try:
        with urllib.request.urlopen(f"https://serpapi.com/search?{params}", timeout=_TIMEOUT) as r:
            payload = json.load(r)
    except Exception as exc:
        return {"error": f"Search failed: {exc}", "results": []}

    results = [
        {
            "title": item.get("title", ""),
            "link": item.get("link", ""),
            "snippet": item.get("snippet", ""),
        }
        for item in payload.get("organic_results", [])[:limit]
    ]
    return {"query": query, "results": results}
