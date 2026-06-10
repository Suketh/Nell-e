import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from llm.client_factory import create_llm_client
from services.audio.factory import create_tts_service
from services.backend.local_adapter import LocalBackendAdapter
from services.audio.stt_factory import create_stt_service
from services.config_paths import resolve_config_paths
from services.memory.sqlite_store import MemoryStore


CONFIG_PATH = ROOT / "config.yaml"
API_VERSION = 2


def load_config() -> dict[str, Any]:
    conf = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(conf, dict):
        raise RuntimeError(f"Expected a mapping in {CONFIG_PATH}")
    return resolve_config_paths(conf, ROOT)


def project_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path if path.is_absolute() else ROOT / path


class NellieBackendHandler(BaseHTTPRequestHandler):
    adapter: LocalBackendAdapter | None = None

    def _json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            data = json.loads(raw.decode("utf-8"))
        except Exception:
            data = {}
        return data if isinstance(data, dict) else {}

    def _send(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self._send(
                {
                    "status": "ok",
                    "service": "nellie-backend",
                    "api_version": API_VERSION,
                    "capabilities": ["runtime_model_switching"],
                }
            )
            return
        self._send({"error": "not found"}, status=404)

    def do_POST(self) -> None:
        adapter = self.adapter
        if adapter is None:
            self._send({"error": "adapter not initialized"}, status=500)
            return
        data = self._json()
        try:
            if self.path == "/v1/context/build":
                context = adapter.build_context(
                    data.get("persona") or {},
                    k=int(data.get("k", 4)),
                    max_chars=int(data.get("max_chars", 1000)),
                    per_turn_chars=int(data.get("per_turn_chars", 220)),
                )
                self._send({"context": context})
                return
            if self.path == "/v1/app-state/get":
                value = adapter.load_app_state(str(data.get("key", "")), data.get("default"))
                self._send({"value": value})
                return
            if self.path == "/v1/app-state/set":
                adapter.save_app_state(str(data.get("key", "")), str(data.get("value", "")))
                self._send({"ok": True})
                return
            if self.path == "/v1/llm/model/set":
                model = adapter.set_text_model(str(data.get("model", "")))
                adapter.save_app_state("ollama_text_model", model)
                self._send({"model": model})
                return
            if self.path == "/v1/emotion/load":
                state = adapter.load_emotion_state()
                self._send(
                    {
                        "valence": int(getattr(state, "valence", 0)),
                        "energy": int(getattr(state, "energy", 0)),
                        "attachment": int(getattr(state, "attachment", 0)),
                        "mood": str(getattr(state, "mood", "neutral")),
                    }
                )
                return
            if self.path == "/v1/emotion/save":
                from services.emotion.state import EmotionState

                state = EmotionState(
                    valence=int(data.get("valence", 0)),
                    energy=int(data.get("energy", 0)),
                    attachment=int(data.get("attachment", 0)),
                    mood=str(data.get("mood", "neutral")),
                )
                adapter.save_emotion_state(state)
                self._send({"ok": True})
                return
            if self.path == "/v1/turn/save":
                adapter.save_turn(
                    user=str(data.get("user", "")),
                    ai=str(data.get("ai", "")),
                    mood=str(data.get("mood", "")) or None,
                    persona=data.get("persona") or {},
                )
                self._send({"ok": True})
                return
            if self.path == "/v1/progression/get":
                self._send(adapter.get_progression(data.get("persona") or {}))
                return
            if self.path == "/v1/turn/latest":
                latest = adapter.latest_turn()
                if latest is None:
                    self._send({"found": False})
                else:
                    self._send({"found": True, "user": latest[0], "ai": latest[1], "mood": latest[2]})
                return
            if self.path == "/v1/conversation/clear":
                adapter.clear_conversation()
                self._send({"ok": True})
                return
            if self.path == "/v1/agent/action":
                result = adapter.try_agent_action(str(data.get("text", ""))) or {"handled": False}
                self._send(result)
                return
            if self.path == "/v1/turn/respond":
                result = adapter.respond_turn(
                    persona=data.get("persona") or {},
                    user_text=str(data.get("user_text", "")),
                    emotion_state=str(data.get("emotion_state", "")),
                    policy_state=data.get("policy_state") or {},
                    response_language=str(data.get("response_language", "English")),
                    input_source=str(data.get("input_source", "text")),
                    remember_chat=bool(data.get("remember_chat", True)),
                    web_search_enabled=bool(data.get("web_search_enabled", False)),
                )
                self._send(result)
                return
            if self.path == "/v1/chat/respond":
                reply, meta = adapter.chat(
                    persona=data.get("persona") or {},
                    user_text=str(data.get("user_text", "")),
                    context=str(data.get("context", "")),
                    emotion_state=str(data.get("emotion_state", "")),
                    stream_callback=None,
                    policy_state=data.get("policy_state") or {},
                    web_context=str(data.get("web_context", "")),
                    response_language=str(data.get("response_language", "English")),
                    input_source=str(data.get("input_source", "text")),
                )
                self._send({"reply": reply, "meta": meta})
                return
            if self.path == "/v1/vision/describe":
                reply = adapter.vision(
                    image_path=str(data.get("image_path", "")),
                    prompt=str(data.get("prompt", "Describe the image briefly.")),
                )
                self._send({"reply": reply})
                return
            if self.path == "/v1/tts/prepare":
                prepared = adapter.prepare_spoken_utterance(
                    user_text=str(data.get("user_text", "")),
                    reply=str(data.get("reply", "")),
                    mood=str(data.get("mood", "neutral")),
                    current_tts_engine=str(data.get("current_tts_engine", "xtts_tts")),
                    tts_conf=data.get("tts_conf") or {},
                    persona=data.get("persona") or {},
                )
                self._send(prepared)
                return
            if self.path == "/v1/speech/voxtral/can-start":
                stt_conf = data.get("stt_conf") or {}
                self._send({"can_start": adapter.can_start_local_voxtral(stt_conf)})
                return
            if self.path == "/v1/speech/voxtral/start":
                stt_conf = data.get("stt_conf") or {}
                self._send(adapter.start_local_voxtral(stt_conf))
                return
            if self.path == "/v1/speech/voxtral/probe":
                stt_conf = data.get("stt_conf") or {}
                self._send(
                    adapter.probe_voxtral_runtime(
                        stt_conf,
                        attempts=int(data.get("attempts", 1)),
                        delay_sec=float(data.get("delay_sec", 0.0)),
                    )
                )
                return
            if self.path == "/v1/stt/transcribe":
                text = adapter.transcribe_audio(
                    audio_b64=str(data.get("audio_b64", "")),
                    language=str(data.get("language", "")),
                )
                self._send({"text": text})
                return
            if self.path == "/v1/tts/synthesize":
                audio_b64 = adapter.synthesize_speech(
                    text=str(data.get("text", "")),
                    mood=data.get("mood"),
                    master_volume=int(data.get("master_volume", 100)),
                    **(data.get("overrides") or {}),
                )
                self._send({"audio_b64": audio_b64})
                return
            self._send({"error": "not found"}, status=404)
        except Exception as exc:
            self._send({"error": str(exc)}, status=500)


def main() -> None:
    conf = load_config()
    llm = create_llm_client(conf)
    stt = create_stt_service(conf)
    tts = create_tts_service(conf)
    memory_path = project_path(conf["paths"]["db_path"])
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    memory = MemoryStore(memory_path)
    stored_text_model = memory.load_app_state("ollama_text_model")
    if stored_text_model and hasattr(llm, "text_model"):
        llm.text_model = stored_text_model
    adapter = LocalBackendAdapter(llm=llm, memory=memory, stt=stt, tts=tts)
    NellieBackendHandler.adapter = adapter

    backend_conf = conf.get("backend", {})
    host = str(backend_conf.get("host", "127.0.0.1"))
    port = int(backend_conf.get("port", 8011))

    server = ThreadingHTTPServer((host, port), NellieBackendHandler)
    print(f"Nellie backend listening on http://{host}:{port}")
    try:
        server.serve_forever()
    finally:
        server.server_close()
        memory.close()


if __name__ == "__main__":
    main()
