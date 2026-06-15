from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any


class VoxtralSTT:
    def __init__(
        self,
        model: str = "voxtral-mini-latest",
        language: str = "en",
        base_url: str = "https://api.mistral.ai",
        api_key: str = "",
        mode: str = "api",
        self_hosted_url: str = "http://127.0.0.1:8000",
        self_hosted_api_key: str = "",
        timeout_sec: int = 120,
    ) -> None:
        self.model = model
        self.language = language
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key.strip()
        self.mode = str(mode or "api").strip().lower()
        self.self_hosted_url = self_hosted_url.rstrip("/")
        self.self_hosted_api_key = self_hosted_api_key.strip()
        self.timeout_sec = int(timeout_sec)

    def describe_backend(self) -> str:
        if self.mode == "self_hosted":
            return f"Voxtral Realtime (self-hosted at {self.self_hosted_url})"
        return "Voxtral Realtime (Mistral API)"

    def is_available(self) -> bool:
        try:
            requests = import_module("requests")
        except Exception:
            return False

        timeout = min(self.timeout_sec, 3)
        if self.mode == "self_hosted":
            if not self.self_hosted_url:
                return False
            base = self.self_hosted_url.rstrip("/")
            candidates = [f"{base}/health", f"{base}/v1/models"]
            headers: dict[str, str] = {}
            if self.self_hosted_api_key:
                headers["Authorization"] = f"Bearer {self.self_hosted_api_key}"
            for endpoint in candidates:
                try:
                    response = requests.get(endpoint, headers=headers, timeout=timeout)
                    if response.ok:
                        return True
                except Exception:
                    continue
            return False

        return bool(self.api_key)

    def transcribe_bytes(self, wav_path_or_bytes: str | bytes | bytearray) -> str:
        if isinstance(wav_path_or_bytes, (bytes, bytearray)):
            raise RuntimeError("Voxtral STT currently expects a temporary wav file path from the recorder.")

        requests = import_module("requests")
        audio_path = Path(wav_path_or_bytes)
        if not audio_path.exists():
            raise RuntimeError(f"Audio file not found: {audio_path}")

        endpoint, headers = self._request_target()
        data: dict[str, Any] = {
            "model": self.model,
            "response_format": "json",
        }
        if self.language:
            data["language"] = self.language

        with audio_path.open("rb") as handle:
            files = {
                "file": (audio_path.name, handle, "audio/wav"),
            }
            response = requests.post(endpoint, headers=headers, data=data, files=files, timeout=self.timeout_sec)
        response.raise_for_status()
        payload = response.json()
        text = payload.get("text") or payload.get("transcript") or ""
        return str(text).strip()

    def _request_target(self) -> tuple[str, dict[str, str]]:
        if self.mode == "self_hosted":
            if not self.self_hosted_url:
                raise RuntimeError(
                    "Voxtral self-hosted mode is selected, but `stt.voxtral_self_hosted_url` is empty."
                )
            endpoint = self.self_hosted_url
            if not endpoint.endswith("/v1/audio/transcriptions"):
                endpoint = f"{endpoint}/v1/audio/transcriptions"
            headers: dict[str, str] = {}
            if self.self_hosted_api_key:
                headers["Authorization"] = f"Bearer {self.self_hosted_api_key}"
            return endpoint, headers

        if not self.api_key:
            raise RuntimeError(
                "Voxtral Realtime API mode is selected, but `stt.voxtral_api_key` is not configured."
            )
        endpoint = self.base_url
        if not endpoint.endswith("/v1/audio/transcriptions"):
            endpoint = f"{endpoint}/v1/audio/transcriptions"
        return endpoint, {"Authorization": f"Bearer {self.api_key}"}
