import io
import os
import tempfile
import threading
import warnings
import logging
from contextlib import redirect_stderr, redirect_stdout
from importlib import import_module
from pathlib import Path
from typing import Any, Callable, cast


def _ensure_tts_cache_home() -> str:
    cache_dir = Path.cwd() / "data" / "tts_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("TTS_HOME", str(cache_dir))
    os.environ.setdefault("XDG_DATA_HOME", str(cache_dir))
    os.environ.setdefault("COQUI_TOS_AGREED", "1")
    return str(cache_dir)


def _patch_transformers_compat() -> None:
    try:
        transformers_module = import_module("transformers")
    except Exception:
        return

    if getattr(transformers_module, "BeamSearchScorer", None) is None:
        try:
            beam_search_module = import_module("transformers.generation.beam_search")
            scorer = getattr(beam_search_module, "BeamSearchScorer", None)
            if scorer is not None:
                setattr(transformers_module, "BeamSearchScorer", scorer)
                module_all = getattr(transformers_module, "__all__", None)
                if isinstance(module_all, list) and "BeamSearchScorer" not in module_all:
                    module_all.append("BeamSearchScorer")
                import_structure = getattr(transformers_module, "_import_structure", None)
                if isinstance(import_structure, dict):
                    generation_entries = import_structure.setdefault("generation", [])
                    if "BeamSearchScorer" not in generation_entries:
                        generation_entries.append("BeamSearchScorer")
        except Exception:
            pass


def _patch_torch_load_compat() -> None:
    try:
        torch_module = import_module("torch")
    except Exception:
        return

    load_fn = getattr(torch_module, "load", None)
    if not callable(load_fn):
        return
    if getattr(load_fn, "_nellie_xtts_patched", False):
        return

    def wrapped_load(*args: Any, **kwargs: Any) -> Any:
        kwargs.setdefault("weights_only", False)
        return load_fn(*args, **kwargs)

    setattr(wrapped_load, "_nellie_xtts_patched", True)
    cast(Any, torch_module).load = wrapped_load


def _patch_torchaudio_load_compat() -> None:
    try:
        torchaudio_module = import_module("torchaudio")
        torch_module = import_module("torch")
        soundfile_module = import_module("soundfile")
        numpy_module = import_module("numpy")
    except Exception:
        return

    load_fn = getattr(torchaudio_module, "load", None)
    if not callable(load_fn):
        return
    if getattr(load_fn, "_nellie_xtts_patched", False):
        return

    def wrapped_load(
        uri: str,
        frame_offset: int = 0,
        num_frames: int = -1,
        normalize: bool = True,
        channels_first: bool = True,
        format: str | None = None,
        buffer_size: int = 4096,
        backend: str | None = None,
    ) -> tuple[Any, int]:
        del format, buffer_size, backend
        data, sample_rate = soundfile_module.read(str(uri), dtype="float32", always_2d=True)
        if frame_offset > 0:
            data = data[frame_offset:]
        if num_frames is not None and num_frames >= 0:
            data = data[:num_frames]
        if channels_first:
            data = numpy_module.transpose(data, (1, 0))
        tensor = torch_module.from_numpy(data.copy())
        if not normalize:
            tensor = tensor * 32768.0
        return tensor, int(sample_rate)

    setattr(wrapped_load, "_nellie_xtts_patched", True)
    cast(Any, torchaudio_module).load = wrapped_load


def _patch_xtts_generation_compat() -> None:
    try:
        generation_module = import_module("transformers.generation")
        gpt_inference_module = import_module("TTS.tts.layers.xtts.gpt_inference")
    except Exception:
        return

    generation_mixin = getattr(generation_module, "GenerationMixin", None)
    inference_class = getattr(gpt_inference_module, "GPT2InferenceModel", None)
    if generation_mixin is None or inference_class is None:
        return
    if getattr(inference_class, "_nellie_generation_patched", False):
        return

    for name in dir(generation_mixin):
        if name.startswith("__"):
            continue
        if hasattr(inference_class, name):
            continue
        value = getattr(generation_mixin, name, None)
        if callable(value):
            setattr(inference_class, name, value)

    setattr(inference_class, "_nellie_generation_patched", True)


def _finalize_xtts_runtime_compat(model: Any) -> None:
    try:
        generation_module = import_module("transformers.generation")
    except Exception:
        return

    generation_config_class = getattr(generation_module, "GenerationConfig", None)
    if generation_config_class is None:
        return

    try:
        inference_model = model.synthesizer.tts_model.gpt.gpt_inference
    except Exception:
        return

    if getattr(inference_model, "generation_config", None) is None:
        try:
            inference_model.generation_config = generation_config_class.from_model_config(inference_model.config)
        except Exception:
            try:
                inference_model.generation_config = generation_config_class()
            except Exception:
                pass


def _xtts_warning_filters() -> None:
    warnings.filterwarnings(
        "ignore",
        message=r".*GPT2InferenceModel has generative capabilities.*GenerationMixin.*",
    )
    warnings.filterwarnings(
        "ignore",
        message=r".*attention mask is not set and cannot be inferred.*",
    )
    logging.getLogger("transformers").setLevel(logging.ERROR)
    logging.getLogger("TTS").setLevel(logging.ERROR)
    try:
        transformers_logging = import_module("transformers.utils.logging")
        set_verbosity_error = getattr(transformers_logging, "set_verbosity_error", None)
        if callable(set_verbosity_error):
            set_verbosity_error()
    except Exception:
        pass


class TTS:
    def __init__(
        self,
        model_name: str = "tts_models/multilingual/multi-dataset/xtts_v2",
        language: str = "en",
        speaker_wav: str | None = None,
        device: str = "cuda",
        temperature: float | None = None,
        speed: float = 1.0,
        split_sentences: bool = False,
        lead_silence_ms: int = 240,
        tail_silence_ms: int = 180,
    ) -> None:
        self.model_name = model_name
        self.language = str(language or "en")
        self.speaker_wav = speaker_wav if speaker_wav and os.path.exists(speaker_wav) else None
        self.device = device
        self.temperature = temperature
        self.speed = speed
        self.split_sentences = bool(split_sentences)
        self.lead_silence_ms = max(0, int(lead_silence_ms))
        self.tail_silence_ms = max(0, int(tail_silence_ms))
        self._load_lock = threading.Lock()
        self.tts: Any | None = None

    def _resolve_speed(self, rate: str | None = None) -> float:
        base_speed = float(self.speed or 1.0)
        if not rate:
            return base_speed
        try:
            rate_text = str(rate).replace("%", "").strip()
            if not rate_text:
                return base_speed
            percent = float(rate_text)
        except Exception:
            return base_speed
        adjusted = base_speed * (1.0 + (percent / 100.0))
        return max(0.74, min(1.30, adjusted))

    def _resolve_volume_gain(self, volume: str | None = None) -> float:
        if not volume:
            return 1.0
        try:
            volume_text = str(volume).replace("%", "").strip()
            if not volume_text:
                return 1.0
            percent = float(volume_text)
        except Exception:
            return 1.0
        gain = 1.0 + (percent / 100.0)
        return max(0.25, min(2.0, gain))

    def _resolve_temperature(self, temperature: float | str | None = None) -> float | None:
        value = self.temperature if temperature is None else temperature
        if value is None:
            return None
        try:
            return max(0.55, min(0.95, float(value)))
        except (TypeError, ValueError):
            return self.temperature

    def _ensure_loaded(self) -> None:
        if self.tts is not None:
            return
        with self._load_lock:
            if self.tts is not None:
                return
            _ensure_tts_cache_home()
            _patch_transformers_compat()
            _patch_torch_load_compat()
            _patch_torchaudio_load_compat()
            try:
                import_module("TTS.tts.layers.xtts.stream_generator")
            except Exception:
                pass
            _patch_xtts_generation_compat()
            try:
                tts_api_module = import_module("TTS.api")
            except Exception as exc:
                raise RuntimeError("Coqui TTS is not installed in the current Python environment.") from exc

            tts_class = getattr(tts_api_module, "TTS", None)
            if tts_class is None:
                raise RuntimeError("Coqui TTS API could not be loaded.")
            try:
                with warnings.catch_warnings():
                    _xtts_warning_filters()
                    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                        model = tts_class(self.model_name)
            except EOFError as exc:
                raise RuntimeError(
                    "XTTS needs a one-time non-interactive license confirmation. "
                    "The backend could not complete that step."
                ) from exc
            except FileNotFoundError as exc:
                raise RuntimeError(
                    "XTTS could not resolve its local cache path on Windows."
                ) from exc
            except Exception as exc:
                message = str(exc).lower()
                if "httpsconnectionpool" in message or "failed to establish a new connection" in message:
                    raise RuntimeError(
                        "XTTS could not download its model files. "
                        "Network access is blocked or the download host is unreachable."
                    ) from exc
                raise
            _finalize_xtts_runtime_compat(model)
            move_to = getattr(model, "to", None)
            if callable(move_to) and self.device:
                try:
                    move_to(self.device)
                except Exception:
                    pass
            self.tts = model

    def is_loaded(self) -> bool:
        return self.tts is not None

    def clear_cache(self) -> None:
        return

    def synthesize_audio(
        self,
        text: str,
        mood: str | None = None,
        rate: str | None = None,
        volume: str | None = None,
        temperature: float | str | None = None,
        **_: Any,
    ) -> bytes:
        del mood
        text = str(text or "").strip()
        if not text:
            return b""
        self._ensure_loaded()
        tts = self.tts
        if tts is None:
            raise RuntimeError("XTTS model is not loaded.")
        if not self.speaker_wav:
            raise RuntimeError("XTTS requires a reference voice file in `tts.voice_sample`.")

        try:
            soundfile_module = import_module("soundfile")
            numpy_module = import_module("numpy")
        except Exception as exc:
            raise RuntimeError("XTTS audio dependencies are not installed in the current Python environment.") from exc

        kwargs: dict[str, Any] = {
            "text": text,
            "speaker_wav": self.speaker_wav,
            "language": self.language,
            "file_path": None,
            "split_sentences": self.split_sentences,
        }
        resolved_temperature = self._resolve_temperature(temperature)
        if resolved_temperature is not None:
            kwargs["temperature"] = resolved_temperature
        resolved_speed = self._resolve_speed(rate)
        if resolved_speed != 1.0:
            kwargs["speed"] = resolved_speed

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
            wav_path = Path(handle.name)
        try:
            kwargs["file_path"] = str(wav_path)
            with warnings.catch_warnings():
                _xtts_warning_filters()
                with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                    tts.tts_to_file(**kwargs)
            data, sample_rate = soundfile_module.read(str(wav_path), dtype="float32")
            data = numpy_module.asarray(data, dtype="float32")
            gain = self._resolve_volume_gain(volume)
            if gain != 1.0:
                data = numpy_module.clip(data * gain, -1.0, 1.0)
            if data.ndim >= 1 and sample_rate:
                audio_shape = data.shape[1:]
                lead_samples = int(sample_rate * self.lead_silence_ms / 1000)
                tail_samples = int(sample_rate * self.tail_silence_ms / 1000)
                segments = []
                if lead_samples:
                    segments.append(numpy_module.zeros((lead_samples, *audio_shape), dtype="float32"))
                segments.append(data)
                if tail_samples:
                    segments.append(numpy_module.zeros((tail_samples, *audio_shape), dtype="float32"))
                data = numpy_module.concatenate(segments, axis=0)
            buffer = io.BytesIO()
            soundfile_module.write(buffer, data, sample_rate, format="WAV", subtype="PCM_16")
            return buffer.getvalue()
        finally:
            try:
                wav_path.unlink(missing_ok=True)
            except Exception:
                pass

    def speak(
        self,
        text: str,
        mood: str | None = None,
        on_playback_start: Callable[[], None] | None = None,
        rate: str | None = None,
        volume: str | None = None,
        temperature: float | str | None = None,
        **_: Any,
    ) -> None:
        try:
            soundfile_module = import_module("soundfile")
            sounddevice_module = import_module("sounddevice")
        except Exception as exc:
            raise RuntimeError("XTTS playback dependencies are not installed in the current Python environment.") from exc
        payload = self.synthesize_audio(
            text=text,
            mood=mood,
            rate=rate,
            volume=volume,
            temperature=temperature,
        )
        if not payload:
            return
        data, sample_rate = soundfile_module.read(io.BytesIO(payload), dtype="float32")
        if callable(on_playback_start):
            try:
                on_playback_start()
            except Exception:
                pass
        sounddevice_module.play(data, sample_rate, blocking=True)
        wait_fn = getattr(sounddevice_module, "wait", None)
        if callable(wait_fn):
            wait_fn()
