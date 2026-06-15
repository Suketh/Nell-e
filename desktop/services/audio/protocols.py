from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class STTProtocol(Protocol):
    language: str

    def transcribe_bytes(self, wav_path_or_bytes: str | bytes | bytearray) -> str:
        ...


@runtime_checkable
class TTSProtocol(Protocol):
    enabled: bool
    master_volume: int

    def set_enabled(self, enabled: bool) -> None:
        ...

    def set_master_volume(self, value: int) -> None:
        ...

    def clear_cache(self) -> None:
        ...

    def speak(self, text: str, mood: str | None = None, **overrides: Any) -> None:
        ...
