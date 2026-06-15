from html.parser import HTMLParser
from importlib import import_module
from urllib.parse import urlparse


USER_AGENT = "NellieLocalAssistant/1.0 (local desktop assistant)"


class _VisibleTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._in_title = False
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag: str, _attrs) -> None:
        lowered = tag.casefold()
        if lowered in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
        elif lowered == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.casefold()
        if lowered in {"script", "style", "noscript", "svg"}:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif lowered == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        text = " ".join(str(data or "").split())
        if not text or self._skip_depth:
            return
        (self.title_parts if self._in_title else self.text_parts).append(text)


def extract_url(text: str) -> str:
    for token in str(text or "").split():
        cleaned = token.strip("()[]{}<>.,!?\"'")
        if cleaned.startswith(("https://", "http://")):
            return cleaned
    return ""


def fetch_webpage(url: str, max_chars: int = 4000) -> dict[str, str]:
    cleaned_url = str(url or "").strip()
    parsed = urlparse(cleaned_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Expected a valid HTTP or HTTPS URL.")
    limit = max(200, min(int(max_chars), 12000))

    requests = import_module("requests")
    response = requests.get(
        cleaned_url,
        timeout=20,
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    content_type = str(response.headers.get("content-type", ""))
    if "text/html" not in content_type.casefold():
        text = str(response.text or "")
        return {
            "url": cleaned_url,
            "title": parsed.netloc,
            "content_type": content_type or "unknown",
            "text": text[:limit],
        }

    parser = _VisibleTextExtractor()
    parser.feed(response.text)
    title = " ".join(parser.title_parts).strip() or parsed.netloc
    text = " ".join(" ".join(parser.text_parts).split())
    return {
        "url": cleaned_url,
        "title": title,
        "content_type": content_type,
        "text": text[:limit],
    }
