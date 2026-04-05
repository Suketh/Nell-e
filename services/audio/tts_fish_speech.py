from __future__ import annotations

import re
import time
import wave
from io import BytesIO

import requests


class TTS:
    """HTTP adapter for an external Fish Speech-style TTS server.

    The adapter expects a healthy HTTP service and keeps Nellie's backend
    agnostic to the actual deployment details of Fish Speech.
    """

    def __init__(
        self,
        base_url: str,
        health_url: str | None = None,
        api_key: str = "",
        timeout: float = 90.0,
        language: str = "en",
        output_samplerate: int = 24000,
        synth_path: str = "/v1/tts",
        health_path: str = "/health",
        use_post: bool = False,
        **_: object,
    ):
        self.base_url = str(base_url or "").strip().rstrip("/")
        if not self.base_url:
            raise RuntimeError("Fish Speech requires a base_url.")
        self.health_url = str(health_url or f"{self.base_url}{health_path}").strip()
        self.api_key = str(api_key or "").strip()
        self.timeout = max(5.0, float(timeout or 90.0))
        self.language = str(language or "en").strip().lower()
        self.output_samplerate = int(output_samplerate or 24000)
        self.synth_url = f"{self.base_url}{synth_path}"
        self.use_post = bool(use_post)
        self._session = requests.Session()
        self.voice_profile = ""
        self.voice_sample = ""
        self._health_timeout = min(3.0, self.timeout)
        self._connect_timeout = min(5.0, self.timeout)
        self._failure_backoff_seconds = 20.0
        self._unhealthy_until = 0.0
        self._last_healthcheck_at = 0.0
        self._last_health_ok = False

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def warmup(self):
        self._check_health(force=True)

    def close(self):
        try:
            self._session.close()
        except Exception:
            pass
        return None

    def set_voice_profile(self, voice_profile: str = "", voice_sample: str = ""):
        self.voice_profile = str(voice_profile or "").strip()
        self.voice_sample = str(voice_sample or "").strip()

    def _check_health(self, force: bool = False):
        now = time.time()
        if not force:
            if now < self._unhealthy_until:
                raise RuntimeError("Fish Speech is cooling down after a recent failure.")
            if now - self._last_healthcheck_at < 5.0:
                if self._last_health_ok:
                    return
                raise RuntimeError("Fish Speech health check recently failed.")
        response = self._session.get(
            self.health_url,
            headers=self._headers(),
            timeout=(self._connect_timeout, self._health_timeout),
        )
        response.raise_for_status()
        self._last_healthcheck_at = now
        self._last_health_ok = True
        self._unhealthy_until = 0.0

    def _mark_failure(self):
        now = time.time()
        self._last_healthcheck_at = now
        self._last_health_ok = False
        self._unhealthy_until = now + self._failure_backoff_seconds

    def synthesize_wav_bytes(self, text: str) -> bytes:
        normalized = re.sub(r"\s+", " ", str(text or "").strip())
        if not normalized:
            raise RuntimeError("Fish Speech received empty text.")
        self._check_health()
        headers = self._headers()
        payload = {"text": normalized, "language": self.language}
        if self.voice_profile:
            payload["voice_profile"] = self.voice_profile
        if self.voice_sample:
            payload["voice_sample"] = self.voice_sample
        try:
            if self.use_post:
                response = self._session.post(
                    self.synth_url,
                    json=payload,
                    headers=headers,
                    timeout=(self._connect_timeout, self.timeout),
                )
            else:
                response = self._session.get(
                    self.synth_url,
                    params=payload,
                    headers=headers,
                    timeout=(self._connect_timeout, self.timeout),
                )
            response.raise_for_status()
            content = response.content or b""
            if not content:
                raise RuntimeError("Fish Speech returned empty audio.")
            try:
                with wave.open(BytesIO(content), "rb") as wav_file:
                    self.output_samplerate = int(wav_file.getframerate() or self.output_samplerate)
            except Exception:
                pass
            self._last_health_ok = True
            self._unhealthy_until = 0.0
            return content
        except Exception:
            self._mark_failure()
            raise
