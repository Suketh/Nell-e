import os
import re
import subprocess
import webbrowser
from pathlib import Path
from urllib.parse import quote


def extract_spotify_query(text: str, context: str = "") -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    lowered = raw.lower().strip()

    explicit_contextual_patterns = [
        r"^(?:can you )?play (?:it|that|this|that song|that track|that one|this song) for me on spotify[.!? ]*$",
        r"^(?:can you )?play (?:it|that|this|that song|that track|that one|this song) on spotify for me[.!? ]*$",
        r"^(?:can you )?put (?:it|that|this|that song|that track|that one|this song) on spotify for me[.!? ]*$",
        r"^(?:can you )?put (?:it|that|this|that song|that track|that one|this song) on spotify[.!? ]*$",
        r"^(?:open )?spotify (?:and )?play (?:it|that|this|that song|that track|that one|this song)[.!? ]*$",
    ]
    for pattern in explicit_contextual_patterns:
        if re.match(pattern, lowered, flags=re.IGNORECASE):
            return _resolve_contextual_query(context)

    patterns = [
        r"^(?:can you )?play (.+?) on spotify for me[.!? ]*$",
        r"^(?:can you )?play (.+?) on spotify[.!? ]*$",
        r"^(?:can you )?put on (.+?) on spotify for me[.!? ]*$",
        r"^(?:can you )?put on (.+?) on spotify[.!? ]*$",
        r"^(?:open )?spotify (?:and )?play (.+?)[.!? ]*$",
        r"^(?:open )?spotify (.+?)[.!? ]*$",
        r"^(?:can you )?play (.+?) for me[.!? ]*$",
        r"^(?:play|put on) (.+?)[.!? ]*$",
    ]
    for pattern in patterns:
        match = re.match(pattern, lowered, flags=re.IGNORECASE)
        if not match:
            continue
        query = match.group(1).strip(" .!?")
        if not query:
            continue
        cleaned = _clean_query(query)
        if cleaned in {"it", "that", "that song", "that track", "that one", "this", "this song"}:
            return _resolve_contextual_query(context)
        return cleaned

    if any(
        cue in lowered
        for cue in [
            "play it on spotify",
            "play it on spotify for me",
            "play it for me",
            "open it on spotify",
            "put it on spotify",
            "play that on spotify",
            "play that on spotify for me",
            "play that for me",
        ]
    ):
        return _resolve_contextual_query(context)
    return ""


def open_spotify_query(query: str) -> tuple[bool, str]:
    cleaned = _clean_query(query)
    if not cleaned:
        return False, ""

    protocol_url = f"spotify:search:{quote(cleaned)}"
    web_url = f"https://open.spotify.com/search/{quote(cleaned)}"

    if _open_in_chrome(web_url):
        return True, web_url

    try:
        opened = bool(webbrowser.open(web_url))
        if opened:
            return True, web_url
    except Exception:
        pass

    try:
        opened = bool(webbrowser.open(protocol_url))
        if opened:
            return True, protocol_url
    except Exception:
        pass

    return False, web_url


def _open_in_chrome(url: str) -> bool:
    chrome_candidates = [
        Path(os.environ.get("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
    ]
    for candidate in chrome_candidates:
        if not str(candidate):
            continue
        if candidate.exists():
            try:
                subprocess.Popen([str(candidate), url])
                return True
            except Exception:
                continue
    return False


def _clean_query(query: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(query or "")).strip()
    cleaned = re.sub(r"\bon spotify\b", "", cleaned, flags=re.IGNORECASE).strip()
    return cleaned.strip(" .!?")


def _resolve_contextual_query(context: str) -> str:
    source = str(context or "")
    quoted = re.findall(r'["“](.*?)["”]', source)
    if quoted:
        last = quoted[-1].strip()
        artist = _last_artist(source)
        if artist:
            return f"{last} {artist}"
        return last

    title_artist = re.findall(
        r"\b([A-Za-z][\w'&.-]*(?:\s+[A-Za-z][\w'&.-]*){0,4})\s+by\s+([A-Za-z][\w'&.-]*(?:\s+[A-Za-z][\w'&.-]*){0,3})",
        source,
        flags=re.IGNORECASE,
    )
    if title_artist:
        title, artist = title_artist[-1]
        return f"{title} {artist}"

    how_about = re.findall(
        r"\bhow about (?:some )?([A-Za-z][\w'&.-]*(?:\s+[A-Za-z][\w'&.-]*){0,3})",
        source,
        flags=re.IGNORECASE,
    )
    if how_about:
        return how_about[-1].strip()

    playing_now = re.findall(
        r'\bcalled ["“]?([^"”*.!?]{2,80})["”]?',
        source,
        flags=re.IGNORECASE,
    )
    if playing_now:
        title = playing_now[-1].strip(" ,")
        artist = _last_artist(source)
        if artist:
            return f"{title} {artist}"
        return title

    lets_go_with = re.findall(
        r'\blet[’\']s go with ["“]?([^"”]{2,80})["”]?',
        source,
        flags=re.IGNORECASE,
    )
    if lets_go_with:
        title = lets_go_with[-1].strip(" ,")
        artist = _last_artist(source)
        if artist:
            return f"{title} {artist}"
        return title

    artist = _last_artist(source)
    if artist:
        return artist
    return ""


def _last_artist(context: str) -> str:
    patterns = [
        r"\b(?:by|some|about some|into some|how about some)\s+([A-Za-z][\w'&.-]*(?:\s+[A-Za-z][\w'&.-]*){0,4})",
        r"\blistening to (?:a lot of )?([A-Za-z][\w'&.-]*(?:\s+[A-Za-z][\w'&.-]*){0,4})",
        r"\bheard (?:of )?([A-Za-z][\w'&.-]*(?:\s+[A-Za-z][\w'&.-]*){0,4})",
        r"\bplay(?:ing)? (?:some )?([A-Za-z][\w'&.-]*(?:\s+[A-Za-z][\w'&.-]*){0,4})",
        r"\bfrom\s+([A-Za-z][\w'&.-]*(?:\s+[A-Za-z][\w'&.-]*){0,4})",
        r"\bmeant\s+([A-Za-z][\w'&.-]*(?:\s+[A-Za-z][\w'&.-]*){0,4})",
    ]
    for pattern in patterns:
        artist_matches = re.findall(pattern, context, flags=re.IGNORECASE)
        if artist_matches:
            return artist_matches[-1].strip()
    return ""
