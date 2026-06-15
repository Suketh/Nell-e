import argparse
import base64
import json
from contextlib import suppress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from mimetypes import guess_type
from pathlib import Path
import re
import sys
import threading
import time
import uuid
from urllib.parse import parse_qs, urlparse
from collections import OrderedDict

import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from llm.ollama_client import OllamaClient
from services.conversation_service import ConversationService
from services.memory.sqlite_store import MemoryStore
from services.persona_profile import load_persona


class ConversationRuntime:
    def __init__(self, config_path: Path, persona_path: Path):
        self.config_path = config_path
        self.config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        self.personas = self._load_personas(persona_path)
        self.ollama = OllamaClient(
            self.config["ollama"]["host"],
            text_model=self.config["ollama"]["text_model"],
            vision_model=self.config["ollama"]["vision_model"],
            connect_timeout=self.config.get("ollama", {}).get("connect_timeout", 10),
            read_timeout=self.config.get("ollama", {}).get("read_timeout", 120),
        )
        self._lock = threading.RLock()
        self._user_services: dict[str, dict] = {}
        self._base_db_path = Path(self.config["paths"]["db_path"]).resolve()
        self._gallery_dir = self.config.get("paths", {}).get("gallery_dir")
        self._diagnostics_dir = self._base_db_path.parent / "diagnostics"
        self._diagnostics_dir.mkdir(parents=True, exist_ok=True)
        self.tts, self.tts_fallback = self._build_tts_pair()
        self._tts_cache = OrderedDict()
        self._tts_cache_limit = 48
        self._tts_cache_lock = threading.RLock()
        self._tts_engine_lock = threading.RLock()
        self._tts_inflight: dict[str, threading.Event] = {}
        self._tts_failure_backoff: dict[str, float] = {}
        self._tts_failure_backoff_seconds = float(self.config.get("tts", {}).get("failure_backoff_seconds", 8) or 8)
        self._prime_thread: threading.Thread | None = None
        self._start_background_prime()

    def close(self):
        with self._lock:
            services = list(self._user_services.values())
            self._user_services.clear()
        for entry in services:
            memory = entry.get("memory")
            if memory is not None:
                memory.close()
        if self.tts is not None and hasattr(self.tts, "close"):
            self.tts.close()
        if self.tts_fallback is not None and hasattr(self.tts_fallback, "close"):
            self.tts_fallback.close()

    def set_text_model(self, model_name: str) -> str:
        normalized = str(model_name or "").strip()
        if not normalized:
            raise ValueError("empty_model_name")
        self.config.setdefault("ollama", {})["text_model"] = normalized
        self.ollama.set_text_model(normalized)
        return normalized

    def get_persona_profiles(self) -> list[dict]:
        profiles = []
        for persona_id, persona in self.personas.items():
            profiles.append(
                {
                    "id": persona_id,
                    "name": str(persona.get("name", persona_id.title()) or persona_id.title()),
                    "label": str(persona.get("name", persona_id.title()) or persona_id.title()),
                    "description": str(persona.get("identity", {}).get("role", "") or ""),
                    "voice_profile_id": str(persona.get("voice_profile_id", "") or ""),
                }
            )
        return profiles

    def health(self) -> dict:
        return {
            "ok": True,
            "ollama": {
                "host": self.config.get("ollama", {}).get("host", ""),
                "text_model": self.ollama.text_model,
                "vision_model": self.ollama.vision_model,
                "read_timeout": self.ollama.read_timeout,
            },
            "personas": [profile["id"] for profile in self.get_persona_profiles()],
            "tts": {
                "primary": self._engine_label(self.tts),
                "fallback": self._engine_label(self.tts_fallback),
                "cache_size": len(self._tts_cache),
                "backoff_size": len(self._tts_failure_backoff),
                "priming": bool(self._prime_thread and self._prime_thread.is_alive()),
            },
        }

    def _engine_label(self, engine) -> str:
        if engine is None:
            return ""
        return str(getattr(engine, "__class__", type(engine)).__name__ or "tts")

    def get_persona_profile(self, persona_id: str | None) -> dict:
        normalized = self._normalize_persona_id(persona_id)
        return next((profile for profile in self.get_persona_profiles() if profile["id"] == normalized), self.get_persona_profiles()[0])

    def get_persona(self, persona_id: str | None) -> dict:
        return self.personas.get(self._normalize_persona_id(persona_id), self.personas["nellie"])

    def get_services(self, user_id: str, persona_id: str | None = None) -> dict:
        normalized_user_id = self._normalize_user_id(user_id)
        normalized_persona_id = self._normalize_persona_id(persona_id)
        cache_key = f"{normalized_user_id}:{normalized_persona_id}"
        with self._lock:
            cached = self._user_services.get(cache_key)
            if cached is not None:
                return cached
            db_path = self._db_path_for_user(normalized_user_id, normalized_persona_id)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            memory = MemoryStore(db_path)
            persona = self.get_persona(normalized_persona_id)
            conversation = ConversationService(
                persona=persona,
                ollama=self.ollama,
                memory=memory,
                gallery_dir=self._gallery_dir,
            )
            payload = {
                "user_id": normalized_user_id,
                "persona_id": normalized_persona_id,
                "persona": persona,
                "memory": memory,
                "conversation": conversation,
                "db_path": db_path,
            }
            self._user_services[cache_key] = payload
            return payload

    def _load_personas(self, persona_path: Path) -> dict[str, dict]:
        personas: dict[str, dict] = {}
        personas_dir = persona_path.parent if persona_path.parent.exists() else ROOT_DIR / "data" / "personas"
        if personas_dir.exists():
            for path in sorted(personas_dir.glob("*.json")):
                persona = load_persona(path)
                persona_id = self._safe_identifier(
                    str(persona.get("character_sheet", {}).get("character", {}).get("id", "") or path.stem)
                )
                personas[persona_id] = persona
        if not personas and persona_path.exists():
            personas["nellie"] = load_persona(persona_path)
        if "nellie" not in personas and personas:
            first_id = next(iter(personas))
            personas["nellie"] = personas[first_id]
        personas.setdefault("nellie", load_persona(persona_path))
        personas["nellie"].setdefault("voice_profile_id", self.get_default_voice_profile_id() if hasattr(self, "config") else "")
        return personas

    def _normalize_user_id(self, user_id: str | None) -> str:
        raw = str(user_id or "local-user").strip().lower()
        safe = re.sub(r"[^a-z0-9._-]+", "-", raw).strip("-._")
        return safe or "local-user"

    def _normalize_persona_id(self, persona_id: str | None) -> str:
        safe = self._safe_identifier(persona_id or "nellie")
        if safe in self.personas if hasattr(self, "personas") else {"nellie"}:
            return safe
        return "nellie"

    def _safe_identifier(self, value: str | None) -> str:
        raw = str(value or "").strip().lower()
        return re.sub(r"[^a-z0-9._-]+", "-", raw).strip("-._") or "nellie"

    def _db_path_for_user(self, user_id: str, persona_id: str = "nellie") -> Path:
        stem = self._base_db_path.stem or "nellie"
        suffix = self._base_db_path.suffix or ".sqlite"
        return self._base_db_path.parent / "users" / user_id / persona_id / f"{stem}{suffix}"

    def _diagnostics_path_for_user(self, user_id: str) -> Path:
        return self._diagnostics_dir / f"{user_id}.jsonl"

    def append_diagnostic(self, user_id: str, event: dict):
        normalized_user_id = self._normalize_user_id(user_id)
        payload = {
            "user_id": normalized_user_id,
            "server_ts": time.time(),
            **(event or {}),
        }
        path = self._diagnostics_path_for_user(normalized_user_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def get_recent_diagnostics(self, user_id: str, limit: int = 120) -> list[dict]:
        normalized_user_id = self._normalize_user_id(user_id)
        path = self._diagnostics_path_for_user(normalized_user_id)
        if not path.exists():
            return []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []
        recent = lines[-max(1, int(limit or 120)) :]
        items: list[dict] = []
        for line in recent:
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return items

    def get_voice_profiles(self) -> list[dict]:
        tts_conf = self.config.get("tts", {}) or {}
        raw_profiles = tts_conf.get("voice_profiles", []) or []
        profiles: list[dict] = []
        for item in raw_profiles:
            if not isinstance(item, dict):
                continue
            profile_id = str(item.get("id", "") or "").strip()
            if not profile_id:
                continue
            profiles.append(
                {
                    "id": profile_id,
                    "label": str(item.get("label", profile_id) or profile_id).strip(),
                    "description": str(item.get("description", "") or "").strip(),
                    "sample": str(item.get("sample", "") or "").strip(),
                }
            )
        return profiles

    def get_default_voice_profile_id(self) -> str:
        tts_conf = self.config.get("tts", {}) or {}
        explicit = str(tts_conf.get("default_voice_profile", "") or "").strip()
        if explicit:
            return explicit
        profiles = self.get_voice_profiles()
        return str(profiles[0].get("id", "")) if profiles else ""

    def get_selected_voice_profile(self, user_id: str, persona_id: str | None = None) -> dict | None:
        services = self.get_services(user_id, persona_id)
        memory = services["memory"]
        persona_default = str(services.get("persona", {}).get("voice_profile_id", "") or "").strip()
        selected_id = str(memory.get_agent_state("voice_profile_id", "") or "").strip() or persona_default or self.get_default_voice_profile_id()
        for profile in self.get_voice_profiles():
            if str(profile.get("id", "")) == selected_id:
                return profile
        profiles = self.get_voice_profiles()
        return profiles[0] if profiles else None

    def set_selected_voice_profile(self, user_id: str, profile_id: str, persona_id: str | None = None) -> dict:
        normalized_profile_id = str(profile_id or "").strip()
        selected = None
        for profile in self.get_voice_profiles():
            if str(profile.get("id", "")) == normalized_profile_id:
                selected = profile
                break
        if selected is None:
            raise ValueError("invalid_voice_profile")
        services = self.get_services(user_id, persona_id)
        services["memory"].set_agent_state("voice_profile_id", normalized_profile_id)
        return selected

    def _resolve_voice_sample(self, user_id: str | None = None, persona_id: str | None = None) -> tuple[str, str]:
        profile = self.get_selected_voice_profile(user_id or "local-user", persona_id) if user_id else None
        if profile:
            sample = str(profile.get("sample", "") or "").strip()
            if sample:
                return str(profile.get("id", "") or ""), sample
        tts_conf = self.config.get("tts", {}) or {}
        return "", str(tts_conf.get("voice_sample", "") or "").strip()

    def _apply_voice_profile(self, engine, user_id: str | None = None, persona_id: str | None = None):
        if engine is None:
            return
        profile_id, voice_sample = self._resolve_voice_sample(user_id, persona_id)
        if hasattr(engine, "set_voice_profile"):
            with suppress(Exception):
                engine.set_voice_profile(profile_id, voice_sample)
        if hasattr(engine, "set_voice_sample"):
            with suppress(Exception):
                engine.set_voice_sample(voice_sample)

    def _build_single_tts(self, engine: str):
        tts_conf = self.config.get("tts", {}) or {}
        try:
            if engine == "vibevoice_realtime":
                from services.audio.tts_vibevoice_realtime import TTS as VibeVoiceRealtimeTTS

                vibe_conf = tts_conf.get("vibevoice", {}) or {}
                return VibeVoiceRealtimeTTS(
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
                    python_executable=vibe_conf.get("python_executable", "python"),
                    chunk_join_silence_ms=vibe_conf.get("chunk_join_silence_ms", 90),
                    tail_silence_ms=vibe_conf.get("tail_silence_ms", 220),
                )
            elif engine == "coqui_xtts":
                from services.audio.tts_coqui_xtts import TTS as CoquiXTTSTTS

                return CoquiXTTSTTS(
                    language=tts_conf.get("language", "en"),
                    voice_sample=tts_conf.get("voice_sample"),
                )
            elif engine == "coqui_xtts_server":
                from services.audio.tts_coqui_http import TTS as CoquiXTTSHttpTTS

                xtts_conf = tts_conf.get("coqui_xtts_server", {}) or {}
                return CoquiXTTSHttpTTS(
                    base_url=xtts_conf.get("base_url", ""),
                    health_url=xtts_conf.get("health_url", ""),
                    timeout=xtts_conf.get("timeout", 120),
                    language=tts_conf.get("language", "en"),
                    output_samplerate=xtts_conf.get("output_samplerate", 24000),
                    synth_path=xtts_conf.get("synth_path", "/v1/tts"),
                    health_path=xtts_conf.get("health_path", "/health"),
                    use_post=xtts_conf.get("use_post", False),
                )
            elif engine == "fish_speech":
                from services.audio.tts_fish_speech import TTS as FishSpeechTTS

                fish_conf = tts_conf.get("fish_speech", {}) or {}
                return FishSpeechTTS(
                    base_url=fish_conf.get("base_url", ""),
                    health_url=fish_conf.get("health_url", ""),
                    api_key=fish_conf.get("api_key", ""),
                    timeout=fish_conf.get("timeout", 90),
                    language=tts_conf.get("language", "en"),
                    output_samplerate=fish_conf.get("output_samplerate", 24000),
                    synth_path=fish_conf.get("synth_path", "/v1/tts"),
                    health_path=fish_conf.get("health_path", "/health"),
                    use_post=fish_conf.get("use_post", False),
                )
            else:
                return None
        except Exception:
            return None

    def _build_tts_pair(self):
        tts_conf = self.config.get("tts", {}) or {}
        engine = str(tts_conf.get("engine", "") or "").strip().lower()
        fallback_engine = str(tts_conf.get("fallback_engine", "") or "").strip().lower()
        primary = self._build_single_tts(engine) if engine else None
        if primary is not None:
            try:
                primary.warmup()
            except Exception:
                primary = None
        fallback = None
        if fallback_engine and fallback_engine != engine:
            fallback = self._build_single_tts(fallback_engine)
            if fallback is not None:
                try:
                    fallback.warmup()
                except Exception:
                    fallback = None
        return primary, fallback

    def _prime_tts_cache(self):
        if self.tts is None and self.tts_fallback is None:
            return
        for text in (
            "Hello.",
            "Hi there.",
            "All right.",
            "One second.",
            "Tell me.",
            "I see what you mean.",
            "That's interesting.",
            "Let me think for a second.",
            "Okay. I have it.",
            "I see what you mean. Give me a second and I'll answer it properly.",
        ):
            try:
                self.synthesize_tts(text)
            except Exception:
                break

    def _start_background_prime(self):
        if self.tts is None and self.tts_fallback is None:
            return
        if self._prime_thread is not None and self._prime_thread.is_alive():
            return
        self._prime_thread = threading.Thread(target=self._prime_tts_cache, name="nellie-tts-prime", daemon=True)
        self._prime_thread.start()

    def synthesize_tts(self, text: str, user_id: str | None = None, persona_id: str | None = None) -> tuple[bytes, int, dict]:
        if (self.tts is None or not hasattr(self.tts, "synthesize_wav_bytes")) and (
            self.tts_fallback is None or not hasattr(self.tts_fallback, "synthesize_wav_bytes")
        ):
            raise RuntimeError("TTS is not configured for web playback.")
        normalized_text = re.sub(r"\s+", " ", str(text or "").strip())
        if not normalized_text:
            raise RuntimeError("TTS received empty text.")
        profile_id, voice_sample = self._resolve_voice_sample(user_id, persona_id)
        cache_key = f"{profile_id}|{voice_sample}|{normalized_text}"

        while True:
            with self._tts_cache_lock:
                cached = self._tts_cache.get(cache_key)
                if cached is not None:
                    self._tts_cache.move_to_end(cache_key)
                    wav_bytes, sample_rate = cached
                    meta = {
                        "engine": "cache",
                        "cache_hit": True,
                        "tts_ms": 0,
                        "profile_id": profile_id,
                        "text_chars": len(normalized_text),
                        "language": str((self.config.get("tts", {}) or {}).get("language", "en") or "en"),
                    }
                    return wav_bytes, sample_rate, meta
                backoff_until = self._tts_failure_backoff.get(cache_key)
                if backoff_until is not None:
                    if backoff_until > time.monotonic():
                        raise RuntimeError("TTS is cooling down after a recent failure. The text reply is ready.")
                    self._tts_failure_backoff.pop(cache_key, None)

                inflight = self._tts_inflight.get(cache_key)
                if inflight is None:
                    inflight = threading.Event()
                    self._tts_inflight[cache_key] = inflight
                    is_owner = True
                else:
                    is_owner = False

            if is_owner:
                break
            inflight.wait()

        try:
            wav_bytes = b""
            sample_rate = 24000
            last_error = None
            engine_name = ""
            started_at = time.perf_counter()
            with self._tts_engine_lock:
                for engine in (self.tts, self.tts_fallback):
                    if engine is None or not hasattr(engine, "synthesize_wav_bytes"):
                        continue
                    try:
                        engine_name = str(getattr(engine, "__class__", type(engine)).__name__ or "tts")
                        self._apply_voice_profile(engine, user_id, persona_id)
                        wav_bytes = engine.synthesize_wav_bytes(normalized_text)
                        if not wav_bytes:
                            raise RuntimeError("TTS produced empty audio.")
                        sample_rate = int(getattr(engine, "output_samplerate", 24000) or 24000)
                        break
                    except Exception as exc:
                        last_error = exc
                        continue
            if not wav_bytes:
                raise RuntimeError(str(last_error) if last_error else "TTS produced empty audio.")
            payload = (wav_bytes, sample_rate)
            with self._tts_cache_lock:
                self._tts_cache[cache_key] = payload
                self._tts_cache.move_to_end(cache_key)
                while len(self._tts_cache) > self._tts_cache_limit:
                    self._tts_cache.popitem(last=False)
            meta = {
                "engine": engine_name or "tts",
                "cache_hit": False,
                "tts_ms": int((time.perf_counter() - started_at) * 1000),
                "profile_id": profile_id,
                "text_chars": len(normalized_text),
                "language": str((self.config.get("tts", {}) or {}).get("language", "en") or "en"),
            }
            return wav_bytes, sample_rate, meta
        except Exception:
            if self._tts_failure_backoff_seconds > 0:
                with self._tts_cache_lock:
                    self._tts_failure_backoff[cache_key] = time.monotonic() + self._tts_failure_backoff_seconds
                    if len(self._tts_failure_backoff) > self._tts_cache_limit:
                        expired_or_oldest = min(self._tts_failure_backoff, key=self._tts_failure_backoff.get)
                        self._tts_failure_backoff.pop(expired_or_oldest, None)
            raise
        finally:
            with self._tts_cache_lock:
                done = self._tts_inflight.pop(cache_key, None)
                if done is not None:
                    done.set()


class ConversationHandler(BaseHTTPRequestHandler):
    runtime: ConversationRuntime | None = None
    cors_allow_origin = "*"

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _voice_profile_payload(self, user_id: str, persona_id: str | None = None) -> dict:
        return {
            "voice_profiles": self.runtime.get_voice_profiles(),
            "selected_voice_profile": self.runtime.get_selected_voice_profile(user_id, persona_id),
        }

    def _profile_summary_payload(self, conversation, session_id: str, user_id: str, persona_id: str) -> dict:
        summary = conversation.get_profile_summary(session_id)
        return {
            **summary,
            "persona_id": persona_id,
            "persona_profiles": self.runtime.get_persona_profiles(),
            "selected_persona": self.runtime.get_persona_profile(persona_id),
            **self._voice_profile_payload(user_id, persona_id),
        }

    def _append_tts_diagnostic(self, user_id: str, tts_meta: dict) -> None:
        self.runtime.append_diagnostic(
            user_id,
            {
                "type": "server_tts_timing",
                **tts_meta,
            },
        )

    def _append_chat_diagnostic(self, user_id: str, user_text: str, result, reply_ms: int) -> None:
        self.runtime.append_diagnostic(
            user_id,
            {
                "type": "server_chat_timing",
                "reply_ms": reply_ms,
                "text_chars": len(user_text.strip()),
                "reply_chars": len((result.reply or "").strip()),
                "spoken_chars": len((result.spoken_reply or "").strip()),
                "mode": result.mode,
            },
        )

    def _build_reply_payload(self, services: dict, conversation, session_id: str, result, include_tts_audio: bool = False) -> dict:
        payload = {
            "user_id": services["user_id"],
            "session_id": session_id,
            "reply": result.reply,
            "spoken_reply": result.spoken_reply or "",
            "mood": result.mood,
            "context": result.context,
            "mode": result.mode,
            "tool_events": result.tool_events or [],
            "agent_trace": result.agent_trace or [],
            "gallery_image_path": result.gallery_image_path or "",
            "gallery_image_caption": result.gallery_image_caption or "",
            "new_unlock": result.new_unlock or {},
            **self._profile_summary_payload(conversation, session_id, services["user_id"], services["persona_id"]),
        }
        spoken_reply = str(result.spoken_reply or "").strip()
        if include_tts_audio and spoken_reply:
            try:
                wav_bytes, sample_rate, tts_meta = self.runtime.synthesize_tts(spoken_reply, services["user_id"], services["persona_id"])
                self._append_tts_diagnostic(services["user_id"], tts_meta)
                payload.update(
                    {
                        "tts_audio_base64": base64.b64encode(wav_bytes).decode("ascii"),
                        "tts_audio_content_type": "audio/wav",
                        "tts_sample_rate": sample_rate,
                        "tts_meta": tts_meta,
                    }
                )
            except Exception as exc:
                request_id = self._request_id()
                payload["tts_error"] = {
                    "code": self._error_code(exc, fallback="tts_failed"),
                    "message": self._public_error_message(exc, fallback="Voice generation failed."),
                    "request_id": request_id,
                }
                self._log_server_error(request_id, "embedded_tts_failed", exc)
        return payload

    def _handle_get_routes(self, parsed, services: dict, conversation, memory) -> bool:
        if parsed.path in {"/affection", "/v1/progress", "/progress"}:
            self._send_json(200, {"user_id": services["user_id"], **conversation.get_progress_state()})
            return True
        if parsed.path in {"/gallery/unlocked", "/v1/gallery/unlocked"}:
            self._send_json(200, {"user_id": services["user_id"], "items": conversation.get_unlocked_gallery()})
            return True
        if parsed.path in {"/gallery/catalog", "/v1/gallery/catalog"}:
            self._send_json(200, {"user_id": services["user_id"], "items": conversation.get_gallery_catalog()})
            return True
        if parsed.path == "/v1/profile-summary":
            self._send_json(
                200,
                {
                    "user_id": services["user_id"],
                    **self._profile_summary_payload(
                        conversation,
                        memory.get_agent_state("active_session_id", ""),
                        services["user_id"],
                        services["persona_id"],
                    ),
                },
            )
            return True
        if parsed.path == "/v1/voice-profiles":
            self._send_json(
                200,
                {
                    "user_id": services["user_id"],
                    "persona_id": services["persona_id"],
                    "persona_profiles": self.runtime.get_persona_profiles(),
                    "selected_persona": self.runtime.get_persona_profile(services["persona_id"]),
                    **self._voice_profile_payload(services["user_id"], services["persona_id"]),
                },
            )
            return True
        if parsed.path == "/v1/features":
            self._send_json(
                200,
                {
                    "user_id": services["user_id"],
                    "feature_access": conversation.get_feature_access_state(),
                },
            )
            return True
        if parsed.path == "/v1/tts":
            query = parse_qs(parsed.query or "")
            text = str((query.get("text") or [""])[0] or "").strip()
            if not text:
                self._send_json(400, {"error": "empty_text"})
                return True
            wav_bytes, sample_rate, tts_meta = self.runtime.synthesize_tts(text, services["user_id"], services["persona_id"])
            self._append_tts_diagnostic(services["user_id"], tts_meta)
            self._send_audio(200, wav_bytes, sample_rate)
            return True
        if parsed.path in {"/log", "/v1/log"}:
            query = parse_qs(parsed.query or "")
            limit = int((query.get("limit") or ["250"])[0])
            self._send_json(200, {"user_id": services["user_id"], "log": memory.get_turn_log(limit=limit)})
            return True
        if parsed.path == "/v1/diagnostics":
            query = parse_qs(parsed.query or "")
            limit = int((query.get("limit") or ["120"])[0])
            self._send_json(
                200,
                {
                    "user_id": services["user_id"],
                    "items": self.runtime.get_recent_diagnostics(services["user_id"], limit=limit),
                },
            )
            return True
        return False

    def _handle_get_asset_routes(self, parsed, conversation) -> bool:
        if parsed.path.startswith("/v1/assets/moods/"):
            moods_root = (ROOT_DIR / "assets" / "moods").resolve()
            parts = [part for part in parsed.path.split("/") if part]
            mood_name = Path(parts[-1]).name if parts else "neutral.png"
            persona_id = "nellie"
            if len(parts) >= 5:
                persona_id = re.sub(r"[^a-z0-9._-]+", "-", parts[-2].lower()).strip("-._") or "nellie"
            candidates = [
                (moods_root / persona_id / mood_name).resolve(),
                (moods_root / "nellie" / mood_name).resolve(),
                (moods_root / persona_id / "neutral.png").resolve(),
                (moods_root / "nellie" / "neutral.png").resolve(),
            ]
            mood_path = next((candidate for candidate in candidates if candidate.is_file()), candidates[-1])
            if moods_root not in mood_path.parents or not mood_path.is_file():
                self._send_json(404, {"error": "not_found"})
                return True
            self._send_file(200, mood_path)
            return True
        if parsed.path.startswith("/v1/assets/gallery/"):
            filename = Path(parsed.path).name
            image_path = conversation._resolve_image_path(filename)
            if image_path is None or not image_path.is_file():
                self._send_json(404, {"error": "not_found"})
                return True
            self._send_file(200, image_path)
            return True
        return False

    def _handle_post_chat_routes(self, parsed, payload: dict, services: dict, conversation, memory, session_id: str) -> bool:
        if parsed.path in {"/reply", "/v1/chat/reply"}:
            user_text = str(payload.get("user_text", payload.get("text", "")) or "")
            include_tts_audio = bool(payload.get("include_tts_audio", False))
            reply_started_at = time.perf_counter()
            result = conversation.reply(user_text)
            reply_ms = int((time.perf_counter() - reply_started_at) * 1000)
            self._append_chat_diagnostic(services["user_id"], user_text, result, reply_ms)
            self._send_json(200, self._build_reply_payload(services, conversation, session_id, result, include_tts_audio=include_tts_audio))
            return True
        if parsed.path in {"/clear", "/v1/memory/clear"}:
            memory.clear_all()
            self._send_json(200, {"ok": True, "user_id": services["user_id"]})
            return True
        if parsed.path == "/v1/tts":
            text = str(payload.get("text", "") or "").strip()
            if not text:
                self._send_json(400, {"error": "empty_text"})
                return True
            wav_bytes, sample_rate, tts_meta = self.runtime.synthesize_tts(text, services["user_id"], services["persona_id"])
            self._append_tts_diagnostic(services["user_id"], tts_meta)
            self._send_audio(200, wav_bytes, sample_rate)
            return True
        return False

    def _handle_post_admin_routes(self, parsed, payload: dict, services: dict, conversation, memory) -> bool:
        if parsed.path == "/v1/features/update":
            feature_id = str(payload.get("feature_id", "") or "").strip()
            enabled = bool(payload.get("enabled", False))
            item = conversation.set_feature_enabled(feature_id, enabled)
            self._send_json(
                200,
                {
                    "user_id": services["user_id"],
                    "item": item,
                    "feature_access": conversation.get_feature_access_state(),
                },
            )
            return True
        if parsed.path == "/v1/admin/progression":
            action = str(payload.get("action", "") or "").strip().lower()
            if action == "set_level":
                progress = conversation.admin_set_level(int(payload.get("level", 1) or 1))
            elif action == "reset":
                progress = conversation.admin_reset_progress()
            else:
                self._send_json(400, {"error": "invalid_admin_action"})
                return True
            unlocked = conversation.get_unlocked_gallery()
            summary = conversation.get_profile_summary(memory.get_agent_state("active_session_id", ""))
            self._send_json(
                200,
                {
                    "user_id": services["user_id"],
                    "progress": progress,
                    "feature_access": conversation.get_feature_access_state(),
                    "gallery_unlock_count": len(unlocked),
                    "latest_unlock": unlocked[-1] if unlocked else None,
                    "enabled_feature_labels": summary.get("enabled_feature_labels", []),
                    "available_feature_labels": summary.get("available_feature_labels", []),
                    "next_feature_unlock": summary.get("next_feature_unlock"),
                    "stage_copy": summary.get("stage_copy", ""),
                    "practical_focus": summary.get("practical_focus", ""),
                    "suggested_prompts": summary.get("suggested_prompts", []),
                    "nellie_preferences": summary.get("nellie_preferences", []),
                },
            )
            return True
        if parsed.path == "/v1/admin/features/all":
            enabled = bool(payload.get("enabled", True))
            self._send_json(
                200,
                {
                    "user_id": services["user_id"],
                    "feature_access": conversation.admin_set_all_features(enabled),
                },
            )
            return True
        if parsed.path == "/v1/diagnostics/event":
            event = payload.get("event", {}) if isinstance(payload, dict) else {}
            if not isinstance(event, dict):
                self._send_json(400, {"error": "invalid_event"})
                return True
            self.runtime.append_diagnostic(services["user_id"], event)
            self._send_json(200, {"ok": True, "user_id": services["user_id"]})
            return True
        if parsed.path == "/v1/voice-profile/select":
            profile_id = str(payload.get("voice_profile_id", "") or "").strip()
            selected = self.runtime.set_selected_voice_profile(services["user_id"], profile_id, services["persona_id"])
            self._send_json(
                200,
                {
                    "user_id": services["user_id"],
                    "selected_voice_profile": selected,
                    **self._profile_summary_payload(
                        conversation,
                        memory.get_agent_state("active_session_id", ""),
                        services["user_id"],
                        services["persona_id"],
                    ),
                },
            )
            return True
        if parsed.path == "/v1/admin/ollama-model":
            model_name = self.runtime.set_text_model(str(payload.get("model", "") or ""))
            self._send_json(
                200,
                {
                    "ok": True,
                    "user_id": services["user_id"],
                    "text_model": model_name,
                },
            )
            return True
        return False

    def do_GET(self):
        request_id = self._request_id()
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                self._send_json(200, self.runtime.health())
                return
            user_id = self._request_user_id(parsed)
            persona_id = self._request_persona_id(parsed)
            services = self.runtime.get_services(user_id, persona_id)
            conversation = services["conversation"]
            memory = services["memory"]
            if self._handle_get_routes(parsed, services, conversation, memory):
                return
            if self._handle_get_asset_routes(parsed, conversation):
                return
            self._send_json(404, {"error": "Not found"})
        except Exception as exc:
            self._log_server_error(request_id, "get_failed", exc)
            self._send_error(500, exc, request_id=request_id)

    def do_POST(self):
        request_id = self._request_id()
        try:
            parsed = urlparse(self.path)
            payload = self._read_json()
            user_id = self._payload_user_id(payload)
            persona_id = self._payload_persona_id(payload)
            session_id = str(payload.get("session_id", "") or "").strip()
            services = self.runtime.get_services(user_id, persona_id)
            conversation = services["conversation"]
            memory = services["memory"]
            if session_id:
                memory.set_agent_state("active_session_id", session_id)
            if self._handle_post_chat_routes(parsed, payload, services, conversation, memory, session_id):
                return
            if self._handle_post_admin_routes(parsed, payload, services, conversation, memory):
                return
            self._send_json(404, {"error": "Not found"})
        except json.JSONDecodeError:
            self._send_error(400, "invalid_json", message="The request body was not valid JSON.", request_id=request_id)
        except ValueError as exc:
            self._send_error(400, exc, fallback="invalid_request", request_id=request_id)
        except Exception as exc:
            self._log_server_error(request_id, "post_failed", exc)
            self._send_error(500, exc, request_id=request_id)

    def log_message(self, _format, *_args):
        return

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            return {}
        body = self.rfile.read(length).decode("utf-8")
        return json.loads(body) if body.strip() else {}

    def _request_user_id(self, parsed) -> str:
        query = parse_qs(parsed.query or "")
        return str((query.get("user_id") or ["local-user"])[0] or "local-user")

    def _request_persona_id(self, parsed) -> str:
        query = parse_qs(parsed.query or "")
        return str((query.get("persona_id") or ["nellie"])[0] or "nellie")

    def _payload_user_id(self, payload: dict) -> str:
        return str(payload.get("user_id", "local-user") or "local-user")

    def _payload_persona_id(self, payload: dict) -> str:
        return str(payload.get("persona_id", "nellie") or "nellie")

    def _request_id(self) -> str:
        header_value = str(self.headers.get("X-Request-Id", "") or "").strip()
        if header_value:
            return re.sub(r"[^a-zA-Z0-9._-]+", "-", header_value)[:80] or uuid.uuid4().hex[:12]
        return uuid.uuid4().hex[:12]

    def _error_code(self, error, fallback: str = "request_failed") -> str:
        text = str(error or "").lower()
        if "tts" in text or "voice" in text or "synthesis" in text:
            return "tts_failed"
        if "ollama" in text or "model" in text or "llm" in text:
            return "llm_failed"
        if "timed out" in text or "timeout" in text:
            return "timeout"
        if isinstance(error, str) and error:
            return re.sub(r"[^a-z0-9_]+", "_", error.lower()).strip("_") or fallback
        return fallback

    def _public_error_message(self, error, fallback: str = "Request failed.") -> str:
        code = self._error_code(error, fallback="request_failed")
        if code == "tts_failed":
            return "Voice generation failed. The text reply may still be available."
        if code == "llm_failed":
            return "The language model did not answer in time or returned an error."
        if code == "timeout":
            return "The request timed out. Try again in a moment."
        text = str(error or "").strip()
        if text and len(text) <= 140 and not any(token in text.lower() for token in ["traceback", "password", "api_key", "authorization"]):
            return text
        return fallback

    def _send_error(self, status: int, error, *, message: str | None = None, fallback: str = "request_failed", request_id: str | None = None):
        request_id = request_id or self._request_id()
        payload = {
            "ok": False,
            "error": self._error_code(error, fallback=fallback),
            "message": message or self._public_error_message(error),
            "request_id": request_id,
        }
        self._send_json(status, payload)

    def _log_server_error(self, request_id: str, event_type: str, error) -> None:
        print(f"[conversation-error] request_id={request_id} type={event_type} error={error}", file=sys.stderr)

    def _send_json(self, status: int, payload: dict):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._send_cors_headers()
        if isinstance(payload, dict) and payload.get("request_id"):
            self.send_header("X-Request-Id", str(payload.get("request_id")))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_audio(self, status: int, payload: bytes, sample_rate: int):
        self.send_response(status)
        self._send_cors_headers()
        self.send_header("Content-Type", "audio/wav")
        self.send_header("X-Audio-Sample-Rate", str(sample_rate))
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_file(self, status: int, path: Path):
        payload = path.read_bytes()
        mime_type = guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(status)
        self._send_cors_headers()
        self.send_header("Content-Type", mime_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", self.cors_allow_origin)
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--persona", default="data/personas/nellie.json")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8877)
    args = parser.parse_args()

    runtime = ConversationRuntime(Path(args.config), Path(args.persona))
    ConversationHandler.runtime = runtime
    server = ThreadingHTTPServer((args.host, args.port), ConversationHandler)
    try:
        server.serve_forever()
    finally:
        runtime.close()
        server.server_close()


if __name__ == "__main__":
    main()
