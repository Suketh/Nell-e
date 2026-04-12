from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import requests


class FishAdapterBackend:
    def __init__(
        self,
        upstream_url: str = "",
        upstream_health_url: str = "",
        api_key: str = "",
        timeout: float = 90.0,
        language: str = "en",
        upstream_use_post: bool = False,
        mock_mode: bool = False,
    ):
        self.upstream_url = str(upstream_url or "").strip()
        self.upstream_health_url = str(upstream_health_url or "").strip()
        self.api_key = str(api_key or "").strip()
        self.timeout = max(5.0, float(timeout or 90.0))
        self.language = str(language or "en").strip().lower()
        self.upstream_use_post = bool(upstream_use_post)
        self.mock_mode = bool(mock_mode)
        self._session = requests.Session()

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def health(self) -> tuple[bool, dict]:
        if self.mock_mode:
            return True, {"ok": True, "mode": "mock", "engine": "fish_speech_adapter"}
        if not self.upstream_health_url:
            return False, {"ok": False, "error": "missing_upstream_health_url"}
        try:
            response = self._session.get(self.upstream_health_url, headers=self._headers(), timeout=min(10.0, self.timeout))
            return response.ok, {
                "ok": response.ok,
                "status": response.status_code,
                "engine": "fish_speech_adapter",
                "mode": "proxy",
            }
        except Exception as exc:
            return False, {"ok": False, "error": str(exc), "engine": "fish_speech_adapter", "mode": "proxy"}

    def synthesize(self, text: str, language: str | None = None) -> tuple[bytes, str]:
        normalized = str(text or "").strip()
        if not normalized:
            raise RuntimeError("empty_text")
        selected_language = str(language or self.language or "en").strip().lower()
        if self.mock_mode:
            raise RuntimeError("mock_mode_has_no_audio")
        if not self.upstream_url:
            raise RuntimeError("missing_upstream_url")

        headers = self._headers()
        if self.upstream_use_post:
            response = self._session.post(
                self.upstream_url,
                json={"text": normalized, "language": selected_language},
                headers=headers,
                timeout=self.timeout,
            )
        else:
            response = self._session.get(
                self.upstream_url,
                params={"text": normalized, "language": selected_language},
                headers=headers,
                timeout=self.timeout,
            )
        response.raise_for_status()
        return response.content or b"", response.headers.get("Content-Type", "audio/wav")


class FishAdapterHandler(BaseHTTPRequestHandler):
    backend: FishAdapterBackend | None = None
    cors_allow_origin = "*"

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            ok, payload = self.backend.health()
            self._send_json(200 if ok else 503, payload)
            return
        if parsed.path == "/v1/tts":
            query = parse_qs(parsed.query or "")
            text = str((query.get("text") or [""])[0] or "").strip()
            language = str((query.get("language") or [""])[0] or "").strip()
            try:
                payload, content_type = self.backend.synthesize(text, language=language or None)
            except Exception as exc:
                self._send_json(500, {"error": str(exc) or "synthesis_failed"})
                return
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", content_type or "audio/wav")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        self._send_json(404, {"error": "not_found"})

    def log_message(self, _format, *_args):
        return

    def _send_json(self, status: int, payload: dict):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", self.cors_allow_origin)
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")


def build_backend(args) -> FishAdapterBackend:
    return FishAdapterBackend(
        upstream_url=args.upstream_url,
        upstream_health_url=args.upstream_health_url,
        api_key=args.api_key,
        timeout=args.timeout,
        language=args.language,
        upstream_use_post=args.upstream_use_post,
        mock_mode=args.mock,
    )


def parse_args():
    parser = argparse.ArgumentParser(description="Fish Speech HTTP adapter for Nellie.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8890)
    parser.add_argument("--upstream-url", default="")
    parser.add_argument("--upstream-health-url", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--language", default="en")
    parser.add_argument("--upstream-use-post", action="store_true")
    parser.add_argument("--mock", action="store_true", help="Expose the contract without a real upstream TTS engine.")
    return parser.parse_args()


def main():
    args = parse_args()
    FishAdapterHandler.backend = build_backend(args)
    server = ThreadingHTTPServer((args.host, args.port), FishAdapterHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
