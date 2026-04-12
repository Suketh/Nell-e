from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import threading
from collections import OrderedDict
from urllib.parse import parse_qs, urlparse

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from services.audio.tts_coqui_xtts import TTS as CoquiXTTSTTS


class XTTSRuntime:
    def __init__(self, language: str = "en", default_voice_sample: str = ""):
        self.language = str(language or "en").strip().lower()
        self.default_voice_sample = str(default_voice_sample or "").strip()
        self._tts: CoquiXTTSTTS | None = None
        self._active_voice_sample = ""
        self._cache_lock = threading.RLock()
        self._engine_lock = threading.RLock()
        self._inflight: dict[str, threading.Event] = {}
        self._cache: OrderedDict[str, bytes] = OrderedDict()
        self._cache_limit = 32

    def _resolve_sample(self, voice_sample: str = "") -> str:
        chosen = str(voice_sample or "").strip() or self.default_voice_sample
        if not chosen:
            return ""
        path = Path(chosen)
        if not path.is_absolute():
            path = (ROOT_DIR / chosen).resolve()
        return str(path)

    def ensure_loaded(self, voice_sample: str = ""):
        sample = self._resolve_sample(voice_sample)
        with self._engine_lock:
            if self._tts is None:
                self._tts = CoquiXTTSTTS(language=self.language, voice_sample=sample or None)
                self._active_voice_sample = sample
                return
            if sample != self._active_voice_sample and hasattr(self._tts, "set_voice_sample"):
                self._tts.set_voice_sample(sample or None)
                self._active_voice_sample = sample

    def health(self) -> dict:
        return {"ok": True, "engine": "coqui_xtts", "voice_sample": self._active_voice_sample or self.default_voice_sample}

    def synthesize(self, text: str, voice_sample: str = "") -> bytes:
        normalized = str(text or "").strip()
        if not normalized:
            raise RuntimeError("empty_text")
        resolved_sample = self._resolve_sample(voice_sample)
        cache_key = f"{resolved_sample}|{normalized}"
        while True:
            with self._cache_lock:
                cached = self._cache.get(cache_key)
                if cached is not None:
                    self._cache.move_to_end(cache_key)
                    return cached
                inflight = self._inflight.get(cache_key)
                if inflight is None:
                    inflight = threading.Event()
                    self._inflight[cache_key] = inflight
                    is_owner = True
                else:
                    is_owner = False
            if is_owner:
                break
            inflight.wait()

        try:
            with self._engine_lock:
                self.ensure_loaded(voice_sample=voice_sample)
                if self._tts is None:
                    raise RuntimeError("xtts_not_loaded")
                payload = self._tts.synthesize_wav_bytes(normalized)
            with self._cache_lock:
                self._cache[cache_key] = payload
                self._cache.move_to_end(cache_key)
                while len(self._cache) > self._cache_limit:
                    self._cache.popitem(last=False)
            return payload
        finally:
            with self._cache_lock:
                done = self._inflight.pop(cache_key, None)
                if done is not None:
                    done.set()


class XTTSHandler(BaseHTTPRequestHandler):
    runtime: XTTSRuntime | None = None
    cors_allow_origin = "*"

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._send_json(200, self.runtime.health())
            return
        if parsed.path == "/v1/tts":
            query = parse_qs(parsed.query or "")
            text = str((query.get("text") or [""])[0] or "").strip()
            voice_sample = str((query.get("voice_sample") or [""])[0] or "").strip()
            try:
                payload = self.runtime.synthesize(text, voice_sample=voice_sample)
            except Exception as exc:
                self._send_json(500, {"error": str(exc) or "synthesis_failed"})
                return
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        self._send_json(404, {"error": "not_found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path != "/v1/tts":
            self._send_json(404, {"error": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
            raw = self.rfile.read(length) if length > 0 else b"{}"
            payload = json.loads(raw.decode("utf-8") or "{}")
            text = str(payload.get("text", "") or "").strip()
            voice_sample = str(payload.get("voice_sample", "") or "").strip()
            audio = self.runtime.synthesize(text, voice_sample=voice_sample)
        except Exception as exc:
            self._send_json(500, {"error": str(exc) or "synthesis_failed"})
            return
        self.send_response(200)
        self._send_cors_headers()
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(len(audio)))
        self.end_headers()
        self.wfile.write(audio)

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
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")


def parse_args():
    parser = argparse.ArgumentParser(description="Coqui XTTS HTTP server for Nellie.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8891)
    parser.add_argument("--language", default="en")
    parser.add_argument("--default-voice-sample", default="assets/voices/Nellie1.wav")
    return parser.parse_args()


def main():
    args = parse_args()
    XTTSHandler.runtime = XTTSRuntime(language=args.language, default_voice_sample=args.default_voice_sample)
    server = ThreadingHTTPServer((args.host, args.port), XTTSHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
