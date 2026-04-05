import json
import re
import subprocess
import threading
import time
import urllib.parse
import urllib.request
import wave
from io import BytesIO
from pathlib import Path

import sounddevice as sd
from websockets.sync.client import connect


class TTS:
    def __init__(
        self,
        repo_path: str,
        model_path: str = "microsoft/VibeVoice-Realtime-0.5B",
        speaker_name: str = "Emma",
        device: str = "auto",
        cfg_scale: float = 1.5,
        inference_steps: int = 3,
        max_chars_per_chunk: int = 220,
        playback_rate: float = 1.0,
        ssml_lite_enabled: bool = False,
        server_port: int = 3000,
        server_start_timeout: float = 180.0,
        python_executable: str = "python",
        language: str = "en",
        chunk_join_silence_ms: int = 90,
        tail_silence_ms: int = 220,
    ):
        self.repo_path = Path(repo_path).resolve()
        self.model_path = model_path
        self.speaker_name = speaker_name
        self.language = (language or "en").strip().lower()
        self.device = "cuda" if device == "auto" else device
        self.cfg_scale = cfg_scale
        self.inference_steps = inference_steps
        self.max_chars_per_chunk = max_chars_per_chunk
        self.playback_rate = max(0.85, min(1.20, float(playback_rate or 1.0)))
        self.ssml_lite_enabled = bool(ssml_lite_enabled)
        self.output_samplerate = int(24000 * self.playback_rate)
        self.server_port = server_port
        self.server_start_timeout = server_start_timeout
        self.python_executable = python_executable
        self.chunk_join_silence_ms = max(0, int(chunk_join_silence_ms or 0))
        self.tail_silence_ms = max(0, int(tail_silence_ms or 0))

        self.server_script = self.repo_path / "demo" / "vibevoice_realtime_demo.py"
        if not self.server_script.exists():
            raise FileNotFoundError(f"VibeVoice realtime server script not found: {self.server_script}")

        self.base_http_url = f"http://127.0.0.1:{self.server_port}"
        self.stream_url = f"ws://127.0.0.1:{self.server_port}/stream"
        self._server_process = None
        self._stop_event = threading.Event()
        self._available_voices = None

    def speak(self, text: str):
        segments = self._prepare_segments(text)
        if not segments:
            return

        self._ensure_server()
        self._stop_event.clear()
        for kind, value in segments:
            if self._stop_event.is_set():
                break
            if kind == "pause":
                time.sleep(value / 1000.0)
                continue

            chunk = value
            params = urllib.parse.urlencode(
                {
                    "text": chunk,
                    "cfg": self.cfg_scale,
                    "steps": self.inference_steps,
                    "voice": self._voice_key(),
                }
            )

            with connect(f"{self.stream_url}?{params}", open_timeout=30, close_timeout=10, max_size=None) as websocket:
                stream = sd.RawOutputStream(
                    samplerate=self.output_samplerate,
                    channels=1,
                    dtype="int16",
                    blocksize=0,
                )
                stream.start()
                try:
                    while True:
                        if self._stop_event.is_set():
                            break
                        try:
                            message = websocket.recv()
                        except Exception:
                            break

                        if isinstance(message, bytes):
                            if self._stop_event.is_set():
                                break
                            stream.write(message)
                            continue

                        if isinstance(message, str):
                            try:
                                payload = json.loads(message)
                            except json.JSONDecodeError:
                                continue
                            if payload.get("event") == "backend_error":
                                details = payload.get("data", {}).get("message", "Unknown backend error")
                                raise RuntimeError(f"VibeVoice backend error: {details}")
                finally:
                    stream.stop()
                    stream.close()

        self._stop_event.clear()

    def synthesize_pcm16(self, text: str) -> tuple[bytes, int]:
        segments = self._prepare_segments(text)
        if not segments:
            return b"", self.output_samplerate

        self._ensure_server()
        pcm_chunks: list[bytes] = []
        text_segment_count = sum(1 for kind, _ in segments if kind == "text")
        seen_text_segments = 0
        for kind, value in segments:
            if kind == "pause":
                pause_samples = max(1, int(self.output_samplerate * (int(value) / 1000.0)))
                pcm_chunks.append(b"\x00\x00" * pause_samples)
                continue

            chunk = value
            seen_text_segments += 1
            params = urllib.parse.urlencode(
                {
                    "text": chunk,
                    "cfg": self.cfg_scale,
                    "steps": self.inference_steps,
                    "voice": self._voice_key(),
                }
            )

            with connect(f"{self.stream_url}?{params}", open_timeout=30, close_timeout=10, max_size=None) as websocket:
                while True:
                    try:
                        message = websocket.recv()
                    except Exception:
                        break

                    if isinstance(message, bytes):
                        pcm_chunks.append(message)
                        continue

                    if isinstance(message, str):
                        try:
                            payload = json.loads(message)
                        except json.JSONDecodeError:
                            continue
                        if payload.get("event") == "backend_error":
                            details = payload.get("data", {}).get("message", "Unknown backend error")
                            raise RuntimeError(f"VibeVoice backend error: {details}")
            if seen_text_segments < text_segment_count and self.chunk_join_silence_ms > 0:
                join_samples = max(1, int(self.output_samplerate * (self.chunk_join_silence_ms / 1000.0)))
                pcm_chunks.append(b"\x00\x00" * join_samples)

        if pcm_chunks and self.tail_silence_ms > 0:
            tail_samples = max(1, int(self.output_samplerate * (self.tail_silence_ms / 1000.0)))
            pcm_chunks.append(b"\x00\x00" * tail_samples)

        return b"".join(pcm_chunks), self.output_samplerate

    def synthesize_wav_bytes(self, text: str) -> bytes:
        pcm_bytes, sample_rate = self.synthesize_pcm16(text)
        if not pcm_bytes:
            return b""

        buffer = BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm_bytes)
        return buffer.getvalue()

    def set_ssml_lite_enabled(self, enabled: bool):
        self.ssml_lite_enabled = bool(enabled)

    def is_ssml_lite_enabled(self) -> bool:
        return self.ssml_lite_enabled

    def stop(self):
        self._stop_event.set()

    def close(self):
        self.stop()
        if self._server_process and self._server_process.poll() is None:
            self._server_process.terminate()
            try:
                self._server_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._server_process.kill()
        self._server_process = None

    def warmup(self):
        self._ensure_server()
        self._load_config()
        try:
            self.synthesize_pcm16("Hello.")
        except Exception:
            pass

    def is_ready(self) -> bool:
        return self._server_ready()

    def get_available_voices(self) -> list[str]:
        config = self._load_config()
        voices = config.get("voices", [])
        if isinstance(voices, list):
            filtered = []
            for item in voices:
                voice = str(item).strip()
                if not voice:
                    continue
                if voice.endswith("_woman"):
                    filtered.append(voice)
            current = str(self.speaker_name or "").strip()
            if current.endswith("_woman"):
                return [current]
            return filtered[:1]
        return []

    def get_selected_voice(self) -> str:
        return self._voice_key()

    def set_voice(self, voice_key: str):
        voice = (voice_key or "").strip()
        if not voice:
            return
        if not voice.endswith("_woman"):
            raise ValueError("Only female voice presets are allowed for Nellie.")
        self.speaker_name = voice

    def set_language(self, language: str):
        normalized = (language or "en").strip().lower() or "en"
        self.language = normalized
        voices = self.get_available_voices()
        if not voices:
            return
        current = self._voice_key()
        if current.startswith(f"{normalized}-"):
            return
        for voice in voices:
            if voice.startswith(f"{normalized}-"):
                self.speaker_name = voice
                return

    def get_language(self) -> str:
        return self.language

    def get_supported_languages(self) -> list[str]:
        prefixes = []
        for voice in self.get_available_voices():
            if "-" not in voice:
                continue
            prefix = voice.split("-", 1)[0].strip().lower()
            if prefix and prefix not in prefixes:
                prefixes.append(prefix)
        return prefixes or [self.language]

    def _ensure_server(self):
        if self._server_ready():
            return

        if self._server_process and self._server_process.poll() is not None:
            self._server_process = None

        if self._server_process is None:
            command = [
                self.python_executable,
                str(self.server_script),
                "--port",
                str(self.server_port),
                "--model_path",
                self.model_path,
                "--device",
                self.device,
            ]
            self._server_process = subprocess.Popen(
                command,
                cwd=str(self.repo_path),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        deadline = time.time() + self.server_start_timeout
        while time.time() < deadline:
            if self._server_ready():
                return
            if self._server_process and self._server_process.poll() is not None:
                raise RuntimeError("VibeVoice server exited during startup.")
            time.sleep(1.0)

        raise RuntimeError("Timed out while waiting for the VibeVoice server to become ready.")

    def _server_ready(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.base_http_url}/config", timeout=3) as response:
                return response.status == 200
        except Exception:
            return False

    def _voice_key(self) -> str:
        speaker = (self.speaker_name or "").strip()
        if not speaker:
            return f"{self.language}-Emma_woman"
        if re.match(r"^[a-z]{2}-", speaker, flags=re.IGNORECASE):
            return speaker
        suffix = speaker if "_" in speaker else f"{speaker}_woman"
        return f"{self.language}-{suffix}"

    def _load_config(self) -> dict:
        self._ensure_server()
        with urllib.request.urlopen(f"{self.base_http_url}/config", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if isinstance(payload, dict):
            voices = payload.get("voices", [])
            self._available_voices = [
                str(item).strip()
                for item in voices
                if str(item).strip() and str(item).strip().endswith("_woman")
            ]
            default_voice = str(payload.get("default_voice", "") or "").strip()
            if default_voice.endswith("_woman") and not self.speaker_name:
                self.speaker_name = default_voice
            elif self.speaker_name and not str(self.speaker_name).strip().endswith("_woman"):
                available = self._available_voices
                if available:
                    self.speaker_name = available[0]
            return payload
        return {"voices": []}

    def _prepare_segments(self, text: str):
        normalized = self._normalize_spoken_text(text)
        if not normalized:
            return []

        if self.ssml_lite_enabled:
            normalized = self._apply_ssml_lite_markup(normalized)
            return self._segments_from_markup(normalized)

        return [("text", chunk) for chunk in self._split_text_for_tts(normalized)]

    def _normalize_spoken_text(self, text: str) -> str:
        text = re.sub(r"<(?!/?(?:speak|break|prosody|filler|laugh|p)\b)[^>]+>", " ", text or "", flags=re.IGNORECASE)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _apply_ssml_lite_markup(self, text: str) -> str:
        text = text or ""
        text = re.sub(r"(?i)</p\s*>", " [[PAUSE=220]] ", text)
        text = re.sub(r"(?i)<p\s*>", "", text)
        text = re.sub(r"(?i)</?speak\s*>", "", text)
        text = re.sub(r"(?is)<prosody\b[^>]*>(.*?)</prosody>", r"\1", text)
        text = re.sub(
            r'(?i)<break\s+time="(\d+)(ms|s)"\s*/?>',
            lambda match: f" [[PAUSE={self._coerce_pause_ms(match.group(1), match.group(2))}]] ",
            text,
        )
        text = re.sub(
            r'(?i)<filler\s+kind="([^"]+)"\s*/?>',
            lambda match: f" {self._map_filler(match.group(1))} ",
            text,
        )
        text = re.sub(
            r"(?is)<laugh>(.*?)</laugh>",
            lambda match: f" {self._map_laugh(match.group(1))} ",
            text,
        )
        text = re.sub(r"\n\s*\n+", " [[PAUSE=220]] ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _segments_from_markup(self, text: str):
        parts = re.split(r"(\[\[PAUSE=\d+\]\])", text)
        segments = []
        for part in parts:
            if not part:
                continue
            pause_match = re.fullmatch(r"\[\[PAUSE=(\d+)\]\]", part)
            if pause_match:
                segments.append(("pause", int(pause_match.group(1))))
                continue

            for chunk in self._split_sentences_for_tts(part):
                if chunk:
                    segments.append(("text", chunk))
                    pause_ms = self._sentence_pause_ms(chunk)
                    if pause_ms:
                        segments.append(("pause", pause_ms))

        while segments and segments[-1][0] == "pause":
            segments.pop()
        return segments

    def _coerce_pause_ms(self, amount: str, unit: str) -> int:
        value = int(amount)
        if unit.lower() == "s":
            value *= 1000
        return max(40, min(800, value))

    def _map_filler(self, kind: str) -> str:
        key = (kind or "").strip().lower()
        fillers = {
            "mm": "Mm,",
            "hm": "Hm,",
            "ehh": "Ehh,",
            "well": "Well,",
            "heh": "Heh,",
            "mmh": "Mmh,",
        }
        return fillers.get(key, "Mm,")

    def _map_laugh(self, text: str) -> str:
        candidate = re.sub(r"[^a-zA-Z]", "", (text or "")).lower()
        if candidate in {"heh", "mmh", "hah"}:
            return f"{candidate.capitalize()},"
        return "Heh,"

    def _sentence_pause_ms(self, chunk: str) -> int:
        text = (chunk or "").strip()
        if not text:
            return 0
        if text.endswith("?"):
            return 165
        if text.endswith("!"):
            return 90
        if text.endswith("."):
            return 135
        if text.endswith(","):
            return 80
        return 95

    def _split_sentences_for_tts(self, text: str):
        text = re.sub(r"\s+", " ", (text or "").strip())
        if not text:
            return []

        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
        if len(sentences) <= 1:
            return self._split_text_for_tts(text)

        chunks = []
        for sentence in sentences:
            chunks.extend(self._split_text_for_tts(sentence))
        return chunks

    def _split_text_for_tts(self, text: str):
        text = re.sub(r"\s+", " ", (text or "").strip())
        if not text:
            return []
        if len(text) <= self.max_chars_per_chunk:
            return [text]

        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
        chunks = []
        current = ""
        for sentence in sentences:
            candidate = f"{current} {sentence}".strip()
            if current and len(candidate) > self.max_chars_per_chunk:
                chunks.append(current)
                current = sentence
            else:
                current = candidate

        if current:
            chunks.append(current)

        normalized_chunks = []
        for chunk in chunks:
            if len(chunk) <= self.max_chars_per_chunk:
                normalized_chunks.append(chunk)
                continue
            words = chunk.split()
            current_words = []
            for word in words:
                candidate = " ".join(current_words + [word]).strip()
                if current_words and len(candidate) > self.max_chars_per_chunk:
                    normalized_chunks.append(" ".join(current_words))
                    current_words = [word]
                else:
                    current_words.append(word)
            if current_words:
                normalized_chunks.append(" ".join(current_words))

        return [chunk for chunk in normalized_chunks if chunk]

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
