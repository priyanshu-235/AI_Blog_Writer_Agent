from __future__ import annotations

import os
from typing import List


def perform_web_lookup(query: str, max_results: int = 5) -> List[dict]:
    api_key = os.getenv("TAVILY_API_KEY")

    if not api_key:
        return []

    try:
        from tavily import TavilyClient

        client = TavilyClient(api_key=api_key)
        raw_results = client.search(query=query, max_results=max_results)
        items = raw_results.get("results") or []
        cleaned = []

        for item in items:
            cleaned.append(
                {
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "snippet": item.get("content") or item.get("snippet") or "",
                    "published_date": item.get("published_date")
                    or item.get("published_at"),
                    "source_name": item.get("source"),
                }
            )

        return cleaned

    except Exception:
        return []
