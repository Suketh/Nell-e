from typing import Any
import base64
import re
from services.audio.protocols import TTSProtocol


class TTSService(TTSProtocol):
    def __init__(self, backend: Any, mood_profiles: dict[str, dict[str, Any]] | None = None) -> None:
        self.backend = backend
        self.mood_profiles = mood_profiles or {}
        self.enabled = True
        self.master_volume = 100

    def speak(self, text: str, mood: str | None = None, **overrides: Any) -> None:
        if not self.enabled:
            return
        options: dict[str, Any] = {}
        if mood:
            options["mood"] = mood
            options.update(self.mood_profiles.get(mood, {}))
        options.update({k: v for k, v in overrides.items() if v is not None})
        options["volume"] = self._apply_master_volume(options.get("volume"))
        chunks = self._speech_chunks(str(text or ""))
        playback_callback = options.pop("on_playback_start", None)
        for index, chunk in enumerate(chunks):
            chunk_options = dict(options)
            if index == 0 and playback_callback is not None:
                chunk_options["on_playback_start"] = playback_callback
            self.backend.speak(chunk, **chunk_options)

    @property
    def last_engine(self) -> str:
        return str(getattr(self.backend, "last_engine", self.backend.__class__.__name__))

    @property
    def last_fallback_reason(self) -> str:
        return str(getattr(self.backend, "last_fallback_reason", "") or "")

    def _speech_chunks(self, text: str, max_chars: int = 260) -> list[str]:
        cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
        if not cleaned:
            return []
        sentences = re.split(r"(?<=[.!?])\s+", cleaned)
        chunks: list[str] = []
        current = ""
        expanded_sentences: list[str] = []
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            if len(sentence) <= max_chars:
                expanded_sentences.append(sentence)
                continue
            clauses = re.split(r"(?<=[,;:])\s+", sentence)
            clause_chunk = ""
            for clause in clauses:
                candidate = f"{clause_chunk} {clause}".strip()
                if clause_chunk and len(candidate) > max_chars:
                    expanded_sentences.append(clause_chunk)
                    clause_chunk = clause
                else:
                    clause_chunk = candidate
            if clause_chunk:
                expanded_sentences.append(clause_chunk)

        for sentence in expanded_sentences:
            candidate = f"{current} {sentence}".strip()
            if current and len(candidate) > max_chars:
                chunks.append(current)
                current = sentence
            else:
                current = candidate
        if current:
            chunks.append(current)
        return chunks

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = bool(enabled)

    def set_master_volume(self, value: int) -> None:
        self.master_volume = max(0, min(100, int(value)))

    def clear_cache(self) -> None:
        clear_fn = getattr(self.backend, "clear_cache", None)
        if callable(clear_fn):
            clear_fn()

    def synthesize_audio(self, text: str, mood: str | None = None, **overrides: Any) -> str:
        options: dict[str, Any] = {}
        if mood:
            options["mood"] = mood
            options.update(self.mood_profiles.get(mood, {}))
        options.update({k: v for k, v in overrides.items() if v is not None})
        options["volume"] = self._apply_master_volume(options.get("volume"))
        synthesize_fn = getattr(self.backend, "synthesize_audio", None)
        if not callable(synthesize_fn):
            raise RuntimeError("Current TTS backend cannot synthesize audio payloads.")
        payload = synthesize_fn(text, **options)
        if not isinstance(payload, (bytes, bytearray)):
            raise RuntimeError("Current TTS backend returned an invalid audio payload.")
        return base64.b64encode(payload).decode("ascii")

    def _apply_master_volume(self, base_volume: str | None) -> str:
        base = self._parse_percent(base_volume or "+0%")
        adjusted = base + (self.master_volume - 100)
        adjusted = max(-100, min(100, adjusted))
        sign = "+" if adjusted >= 0 else ""
        return f"{sign}{adjusted}%"

    def _parse_percent(self, value: str) -> int:
        try:
            return int(str(value).replace("%", "").strip())
        except Exception:
            return 0
