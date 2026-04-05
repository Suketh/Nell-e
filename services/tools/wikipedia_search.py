from __future__ import annotations

from urllib.parse import quote

import requests


WIKI_SEARCH_API = "https://en.wikipedia.org/w/api.php"


def search_wikipedia(query: str, limit: int = 3) -> list[dict[str, str]]:
    cleaned = (query or "").strip()
    if not cleaned:
        raise ValueError("Wikipedia search requires a query.")

    response = requests.get(
        WIKI_SEARCH_API,
        params={
            "action": "query",
            "list": "search",
            "srsearch": cleaned,
            "srlimit": max(1, min(limit, 5)),
            "utf8": 1,
            "format": "json",
        },
        headers={"User-Agent": "Nellie/1.0"},
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    results = payload.get("query", {}).get("search", [])

    items = []
    for item in results:
        title = (item.get("title") or "").strip()
        snippet = _clean_html(item.get("snippet", ""))
        items.append(
            {
                "title": title,
                "url": f"https://en.wikipedia.org/wiki/{quote(title.replace(' ', '_'))}",
                "snippet": snippet,
            }
        )
    return items


def _clean_html(text: str) -> str:
    cleaned = (text or "").replace("<span class=\"searchmatch\">", "").replace("</span>", "")
    cleaned = cleaned.replace("&quot;", '"').replace("&#039;", "'").replace("&amp;", "&")
    return " ".join(cleaned.split())
