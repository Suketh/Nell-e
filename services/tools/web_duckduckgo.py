import html
import re
import xml.etree.ElementTree as ET
from importlib import import_module
from urllib.parse import quote_plus, urlparse


SEARCH_URL = "https://duckduckgo.com/html/?q={query}"
BING_RSS_URL = "https://www.bing.com/search"
WIKIPEDIA_API_URL = "https://en.wikipedia.org/w/api.php"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
)
WIKIPEDIA_USER_AGENT = "NellieLocalAssistant/1.0 (local desktop assistant)"


def search(query: str, k: int = 5) -> list[dict[str, str]]:
    query = str(query or "").strip()
    if not query:
        return []

    try:
        requests = import_module("requests")
    except Exception as exc:
        raise RuntimeError("requests is not installed in the current Python environment.") from exc

    wikipedia_results = (
        _search_wikipedia(requests, query, min(k, 2))
        if _prefer_wikipedia(query)
        else []
    )
    response = requests.get(
        SEARCH_URL.format(query=quote_plus(query)),
        headers={"User-Agent": USER_AGENT},
        timeout=20,
    )
    response.raise_for_status()
    results = _parse_results(response.text, k)
    if not results:
        results = _search_bing_rss(requests, query, k)
    return _merge_results(wikipedia_results, results, k)


def summarize_results(results: list[dict[str, str]]) -> str:
    lines: list[str] = []
    for index, item in enumerate(results, start=1):
        title = item.get("title", "").strip()
        url = item.get("url", "").strip()
        snippet = item.get("snippet", "").strip()
        domain = item.get("domain", "").strip()
        lines.append(f"{index}. {title} ({domain})")
        if snippet:
            lines.append(f"   {snippet}")
        if url:
            lines.append(f"   Source: {url}")
    return "\n".join(lines)


def _parse_results(body: str, k: int) -> list[dict[str, str]]:
    blocks = re.findall(
        r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>(?P<rest>.*?)(?=<a[^>]*class="[^"]*result__a|$)',
        body,
        flags=re.IGNORECASE | re.DOTALL,
    )

    results: list[dict[str, str]] = []
    for url, title_html, rest in blocks:
        clean_url = html.unescape(url)
        title = _clean_html(title_html)
        snippet_match = re.search(
            r'<a[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(?P<snippet>.*?)</a>|<div[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(?P<snippet_div>.*?)</div>',
            rest,
            flags=re.IGNORECASE | re.DOTALL,
        )
        snippet = ""
        if snippet_match:
            snippet = _clean_html(snippet_match.group("snippet") or snippet_match.group("snippet_div") or "")
        domain = urlparse(clean_url).netloc.replace("www.", "")
        if title and clean_url:
            results.append(
                {
                    "title": title,
                    "url": clean_url,
                    "snippet": snippet,
                    "domain": domain,
                }
            )
        if len(results) >= k:
            break
    return results


def _clean_html(value: str) -> str:
    text = re.sub(r"<.*?>", " ", value or "", flags=re.DOTALL)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _search_bing_rss(requests: object, query: str, k: int) -> list[dict[str, str]]:
    response = requests.get(
        BING_RSS_URL,
        params={"q": query, "format": "rss"},
        headers={"User-Agent": USER_AGENT},
        timeout=20,
    )
    response.raise_for_status()
    root = ET.fromstring(response.text)
    results: list[dict[str, str]] = []
    for item in root.findall("./channel/item"):
        title = (item.findtext("title") or "").strip()
        url = (item.findtext("link") or "").strip()
        snippet = _clean_html(item.findtext("description") or "")
        if title and url:
            results.append(
                {
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                    "domain": urlparse(url).netloc.replace("www.", ""),
                }
            )
        if len(results) >= k:
            break
    return results


def _search_wikipedia(requests: object, query: str, k: int) -> list[dict[str, str]]:
    wikipedia_query = _wikipedia_query(query)
    try:
        search_response = requests.get(
            WIKIPEDIA_API_URL,
            params={
                "action": "query",
                "list": "search",
                "srsearch": wikipedia_query,
                "srlimit": max(1, k),
                "format": "json",
                "utf8": 1,
            },
            headers={"User-Agent": WIKIPEDIA_USER_AGENT},
            timeout=20,
        )
        search_response.raise_for_status()
        matches = search_response.json().get("query", {}).get("search", [])
    except Exception:
        return []

    extracts: dict[str, str] = {}
    page_ids = [str(match.get("pageid", "")) for match in matches[:k] if match.get("pageid")]
    if page_ids:
        try:
            extract_response = requests.get(
                WIKIPEDIA_API_URL,
                params={
                    "action": "query",
                    "prop": "extracts",
                    "exintro": 1,
                    "explaintext": 1,
                    "pageids": "|".join(page_ids),
                    "format": "json",
                    "utf8": 1,
                },
                headers={"User-Agent": WIKIPEDIA_USER_AGENT},
                timeout=20,
            )
            extract_response.raise_for_status()
            pages = extract_response.json().get("query", {}).get("pages", {})
            extracts = {
                str(page_id): re.sub(r"\s+", " ", str(page.get("extract", ""))).strip()
                for page_id, page in pages.items()
            }
        except Exception:
            extracts = {}

    results: list[dict[str, str]] = []
    for match in matches[:k]:
        title = str(match.get("title", "")).strip()
        page_id = str(match.get("pageid", ""))
        snippet = extracts.get(page_id) or _clean_html(str(match.get("snippet", "")))
        if len(snippet) > 1600:
            snippet = snippet[:1597].rstrip() + "..."
        if not title:
            continue
        results.append(
            {
                "title": title,
                "url": f"https://en.wikipedia.org/wiki/{quote_plus(title.replace(' ', '_'))}",
                "snippet": snippet,
                "domain": "en.wikipedia.org",
            }
        )
    return results


def _wikipedia_query(query: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(query or "")).strip()
    lowered = cleaned.casefold()
    for marker, suffix in (
        (" discography", " discography"),
        (" first studio album", ""),
        (" best known songs", ""),
        (" official discography", " discography"),
    ):
        index = lowered.find(marker)
        if index > 0:
            return f"{cleaned[:index].strip()}{suffix}"
    return cleaned


def _prefer_wikipedia(query: str) -> bool:
    lowered = str(query or "").casefold()
    cues = (
        "wikipedia",
        "discography",
        "album",
        "song",
        "biography",
        "who is",
        "who was",
    )
    return any(cue in lowered for cue in cues)


def _merge_results(
    preferred: list[dict[str, str]],
    other: list[dict[str, str]],
    k: int,
) -> list[dict[str, str]]:
    merged: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in [*preferred, *other]:
        url = str(item.get("url", "")).strip()
        key = url.casefold()
        if not url or key in seen:
            continue
        seen.add(key)
        merged.append(item)
        if len(merged) >= k:
            break
    return merged
