import os
import re
import subprocess
import time
from base64 import b64decode
from copy import deepcopy
from tempfile import NamedTemporaryFile
from typing import Any, Callable

from services.tools.web_duckduckgo import search as web_search, summarize_results
from services.tools.weather_open_meteo import (
    current_weather,
    extract_location,
    format_weather,
    is_weather_query,
)
from services.backend.speech_prep import prepare_spoken_utterance
from services.tools.browser_actions import (
    extract_wikipedia_query,
    extract_youtube_query,
    open_wikipedia_query,
    open_youtube_query,
)
from services.tools.spotify import (
    extract_spotify_query,
    extract_spotify_suggestion,
    is_spotify_choice_request,
    open_spotify_query,
)
from services.tools.calculator_safe import evaluate_expression, extract_expression
from services.tools.datetime_local import lookup_local_datetime
from services.tools.web_fetch import extract_url, fetch_webpage


class LocalBackendAdapter:
    def __init__(self, llm: Any | None, memory: Any | None, stt: Any | None = None, tts: Any | None = None) -> None:
        self.llm = llm
        self.memory = memory
        self.stt = stt
        self.tts = tts
        self._voxtral_process: subprocess.Popen[str] | None = None

    def _require_memory(self) -> Any:
        if self.memory is None:
            raise RuntimeError("Local backend adapter requires a memory store, but none is configured.")
        return self.memory

    def _require_llm(self) -> Any:
        if self.llm is None:
            raise RuntimeError("Local backend adapter requires an LLM client, but none is configured.")
        return self.llm

    def _require_stt(self) -> Any:
        if self.stt is None:
            raise RuntimeError("Local backend adapter requires an STT service, but none is configured.")
        return self.stt

    def _require_tts(self) -> Any:
        if self.tts is None:
            raise RuntimeError("Local backend adapter requires a TTS service, but none is configured.")
        return self.tts

    def build_context(
        self,
        persona: dict[str, Any],
        k: int = 4,
        max_chars: int = 1000,
        per_turn_chars: int = 220,
    ) -> str:
        memory = self._require_memory()
        return memory.build_context(persona, k=k, max_chars=max_chars, per_turn_chars=per_turn_chars)

    def load_app_state(self, key: str, default: str | None = None) -> str | None:
        memory = self._require_memory()
        return memory.load_app_state(key, default)

    def save_app_state(self, key: str, value: str) -> None:
        memory = self._require_memory()
        memory.save_app_state(key, value)

    def set_text_model(self, model: str) -> str:
        model_name = str(model or "").strip()
        if not model_name:
            raise ValueError("Model name cannot be empty.")
        llm = self._require_llm()
        if not hasattr(llm, "text_model"):
            raise RuntimeError("The active LLM backend does not support runtime model switching.")
        llm.text_model = model_name
        return model_name

    def load_emotion_state(self) -> Any:
        memory = self._require_memory()
        return memory.load_emotion_state()

    def save_emotion_state(self, state: Any) -> None:
        memory = self._require_memory()
        memory.save_emotion_state(state)

    def save_turn(self, user: str, ai: str, mood: str | None = None, persona: dict[str, Any] | None = None) -> None:
        memory = self._require_memory()
        memory.save_turn(user=user, ai=ai, mood=mood, persona=persona)

    def get_progression(self, persona: dict[str, Any] | None = None) -> dict[str, Any]:
        memory = self._require_memory()
        getter = getattr(memory, "get_progression", None)
        if callable(getter):
            result = getter(persona)
            if isinstance(result, dict):
                return result
        return {
            "level": 1,
            "level_cap": 255,
            "xp": 0,
            "progress_percent": 0,
            "xp_to_next": 0,
            "bond_factor": 0.0,
            "unlocked_keys": [],
            "next_unlock": None,
        }

    def clear_conversation(self) -> None:
        memory = self._require_memory()
        memory.clear_conversation()

    def latest_turn(self) -> tuple[str, str, str] | None:
        memory = self._require_memory()
        latest = getattr(memory, "latest_turn", None)
        if callable(latest):
            result = latest()
            if (
                isinstance(result, tuple)
                and len(result) == 3
            ):
                return (str(result[0]), str(result[1]), str(result[2]))
        return None

    def try_agent_action(self, text: str, tools_enabled: dict | None = None) -> dict[str, Any] | None:
        te = tools_enabled or {}
        lowered = re.sub(r"\s+", " ", str(text or "").strip().casefold())
        memory = self._require_memory()
        remember_match = re.match(r"^(?:remember|remember that|remember this)[: ]+(.+)$", lowered, flags=re.IGNORECASE)
        forget_match = re.match(r"^(?:forget|forget that|forget this)[: ]+(.+)$", lowered, flags=re.IGNORECASE)
        user_name = memory.get_user_fact("user_name") if hasattr(memory, "get_user_fact") else None
        user_role = memory.get_user_fact("user_role") if hasattr(memory, "get_user_fact") else None

        expression = extract_expression(text)
        if expression and te.get("calculator", True):
            try:
                result = evaluate_expression(expression)
            except (ArithmeticError, SyntaxError, ValueError) as exc:
                return {
                    "handled": True,
                    "action": "calculator",
                    "reply": f"I could not calculate that safely: {exc}",
                    "mood": "neutral",
                    "status": "error",
                }
            return {
                "handled": True,
                "action": "calculator",
                "reply": f"That comes to {result}.",
                "mood": "neutral",
                "status": "handled",
            }

        if te.get("datetime_local", True) and lowered in {
            "what time is it",
            "what's the time",
            "what is the time",
            "what date is it",
            "what's today's date",
            "what day is it",
            "vad är klockan",
            "vilket datum är det",
            "vilken dag är det",
        }:
            local = lookup_local_datetime()
            if "time" in lowered or "klockan" in lowered:
                reply = f"It is {local['time']} ({local['timezone']})."
            elif "day" in lowered or "dag" in lowered:
                reply = f"Today is {local['day']}, {local['date']}."
            else:
                reply = f"Today's date is {local['date']}."
            return {
                "handled": True,
                "action": "datetime_local",
                "reply": reply,
                "mood": "neutral",
                "status": "handled",
            }

        page_url = extract_url(text)
        if page_url and te.get("web_fetch", True) and any(cue in lowered for cue in ("read ", "summarize ", "check ", "läs ", "sammanfatta ")):
            try:
                page = fetch_webpage(page_url, max_chars=1800)
            except Exception as exc:
                return {
                    "handled": True,
                    "action": "web_fetch",
                    "reply": f"I could not read that page: {exc}",
                    "mood": "neutral",
                    "status": "error",
                }
            excerpt = str(page.get("text", "")).strip()
            if len(excerpt) > 700:
                excerpt = excerpt[:697].rstrip() + "..."
            return {
                "handled": True,
                "action": "web_fetch",
                "reply": f"I read {page.get('title', page_url)}. {excerpt or 'The page had no readable text.'}",
                "mood": "neutral",
                "status": "handled",
                "source_url": page_url,
            }

        if lowered in {"what's my name", "what is my name", "who am i", "do you know my name"}:
            if user_name:
                reply = f"Your name is {user_name}."
                if user_role:
                    reply += f" I've got you as {user_role} too."
            else:
                reply = "You have not told me your name clearly enough for me to trust it yet."
            return {"handled": True, "action": "memory_name_recall", "reply": reply, "mood": "happy", "status": "handled"}

        if lowered in {
            "what is my role",
            "what's my role",
            "am i your administrator",
            "do you remember that i'm your administrator",
            "do you remember i am your administrator",
        }:
            if user_role:
                reply = f"Yes. I have your role as {user_role}."
            else:
                reply = "Not confidently yet. Tell me your role again and I'll keep it straight."
            return {"handled": True, "action": "memory_role_recall", "reply": reply, "mood": "happy", "status": "handled"}

        if "what do you remember about me" in lowered or lowered in {"what do you remember", "do you remember me"}:
            lines = memory.summarize_user_memory(limit=8) if hasattr(memory, "summarize_user_memory") else []
            if lines:
                reply = "Here's what I remember about you: " + " | ".join(lines[:5])
            else:
                reply = "I do not have much saved about you yet. You can tell me to remember something."
            return {"handled": True, "action": "memory_recall", "reply": reply, "mood": "happy", "status": "handled"}

        if remember_match and hasattr(memory, "add_user_memory_note"):
            note_text = remember_match.group(1)
            if hasattr(memory, "capture_user_facts"):
                memory.capture_user_facts(note_text)
            note = memory.add_user_memory_note(note_text)
            if note:
                name = memory.get_user_fact("user_name") if hasattr(memory, "get_user_fact") else None
                role = memory.get_user_fact("user_role") if hasattr(memory, "get_user_fact") else None
                extras = []
                if name:
                    extras.append(f"name={name}")
                if role:
                    extras.append(f"role={role}")
                extra_text = f" I've got {', '.join(extras)}." if extras else ""
                return {
                    "handled": True,
                    "action": "memory_save",
                    "reply": f"Okay. I'll remember that: {note}.{extra_text}",
                    "mood": "happy",
                    "status": "handled",
                }

        if forget_match and hasattr(memory, "forget_user_memory"):
            removed = memory.forget_user_memory(forget_match.group(1))
            return {
                "handled": True,
                "action": "memory_forget",
                "reply": "Okay. I forgot that." if removed > 0 else "I could not find anything matching that to forget.",
                "mood": "neutral",
                "status": "handled",
            }

        recent_context = self._recent_tool_context()

        if te.get("wikipedia_search", True):
            wikipedia_query = extract_wikipedia_query(text, context=recent_context)
            if wikipedia_query:
                return self._browser_action("wikipedia_open", "Wikipedia", wikipedia_query, open_wikipedia_query)

        if te.get("youtube_control", False):
            youtube_query = extract_youtube_query(text, context=recent_context)
            if youtube_query:
                return self._browser_action("youtube_open", "YouTube", youtube_query, open_youtube_query)

        if te.get("spotify_control", False):
            spotify_query = extract_spotify_query(text, context=recent_context)
            if spotify_query:
                return self._browser_action("spotify_play", "Spotify", spotify_query, open_spotify_query)

        return None

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
        tools_enabled: dict | None = None,
    ) -> dict[str, Any]:
        te = tools_enabled or {}
        persona = self._persona_with_runtime_progression(persona)
        agent_result = self.try_agent_action(user_text, tools_enabled=te)
        if agent_result and agent_result.get("handled"):
            result = dict(agent_result)
            result["kind"] = "agent"
            return result

        context = ""
        if remember_chat:
            context = self.build_context(persona, k=5, max_chars=1400, per_turn_chars=240)

        query_text = str(user_text or "")
        web_context = ""
        web_query = ""
        web_results = 0
        followup_query = self._followup_web_query(query_text)
        if followup_query:
            query_text = followup_query
        if web_search_enabled and self._should_use_web_search(query_text):
            web_query = self._extract_web_query(query_text)
            if is_weather_query(web_query) and te.get("weather_lookup", True):
                try:
                    weather = current_weather(extract_location(web_query))
                    return {
                        "kind": "chat",
                        "reply": format_weather(weather),
                        "meta": {"mood": "neutral", "source": "open-meteo"},
                        "query_text": query_text,
                        "web_query": web_query,
                        "web_results": 1,
                        "web_source": "open-meteo",
                    }
                except Exception as exc:
                    return {
                        "kind": "error",
                        "reply": f"[Weather lookup unavailable] {exc}",
                        "mood": "neutral",
                        "error": str(exc),
                        "stage": "weather_lookup",
                    }
            query_text = web_query
            try:
                results = web_search(web_query, k=5)
                web_results = len(results)
                if results:
                    web_context = summarize_results(results)
            except Exception as exc:
                return {
                    "kind": "error",
                    "reply": f"[Web search unavailable] {exc}",
                    "mood": "neutral",
                    "error": str(exc),
                    "stage": "web_search",
                }

        reply, meta = self.chat(
            persona,
            query_text,
            context=context,
            emotion_state=emotion_state,
            stream_callback=None,
            policy_state=policy_state,
            web_context=web_context,
            response_language=response_language,
            input_source=input_source,
        )
        if te.get("spotify_control", False) and is_spotify_choice_request(user_text, context=context):
            suggestion = extract_spotify_suggestion(reply)
            if suggestion:
                action_result = self._browser_action(
                    "spotify_play",
                    "Spotify",
                    suggestion,
                    open_spotify_query,
                )
                action_result["kind"] = "agent"
                if action_result.get("status") == "opened":
                    action_result["reply"] = f"{reply.rstrip()} Opening Spotify now."
                return action_result
        return {
            "kind": "chat",
            "reply": reply,
            "meta": meta,
            "query_text": query_text,
            "web_query": web_query,
            "web_results": web_results,
        }

    def _browser_action(
        self,
        action: str,
        label: str,
        query: str,
        opener: Callable[[str], tuple[bool, str]],
    ) -> dict[str, Any]:
        opened, target = opener(query)
        if opened:
            return {
                "handled": True,
                "action": action,
                "label": label,
                "query": query,
                "target": target,
                "status": "opened",
                "reply": f"Opening {label} for {query}.",
                "mood": "happy",
            }
        return {
            "handled": True,
            "action": action,
            "label": label,
            "query": query,
            "target": target,
            "status": "failed",
            "reply": f"I tried to open {label} for {query}, but it did not go through.",
            "mood": "neutral",
        }

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
        llm = self._require_llm()
        persona = self._persona_with_runtime_progression(persona)
        return llm.chat(
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

    def _persona_with_runtime_progression(self, persona: dict[str, Any]) -> dict[str, Any]:
        enriched = deepcopy(persona or {})
        enriched["runtime_progression"] = self.get_progression(enriched)
        return enriched

    def vision(self, image_path: str, prompt: str) -> str:
        llm = self._require_llm()
        return llm.vision(image_path, prompt=prompt)

    def transcribe_audio(self, audio_b64: str, language: str = "") -> str:
        stt = self._require_stt()
        original_language = getattr(stt, "language", None)
        if language and hasattr(stt, "language"):
            stt.language = str(language)
        try:
            payload = b64decode(audio_b64.encode("ascii"))
            with NamedTemporaryFile(suffix=".wav", delete=False) as handle:
                temp_path = handle.name
                handle.write(payload)
            try:
                return str(stt.transcribe_bytes(temp_path) or "").strip()
            finally:
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
        finally:
            if original_language is not None and hasattr(stt, "language"):
                stt.language = original_language

    def synthesize_speech(self, text: str, mood: str | None = None, master_volume: int = 100, **overrides: Any) -> str:
        tts = self._require_tts()
        previous_volume = int(getattr(tts, "master_volume", 100))
        try:
            tts.set_master_volume(int(master_volume))
            return tts.synthesize_audio(text=str(text or ""), mood=mood, **overrides)
        finally:
            tts.set_master_volume(previous_volume)

    def prepare_spoken_utterance(
        self,
        user_text: str,
        reply: str,
        mood: str,
        current_tts_engine: str,
        tts_conf: dict[str, Any],
        persona: dict[str, Any],
    ) -> dict[str, str]:
        return prepare_spoken_utterance(
            user_text=user_text,
            reply=reply,
            mood=mood,
            current_tts_engine=current_tts_engine,
            tts_conf=tts_conf,
            persona=persona,
        )

    def can_start_local_voxtral(self, stt_conf: dict[str, Any]) -> bool:
        if str(stt_conf.get("voxtral_mode", "api")).strip().lower() != "self_hosted":
            return False
        return bool(str(stt_conf.get("voxtral_self_hosted_launch", "")).strip())

    def start_local_voxtral(self, stt_conf: dict[str, Any]) -> dict[str, Any]:
        if not self.can_start_local_voxtral(stt_conf):
            return {
                "ok": False,
                "status": "blocked",
                "detail": "the local Voxtral launch command is not configured.",
            }
        if self._voxtral_process is not None and self._voxtral_process.poll() is None:
            return {"ok": True, "status": "already_running"}

        command = str(stt_conf.get("voxtral_self_hosted_launch", "")).strip()
        workdir = str(stt_conf.get("voxtral_self_hosted_workdir", "")).strip() or None
        try:
            self._voxtral_process = subprocess.Popen(
                command,
                cwd=workdir,
                shell=True,
                text=True,
            )
        except Exception as exc:
            return {"ok": False, "status": "error", "detail": str(exc)}
        return {"ok": True, "status": "started"}

    def probe_voxtral_runtime(self, stt_conf: dict[str, Any], attempts: int = 1, delay_sec: float = 0.0) -> dict[str, Any]:
        available = self._voxtral_is_available(stt_conf)
        tries = max(1, int(attempts))
        if not available and tries > 1:
            for _ in range(tries - 1):
                time.sleep(max(0.0, float(delay_sec)))
                if self._voxtral_is_available(stt_conf):
                    available = True
                    break
        detail = f"Voxtral online at {stt_conf.get('voxtral_self_hosted_url', '')}." if available else "Voxtral unreachable."
        return {"available": bool(available), "detail": detail}

    def _should_use_web_search(self, text: str) -> bool:
        lower = (text or "").strip().lower()
        if lower.startswith("/search "):
            return True
        if re.fullmatch(
            r"(?:shall|should|can|could) we (?:try to )?(?:look up|search for|find) "
            r"(?:a |another )?(?:song|track|video|topic)(?: again)?[?.! ]*",
            lower,
        ):
            return False
        search_cues = [
            "search", "look up", "lookup", "find online", "on the internet",
            "browse", "web search", "latest", "current", "today", "news", "recent",
            "weather", "forecast", "temperature", "väder", "vädret", "prognos", "temperatur",
            "who is", "what is", "when is", "where is",
            "how many", "number of", "first album", "first record", "discography",
            "sok", "sök", "leta upp", "pa natet", "på nätet", "senaste",
            "idag", "nyheter", "vem ar", "vem är", "vad ar", "vad är", "nar ar", "när är", "var ar", "var är",
        ]
        return any(cue in lower for cue in search_cues)

    def _extract_web_query(self, text: str) -> str:
        stripped = (text or "").strip()
        if stripped.lower().startswith("/search "):
            stripped = stripped[8:].strip()
        stripped = re.sub(r"^(?:can you\s+)?browse\s+(?:for\s+)?", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s+for me[?!.]*$", "", stripped, flags=re.IGNORECASE)
        replacements = {
            r"\bdinstace\b": "distance",
            r"\bdistancee\b": "distance",
            r"\bbeteen\b": "between",
            r"\brivendel\b": "Rivendell",
        }
        for pattern, replacement in replacements.items():
            stripped = re.sub(pattern, replacement, stripped, flags=re.IGNORECASE)
        produced_match = re.search(
            r"\bhow many\s+(?:records|albums)\s+(?:has|have|did)\s+(.+?)\s+(?:produced|released|made)[?!.]*$",
            stripped,
            flags=re.IGNORECASE,
        )
        if produced_match:
            artist = produced_match.group(1).strip()
            stripped = f"{artist} discography number of studio albums released"
        distance_match = re.search(
            r"\bdistance\s+between\s+(.+?)\s+and\s+(.+?)(?:\s+in\s+(?:kilometres?|kilometers?|miles?))?[?!.]*$",
            stripped,
            flags=re.IGNORECASE,
        )
        if distance_match:
            start = distance_match.group(1).strip(" ,?!.")
            destination = distance_match.group(2).strip(" ,?!.")
            stripped = f"{start} {destination} distance kilometres"
        stripped = re.sub(
            r"^(?:oh\s+i\s+have\s+one[,. ]*)?(?:what\s+is|what's|can\s+you\s+tell\s+me)\s+(?:the\s+)?(?:actual\s+)?",
            "",
            stripped,
            flags=re.IGNORECASE,
        )
        return stripped or text

    def _followup_web_query(self, text: str) -> str:
        normalized = re.sub(r"[^\w\s]", "", str(text or "").casefold()).strip()
        direct_confirmations = {
            "yes",
            "yes please",
            "yes pleace",
            "yeah",
            "sure",
            "okay",
            "ok",
            "do it",
            "look it up",
            "can you look it up",
            "can you look it up for me",
        }
        subject = self._recent_named_subject()
        if normalized in {"number of records", "number of albums", "how many records", "how many albums"}:
            return f"{subject} discography number of studio albums released" if subject else ""
        if normalized in {"whats his first album", "what is his first album", "his first album"}:
            return f"{subject} first studio album" if subject else ""
        if any(
            cue in normalized
            for cue in ("anything from him", "a good song", "good song from him", "song by him")
        ):
            return f"{subject} best known songs official discography" if subject else ""
        if normalized not in direct_confirmations:
            return ""
        latest = self.latest_turn()
        if latest is None:
            return ""
        previous_user, previous_ai, _mood = latest
        joined = f"{previous_user}\n{previous_ai}"
        if is_weather_query(joined):
            location = extract_location(joined)
            if location:
                return f"weather in {location} today"
        if any(cue in previous_ai.casefold() for cue in ("look up", "search the web", "search online")):
            return previous_user
        return ""

    def _recent_tool_context(self) -> str:
        memory = self._require_memory()
        builder = getattr(memory, "build_context", None)
        if callable(builder):
            try:
                return str(builder(None, k=4, max_chars=1600, per_turn_chars=320))
            except Exception:
                pass
        latest = self.latest_turn()
        return f"USER: {latest[0]}\nNELLIE: {latest[1]}" if latest else ""

    def _recent_named_subject(self) -> str:
        context = self._recent_tool_context()
        candidates = re.findall(
            r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b",
            context,
        )
        ignored = {
            "Recent Conversation", "Stable User Details", "Bond Level",
            "You Tube", "Blue Blue Sky",
        }
        useful = [item for item in candidates if item not in ignored]
        return useful[-1] if useful else ""

    def _voxtral_is_available(self, stt_conf: dict[str, Any]) -> bool:
        try:
            from services.audio.stt_voxtral import VoxtralSTT
        except Exception:
            return False

        probe = VoxtralSTT(
            model=str(stt_conf.get("voxtral_model", "voxtral-mini-latest")),
            language=str(stt_conf.get("language", "en")),
            base_url=str(stt_conf.get("voxtral_base_url", "https://api.mistral.ai")),
            api_key=str(stt_conf.get("voxtral_api_key", "")),
            mode="self_hosted",
            self_hosted_url=str(stt_conf.get("voxtral_self_hosted_url", "http://127.0.0.1:8000")),
            self_hosted_api_key=str(stt_conf.get("voxtral_self_hosted_api_key", "")),
            timeout_sec=int(stt_conf.get("voxtral_timeout_sec", 120)),
        )
        return probe.is_available()
