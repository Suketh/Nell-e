from html.parser import HTMLParser
from urllib.parse import urlparse

import requests


class _VisibleTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._skip_stack: list[str] = []
        self._in_title = False
        self.title_parts: list[str] = []
        self.text_parts: list[str] = []

    def handle_starttag(self, tag, _attrs):
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript"}:
            self._skip_stack.append(lowered)
        elif lowered == "title":
            self._in_title = True

    def handle_endtag(self, tag):
        lowered = tag.lower()
        if lowered in {"script", "style", "noscript"} and self._skip_stack:
            self._skip_stack.pop()
        elif lowered == "title":
            self._in_title = False

    def handle_data(self, data):
        text = " ".join((data or "").split())
        if not text or self._skip_stack:
            return
        if self._in_title:
            self.title_parts.append(text)
        else:
            self.text_parts.append(text)


def fetch_webpage(url: str, max_chars: int = 4000) -> dict[str, str]:
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Expected a valid http or https URL.")

    response = requests.get(url, timeout=20, headers={"User-Agent": "Nellie/1.0"})
    response.raise_for_status()

    content_type = response.headers.get("content-type", "")
    if "text/html" not in content_type.lower():
        return {
            "url": url,
            "title": parsed.netloc,
            "content_type": content_type or "unknown",
            "text": response.text[:max_chars],
        }

    parser = _VisibleTextExtractor()
    parser.feed(response.text)
    title = " ".join(parser.title_parts).strip() or parsed.netloc
    text = " ".join(parser.text_parts).strip()
    text = " ".join(text.split())

    return {
        "url": url,
        "title": title,
        "content_type": content_type,
        "text": text[:max_chars],
    }
