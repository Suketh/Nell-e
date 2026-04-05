import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from mimetypes import guess_type
from pathlib import Path
import os
import re
import sys
import threading
import time
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
        self.persona = load_persona(persona_path)
        self.ollama = OllamaClient(
            self.config["ollama"]["host"],
            text_model=self.config["ollama"]["text_model"],
            vision_model=self.config["ollama"]["vision_model"],
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
        self._tts_lock = threading.RLock()
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

    def get_services(self, user_id: str) -> dict:
        normalized_user_id = self._normalize_user_id(user_id)
        with self._lock:
            cached = self._user_services.get(normalized_user_id)
            if cached is not None:
                return cached
            db_path = self._db_path_for_user(normalized_user_id)
            db_path.parent.mkdir(parents=True, exist_ok=True)
            memory = MemoryStore(db_path)
            conversation = ConversationService(
                persona=self.persona,
                ollama=self.ollama,
                memory=memory,
                gallery_dir=self._gallery_dir,
            )
            payload = {
                "user_id": normalized_user_id,
                "memory": memory,
                "conversation": conversation,
                "db_path": db_path,
            }
            self._user_services[normalized_user_id] = payload
            return payload

    def _normalize_user_id(self, user_id: str | None) -> str:
        raw = str(user_id or "local-user").strip().lower()
        safe = re.sub(r"[^a-z0-9._-]+", "-", raw).strip("-._")
        return safe or "local-user"

    def _db_path_for_user(self, user_id: str) -> Path:
        stem = self._base_db_path.stem or "nellie"
        suffix = self._base_db_path.suffix or ".sqlite"
        return self._base_db_path.parent / "users" / user_id / f"{stem}{suffix}"

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

    def get_selected_voice_profile(self, user_id: str) -> dict | None:
        services = self.get_services(user_id)
        memory = services["memory"]
        selected_id = str(memory.get_agent_state("voice_profile_id", "") or "").strip() or self.get_default_voice_profile_id()
        for profile in self.get_voice_profiles():
            if str(profile.get("id", "")) == selected_id:
                return profile
        profiles = self.get_voice_profiles()
        return profiles[0] if profiles else None

    def set_selected_voice_profile(self, user_id: str, profile_id: str) -> dict:
        normalized_profile_id = str(profile_id or "").strip()
        selected = None
        for profile in self.get_voice_profiles():
            if str(profile.get("id", "")) == normalized_profile_id:
                selected = profile
                break
        if selected is None:
            raise ValueError("invalid_voice_profile")
        services = self.get_services(user_id)
        services["memory"].set_agent_state("voice_profile_id", normalized_profile_id)
        return selected

    def _resolve_voice_sample(self, user_id: str | None = None) -> tuple[str, str]:
        profile = self.get_selected_voice_profile(user_id or "local-user") if user_id else None
        if profile:
            sample = str(profile.get("sample", "") or "").strip()
            if sample:
                return str(profile.get("id", "") or ""), sample
        tts_conf = self.config.get("tts", {}) or {}
        return "", str(tts_conf.get("voice_sample", "") or "").strip()

    def _apply_voice_profile(self, engine, user_id: str | None = None):
        if engine is None:
            return
        profile_id, voice_sample = self._resolve_voice_sample(user_id)
        if hasattr(engine, "set_voice_profile"):
            try:
                engine.set_voice_profile(profile_id, voice_sample)
            except Exception:
                pass
        if hasattr(engine, "set_voice_sample"):
            try:
                engine.set_voice_sample(voice_sample)
            except Exception:
                pass

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

    def synthesize_tts(self, text: str, user_id: str | None = None) -> tuple[bytes, int, dict]:
        if (self.tts is None or not hasattr(self.tts, "synthesize_wav_bytes")) and (
            self.tts_fallback is None or not hasattr(self.tts_fallback, "synthesize_wav_bytes")
        ):
            raise RuntimeError("TTS is not configured for web playback.")
        normalized_text = re.sub(r"\s+", " ", str(text or "").strip())
        if not normalized_text:
            raise RuntimeError("TTS received empty text.")
        profile_id, voice_sample = self._resolve_voice_sample(user_id)
        cache_key = f"{profile_id}|{voice_sample}|{normalized_text}"

        with self._tts_lock:
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

            wav_bytes = b""
            sample_rate = 24000
            last_error = None
            engine_name = ""
            started_at = time.perf_counter()
            for engine in (self.tts, self.tts_fallback):
                if engine is None or not hasattr(engine, "synthesize_wav_bytes"):
                    continue
                try:
                    engine_name = str(getattr(engine, "__class__", type(engine)).__name__ or "tts")
                    self._apply_voice_profile(engine, user_id)
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


class ConversationHandler(BaseHTTPRequestHandler):
    runtime: ConversationRuntime | None = None
    cors_allow_origin = "*"

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        try:
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                self._send_json(200, {"ok": True})
                return
            user_id = self._request_user_id(parsed)
            services = self.runtime.get_services(user_id)
            conversation = services["conversation"]
            memory = services["memory"]
            if parsed.path in {"/affection", "/v1/progress"}:
                self._send_json(200, {"user_id": services["user_id"], **conversation.get_progress_state()})
                return
            if parsed.path == "/progress":
                self._send_json(200, {"user_id": services["user_id"], **conversation.get_progress_state()})
                return
            if parsed.path in {"/gallery/unlocked", "/v1/gallery/unlocked"}:
                self._send_json(200, {"user_id": services["user_id"], "items": conversation.get_unlocked_gallery()})
                return
            if parsed.path in {"/gallery/catalog", "/v1/gallery/catalog"}:
                self._send_json(200, {"user_id": services["user_id"], "items": conversation.get_gallery_catalog()})
                return
            if parsed.path == "/v1/profile-summary":
                summary = conversation.get_profile_summary(memory.get_agent_state("active_session_id", ""))
                self._send_json(
                    200,
                    {
                        "user_id": services["user_id"],
                        "voice_profiles": self.runtime.get_voice_profiles(),
                        "selected_voice_profile": self.runtime.get_selected_voice_profile(services["user_id"]),
                        **summary,
                    },
                )
                return
            if parsed.path == "/v1/voice-profiles":
                self._send_json(
                    200,
                    {
                        "user_id": services["user_id"],
                        "voice_profiles": self.runtime.get_voice_profiles(),
                        "selected_voice_profile": self.runtime.get_selected_voice_profile(services["user_id"]),
                    },
                )
                return
            if parsed.path == "/v1/features":
                self._send_json(
                    200,
                    {
                        "user_id": services["user_id"],
                        "feature_access": conversation.get_feature_access_state(),
                    },
                )
                return
            if parsed.path == "/v1/tts":
                query = parse_qs(parsed.query or "")
                text = str((query.get("text") or [""])[0] or "").strip()
                if not text:
                    self._send_json(400, {"error": "empty_text"})
                    return
                wav_bytes, sample_rate, tts_meta = self.runtime.synthesize_tts(text, services["user_id"])
                self.runtime.append_diagnostic(
                    services["user_id"],
                    {
                        "type": "server_tts_timing",
                        **tts_meta,
                    },
                )
                self._send_audio(200, wav_bytes, sample_rate)
                return
            if parsed.path.startswith("/v1/assets/moods/"):
                mood_name = Path(parsed.path).name
                mood_path = (ROOT_DIR / "assets" / "moods" / mood_name).resolve()
                moods_root = (ROOT_DIR / "assets" / "moods").resolve()
                if moods_root not in mood_path.parents or not mood_path.is_file():
                    self._send_json(404, {"error": "not_found"})
                    return
                self._send_file(200, mood_path)
                return
            if parsed.path.startswith("/v1/assets/gallery/"):
                filename = Path(parsed.path).name
                image_path = conversation._resolve_image_path(filename)
                if image_path is None or not image_path.is_file():
                    self._send_json(404, {"error": "not_found"})
                    return
                self._send_file(200, image_path)
                return
            if parsed.path in {"/log", "/v1/log"}:
                query = parse_qs(parsed.query or "")
                limit = int((query.get("limit") or ["250"])[0])
                self._send_json(200, {"user_id": services["user_id"], "log": memory.get_turn_log(limit=limit)})
                return
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
                return
            self._send_json(404, {"error": "Not found"})
        except Exception as exc:
            self._send_json(500, {"error": str(exc) or "Request failed"})

    def do_POST(self):
        try:
            parsed = urlparse(self.path)
            payload = self._read_json()
            user_id = self._payload_user_id(payload)
            session_id = str(payload.get("session_id", "") or "").strip()
            services = self.runtime.get_services(user_id)
            conversation = services["conversation"]
            memory = services["memory"]
            if session_id:
                memory.set_agent_state("active_session_id", session_id)
            if parsed.path in {"/reply", "/v1/chat/reply"}:
                user_text = str(payload.get("user_text", payload.get("text", "")) or "")
                reply_started_at = time.perf_counter()
                result = conversation.reply(user_text)
                reply_ms = int((time.perf_counter() - reply_started_at) * 1000)
                self.runtime.append_diagnostic(
                    services["user_id"],
                    {
                        "type": "server_chat_timing",
                        "reply_ms": reply_ms,
                        "text_chars": len(user_text.strip()),
                        "reply_chars": len((result.reply or "").strip()),
                        "spoken_chars": len((result.spoken_reply or "").strip()),
                        "mode": result.mode,
                    },
                )
                summary = conversation.get_profile_summary(session_id)
                self._send_json(
                    200,
                    {
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
                        "progress": summary.get("progress"),
                        "feature_access": summary.get("feature_access"),
                        "gallery_unlock_count": summary.get("gallery_unlock_count"),
                        "latest_unlock": summary.get("latest_unlock"),
                        "enabled_feature_labels": summary.get("enabled_feature_labels", []),
                        "available_feature_labels": summary.get("available_feature_labels", []),
                        "next_feature_unlock": summary.get("next_feature_unlock"),
                        "stage_copy": summary.get("stage_copy", ""),
                        "practical_focus": summary.get("practical_focus", ""),
                        "suggested_prompts": summary.get("suggested_prompts", []),
                        "nellie_preferences": summary.get("nellie_preferences", []),
                        "voice_profiles": self.runtime.get_voice_profiles(),
                        "selected_voice_profile": self.runtime.get_selected_voice_profile(services["user_id"]),
                    },
                )
                return
            if parsed.path in {"/clear", "/v1/memory/clear"}:
                memory.clear_all()
                self._send_json(200, {"ok": True, "user_id": services["user_id"]})
                return
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
                return
            if parsed.path == "/v1/admin/progression":
                action = str(payload.get("action", "") or "").strip().lower()
                if action == "set_level":
                    level = int(payload.get("level", 1) or 1)
                    progress = conversation.admin_set_level(level)
                elif action == "reset":
                    progress = conversation.admin_reset_progress()
                else:
                    self._send_json(400, {"error": "invalid_admin_action"})
                    return
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
                return
            if parsed.path == "/v1/admin/features/all":
                enabled = bool(payload.get("enabled", True))
                self._send_json(
                    200,
                    {
                        "user_id": services["user_id"],
                        "feature_access": conversation.admin_set_all_features(enabled),
                    },
                )
                return
            if parsed.path == "/v1/diagnostics/event":
                event = payload.get("event", {}) if isinstance(payload, dict) else {}
                if not isinstance(event, dict):
                    self._send_json(400, {"error": "invalid_event"})
                    return
                self.runtime.append_diagnostic(services["user_id"], event)
                self._send_json(200, {"ok": True, "user_id": services["user_id"]})
                return
            if parsed.path == "/v1/voice-profile/select":
                profile_id = str(payload.get("voice_profile_id", "") or "").strip()
                selected = self.runtime.set_selected_voice_profile(services["user_id"], profile_id)
                summary = conversation.get_profile_summary(memory.get_agent_state("active_session_id", ""))
                self._send_json(
                    200,
                    {
                        "user_id": services["user_id"],
                        "selected_voice_profile": selected,
                        "voice_profiles": self.runtime.get_voice_profiles(),
                        **summary,
                    },
                )
                return
            if parsed.path == "/v1/tts":
                text = str(payload.get("text", "") or "").strip()
                if not text:
                    self._send_json(400, {"error": "empty_text"})
                    return
                wav_bytes, sample_rate, tts_meta = self.runtime.synthesize_tts(text, services["user_id"])
                self.runtime.append_diagnostic(
                    services["user_id"],
                    {
                        "type": "server_tts_timing",
                        **tts_meta,
                    },
                )
                self._send_audio(200, wav_bytes, sample_rate)
                return
            self._send_json(404, {"error": "Not found"})
        except json.JSONDecodeError:
            self._send_json(400, {"error": "invalid_json"})
        except ValueError as exc:
            self._send_json(400, {"error": str(exc) or "invalid_request"})
        except Exception as exc:
            self._send_json(500, {"error": str(exc) or "Request failed"})

    def log_message(self, format, *args):
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

    def _payload_user_id(self, payload: dict) -> str:
        return str(payload.get("user_id", "local-user") or "local-user")

    def _send_json(self, status: int, payload: dict):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._send_cors_headers()
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
    parser.add_argument("--persona", default="data/personality.json")
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
