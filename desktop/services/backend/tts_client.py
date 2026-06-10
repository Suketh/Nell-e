import base64
import io
from importlib import import_module
from typing import Any

from services.audio.protocols import TTSProtocol

class BackendTTSProxy(TTSProtocol):
    def __init__(self, backend_client: Any) -> None:
        self.backend = backend_client
        self.enabled = True
        self.master_volume = 100

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)

    def set_master_volume(self, value: int) -> None:
        self.master_volume = max(0, min(100, int(value)))

    def clear_cache(self) -> None:
        return

    def speak(self, text: str, mood: str | None = None, on_playback_start: Any = None, **overrides: Any) -> None:
        if not self.enabled:
            return
        payload_b64 = self.backend.synthesize_speech(text=str(text or ""), mood=mood, master_volume=self.master_volume, **overrides)
        if not payload_b64:
            return
        try:
            soundfile_module = import_module("soundfile")
            sounddevice_module = import_module("sounddevice")
        except Exception as exc:
            raise RuntimeError("Backend TTS playback dependencies are not installed in the current Python environment.") from exc

        wav_bytes = base64.b64decode(payload_b64.encode("ascii"))
        data, sample_rate = soundfile_module.read(io.BytesIO(wav_bytes), dtype="float32")
        if callable(on_playback_start):
            try:
                on_playback_start()
            except Exception:
                pass
        sounddevice_module.play(data, sample_rate, blocking=True)
        wait_fn = getattr(sounddevice_module, "wait", None)
        if callable(wait_fn):
            wait_fn()
