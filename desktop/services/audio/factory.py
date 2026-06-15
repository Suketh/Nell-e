from typing import Any

from services.audio.service import TTSService

try:
    from services.audio.tts_xtts import TTS as XTTS
except Exception:
    XTTS = None

try:
    from services.audio.tts_chatterbox import TTS as ChatterboxTurbo
except Exception:
    ChatterboxTurbo = None


def create_tts_service(conf: dict[str, Any]) -> TTSService:
    tts_conf = conf.get("tts", {})
    engine = str(tts_conf.get("engine", "chatterbox_turbo")).strip().lower()
    if engine == "chatterbox_turbo":
        backend = _create_chatterbox_backend(tts_conf)
    elif engine == "xtts_tts":
        backend = _create_xtts_backend(tts_conf)
    else:
        raise RuntimeError(f"Unknown TTS engine: {engine}")
    if backend is None:
        raise RuntimeError(f"{engine} backend is not available in the current environment.")

    return TTSService(backend=backend, mood_profiles=_default_mood_profiles(tts_conf))


def _create_chatterbox_backend(tts_conf: dict[str, Any]) -> Any | None:
    if ChatterboxTurbo is None:
        return None
    fallback = _create_xtts_backend(tts_conf)
    return ChatterboxTurbo(
        python_executable=str(tts_conf.get("chatterbox_python", ".venv_chatterbox/Scripts/python.exe")),
        worker_script=str(tts_conf.get("chatterbox_worker", "tools/chatterbox_turbo_worker.py")),
        speaker_wav=tts_conf.get("voice_sample"),
        device=str(tts_conf.get("chatterbox_device", "cuda")),
        timeout_sec=float(tts_conf.get("chatterbox_timeout_sec", 300)),
        lead_silence_ms=int(tts_conf.get("chatterbox_lead_silence_ms", 180)),
        tail_silence_ms=int(tts_conf.get("chatterbox_tail_silence_ms", 140)),
        fallback=fallback,
    )


def _create_xtts_backend(tts_conf: dict[str, Any]) -> Any | None:
    if XTTS is None:
        return None
    language = str(tts_conf.get("language", "en"))
    xtts_language = str(tts_conf.get("xtts_language", language))
    return XTTS(
        model_name=tts_conf.get("xtts_model", "tts_models/multilingual/multi-dataset/xtts_v2"),
        language=xtts_language,
        speaker_wav=tts_conf.get("voice_sample"),
        device=str(tts_conf.get("xtts_device", "cuda")),
        temperature=float(tts_conf.get("xtts_temperature", 0.7)),
        speed=float(tts_conf.get("xtts_speed", 1.0)),
        split_sentences=bool(tts_conf.get("xtts_split_sentences", True)),
        lead_silence_ms=int(tts_conf.get("xtts_lead_silence_ms", 240)),
        tail_silence_ms=int(tts_conf.get("xtts_tail_silence_ms", 180)),
    )


def _default_mood_profiles(tts_conf: dict[str, Any]) -> dict[str, dict[str, Any]]:
    defaults: dict[str, dict[str, Any]] = {
        "neutral": {"rate": "-2%", "pitch": "+2Hz", "volume": "+0%", "temperature": 0.72},
        "happy": {"rate": "+5%", "pitch": "+10Hz", "volume": "+4%", "temperature": 0.78},
        "excited": {"rate": "+10%", "pitch": "+18Hz", "volume": "+8%", "temperature": 0.84},
        "sensual": {"rate": "-7%", "pitch": "-2Hz", "volume": "+2%", "temperature": 0.76},
        "sad": {"rate": "-9%", "pitch": "-6Hz", "volume": "-4%", "temperature": 0.66},
        "tired": {"rate": "-12%", "pitch": "-10Hz", "volume": "-6%", "temperature": 0.62},
        "bored": {"rate": "-5%", "pitch": "-6Hz", "volume": "-2%", "temperature": 0.65},
        "angry": {"rate": "+6%", "pitch": "-2Hz", "volume": "+6%", "temperature": 0.80},
        "thinking": {"rate": "-7%", "pitch": "+0Hz", "volume": "+0%", "temperature": 0.68},
        "sceptical": {"rate": "-1%", "pitch": "-2Hz", "volume": "+0%", "temperature": 0.73},
        "_reaction": {"rate": "-2%", "pitch": "+1Hz", "volume": "-8%", "temperature": 0.78},
    }

    configured = tts_conf.get("mood_profiles", {})
    if isinstance(configured, dict):
        for mood, options in configured.items():
            if isinstance(options, dict):
                merged = defaults.get(mood, {}).copy()
                merged.update(options)
                defaults[mood] = merged
    return defaults
