import requests
DDG = "https://duckduckgo.com/?q={q}&format=json&no_redirect=1&no_html=1"

def search(q: str, k: int = 5):
    r = requests.get(DDG.format(q=q), timeout=20)
    r.raise_for_status()
    return [{"title": q, "url": "https://duckduckgo.com", "snippet": "Result stub"} for _ in range(k)]
