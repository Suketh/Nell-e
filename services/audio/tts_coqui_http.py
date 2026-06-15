from __future__ import annotations

import re
import tempfile
import time
import wave
from contextlib import suppress
from io import BytesIO
from pathlib import Path

import requests


class TTS:
    """HTTP adapter for an external Coqui XTTS server."""

    def __init__(
        self,
        base_url: str,
        health_url: str | None = None,
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
            raise RuntimeError("Coqui XTTS server requires a base_url.")
        self.health_url = str(health_url or f"{self.base_url}{health_path}").strip()
        self.timeout = max(5.0, float(timeout or 90.0))
        self.language = str(language or "en").strip().lower()
        self.output_samplerate = int(output_samplerate or 24000)
        self.synth_url = f"{self.base_url}{synth_path}"
        self.use_post = bool(use_post)
        self.voice_profile = ""
        self.voice_sample = ""
        self._session = requests.Session()
        self._health_timeout = min(3.0, self.timeout)
        self._connect_timeout = min(5.0, self.timeout)
        self._failure_backoff_seconds = 20.0
        self._unhealthy_until = 0.0
        self._last_healthcheck_at = 0.0
        self._last_health_ok = False

    def warmup(self):
        self._check_health(force=True)

    def close(self):
        with suppress(Exception):
            self._session.close()
        return None

    def speak(self, text: str):
        audio = self.synthesize_wav_bytes(text)
        temporary_path = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as audio_file:
                audio_file.write(audio)
                temporary_path = audio_file.name
            import winsound

            winsound.PlaySound(temporary_path, winsound.SND_FILENAME)
        finally:
            if temporary_path:
                with suppress(OSError):
                    Path(temporary_path).unlink()

    def set_voice_profile(self, voice_profile: str = "", voice_sample: str = ""):
        self.voice_profile = str(voice_profile or "").strip()
        self.voice_sample = str(voice_sample or "").strip()

    def _check_health(self, force: bool = False):
        now = time.time()
        if not force:
            if now < self._unhealthy_until:
                raise RuntimeError("Coqui XTTS is cooling down after a recent failure.")
            if now - self._last_healthcheck_at < 5.0:
                if self._last_health_ok:
                    return
                raise RuntimeError("Coqui XTTS health check recently failed.")
        response = self._session.get(
            self.health_url,
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
            raise RuntimeError("Coqui XTTS received empty text.")
        self._check_health()
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
                    timeout=(self._connect_timeout, self.timeout),
                )
            else:
                response = self._session.get(
                    self.synth_url,
                    params=payload,
                    timeout=(self._connect_timeout, self.timeout),
                )
            response.raise_for_status()
            content = response.content or b""
            if not content:
                raise RuntimeError("Coqui XTTS returned empty audio.")
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
