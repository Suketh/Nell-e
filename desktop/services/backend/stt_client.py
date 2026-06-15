import base64
from importlib import import_module
from typing import Any

from services.audio.protocols import STTProtocol

class BackendSTTProxy(STTProtocol):
    def __init__(self, backend_client: Any, language: str = "en") -> None:
        self.backend = backend_client
        self.language = str(language or "en")

    def transcribe_bytes(self, wav_path_or_bytes: str | bytes | bytearray) -> str:
        payload_b64 = self._audio_payload(wav_path_or_bytes)
        return self.backend.transcribe_audio(payload_b64, language=self.language)

    def _audio_payload(self, wav_path_or_bytes: str | bytes | bytearray) -> str:
        if isinstance(wav_path_or_bytes, (bytes, bytearray)):
            raw = bytes(wav_path_or_bytes)
        else:
            with open(str(wav_path_or_bytes), "rb") as handle:
                raw = handle.read()
        return base64.b64encode(raw).decode("ascii")
