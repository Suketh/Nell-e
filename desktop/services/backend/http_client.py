from importlib import import_module
from threading import local
from typing import Any, Callable

from services.emotion.state import EmotionState


class HttpBackendClient:
    def __init__(self, base_url: str, timeout: float = 120.0) -> None:
        self.base_url = str(base_url or "http://127.0.0.1:8011").rstrip("/")
        self.timeout = float(timeout or 120.0)
        self._thread_state = local()

    def _session(self) -> Any:
        session = getattr(self._thread_state, "session", None)
        if session is not None:
            return session
        try:
            requests = import_module("requests")
        except Exception as exc:
            raise RuntimeError("requests is not installed in the current Python environment.") from exc
        session = requests.Session()
        self._thread_state.session = session
        return session

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        response = self._session().post(
            f"{self.base_url}{path}",
            json=payload,
            timeout=(10, self.timeout),
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError(f"Unexpected backend response from {path}")
        return data

    def build_context(self, persona: dict[str, Any], k: int = 4, max_chars: int = 1000, per_turn_chars: int = 220) -> str:
        data = self._post(
            "/v1/context/build",
            {"persona": persona, "k": k, "max_chars": max_chars, "per_turn_chars": per_turn_chars},
        )
        return str(data.get("context", ""))

    def load_app_state(self, key: str, default: str | None = None) -> str | None:
        data = self._post("/v1/app-state/get", {"key": key, "default": default})
        value = data.get("value", default)
        return None if value is None else str(value)

    def save_app_state(self, key: str, value: str) -> None:
        self._post("/v1/app-state/set", {"key": key, "value": value})

    def set_text_model(self, model: str) -> str:
        try:
            data = self._post("/v1/llm/model/set", {"model": model})
        except Exception as exc:
            response = getattr(exc, "response", None)
            if getattr(response, "status_code", None) == 404:
                raise RuntimeError(
                    "The running Nellie backend is outdated. Restart Nellie before changing models."
                ) from exc
            raise
        return str(data.get("model", ""))

    def load_emotion_state(self) -> EmotionState:
        data = self._post("/v1/emotion/load", {})
        return EmotionState(
            valence=int(data.get("valence", 0)),
            energy=int(data.get("energy", 0)),
            attachment=int(data.get("attachment", 0)),
            mood=str(data.get("mood", "neutral")),
        )

    def save_emotion_state(self, state: Any) -> None:
        self._post(
            "/v1/emotion/save",
            {
                "valence": int(getattr(state, "valence", 0)),
                "energy": int(getattr(state, "energy", 0)),
                "attachment": int(getattr(state, "attachment", 0)),
                "mood": str(getattr(state, "mood", "neutral")),
            },
        )

    def save_turn(self, user: str, ai: str, mood: str | None = None, persona: dict[str, Any] | None = None) -> None:
        self._post("/v1/turn/save", {"user": user, "ai": ai, "mood": mood, "persona": persona or {}})

    def get_progression(self, persona: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._post("/v1/progression/get", {"persona": persona or {}})

    def clear_conversation(self) -> None:
        self._post("/v1/conversation/clear", {})

    def latest_turn(self) -> tuple[str, str, str] | None:
        data = self._post("/v1/turn/latest", {})
        if not data.get("found"):
            return None
        return (
            str(data.get("user", "")),
            str(data.get("ai", "")),
            str(data.get("mood", "")),
        )

    def try_agent_action(self, text: str) -> dict[str, Any] | None:
        data = self._post("/v1/agent/action", {"text": text})
        return data if data.get("handled") else None

    def respond_turn(
        self,
        persona: dict[str, Any],
        user_text: str,
        emotion_state: str = "",
        policy_state: dict[str, Any] | None = None,
        response_language: str = "English",
        input_source: str = "text",
        remember_chat: bool = True,
        web_search_enabled: bool = False,
    ) -> dict[str, Any]:
        return self._post(
            "/v1/turn/respond",
            {
                "persona": persona,
                "user_text": user_text,
                "emotion_state": emotion_state,
                "policy_state": policy_state or {},
                "response_language": response_language,
                "input_source": input_source,
                "remember_chat": bool(remember_chat),
                "web_search_enabled": bool(web_search_enabled),
            },
        )

    def chat(
        self,
        persona: dict[str, Any],
        user_text: str,
        context: str = "",
        emotion_state: str = "",
        stream_callback: Callable[[str], None] | None = None,
        policy_state: dict[str, Any] | None = None,
        web_context: str = "",
        response_language: str = "English",
        input_source: str = "text",
    ) -> tuple[str, dict[str, str]]:
        del stream_callback
        data = self._post(
            "/v1/chat/respond",
            {
                "persona": persona,
                "user_text": user_text,
                "context": context,
                "emotion_state": emotion_state,
                "policy_state": policy_state or {},
                "web_context": web_context,
                "response_language": response_language,
                "input_source": input_source,
            },
        )
        reply = str(data.get("reply", ""))
        meta = data.get("meta", {})
        if not isinstance(meta, dict):
            meta = {}
        return reply, {str(k): str(v) for k, v in meta.items()}

    def vision(self, image_path: str, prompt: str) -> str:
        data = self._post("/v1/vision/describe", {"image_path": image_path, "prompt": prompt})
        return str(data.get("reply", ""))

    def prepare_spoken_utterance(
        self,
        user_text: str,
        reply: str,
        mood: str,
        current_tts_engine: str,
        tts_conf: dict[str, Any],
        persona: dict[str, Any],
    ) -> dict[str, str]:
        data = self._post(
            "/v1/tts/prepare",
            {
                "user_text": user_text,
                "reply": reply,
                "mood": mood,
                "current_tts_engine": current_tts_engine,
                "tts_conf": tts_conf,
                "persona": persona,
            },
        )
        return {
            "spoken_reply": str(data.get("spoken_reply", "")),
            "reaction": str(data.get("reaction", "")),
        }

    def can_start_local_voxtral(self, stt_conf: dict[str, Any]) -> bool:
        data = self._post("/v1/speech/voxtral/can-start", {"stt_conf": stt_conf})
        return bool(data.get("can_start", False))

    def start_local_voxtral(self, stt_conf: dict[str, Any]) -> dict[str, Any]:
        return self._post("/v1/speech/voxtral/start", {"stt_conf": stt_conf})

    def probe_voxtral_runtime(self, stt_conf: dict[str, Any], attempts: int = 1, delay_sec: float = 0.0) -> dict[str, Any]:
        return self._post(
            "/v1/speech/voxtral/probe",
            {
                "stt_conf": stt_conf,
                "attempts": int(attempts),
                "delay_sec": float(delay_sec),
            },
        )

    def transcribe_audio(self, audio_b64: str, language: str = "") -> str:
        data = self._post(
            "/v1/stt/transcribe",
            {
                "audio_b64": audio_b64,
                "language": language,
            },
        )
        return str(data.get("text", ""))

    def synthesize_speech(self, text: str, mood: str | None = None, master_volume: int = 100, **overrides: Any) -> str:
        data = self._post(
            "/v1/tts/synthesize",
            {
                "text": text,
                "mood": mood,
                "master_volume": int(master_volume),
                "overrides": overrides,
            },
        )
        return str(data.get("audio_b64", ""))
