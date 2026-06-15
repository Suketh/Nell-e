import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml
from PySide6.QtWidgets import QApplication

from llm.ollama_client import OllamaClient
from services.audio.tts_null import TTS as TTS_Null
from services.conversation_http import HttpConversationClient
from services.conversation_service import ConversationService
from services.memory.sqlite_store import MemoryStore
from services.persona_profile import load_persona
from ui.main_window import MainWindow


CONFIG_PATH = Path("config.yaml")
DEFAULT_PROFILE_PATH = Path("data/client_profile.json")
DEFAULT_PROFILE_REGISTRY_PATH = Path("data/client_profiles.json")
PROFILE_BADGE_COLORS = [
    "#c9785a",
    "#a26f3d",
    "#8f8ce7",
    "#4fa58a",
    "#cf7c66",
    "#5f86d6",
    "#d49b4f",
    "#9b6ad6",
]


@dataclass
class AppContext:
    conf: dict[str, Any]
    persona: dict[str, Any]
    persona_path: Path
    conversation: Any
    ollama: OllamaClient | None
    stt: Any
    tts: Any
    memory: MemoryStore | None


def log_startup(message: str) -> None:
    print(f"[startup] {message}")


def load_config(config_path: Path = CONFIG_PATH) -> dict[str, Any]:
    return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}


def load_json_dict(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def get_profile_path(conf: dict[str, Any]) -> Path:
    raw_path = (conf.get("paths", {}) or {}).get("client_profile_path", str(DEFAULT_PROFILE_PATH))
    return Path(raw_path)


def get_profile_registry_path(conf: dict[str, Any]) -> Path:
    raw_path = (conf.get("paths", {}) or {}).get("client_profiles_path", str(DEFAULT_PROFILE_REGISTRY_PATH))
    return Path(raw_path)


def assign_badge_color(profile: dict[str, Any], existing_profiles: list[dict[str, Any]]) -> str:
    current = str(profile.get("badge_color", "") or "").strip()
    if current:
        return current

    used = {
        str(item.get("badge_color", "") or "").strip().lower()
        for item in existing_profiles
        if isinstance(item, dict)
    }
    for color in PROFILE_BADGE_COLORS:
        if color.lower() not in used:
            return color
    return PROFILE_BADGE_COLORS[len(existing_profiles) % len(PROFILE_BADGE_COLORS)]


def ensure_local_profile(profile_path: Path) -> dict[str, Any]:
    existing_profile = load_json_dict(profile_path)
    if existing_profile and str(existing_profile.get("user_id", "")).strip():
        return existing_profile

    profile = {
        "user_id": f"local-{uuid4().hex[:12]}",
        "display_name": "Local User",
        "badge_color": PROFILE_BADGE_COLORS[0],
        "created_at": int(time.time()),
    }
    write_json(profile_path, profile)
    return profile


def ensure_profile_registry(
    registry_path: Path,
    active_profile: dict[str, Any],
) -> dict[str, Any]:
    registry = {
        "current_user_id": str(active_profile.get("user_id", "") or "").strip(),
        "profiles": [],
    }
    stored_registry = load_json_dict(registry_path) or {}
    stored_profiles = stored_registry.get("profiles", [])
    if isinstance(stored_profiles, list):
        registry["profiles"] = [item for item in stored_profiles if isinstance(item, dict)]

    stored_current_user_id = str(stored_registry.get("current_user_id", "") or "").strip()
    if stored_current_user_id:
        registry["current_user_id"] = stored_current_user_id

    normalized_profile = dict(active_profile)
    normalized_profile["badge_color"] = assign_badge_color(normalized_profile, registry["profiles"])
    active_user_id = str(normalized_profile.get("user_id", "") or "").strip()

    existing_profile = next(
        (
            item
            for item in registry["profiles"]
            if str(item.get("user_id", "") or "").strip() == active_user_id
        ),
        None,
    )
    if existing_profile is None:
        registry["profiles"].append(normalized_profile)
    else:
        existing_profile.update(normalized_profile)

    registry["current_user_id"] = active_user_id
    write_json(registry_path, registry)
    return registry


def apply_local_profile_to_config(
    conf: dict[str, Any],
    local_profile: dict[str, Any],
    profile_path: Path,
    registry_path: Path,
    registry: dict[str, Any],
) -> None:
    local_profile["badge_color"] = assign_badge_color(local_profile, registry.get("profiles", []))

    profile_conf = conf.setdefault("profile", {})
    profile_conf["user_id"] = str(local_profile.get("user_id", "") or profile_conf.get("user_id", "local-user"))
    profile_conf["display_name"] = str(
        local_profile.get("display_name", "") or profile_conf.get("display_name", "Local User")
    )
    profile_conf["badge_color"] = str(
        local_profile.get("badge_color", "") or profile_conf.get("badge_color", PROFILE_BADGE_COLORS[0])
    )

    paths_conf = conf.setdefault("paths", {})
    paths_conf["client_profile_path"] = str(profile_path)
    paths_conf["client_profiles_path"] = str(registry_path)


def build_http_conversation_client(conf: dict[str, Any], persona_path: Path) -> HttpConversationClient:
    return HttpConversationClient(conf=conf, persona_path=persona_path, config_path=CONFIG_PATH)


def build_local_conversation_service(
    conf: dict[str, Any],
    persona: dict[str, Any],
) -> tuple[ConversationService, OllamaClient, MemoryStore]:
    ollama = OllamaClient(
        conf["ollama"]["host"],
        text_model=conf["ollama"]["text_model"],
        vision_model=conf["ollama"]["vision_model"],
    )
    memory = MemoryStore(Path(conf["paths"]["db_path"]))
    conversation = ConversationService(
        persona=persona,
        ollama=ollama,
        memory=memory,
        gallery_dir=conf.get("paths", {}).get("gallery_dir"),
    )
    return conversation, ollama, memory


def build_conversation_stack(
    conf: dict[str, Any],
    persona: dict[str, Any],
    persona_path: Path,
) -> tuple[Any, OllamaClient | None, MemoryStore | None]:
    backend_conf = ((conf.get("backend", {}) or {}).get("conversation", {}) or {})
    if bool(backend_conf.get("enabled", True)):
        try:
            return build_http_conversation_client(conf, persona_path), None, None
        except Exception as exc:
            log_startup(f"Conversation backend unavailable: {exc}. Falling back to in-process conversation.")

    return build_local_conversation_service(conf, persona)


def build_stt(conf: dict[str, Any]) -> Any:
    if not conf.get("ui", {}).get("enable_voice_input", True):
        return None

    stt_conf = conf.get("stt", {})
    stt_engine = stt_conf.get("engine", "faster_whisper")
    if stt_engine == "whispercpp":
        from services.audio.stt_whispercpp import WhisperCppSTT

        return WhisperCppSTT(stt_conf)
    if stt_engine == "server_http":
        from services.audio.stt_server_http import ServerHttpSTT

        return ServerHttpSTT(stt_conf)

    from services.audio.stt_faster_whisper import FasterWhisperSTT

    return FasterWhisperSTT(stt_conf)


def build_pyttsx3_or_null() -> Any:
    try:
        from services.audio.tts_pyttsx3 import TTS as TTS_Pyttsx3

        return TTS_Pyttsx3()
    except Exception as exc:
        log_startup(f"pyttsx3 unavailable: {exc}. Starting without TTS.")
        return TTS_Null()


def fallback_to_pyttsx3_or_null(reason: str, exc: Exception) -> Any:
    log_startup(f"{reason}: {exc}. Falling back to pyttsx3.")
    return build_pyttsx3_or_null()


def build_tts(conf: dict[str, Any]) -> Any:
    tts_conf = conf.get("tts", {})
    tts_engine = tts_conf.get("engine", "none")

    if tts_engine == "coqui_xtts_server":
        from services.audio.tts_coqui_http import TTS as TTS_CoquiHttp

        server_conf = tts_conf.get("coqui_xtts_server", {})
        try:
            tts = TTS_CoquiHttp(
                base_url=server_conf.get("base_url", "http://127.0.0.1:8891"),
                health_url=server_conf.get("health_url"),
                timeout=server_conf.get("timeout", 120),
                language=tts_conf.get("language", "en"),
                output_samplerate=server_conf.get("output_samplerate", 24000),
                synth_path=server_conf.get("synth_path", "/v1/tts"),
                health_path=server_conf.get("health_path", "/health"),
                use_post=server_conf.get("use_post", True),
            )
            tts.set_voice_profile(
                tts_conf.get("default_voice_profile", ""),
                tts_conf.get("voice_sample", ""),
            )
            return tts
        except Exception as exc:
            return fallback_to_pyttsx3_or_null("Coqui XTTS server unavailable", exc)

    if tts_engine == "coqui_xtts":
        from services.audio.tts_coqui_xtts import TTS as TTS_Coqui

        try:
            return TTS_Coqui(
                language=tts_conf.get("language", "en"),
                voice_sample=tts_conf.get("voice_sample"),
            )
        except Exception as exc:
            return fallback_to_pyttsx3_or_null("Coqui XTTS unavailable", exc)

    if tts_engine == "vibevoice_realtime":
        from services.audio.tts_vibevoice_realtime import TTS as TTS_VibeVoiceRealtime

        vibe_conf = tts_conf.get("vibevoice", {})
        try:
            return TTS_VibeVoiceRealtime(
                repo_path=vibe_conf.get("repo_path", "external/VibeVoice"),
                model_path=vibe_conf.get("model_path", "microsoft/VibeVoice-Realtime-0.5B"),
                speaker_name=vibe_conf.get("speaker_name", "Emma"),
                language=tts_conf.get("language", "en"),
                device=vibe_conf.get("device", "auto"),
                cfg_scale=vibe_conf.get("cfg_scale", 1.5),
                inference_steps=vibe_conf.get("inference_steps", 3),
                max_chars_per_chunk=vibe_conf.get("max_chars_per_chunk", 220),
                playback_rate=vibe_conf.get("playback_rate", 1.0),
                ssml_lite_enabled=vibe_conf.get("ssml_lite_enabled", False),
                server_port=vibe_conf.get("server_port", 3000),
                server_start_timeout=vibe_conf.get("server_start_timeout", 180),
                python_executable=vibe_conf.get("python_executable", sys.executable),
            )
        except Exception as exc:
            return fallback_to_pyttsx3_or_null("VibeVoice realtime unavailable", exc)

    if tts_engine == "pyttsx3":
        return build_pyttsx3_or_null()

    return TTS_Null()


def bootstrap_app_context() -> AppContext:
    conf = load_config()
    profile_path = get_profile_path(conf)
    registry_path = get_profile_registry_path(conf)
    local_profile = ensure_local_profile(profile_path)
    registry = ensure_profile_registry(registry_path, local_profile)
    apply_local_profile_to_config(conf, local_profile, profile_path, registry_path, registry)

    persona_path = Path(conf["paths"]["personality_path"])
    persona = load_persona(persona_path)
    conversation, ollama, memory = build_conversation_stack(conf, persona, persona_path)
    stt = build_stt(conf)
    tts = build_tts(conf)

    return AppContext(
        conf=conf,
        persona=persona,
        persona_path=persona_path,
        conversation=conversation,
        ollama=ollama,
        stt=stt,
        tts=tts,
        memory=memory,
    )


def connect_optional_close(app: QApplication, service: Any) -> None:
    if hasattr(service, "close"):
        app.aboutToQuit.connect(service.close)


def ensure_window_is_visible(app: QApplication, window: MainWindow) -> None:
    frame = window.frameGeometry()
    visible_screens = [
        screen.availableGeometry()
        for screen in app.screens()
        if screen.availableGeometry().intersects(frame)
    ]
    if visible_screens:
        return

    screen = app.primaryScreen()
    if screen is None:
        return
    available = screen.availableGeometry()
    window.move(
        available.center().x() - window.width() // 2,
        available.center().y() - window.height() // 2,
    )


def main() -> None:
    print("[startup] bootstrapping app context", flush=True)
    context = bootstrap_app_context()
    print("[startup] creating QApplication", flush=True)
    app = QApplication(sys.argv)

    connect_optional_close(app, context.memory)
    connect_optional_close(app, context.conversation)
    connect_optional_close(app, context.tts)
    connect_optional_close(app, context.stt)

    print("[startup] creating MainWindow", flush=True)
    window = MainWindow(
        conf=context.conf,
        persona=context.persona,
        ollama=context.ollama,
        stt=context.stt,
        tts=context.tts,
        memory=context.memory,
        conversation=context.conversation,
    )
    print("[startup] showing MainWindow", flush=True)
    window.show()
    ensure_window_is_visible(app, window)
    print(
        "[startup] window state "
        f"platform={app.platformName()} visible={window.isVisible()} "
        f"handle={int(window.winId())} geometry={window.geometry().getRect()}",
        flush=True,
    )
    print("[startup] entering Qt event loop", flush=True)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
