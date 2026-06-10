import os
import re
import subprocess
import webbrowser
from pathlib import Path
from urllib.parse import quote


def extract_wikipedia_query(text: str, context: str = "") -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    lowered = raw.lower().strip()
    patterns = [
        r"^(?:can you )?(?:open|search|look up) (.+?) on wikipedia[.!? ]*$",
        r"^(?:can you )?(?:open|search|look up) wikipedia (?:for )?(.+?)[.!? ]*$",
        r"^(?:wikipedia )(.+?)[.!? ]*$",
    ]
    for pattern in patterns:
        match = re.match(pattern, lowered, flags=re.IGNORECASE)
        if match:
            query = _clean_query(match.group(1))
            if query in {"it", "that", "this", "that topic", "this topic"}:
                return _resolve_contextual_query(context)
            return query
    if any(cue in lowered for cue in ["open it on wikipedia", "look it up on wikipedia", "search it on wikipedia"]):
        return _resolve_contextual_query(context)
    return ""


def extract_youtube_query(text: str, context: str = "") -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    lowered = raw.lower().strip()
    patterns = [
        r"^(?:can you )?(?:start|open) youtube(?: for me)?[.!? ]*$",
        r"^(?:can you )?(?:open|search) (.+?) on youtube[.!? ]*$",
        r"^(?:can you )?play (.+?) on youtube[.!? ]*$",
        r"^(?:can you )?(?:open|search) youtube (?:for )?(.+?)[.!? ]*$",
        r"^(?:youtube )(.+?)[.!? ]*$",
    ]
    for pattern in patterns:
        match = re.match(pattern, lowered, flags=re.IGNORECASE)
        if match:
            query = _clean_query(match.group(1)) if match.lastindex else _resolve_contextual_query(context)
            if query in {"it", "that", "this", "that song", "this song", "that video"}:
                return _resolve_contextual_query(context)
            return query
    if any(cue in lowered for cue in ["open it on youtube", "search it on youtube", "play it on youtube", "play that on youtube"]):
        return _resolve_contextual_query(context)
    return ""


def open_wikipedia_query(query: str) -> tuple[bool, str]:
    cleaned = _clean_query(query)
    if not cleaned:
        return False, ""
    url = f"https://en.wikipedia.org/wiki/Special:Search?search={quote(cleaned)}"
    return _open_url(url), url


def open_youtube_query(query: str) -> tuple[bool, str]:
    cleaned = _clean_query(query)
    if not cleaned:
        return False, ""
    url = f"https://www.youtube.com/results?search_query={quote(cleaned)}"
    return _open_url(url), url


def _open_url(url: str) -> bool:
    if _open_in_chrome(url):
        return True
    try:
        return bool(webbrowser.open(url))
    except Exception:
        return False


def _open_in_chrome(url: str) -> bool:
    chrome_candidates = [
        Path(os.environ.get("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
    ]
    for candidate in chrome_candidates:
        if candidate.exists():
            try:
                subprocess.Popen([str(candidate), url])
                return True
            except Exception:
                continue
    return False


def _clean_query(query: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(query or "")).strip()
    cleaned = re.sub(r"\bon wikipedia\b|\bon youtube\b", "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned.strip(" .!?")


def _resolve_contextual_query(context: str) -> str:
    source = str(context or "")
    quoted = re.findall(r'["“](.*?)["”]', source)
    if quoted:
        return quoted[-1].strip()
    title_artist = re.findall(
        r"\b([A-Za-z][\w'&.-]*(?:\s+[A-Za-z][\w'&.-]*){0,5})\s+by\s+([A-Za-z][\w'&.-]*(?:\s+[A-Za-z][\w'&.-]*){0,3})",
        source,
        flags=re.IGNORECASE,
    )
    if title_artist:
        title, artist = title_artist[-1]
        return f"{title} {artist}"

    ignored = {
        "user", "nellie", "you", "your", "i", "hmm", "well", "since", "maybe",
        "wikipedia", "youtube", "spotify", "okay", "honestly",
    }

    def find_named_subject(text: str) -> str:
        proper_chunks = re.findall(
            r"\b([A-ZÅÄÖ][\wÅÄÖåäö'&.-]*(?:\s+[A-ZÅÄÖ][\wÅÄÖåäö'&.-]*){0,4})",
            text,
        )
        filtered = []
        for chunk in proper_chunks:
            normalized = chunk.strip(" \t\r\n.!?,:;")
            if normalized and normalized.casefold() not in ignored:
                filtered.append(normalized)
        return filtered[-1] if filtered else ""

    user_lines = re.findall(r"(?im)^USER:\s*(.+)$", source)
    subject = find_named_subject("\n".join(user_lines))
    if subject:
        return subject
    return find_named_subject(source)
