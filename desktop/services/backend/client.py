from typing import Any, Callable

from services.backend.local_adapter import LocalBackendAdapter


class BackendClient:
    def __init__(self, adapter: Any) -> None:
        self.adapter = adapter

    def build_context(self, persona: dict[str, Any], k: int = 4, max_chars: int = 1000, per_turn_chars: int = 220) -> str:
        return self.adapter.build_context(persona, k=k, max_chars=max_chars, per_turn_chars=per_turn_chars)

    def load_app_state(self, key: str, default: str | None = None) -> str | None:
        return self.adapter.load_app_state(key, default)

    def save_app_state(self, key: str, value: str) -> None:
        self.adapter.save_app_state(key, value)

    def set_text_model(self, model: str) -> str:
        return str(self.adapter.set_text_model(model))

    def load_emotion_state(self) -> Any:
        return self.adapter.load_emotion_state()

    def save_emotion_state(self, state: Any) -> None:
        self.adapter.save_emotion_state(state)

    def save_turn(self, user: str, ai: str, mood: str | None = None, persona: dict[str, Any] | None = None) -> None:
        self.adapter.save_turn(user=user, ai=ai, mood=mood, persona=persona)

    def get_progression(self, persona: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.adapter.get_progression(persona)

    def clear_conversation(self) -> None:
        self.adapter.clear_conversation()

    def latest_turn(self) -> tuple[str, str, str] | None:
        return self.adapter.latest_turn()

    def try_agent_action(self, text: str) -> dict[str, Any] | None:
        return self.adapter.try_agent_action(text)

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
        return self.adapter.respond_turn(
            persona=persona,
            user_text=user_text,
            emotion_state=emotion_state,
            policy_state=policy_state,
            response_language=response_language,
            input_source=input_source,
            remember_chat=remember_chat,
            web_search_enabled=web_search_enabled,
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
        return self.adapter.chat(
            persona,
            user_text,
            context=context,
            emotion_state=emotion_state,
            stream_callback=stream_callback,
            policy_state=policy_state,
            web_context=web_context,
            response_language=response_language,
            input_source=input_source,
        )

    def vision(self, image_path: str, prompt: str) -> str:
        return self.adapter.vision(image_path, prompt=prompt)

    def prepare_spoken_utterance(
        self,
        user_text: str,
        reply: str,
        mood: str,
        current_tts_engine: str,
        tts_conf: dict[str, Any],
        persona: dict[str, Any],
    ) -> dict[str, str]:
        return self.adapter.prepare_spoken_utterance(
            user_text=user_text,
            reply=reply,
            mood=mood,
            current_tts_engine=current_tts_engine,
            tts_conf=tts_conf,
            persona=persona,
        )

    def can_start_local_voxtral(self, stt_conf: dict[str, Any]) -> bool:
        return bool(self.adapter.can_start_local_voxtral(stt_conf))

    def start_local_voxtral(self, stt_conf: dict[str, Any]) -> dict[str, Any]:
        return self.adapter.start_local_voxtral(stt_conf)

    def probe_voxtral_runtime(self, stt_conf: dict[str, Any], attempts: int = 1, delay_sec: float = 0.0) -> dict[str, Any]:
        return self.adapter.probe_voxtral_runtime(stt_conf, attempts=attempts, delay_sec=delay_sec)

    def transcribe_audio(self, audio_b64: str, language: str = "") -> str:
        return str(self.adapter.transcribe_audio(audio_b64, language=language))


    def synthesize_speech(self, text: str, mood: str | None = None, master_volume: int = 100, **overrides: Any) -> str:
        return str(self.adapter.synthesize_speech(text=text, mood=mood, master_volume=master_volume, **overrides))


def create_backend_client(llm: Any, memory: Any, stt: Any | None = None, tts: Any | None = None) -> BackendClient:
    return BackendClient(LocalBackendAdapter(llm=llm, memory=memory, stt=stt, tts=tts))
