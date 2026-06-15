from typing import Any

from services.audio.stt_fw import FW_STT

try:
    from services.audio.stt_voxtral import VoxtralSTT
except Exception:
    VoxtralSTT = None


def create_stt_service(conf: dict[str, Any]) -> Any:
    stt_conf = conf.get("stt", {})
    engine = preferred_stt_engine(stt_conf)

    if engine == "voxtral_realtime":
        backend = _create_voxtral_backend(stt_conf)
        if backend is None:
            raise RuntimeError("Voxtral Realtime backend is not available in the current environment.")
        return backend

    return _create_fw_backend(stt_conf)


def preferred_stt_engine(stt_conf: dict[str, Any]) -> str:
    engine = str(stt_conf.get("engine", "faster_whisper")).strip().lower()
    if engine == "voxtral_realtime" and _voxtral_is_configured(stt_conf):
        return engine
    if engine == "voxtral_realtime":
        return "faster_whisper"
    if bool(stt_conf.get("prefer_voxtral_when_configured", False)) and _voxtral_is_configured(stt_conf):
        return "voxtral_realtime"
    return "faster_whisper"


def _create_fw_backend(stt_conf: dict[str, Any]) -> FW_STT:
    return FW_STT(
        model_size=str(stt_conf.get("model_size", "small.en")),
        device=str(stt_conf.get("device", "auto")),
        language=str(stt_conf.get("language", "en")),
        beam_size=int(stt_conf.get("beam_size", 5)),
        vad_filter=bool(stt_conf.get("vad_filter", True)),
        hotwords=str(stt_conf.get("hotwords", "Nellie, hello, hi, headset")),
    )


def _create_voxtral_backend(stt_conf: dict[str, Any]) -> Any | None:
    if VoxtralSTT is None:
        return None
    return VoxtralSTT(
        model=str(stt_conf.get("voxtral_model", "voxtral-mini-latest")),
        language=str(stt_conf.get("language", "en")),
        base_url=str(stt_conf.get("voxtral_base_url", "https://api.mistral.ai")),
        api_key=str(stt_conf.get("voxtral_api_key", "")),
        mode=str(stt_conf.get("voxtral_mode", "api")),
        self_hosted_url=str(stt_conf.get("voxtral_self_hosted_url", "http://127.0.0.1:8000")),
        self_hosted_api_key=str(stt_conf.get("voxtral_self_hosted_api_key", "")),
        timeout_sec=int(stt_conf.get("voxtral_timeout_sec", 120)),
    )


def _voxtral_is_configured(stt_conf: dict[str, Any]) -> bool:
    mode = str(stt_conf.get("voxtral_mode", "api")).strip().lower()
    if mode == "self_hosted":
        enabled = bool(stt_conf.get("voxtral_self_hosted_enabled", False))
        url = bool(str(stt_conf.get("voxtral_self_hosted_url", "")).strip())
        return enabled and url
    return bool(str(stt_conf.get("voxtral_api_key", "")).strip())
