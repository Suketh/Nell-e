from __future__ import annotations

from pathlib import Path
import subprocess
from urllib.parse import quote_plus


CHROME_CANDIDATES = [
    Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
    Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    Path.home() / r"AppData\Local\Google\Chrome\Application\chrome.exe",
]

KNOWN_TARGETS = {
    "spotify": "https://open.spotify.com/",
    "youtube": "https://www.youtube.com/",
    "wikipedia": "https://www.wikipedia.org/",
}


def open_in_browser(target: str | None = None, url: str | None = None, query: str | None = None) -> dict[str, str]:
    final_url = _resolve_url(target=target, url=url, query=query)
    chrome_path = _find_chrome()

    if chrome_path is not None:
        subprocess.Popen([str(chrome_path), final_url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        browser_name = "Chrome"
    else:
        subprocess.Popen(["cmd", "/c", "start", "", final_url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        browser_name = "default browser"

    return {
        "status": "opened",
        "browser": browser_name,
        "url": final_url,
        "target": (target or "url").strip() or "url",
    }


def _resolve_url(target: str | None = None, url: str | None = None, query: str | None = None) -> str:
    if url:
        cleaned = (url or "").strip()
        if cleaned.startswith(("http://", "https://")):
            return cleaned
        raise ValueError("Expected a full http or https URL.")

    normalized_target = (target or "").strip().lower()
    if normalized_target in {"spotify", "youtube", "wikipedia"}:
        base = KNOWN_TARGETS[normalized_target]
        if query:
            if normalized_target == "spotify":
                return f"https://open.spotify.com/search/{quote_plus(query)}"
            if normalized_target == "youtube":
                return f"https://www.youtube.com/results?search_query={quote_plus(query)}"
            if normalized_target == "wikipedia":
                return f"https://en.wikipedia.org/w/index.php?search={quote_plus(query)}"
        return base

    if query:
        return f"https://www.google.com/search?q={quote_plus(query)}"

    raise ValueError("Expected a known target, a URL, or a search query.")


def _find_chrome() -> Path | None:
    for candidate in CHROME_CANDIDATES:
        if candidate.exists():
            return candidate
    return None
