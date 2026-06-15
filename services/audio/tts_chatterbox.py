import io
import json
import os
import queue
import subprocess
import tempfile
import threading
import uuid
from importlib import import_module
from pathlib import Path
from typing import Any, Callable


class TTS:
    def __init__(
        self,
        python_executable: str,
        worker_script: str,
        speaker_wav: str | None = None,
        device: str = "cuda",
        timeout_sec: float = 300.0,
        lead_silence_ms: int = 180,
        tail_silence_ms: int = 140,
        fallback: Any | None = None,
    ) -> None:
        self.python_executable = str(python_executable)
        self.worker_script = str(worker_script)
        self.speaker_wav = speaker_wav if speaker_wav and os.path.exists(speaker_wav) else None
        self.device = str(device or "cuda")
        self.timeout_sec = max(30.0, float(timeout_sec))
        self.lead_silence_ms = max(0, int(lead_silence_ms))
        self.tail_silence_ms = max(0, int(tail_silence_ms))
        self.fallback = fallback
        self._process: subprocess.Popen[str] | None = None
        self._responses: queue.Queue[dict[str, Any]] = queue.Queue()
        self._request_lock = threading.Lock()
        self._stderr_tail: list[str] = []
        self.last_engine = "chatterbox_turbo"
        self.last_fallback_reason = ""

    def _ensure_loaded(self) -> None:
        response = self._request({"action": "preload", "device": self.device})
        if not response.get("ok"):
            raise RuntimeError(str(response.get("error", "Chatterbox-Turbo failed to load.")))

    def is_loaded(self) -> bool:
        process = self._process
        return process is not None and process.poll() is None

    def clear_cache(self) -> None:
        process = self._process
        self._process = None
        if process is not None and process.poll() is None:
            try:
                process.terminate()
            except Exception:
                pass
        fallback_clear = getattr(self.fallback, "clear_cache", None)
        if callable(fallback_clear):
            fallback_clear()

    def synthesize_audio(
        self,
        text: str,
        mood: str | None = None,
        volume: str | None = None,
        **overrides: Any,
    ) -> bytes:
        text = self._shape_expression(str(text or "").strip(), mood)
        if not text:
            return b""
        if not self.speaker_wav:
            return self._fallback_audio(text, mood, volume, overrides, "Chatterbox requires a reference voice file.")

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
            output_path = Path(handle.name)
        try:
            response = self._request(
                {
                    "action": "generate",
                    "device": self.device,
                    "text": text,
                    "audio_prompt_path": self.speaker_wav,
                    "output_path": str(output_path),
                }
            )
            if not response.get("ok"):
                raise RuntimeError(str(response.get("error", "Chatterbox generation failed.")))
            self.last_engine = "chatterbox_turbo"
            self.last_fallback_reason = ""
            return self._prepare_wav(output_path, volume)
        except Exception as exc:
            return self._fallback_audio(text, mood, volume, overrides, str(exc))
        finally:
            try:
                output_path.unlink(missing_ok=True)
            except Exception:
                pass

    def speak(
        self,
        text: str,
        mood: str | None = None,
        on_playback_start: Callable[[], None] | None = None,
        **overrides: Any,
    ) -> None:
        soundfile = import_module("soundfile")
        sounddevice = import_module("sounddevice")
        payload = self.synthesize_audio(text=text, mood=mood, **overrides)
        if not payload:
            return
        data, sample_rate = soundfile.read(io.BytesIO(payload), dtype="float32")
        if callable(on_playback_start):
            on_playback_start()
        sounddevice.play(data, sample_rate, blocking=True)
        wait_fn = getattr(sounddevice, "wait", None)
        if callable(wait_fn):
            wait_fn()

    def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._request_lock:
            process = self._ensure_worker()
            request_id = uuid.uuid4().hex
            payload["id"] = request_id
            if process.stdin is None:
                raise RuntimeError("Chatterbox worker input is unavailable.")
            process.stdin.write(json.dumps(payload, ensure_ascii=True) + "\n")
            process.stdin.flush()
            try:
                response = self._responses.get(timeout=self.timeout_sec)
            except queue.Empty as exc:
                self.clear_cache()
                raise RuntimeError("Chatterbox worker timed out.") from exc
            if response.get("id") != request_id:
                raise RuntimeError("Chatterbox worker returned an unexpected response.")
            return response

    def _ensure_worker(self) -> subprocess.Popen[str]:
        process = self._process
        if process is not None and process.poll() is None:
            return process
        python_path = Path(self.python_executable)
        worker_path = Path(self.worker_script)
        if not python_path.exists():
            raise RuntimeError(f"Chatterbox Python runtime not found: {python_path}")
        if not worker_path.exists():
            raise RuntimeError(f"Chatterbox worker not found: {worker_path}")
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        process = subprocess.Popen(
            [str(python_path), str(worker_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            creationflags=creationflags,
        )
        self._process = process
        threading.Thread(target=self._read_stdout, args=(process,), daemon=True).start()
        threading.Thread(target=self._read_stderr, args=(process,), daemon=True).start()
        return process

    def _read_stdout(self, process: subprocess.Popen[str]) -> None:
        if process.stdout is None:
            return
        for line in process.stdout:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                self._responses.put(payload)

    def _read_stderr(self, process: subprocess.Popen[str]) -> None:
        if process.stderr is None:
            return
        for line in process.stderr:
            text = line.strip()
            if text:
                self._stderr_tail.append(text)
                del self._stderr_tail[:-12]

    def _prepare_wav(self, path: Path, volume: str | None) -> bytes:
        soundfile = import_module("soundfile")
        numpy = import_module("numpy")
        data, sample_rate = soundfile.read(str(path), dtype="float32")
        data = numpy.asarray(data, dtype="float32")
        gain = self._volume_gain(volume)
        if gain != 1.0:
            data = numpy.clip(data * gain, -1.0, 1.0)
        shape = data.shape[1:]
        segments = []
        lead = int(sample_rate * self.lead_silence_ms / 1000)
        tail = int(sample_rate * self.tail_silence_ms / 1000)
        if lead:
            segments.append(numpy.zeros((lead, *shape), dtype="float32"))
        segments.append(data)
        if tail:
            segments.append(numpy.zeros((tail, *shape), dtype="float32"))
        output = numpy.concatenate(segments, axis=0)
        buffer = io.BytesIO()
        soundfile.write(buffer, output, sample_rate, format="WAV", subtype="PCM_16")
        return buffer.getvalue()

    def _fallback_audio(
        self,
        text: str,
        mood: str | None,
        volume: str | None,
        overrides: dict[str, Any],
        reason: str,
    ) -> bytes:
        if self.fallback is None:
            details = "\n".join(self._stderr_tail[-4:])
            raise RuntimeError(f"{reason}{': ' + details if details else ''}")
        self.last_engine = "xtts_tts"
        self.last_fallback_reason = reason
        fallback_options = dict(overrides)
        fallback_options.pop("exaggeration", None)
        fallback_options.pop("cfg_weight", None)
        return self.fallback.synthesize_audio(
            text=text,
            mood=mood,
            volume=volume,
            **fallback_options,
        )

    def _shape_expression(self, text: str, mood: str | None) -> str:
        lower = text.casefold()
        if mood in {"happy", "excited"} and not any(tag in lower for tag in ("[laugh]", "[chuckle]")):
            if any(cue in lower for cue in ("haha", "hilarious", "funny", "that's cute", "that is cute")):
                return f"{text} [chuckle]"
        return text

    def _volume_gain(self, volume: str | None) -> float:
        try:
            percent = float(str(volume or "0").replace("%", "").strip())
        except ValueError:
            percent = 0.0
        return max(0.25, min(2.0, 1.0 + percent / 100.0))
