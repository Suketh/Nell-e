from dataclasses import dataclass, field
from difflib import SequenceMatcher, get_close_matches
import re
import unicodedata

from services.feature_access import is_feature_enabled, tool_feature_id


@dataclass
class AgentResult:
    reply: str
    mood: str
    context: str
    mode: str
    tool_events: list[dict] = field(default_factory=list)
    agent_trace: list[dict] = field(default_factory=list)


@dataclass(frozen=True)
class TextSignals:
    text: str
    lowered: str
    compact: str
    ascii_compact: str
    folded_compact: str


class AgentService:
    """Thin orchestration layer for future tool-using Nellie behavior.

    Current default is conservative: most requests go straight to the LLM.
    Tool decisions are intentionally lightweight for now so behavior remains stable.
    """

    TOOL_LEVEL_REQUIREMENTS = {
        "datetime_local": 4,
        "weather_lookup": 1,
        "calculator": 8,
        "wikipedia_search": 12,
        "web_search": 18,
        "web_fetch": 24,
        "vision_describe_image": 30,
        "browser_open": 36,
        "pdf_extract_text": 42,
    }

    def __init__(self, persona: dict, ollama, memory, tool_registry):
        self.persona = persona
        self.ollama = ollama
        self.memory = memory
        self.tool_registry = tool_registry
        self._last_tool_state: dict[str, str] = memory.get_agent_state("last_tool_state", default={}) or {}

    def handle(self, user_text: str, stream_callback=None) -> AgentResult:
        context = self.memory.build_context(self.persona, k=6, current_user_text=user_text)
        plan = self._plan(user_text)
        progress_state = self.memory.get_agent_state("progression_state", default={}) or {}
        user_level = int(progress_state.get("level", 1) or 1)
        agent_trace = [
            {
                "step": "plan",
                "mode": plan["mode"],
                "tool_name": plan.get("tool_name"),
            }
        ]

        if plan["mode"] == "clarify_reply":
            reply = plan.get("reply", "Could you clarify that a little?")
            mood = plan.get("mood", "thoughtful")
            self.memory.save_turn(user=user_text, ai=reply, mood=mood)
            return AgentResult(
                reply=reply,
                mood=mood,
                context=context,
                mode="clarify_reply",
                tool_events=[],
                agent_trace=agent_trace,
            )

        if plan["mode"] == "direct_reply":
            return self._direct_reply(user_text, context, stream_callback=stream_callback, agent_trace=agent_trace)

        tool_events = []
        tool_name = plan.get("tool_name")
        tool_input = plan.get("tool_input", {})
        if tool_name and not self._is_tool_unlocked(tool_name, user_level):
            agent_trace.append(
                {
                    "step": "tool_gate",
                    "status": "locked",
                    "tool_name": tool_name,
                    "reason": f"requires level {self.TOOL_LEVEL_REQUIREMENTS.get(tool_name, 1)}",
                }
            )
            return self._direct_reply(user_text, context, stream_callback=stream_callback, agent_trace=agent_trace)
        if tool_name and not self._is_feature_enabled(tool_name, tool_input, user_level):
            feature_id = tool_feature_id(tool_name, tool_input)
            agent_trace.append(
                {
                    "step": "feature_gate",
                    "status": "disabled",
                    "tool_name": tool_name,
                    "feature_id": feature_id,
                }
            )
            return self._direct_reply(user_text, context, stream_callback=stream_callback, agent_trace=agent_trace)
        tool = self.tool_registry.get(tool_name) if tool_name else None
        if tool is None:
            agent_trace.append({"step": "tool_lookup", "status": "missing", "tool_name": tool_name})
            return self._direct_reply(user_text, context, stream_callback=stream_callback, agent_trace=agent_trace)

        try:
            tool_output = tool.handler(**tool_input)
            tool_events.append({"tool": tool.name, "input": tool_input, "status": "ok"})
            agent_trace.append({"step": "tool_execute", "status": "ok", "tool_name": tool.name})
            self._remember_tool_state(tool.name, user_text, tool_input, tool_output)
        except Exception as exc:
            tool_events.append({"tool": tool.name, "input": tool_input, "status": "error", "error": str(exc)})
            agent_trace.append({"step": "tool_execute", "status": "error", "tool_name": tool.name, "error": str(exc)})
            fallback_context = f"{context}\n\nTOOL_ERROR ({tool.name}):\n{exc}"
            return self._direct_reply(
                user_text,
                fallback_context,
                stream_callback=stream_callback,
                mode="tool_fallback",
                tool_events=tool_events,
                agent_trace=agent_trace,
            )

        direct_tool_reply = self._render_direct_tool_reply(tool.name, tool_output, user_text)
        if direct_tool_reply is not None:
            self.memory.save_turn(user=user_text, ai=direct_tool_reply, mood="thoughtful")
            return AgentResult(
                reply=direct_tool_reply,
                mood="thoughtful",
                context=context,
                mode="tool_reply",
                tool_events=tool_events,
                agent_trace=agent_trace,
            )

        augmented_context = f"{context}\n\nTOOL_RESULT ({tool.name}):\n{tool_output}"
        reply, meta = self.ollama.chat(
            self.persona,
            user_text,
            context=augmented_context,
            stream_callback=stream_callback,
        )
        mood = (meta or {}).get("mood", "thoughtful")
        self.memory.save_turn(user=user_text, ai=reply, mood=mood)
        return AgentResult(
            reply=reply,
            mood=mood,
            context=augmented_context,
            mode="tool_reply",
            tool_events=tool_events,
            agent_trace=agent_trace,
        )

    def _direct_reply(self, user_text: str, context: str, stream_callback=None, mode: str = "direct_reply", tool_events=None, agent_trace=None) -> AgentResult:
        reply, meta = self.ollama.chat(
            self.persona,
            user_text,
            context=context,
            stream_callback=stream_callback,
        )
        mood = (meta or {}).get("mood", "thoughtful")
        self.memory.save_turn(user=user_text, ai=reply, mood=mood)
        return AgentResult(
            reply=reply,
            mood=mood,
            context=context,
            mode=mode,
            tool_events=tool_events or [],
            agent_trace=agent_trace or [],
        )

    def _build_text_signals(self, user_text: str) -> TextSignals:
        text = (user_text or "").strip()
        lowered = text.lower()
        compact = re.sub(r"\s+", " ", lowered).strip()
        folded_compact = unicodedata.normalize("NFKD", compact).encode("ascii", "ignore").decode("ascii")
        ascii_compact = folded_compact
        return TextSignals(
            text=text,
            lowered=lowered,
            compact=compact,
            ascii_compact=ascii_compact,
            folded_compact=folded_compact,
        )

    def _tool_plan(self, tool_name: str, **tool_input) -> dict:
        return {
            "mode": "tool_reply",
            "tool_name": tool_name,
            "tool_input": tool_input,
        }

    def _clarify_plan(self, reply: str, mood: str = "thoughtful") -> dict:
        return {
            "mode": "clarify_reply",
            "reply": reply,
            "mood": mood,
        }

    def _render_direct_tool_reply(self, tool_name: str, tool_output, user_text: str) -> str | None:
        signals = self._build_text_signals(user_text)
        compact = signals.compact
        ascii_compact = signals.ascii_compact

        if tool_name == "datetime_local" and isinstance(tool_output, dict):
            if "time" in compact:
                return f"It's {tool_output.get('time', '')} right now."
            if "date" in compact or "datum" in compact:
                return f"Today is {tool_output.get('date', '')}."
            if "day" in compact or "dag" in compact:
                return f"It's {tool_output.get('day', '')} today."
            if "week" in compact or "vecka" in compact:
                return f"We're in week {tool_output.get('week', '')}."
            if "month" in compact or "manad" in ascii_compact or "mÃƒÂ¥nad" in compact:
                return f"It's {tool_output.get('month', '')}."
            if "year" in compact or "ar" in ascii_compact or "ÃƒÂ¥r" in compact:
                return f"It's {tool_output.get('year', '')}."
            return f"It's {tool_output.get('time', '')} on {tool_output.get('date', '')}."

        if tool_name == "calculator":
            return f"That comes to {tool_output}."

        if tool_name == "weather_lookup" and isinstance(tool_output, dict):
            return self._render_weather_reply(tool_output)

        if tool_name == "web_fetch" and isinstance(tool_output, dict):
            title = tool_output.get("title", "webpage")
            snippet = (tool_output.get("text", "") or "").strip()
            url = (tool_output.get("url", "") or "").strip()
            if snippet:
                snippet = snippet[:280].rstrip()
                source_hint = f" If you want, I can give you the source too: {url}" if url else " If you want, I can point you to the source."
                return f"All right, I checked {title}. In brief: {snippet}{source_hint}"
            return f"All right, I checked {title}, but there wasn't much readable text to pull out. If you want, I can still give you the source."

        if tool_name == "web_search" and isinstance(tool_output, list):
            if not tool_output:
                return "All right, I checked, but nothing looked especially solid."
            top = tool_output[:3]
            parts = []
            for item in top:
                title = (item.get("title", "") or "Result").strip()
                snippet = re.sub(r"\s+", " ", (item.get("snippet", "") or "").strip())
                if snippet:
                    parts.append(f"{title}: {snippet[:120].rstrip()}")
                else:
                    parts.append(title)
            if any(token in ascii_compact for token in ["who is", "what is", "when did", "where is", "how does", "varfor", "varfÃƒÂ¶r", "vad ar", "vad ÃƒÂ¤r"]):
                follow_up = " Want the quick answer, the deeper version, or the source?"
            else:
                follow_up = " Want me to keep it brief, dig a little further, or give you the source?"
            return "All right, here's the shape of it: " + " | ".join(parts) + follow_up

        if tool_name == "wikipedia_search" and isinstance(tool_output, list):
            if not tool_output:
                return "All right, I checked Wikipedia, but nothing looked like a clean match."
            top = tool_output[:3]
            lead = top[0]
            lead_title = (lead.get("title", "") or "That topic").strip()
            lead_snippet = re.sub(r"\s+", " ", (lead.get("snippet", "") or "").strip())
            lead_url = (lead.get("url", "") or "").strip()
            knowledge_prompt = any(
                token in ascii_compact
                for token in [
                    "tell me about",
                    "who is",
                    "who was",
                    "what is",
                    "what was",
                    "beratta om",
                    "berÃƒÂ¤tta om",
                ]
            )
            if knowledge_prompt and lead_snippet:
                summary = lead_snippet[:220].rstrip(" ,;:-")
                source_hint = f" Source if you want it: {lead_url}" if lead_url else " If you want, I can give you the source too."
                return f"All right. {lead_title} is the short version: {summary} Want the quick take, a deeper one, or the source?{source_hint}"
            parts = []
            for item in top:
                title = (item.get("title", "") or "Article").strip()
                snippet = re.sub(r"\s+", " ", (item.get("snippet", "") or "").strip())
                url = (item.get("url", "") or "").strip()
                segment = f"{title}: {snippet[:140].rstrip()}" if snippet else title
                if url:
                    segment += f" ({url})"
                parts.append(segment)
            return "All right, Wikipedia gives me this: " + " | ".join(parts) + " Want the short version, a deeper one, or the source?"

        if tool_name == "browser_open" and isinstance(tool_output, dict):
            target = tool_output.get("target", "page")
            browser = tool_output.get("browser", "browser")
            url = tool_output.get("url", "")
            if target == "spotify":
                return f"On it, opened {target} in {browser}: {url} Want something in the same vibe, heavier, or softer after that?"
            if target == "youtube":
                return f"On it, opened {target} in {browser}: {url} Want another clip in the same lane, or something a bit different?"
            if target == "wikipedia":
                return f"On it, opened {target} in {browser}: {url} Want the quick version here too, or are you just browsing?"
            return f"On it, opened {target} in {browser}: {url}"

        if tool_name == "pdf_extract_text" and isinstance(tool_output, dict):
            text = re.sub(r"\s+", " ", (tool_output.get("text", "") or "").strip())
            if text:
                return f"All right, I pulled text from the PDF. In brief: {text[:320].rstrip()} Want a cleaner summary, key points, or just the raw gist?"
            return "All right, I read the PDF, but there wasn't enough clean text to summarize."

        if tool_name == "vision_describe_image" and isinstance(tool_output, str):
            summary = re.sub(r"\s+", " ", tool_output).strip()
            if summary:
                return "All right, " + summary[:320].rstrip()
            return "All right, I looked at the image, but I couldn't get a clean read on it."

        return None

    def _render_weather_reply(self, tool_output: dict) -> str:
        location = str(tool_output.get("location", "that place") or "that place")
        condition = str(tool_output.get("condition", "mixed") or "mixed")
        temp_c = float(tool_output.get("temperature_c", 0.0) or 0.0)
        feels_like_c = float(tool_output.get("feels_like_c", temp_c) or temp_c)
        wind_kmh = float(tool_output.get("wind_kmh", 0.0) or 0.0)
        observed_at = str(tool_output.get("observed_at", "") or "").strip()
        source = str(tool_output.get("source", "") or "").strip()

        wind_note = ""
        if wind_kmh >= 45:
            wind_note = " It sounds pretty windy there."
        elif wind_kmh >= 28:
            wind_note = " There's a noticeable breeze too."

        if observed_at or source:
            summary = (
                f"In {location} it's {temp_c:.0f} degrees C right now, feels like {feels_like_c:.0f} degrees C, "
                f"with {condition} and wind around {wind_kmh:.0f} km/h.{wind_note}"
            )
            if observed_at:
                observed_time = observed_at.replace("T", " ")
                summary += f" That reading is from {observed_time}"
                summary += f" via {source}." if source else "."
                return summary
            if source:
                summary += f" Source: {source}."
            return summary

        if abs(temp_c - feels_like_c) >= 4:
            return (
                f"In {location} it's about {temp_c:.0f} degrees right now, but it feels more like {feels_like_c:.0f}, "
                f"with {condition} and wind around {wind_kmh:.0f} km/h.{wind_note}"
            )
        return (
            f"In {location} it's about {temp_c:.0f} degrees right now with {condition} and wind around {wind_kmh:.0f} km/h."
            f"{wind_note}"
        )

    def _extract_weather_location(self, text: str) -> str:
        for pattern in (
            r"(?i)\b(?:in|for|at|i)\s+([\w' .-]+)[.!?]*$",
            r"(?i)^(?:weather|forecast|temperature|v\w*der(?:et)?|temperatur(?:en)?)\s+([\w' .-]+)[.!?]*$",
        ):
            match = re.search(pattern, (text or "").strip())
            if match:
                location = (match.group(1) or "").strip(" :,-")
                if location:
                    return location
        return ""

    def _weather_clarify_reply(self, _signals: TextSignals) -> str:
        return "I can check the weather. Which place do you want?"

    def _is_weather_request(self, signals: TextSignals) -> bool:
        explicit_tokens = {
            "weather",
            "forecast",
            "temperature",
            "vader",
            "vadret",
            "temperatur",
        }
        if any(
            token in signals.compact or token in signals.ascii_compact or token in signals.folded_compact
            for token in explicit_tokens
        ):
            return True

        query_markers = {
            "what is",
            "whats",
            "how is",
            "hows",
            "tell me",
            "check",
            "can you check",
            "kan du kolla",
            "hur ar",
            "vad ar",
        }
        condition_markers = {
            "rain",
            "sun",
            "wind",
            "storm",
            "snow",
            "regn",
            "sol",
            "vind",
            "sno",
        }
        return any(marker in signals.ascii_compact for marker in query_markers) and any(
            marker in signals.ascii_compact for marker in condition_markers
        )

    def _plan_weather_request(self, signals: TextSignals) -> dict | None:
        if not self._is_weather_request(signals):
            return None
        location = self._extract_weather_location(signals.text)
        if location:
            return self._tool_plan("weather_lookup", location=location)
        return self._clarify_plan(self._weather_clarify_reply(signals))

    def _is_time_query(self, signals: TextSignals) -> bool:
        time_query_patterns = [
            "what time is it",
            "whats the time",
            "what is the time",
            "what date is it",
            "whats the date",
            "what is the date",
            "what day is it",
            "which day is it",
            "what week is it",
            "what week are we in",
            "what month is it",
            "which month is it",
            "what year is it",
            "vad ar klockan",
            "vad ÃƒÂ¤r klockan",
            "vilken dag ar det",
            "vilken dag ÃƒÂ¤r det",
            "vilket datum ar det",
            "vilket datum ÃƒÂ¤r det",
            "vilken vecka ar det",
            "vilken vecka ÃƒÂ¤r det",
            "vilken manad ar det",
            "vilken mÃƒÂ¥nad ÃƒÂ¤r det",
            "vilket ar ar det",
            "vilket ÃƒÂ¥r ÃƒÂ¤r det",
        ]
        return any(pattern in signals.compact or pattern in signals.ascii_compact for pattern in time_query_patterns)

    def _maybe_clarify_plan(self, query: str) -> dict | None:
        fuzzy_query = self._maybe_clarify_search_query(query)
        if fuzzy_query.startswith("CLARIFY::"):
            return self._clarify_plan(fuzzy_query.split("::", 1)[1])
        return None

    def _wikipedia_plan(self, query: str) -> dict | None:
        if not query or len(query) < 3:
            return None
        clarify = self._maybe_clarify_plan(query)
        if clarify is not None:
            return clarify
        fuzzy_query = self._maybe_clarify_search_query(query)
        return self._tool_plan("wikipedia_search", query=fuzzy_query, limit=3)

    def _web_search_plan(self, query: str) -> dict | None:
        if not query:
            return None
        clarify = self._maybe_clarify_plan(query)
        if clarify is not None:
            return clarify
        fuzzy_query = self._maybe_clarify_search_query(query)
        return self._tool_plan("web_search", q=fuzzy_query, k=5)

    def _plan_resource_request(self, text: str, lowered: str, ascii_compact: str) -> dict | None:
        url_match = re.search(r"(https?://[^\s]+)", text, re.IGNORECASE)
        if url_match and any(token in ascii_compact for token in ["open", "oppna", "launch", "go to"]):
            return self._tool_plan("browser_open", url=url_match.group(1).rstrip(".,!?"))
        if url_match:
            return self._tool_plan("web_fetch", url=url_match.group(1).rstrip(".,!?"), max_chars=4000)

        pdf_match = re.search(r"([A-Za-z]:\\[^\\/:*?\"<>|\r\n]+(?:\\[^\\/:*?\"<>|\r\n]+)*\.pdf)\b", text)
        if pdf_match and any(token in lowered for token in ["pdf", "file", "read", "open", "extract", "summarize", "scan"]):
            return self._tool_plan("pdf_extract_text", pdf_path=pdf_match.group(1), max_pages=30)

        image_match = re.search(r"([A-Za-z]:\\[^\\/:*?\"<>|\r\n]+(?:\\[^\\/:*?\"<>|\r\n]+)*\.(png|jpg|jpeg|webp))\b", text, re.IGNORECASE)
        if image_match and any(token in lowered for token in ["describe", "what is in", "what's in", "look at", "image", "picture", "photo", "see", "analyze"]):
            return self._tool_plan("vision_describe_image", image_path=image_match.group(1))

        return None

    def _plan_browser_or_media(self, text: str, ascii_compact: str) -> dict | None:
        browser_targets = {
            "spotify": ["open spotify", "oppna spotify", "start spotify", "launch spotify"],
            "youtube": ["open youtube", "oppna youtube", "start youtube", "launch youtube"],
            "wikipedia": ["open wikipedia", "oppna wikipedia", "start wikipedia", "launch wikipedia"],
        }
        for target, patterns in browser_targets.items():
            if any(pattern in ascii_compact for pattern in patterns):
                query = None
                if target == "youtube":
                    query_match = re.search(r"(?i)\b(?:on youtube|youtube)\b\s*(?:for|about|om)?\s*(.+)$", text)
                    if query_match:
                        query = query_match.group(1).strip(" :,-") or None
                elif target == "wikipedia":
                    query_match = re.search(r"(?i)\b(?:wikipedia)\b\s*(?:for|about|om)?\s*(.+)$", text)
                    if query_match:
                        query = query_match.group(1).strip(" :,-") or None
                return self._tool_plan("browser_open", target=target, query=query)

        spotify_play_match = re.search(
            r"(?i)\b(?:play|put on|start|queue|spela|satt pa|sÃƒÂ¤tt pÃƒÂ¥)\b(?:\s+(?:me|us|mig|oss))?\s+(.+?)(?:\s+(?:on|in|via|pa|pÃƒÂ¥)\s+spotify)?[.!?]*$",
            text,
        )
        if spotify_play_match:
            query = self._build_spotify_query(spotify_play_match.group(1))
            if query.startswith("CLARIFY::"):
                return self._clarify_plan(query.split("::", 1)[1])
            lowered_query = query.lower()
            if query and lowered_query not in {"spotify", "youtube", "wikipedia"}:
                return self._tool_plan("browser_open", target="spotify", query=query)

        youtube_play_match = re.search(
            r"(?i)\b(?:play|watch|show|spela|visa)\b(?:\s+(?:me|mig))?\s+(.+?)\s+(?:on|pa|pÃƒÂ¥)\s+youtube[.!?]*$",
            text,
        )
        if youtube_play_match:
            query = self._clean_media_query(youtube_play_match.group(1))
            if query:
                return self._tool_plan("browser_open", target="youtube", query=query)

        return None

    def _plan_knowledge_or_search(self, text: str, ascii_compact: str) -> dict | None:
        if self._looks_like_personal_followup(ascii_compact):
            return {"mode": "direct_reply"}

        wikipedia_subject_match = re.search(
            r"(?i)\b(?:tell me about|can you tell me about|look up|check up|search for|find)\b\s+(.+?)\s+\b(?:on|in)\s+wikipedia\b[.!?]*$",
            text,
        )
        if wikipedia_subject_match:
            return self._wikipedia_plan(self._resolve_recent_topic_query(wikipedia_subject_match.group(1)))

        bare_wikipedia_patterns = [
            "can you look at wikipedia",
            "can you check wikipedia",
            "could you look at wikipedia",
            "could you check wikipedia",
            "look at wikipedia",
            "check wikipedia",
            "use wikipedia",
            "can you use wikipedia",
            "can you look on wikipedia",
            "can you check on wikipedia",
        ]
        if any(pattern in ascii_compact for pattern in bare_wikipedia_patterns):
            topic = self._best_recent_topic_reference()
            if topic:
                return self._tool_plan("wikipedia_search", query=topic, limit=3)
            return self._clarify_plan("I can. What do you want me to look up on Wikipedia?")

        wikipedia_match = re.search(
            r"(?i)\b(?:search wikipedia for|look up on wikipedia|wikipedia|sok pa wikipedia|sÃƒÂ¶k pÃƒÂ¥ wikipedia|kolla wikipedia|slag upp pa wikipedia|slÃƒÂ¥ upp pÃƒÂ¥ wikipedia)\b(?:\s*[:,-]?\s*(.+))?$",
            text,
        )
        if wikipedia_match:
            query = self._resolve_recent_topic_query((wikipedia_match.group(1) or "").strip(" :,-?!"))
            if query:
                return self._wikipedia_plan(query)
            topic = self._best_recent_topic_reference()
            if topic:
                return self._tool_plan("wikipedia_search", query=topic, limit=3)
            return self._clarify_plan("Sure. What should I look up on Wikipedia?")

        knowledge_match = re.search(
            r"(?i)\b(?:tell me about|who is|who was|what is|what was|can you tell me about|kan du beratta om|kan du berÃƒÂ¤tta om|beratta om|berÃƒÂ¤tta om)\b\s+(.+?)[.!?]*$",
            text,
        )
        if knowledge_match:
            query = self._resolve_recent_topic_query(knowledge_match.group(1))
            if self._looks_like_personal_followup(ascii_compact) or self._looks_like_personal_followup(query.lower()):
                return {"mode": "direct_reply"}
            if query and len(query) >= 3 and query.lower() not in {"you", "yourself", "me"}:
                return self._wikipedia_plan(query)

        person_lookup_match = re.search(
            r"(?i)\b(?:check up|look up|lookup|check out|find|search for|tell me about)\b.*?\b(?:person|author|writer|poet|painter|artist)\b\s+(.+?)(?:\s+for me)?[.!?]*$",
            text,
        )
        if person_lookup_match:
            return self._wikipedia_plan(self._resolve_recent_topic_query(person_lookup_match.group(1)))

        person_followup_match = re.search(r"(?i)^\s*(?:the\s+)?(?:person|author|writer|poet|painter|artist)\s+(.+?)\s*$", text)
        if person_followup_match:
            query = self._resolve_recent_topic_query(person_followup_match.group(1))
            if query and len(query) >= 3:
                return self._tool_plan("wikipedia_search", query=query, limit=3)

        generic_search_match = re.search(
            r"(?i)\b(search for|look up|find online|google|duckduckgo|find me info on|check online|sok efter|sÃƒÂ¶k efter|sok upp|sÃƒÂ¶k upp|kolla upp)\b\s*[:,-]?\s*(.+)$",
            text,
        )
        if generic_search_match:
            query = generic_search_match.group(2).strip(" :,-")
            if query:
                return self._web_search_plan(query)

        return None

    def _looks_like_personal_followup(self, text: str) -> bool:
        compact = re.sub(r"[^a-z0-9\s]", "", str(text or "").lower())
        compact = re.sub(r"\s+", " ", compact).strip()
        if not compact:
            return False
        personal_markers = {
            "do you like",
            "you like",
            "what do you like",
            "what is it that you like",
            "that you like",
            "song that you like",
            "artist that you like",
            "your favorite",
            "your favourite",
        }
        pronoun_markers = {"about them", "about it", "like them", "like it"}
        return any(marker in compact for marker in personal_markers | pronoun_markers)

    def _plan(self, user_text: str) -> dict:
        signals = self._build_text_signals(user_text)
        text = signals.text
        lowered = signals.lowered
        compact = signals.compact
        ascii_compact = signals.ascii_compact

        follow_up_plan = self._plan_follow_up(text, compact, ascii_compact)
        if follow_up_plan is not None:
            return follow_up_plan

        weather_plan = self._plan_weather_request(signals)
        if weather_plan is not None:
            return weather_plan

        if self._is_time_query(signals):
            return self._tool_plan("datetime_local")

        math_match = re.search(
            r"(?i)(?:what is|what's|calculate|calc|solve|vad ar|vad ÃƒÂ¤r|rakna ut|rÃƒÂ¤kna ut)?\s*([-+*/().\d\s]{3,})$",
            text,
        )
        if math_match:
            expression = math_match.group(1).strip()
            if re.fullmatch(r"[-+*/().\d\s]+", expression) and any(ch.isdigit() for ch in expression):
                return {
                    "mode": "tool_reply",
                    "tool_name": "calculator",
                    "tool_input": {"expression": expression},
                }

        resource_plan = self._plan_resource_request(text, lowered, ascii_compact)
        if resource_plan is not None:
            return resource_plan

        browser_plan = self._plan_browser_or_media(text, ascii_compact)
        if browser_plan is not None:
            return browser_plan

        knowledge_plan = self._plan_knowledge_or_search(text, ascii_compact)
        if knowledge_plan is not None:
            return knowledge_plan

        return {"mode": "direct_reply"}

    def _is_tool_unlocked(self, tool_name: str, user_level: int) -> bool:
        required_level = int(self.TOOL_LEVEL_REQUIREMENTS.get(tool_name, 1) or 1)
        return int(user_level or 1) >= required_level

    def _is_feature_enabled(self, tool_name: str, tool_input: dict, user_level: int) -> bool:
        feature_id = tool_feature_id(tool_name, tool_input)
        if not feature_id:
            return True
        feature_state = self.memory.get_agent_state("feature_access_state", default={}) or {}
        overrides = feature_state.get("overrides", {}) if isinstance(feature_state, dict) else {}
        return is_feature_enabled(feature_id, int(user_level or 1), overrides=overrides)

    def _plan_follow_up(self, text: str, _compact: str, ascii_compact: str) -> dict | None:
        last_tool = self._last_tool_state.get("tool_name", "")
        last_seed = self._last_tool_state.get("seed_query", "")
        last_ai = self._last_tool_state.get("reply_hint", "")
        last_source_type = self._last_tool_state.get("last_source_type", "")
        last_topic = self._last_tool_state.get("last_topic", "") or last_seed
        last_artist = self._last_tool_state.get("last_artist", "")
        last_song = self._last_tool_state.get("last_song", "")
        last_source_url = self._last_tool_state.get("last_source_url", "")
        last_source_title = self._last_tool_state.get("last_source_title", "") or last_topic
        lowered = (text or "").strip().lower()
        if self._looks_like_corrected_lookup(text):
            recent_turns = self.memory.get_recent_turns(limit=4)
            for turn in reversed(recent_turns):
                ai_text = str(turn.get("ai", "") or "").lower()
                user_text = str(turn.get("user", "") or "").lower()
                if "nothing looked like a clean match" in ai_text or re.search(r"\bwhat is (?:a |an )?", user_text):
                    return self._tool_plan("wikipedia_search", query=text.strip(" :,-.!?"), limit=3)

        if not last_ai and not last_tool:
            recent_turns = self.memory.get_recent_turns(limit=3)
            if self._looks_like_location_reply(text):
                for turn in reversed(recent_turns):
                    ai_text = str(turn.get("ai", "") or "").lower()
                    user_text = str(turn.get("user", "") or "").lower()
                    if "weather" in ai_text or "vader" in ai_text or "forecast" in ai_text:
                        return {
                            "mode": "tool_reply",
                            "tool_name": "weather_lookup",
                            "tool_input": {"location": text.strip(" :,-.!?")},
                        }
                    if "which place" in ai_text or "vilken plats" in ai_text:
                        return {
                            "mode": "tool_reply",
                            "tool_name": "weather_lookup",
                            "tool_input": {"location": text.strip(" :,-.!?")},
                        }
                    if "weather" in user_text or "vader" in user_text or "forecast" in user_text:
                        return {
                            "mode": "tool_reply",
                            "tool_name": "weather_lookup",
                            "tool_input": {"location": text.strip(" :,-.!?")},
                        }
            if self._is_weather_comment(lowered):
                for turn in reversed(recent_turns):
                    user_text = str(turn.get("user", "") or "").lower()
                    ai_text = str(turn.get("ai", "") or "").lower()
                    if "weather" in user_text or "vader" in user_text or "forecast" in user_text:
                        return {"mode": "direct_reply"}
                    if "weather" in ai_text or "vader" in ai_text or "forecast" in ai_text:
                        return {"mode": "direct_reply"}
            return None

        if ascii_compact in {
            "source",
            "the source",
            "give me the source",
            "show me the source",
            "source please",
            "link",
            "the link",
            "give me the link",
            "show me the link",
            "link please",
        }:
            if last_source_url:
                return {
                    "mode": "clarify_reply",
                    "reply": f"Sure. The source for {last_source_title or 'that'} is {last_source_url}",
                    "mood": "thoughtful",
                }
            return {
                "mode": "clarify_reply",
                "reply": "I don't have a clean source saved for that one yet. Want me to look it up again properly?",
                "mood": "thoughtful",
            }

        if ascii_compact in {"continue", "go on", "keep going", "so continue", "continue then", "carry on"}:
            if last_source_type in {"knowledge", "document", "webpage"}:
                return {"mode": "direct_reply"}

        if ascii_compact in {"same vibe", "same lane", "heavier", "softer"}:
            if last_source_type != "music" and (
                last_tool != "browser_open" or self._last_tool_state.get("target") != "spotify"
            ):
                return None
            seed = last_seed or self._compose_music_seed(last_song, last_artist) or self._last_media_seed()
            if not seed:
                return {
                    "mode": "clarify_reply",
                    "reply": "I can do that, but I need a track or artist to steer from first.",
                    "mood": "thoughtful",
                }
            flavor_map = {
                "same vibe": seed,
                "same lane": seed,
                "heavier": f"{seed} heavier",
                "softer": f"{seed} softer",
            }
            return {
                "mode": "tool_reply",
                "tool_name": "browser_open",
                "tool_input": {"target": "spotify", "query": flavor_map.get(ascii_compact, seed)},
            }

        if ascii_compact in {"deeper", "dig deeper", "deeper version", "go deeper", "quick version", "short version", "brief version"}:
            if last_source_type in {"knowledge", "document", "webpage"}:
                return {"mode": "direct_reply"}
            if last_tool in {"wikipedia_search", "web_search", "pdf_extract_text"} or any(
                marker in last_ai.lower() for marker in ["wikipedia gives me this", "here's the shape of it", "pulled text from the pdf"]
            ):
                return {"mode": "direct_reply"}

        if ascii_compact in {"what was that again", "what was it again", "what were we looking at"}:
            if last_topic:
                return {
                    "mode": "clarify_reply",
                    "reply": f"We were on '{last_topic}'. Want me to pick that back up?",
                    "mood": "thoughtful",
                }

        if self._looks_like_location_reply(text):
            recent_turns = self.memory.get_recent_turns(limit=3)
            weather_context = last_tool == "weather_lookup" or last_source_type == "weather"
            if not weather_context:
                for turn in reversed(recent_turns):
                    ai_text = str(turn.get("ai", "") or "").lower()
                    user_text = str(turn.get("user", "") or "").lower()
                    if "which place" in ai_text or "vilken plats" in ai_text:
                        weather_context = True
                        break
                    if "weather" in user_text or "vader" in user_text or "forecast" in user_text:
                        weather_context = True
                        break
            if weather_context:
                return {
                    "mode": "tool_reply",
                    "tool_name": "weather_lookup",
                    "tool_input": {"location": text.strip(" :,-.!?")},
                }

        if (last_tool == "weather_lookup" or last_source_type == "weather") and self._is_weather_comment(lowered):
            return {"mode": "direct_reply"}

        return None

    def _looks_like_corrected_lookup(self, text: str) -> bool:
        candidate = re.sub(r"\s+", " ", str(text or "").strip())
        if not candidate or len(candidate) > 48:
            return False
        lowered = candidate.lower()
        blocked = {"yes", "no", "ok", "okay", "thanks", "thank you", "hi", "hey", "hello"}
        if lowered in blocked:
            return False
        if not re.fullmatch(r"[A-Za-z][A-Za-z' -]{2,47}", candidate):
            return False
        return len(candidate.split()) <= 3

    def _looks_like_location_reply(self, text: str) -> bool:
        candidate = re.sub(r"\s+", " ", str(text or "").strip())
        if not candidate or len(candidate) < 2 or len(candidate) > 64:
            return False
        if "_" in candidate or not re.fullmatch(r"[\w'., -]+", candidate):
            return False
        word_count = len([part for part in candidate.replace(",", " ").split() if part])
        if word_count == 0 or word_count > 5:
            return False
        lowered = candidate.lower()
        blocked = {"yes", "no", "maybe", "okay", "ok", "thanks", "thank you", "hello", "hey", "hi", "waiting"}
        if lowered in blocked:
            return False
        if any(marker in lowered for marker in ["it's", "its", "almost", "storm", "weather", "forecast", "wind", "rain", "coming", "feels like"]):
            return False
        return True

    def _is_weather_comment(self, lowered_text: str) -> bool:
        text = str(lowered_text or "").strip()
        if not text:
            return False
        markers = {
            "storm",
            "stormy",
            "wind",
            "windy",
            "rain",
            "raining",
            "snow",
            "cold",
            "warm",
            "hot",
            "forecast",
            "weather",
            "feels like",
            "overcast",
            "sunny",
            "cloudy",
            "regn",
            "vind",
            "stormigt",
            "kallt",
            "varmt",
            "vader",
        }
        return any(marker in text for marker in markers)

    def _last_media_seed(self) -> str | None:
        candidates = self._collect_recent_media_references()
        if not candidates:
            return None
        return candidates[-1]

    def _remember_tool_state(self, tool_name: str, user_text: str, tool_input: dict, tool_output) -> None:
        state = {
            "tool_name": tool_name,
            "user_text": user_text or "",
            "reply_hint": "",
            "target": "",
            "seed_query": "",
            "last_artist": "",
            "last_song": "",
            "last_album": "",
            "last_topic": "",
            "last_source_type": "",
            "last_source_url": "",
            "last_source_title": "",
            "last_weather_summary": "",
            "last_followup_options": [],
        }

        if tool_name == "browser_open" and isinstance(tool_output, dict):
            state["target"] = str(tool_output.get("target", "") or tool_input.get("target", ""))
            state["seed_query"] = str(tool_input.get("query", "") or "")
            state["reply_hint"] = f"opened {state['target']}"
            state["last_topic"] = state["seed_query"] or str(tool_output.get("url", "") or "")
            if state["target"] == "spotify":
                state["last_source_type"] = "music"
                state["last_followup_options"] = ["same vibe", "heavier", "softer"]
                state.update(self._extract_spotify_state(state["seed_query"]))
            elif state["target"] == "youtube":
                state["last_source_type"] = "video"
                state["last_followup_options"] = ["same lane", "something different"]
            elif state["target"] == "wikipedia":
                state["last_source_type"] = "knowledge"
                state["last_followup_options"] = ["quick version", "deeper"]
            else:
                state["last_source_type"] = "browser"
        elif tool_name == "wikipedia_search":
            state["seed_query"] = str(tool_input.get("query", "") or "")
            state["reply_hint"] = "wikipedia gives me this"
            state["last_topic"] = state["seed_query"]
            state["last_source_type"] = "knowledge"
            if isinstance(tool_output, list) and tool_output:
                state["last_source_url"] = str(tool_output[0].get("url", "") or "")
                state["last_source_title"] = str(tool_output[0].get("title", "") or state["last_topic"])
            state["last_followup_options"] = ["quick version", "deeper"]
        elif tool_name == "web_search":
            state["seed_query"] = str(tool_input.get("q", "") or "")
            state["reply_hint"] = "here's the shape of it"
            state["last_topic"] = state["seed_query"]
            state["last_source_type"] = "knowledge"
            if isinstance(tool_output, list) and tool_output:
                state["last_source_url"] = str(tool_output[0].get("url", "") or "")
                state["last_source_title"] = str(tool_output[0].get("title", "") or state["last_topic"])
            state["last_followup_options"] = ["quick version", "deeper"]
        elif tool_name == "pdf_extract_text":
            state["seed_query"] = str(tool_input.get("pdf_path", "") or "")
            state["reply_hint"] = "pulled text from the pdf"
            state["last_topic"] = state["seed_query"]
            state["last_source_type"] = "document"
            state["last_followup_options"] = ["cleaner summary", "key points", "raw gist"]
        elif tool_name == "web_fetch":
            state["seed_query"] = str(tool_input.get("url", "") or "")
            state["reply_hint"] = "checked a page"
            state["last_topic"] = state["seed_query"]
            state["last_source_type"] = "webpage"
            if isinstance(tool_output, dict):
                state["last_source_url"] = str(tool_output.get("url", "") or tool_input.get("url", "") or "")
                state["last_source_title"] = str(tool_output.get("title", "") or state["last_topic"])
            state["last_followup_options"] = ["quick version", "deeper"]
        elif tool_name == "vision_describe_image":
            state["seed_query"] = str(tool_input.get("image_path", "") or "")
            state["reply_hint"] = "looked at the image"
            state["last_topic"] = state["seed_query"]
            state["last_source_type"] = "image"
        elif tool_name == "weather_lookup":
            state["seed_query"] = str(tool_input.get("location", "") or "")
            state["reply_hint"] = "checked the weather"
            state["last_topic"] = state["seed_query"]
            state["last_source_type"] = "weather"
            if isinstance(tool_output, dict):
                state["last_source_title"] = str(tool_output.get("location", "") or state["seed_query"])
                state["last_weather_summary"] = (
                    f"{tool_output.get('location', state['seed_query'])}: "
                    f"{tool_output.get('condition', 'mixed')}, "
                    f"{float(tool_output.get('temperature_c', 0.0) or 0.0):.0f}C, "
                    f"feels like {float(tool_output.get('feels_like_c', 0.0) or 0.0):.0f}C, "
                    f"wind {float(tool_output.get('wind_kmh', 0.0) or 0.0):.0f} km/h"
                )
            state["last_followup_options"] = ["another place", "brief version"]

        if not state["last_topic"]:
            state["last_topic"] = state["seed_query"]

        self._last_tool_state = state
        self.memory.set_agent_state("last_tool_state", state)

    def _clean_media_query(self, raw_query: str) -> str:
        query = (raw_query or "").strip(" :,-.!?")
        query = re.sub(
            r'(?i)^(?:some|something|anything|the song|song|track|music|a song|an artist|artist)\s+',
            "",
            query,
        )
        query = re.sub(r'(?i)^(?:with|by|from)\s+', "", query)
        query = re.sub(r'(?i)\s+(?:please|for me)$', "", query)
        query = query.strip(" \"'")
        return query

    def _build_spotify_query(self, raw_query: str) -> str:
        query = self._clean_media_query(raw_query)
        if not query:
            return ""
        query = self._resolve_contextual_media_query(query)
        if query.startswith("CLARIFY::"):
            return query

        fuzzy_candidate = self._fuzzy_match_recent_media_reference(query)
        if fuzzy_candidate is not None and fuzzy_candidate.lower() != query.lower():
            return f"CLARIFY::I think you might mean '{fuzzy_candidate}'. Want me to run with that on Spotify?"

        quoted = re.search(r'"([^"]+)"', raw_query or "")
        if quoted:
            title = self._clean_media_query(quoted.group(1))
            artist_match = re.search(r'(?i)\b(?:by|with|from)\b\s+(.+)$', raw_query or "")
            if artist_match:
                artist = self._clean_media_query(artist_match.group(1))
                return f'track:{title} artist:{artist}' if artist else title
            return f"track:{title}"

        song_by_match = re.search(r'(?i)\b(?:song|track)\b\s+(.+?)\s+\bby\b\s+(.+)$', query)
        if song_by_match:
            title = self._clean_media_query(song_by_match.group(1))
            artist = self._clean_media_query(song_by_match.group(2))
            return f'track:{title} artist:{artist}'

        album_match = re.search(r'(?i)\balbum\b\s+(.+?)(?:\s+\bby\b\s+(.+))?$', query)
        if album_match:
            album = self._clean_media_query(album_match.group(1))
            artist = self._clean_media_query(album_match.group(2) or "")
            return f'album:{album} artist:{artist}'.strip()

        artist_match = re.search(r'(?i)\b(?:by|with|from)\b\s+(.+)$', query)
        if artist_match:
            artist = self._clean_media_query(artist_match.group(1))
            lead = self._clean_media_query(query[: artist_match.start()])
            if lead:
                return f'track:{lead} artist:{artist}'
            return artist

        return query

    def _resolve_contextual_media_query(self, query: str) -> str:
        lowered = (query or "").strip().lower()
        if lowered not in {"them", "it", "that", "them please", "it please", "that please"}:
            return query

        remembered_artist = self._last_tool_state.get("last_artist", "")
        if remembered_artist:
            return remembered_artist
        remembered_song = self._last_tool_state.get("last_song", "")
        if remembered_song:
            return remembered_song

        recent_turns = self.memory.get_recent_turns(limit=6)
        for turn in reversed(recent_turns):
            artist = self._extract_recent_artist_reference(turn.get("user", ""))
            if artist:
                return artist
        return "CLARIFY::I can take a guess, but I'm not fully sure what 'them' refers to. Do you mean the band you just mentioned?"

    def _extract_recent_artist_reference(self, user_text: str) -> str | None:
        text = (user_text or "").strip()
        if not text:
            return None

        patterns = [
            r'(?i)\bi like the band\s+([A-Za-z0-9&\'".\- ]{2,60})',
            r'(?i)\bi like\s+([A-Za-z0-9&\'".\- ]{2,60})',
            r'(?i)\bplay\s+.+?\bby\s+([A-Za-z0-9&\'".\- ]{2,60})',
            r'(?i)\bplay\s+.+?\bwith\s+([A-Za-z0-9&\'".\- ]{2,60})',
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                artist = self._clean_media_query(match.group(1))
                return artist or None
        return None

    def _fuzzy_match_recent_media_reference(self, query: str) -> str | None:
        cleaned_query = self._clean_media_query(query)
        if not cleaned_query or len(cleaned_query) < 3:
            return None

        candidates = self._collect_recent_media_references()
        if not candidates:
            return None

        direct = get_close_matches(cleaned_query.lower(), [item.lower() for item in candidates], n=1, cutoff=0.82)
        if direct:
            lowered = direct[0]
            for candidate in candidates:
                if candidate.lower() == lowered:
                    return candidate

        best_candidate = None
        best_score = 0.0
        for candidate in candidates:
            score = SequenceMatcher(None, cleaned_query.lower(), candidate.lower()).ratio()
            if score > best_score:
                best_score = score
                best_candidate = candidate
        if best_candidate and best_score >= 0.86:
            return best_candidate
        return None

    def _maybe_clarify_search_query(self, query: str) -> str:
        cleaned_query = self._clean_media_query(query)
        if not cleaned_query or len(cleaned_query) < 3:
            return query

        fuzzy_candidate = self._fuzzy_match_recent_reference(cleaned_query)
        if fuzzy_candidate is None:
            return cleaned_query
        if fuzzy_candidate.lower() == cleaned_query.lower():
            return cleaned_query
        return f"CLARIFY::I think you might mean '{fuzzy_candidate}'. Want me to search for that instead?"

    def _fuzzy_match_recent_reference(self, query: str) -> str | None:
        candidates = self._collect_recent_references()
        if not candidates:
            return None

        direct = get_close_matches(query.lower(), [item.lower() for item in candidates], n=1, cutoff=0.82)
        if direct:
            lowered = direct[0]
            for candidate in candidates:
                if candidate.lower() == lowered:
                    return candidate

        best_candidate = None
        best_score = 0.0
        for candidate in candidates:
            score = SequenceMatcher(None, query.lower(), candidate.lower()).ratio()
            if score > best_score:
                best_score = score
                best_candidate = candidate
        if best_candidate and best_score >= 0.86:
            return best_candidate
        return None

    def _collect_recent_media_references(self) -> list[str]:
        recent_turns = self.memory.get_recent_turns(limit=8)
        candidates: list[str] = []
        seen: set[str] = set()

        for value in (
            self._last_tool_state.get("last_artist", ""),
            self._last_tool_state.get("last_song", ""),
            self._last_tool_state.get("last_album", ""),
            self._last_tool_state.get("seed_query", ""),
        ):
            cleaned = self._clean_media_query(value)
            if cleaned and cleaned.lower() not in seen:
                seen.add(cleaned.lower())
                candidates.append(cleaned)

        patterns = [
            r'(?i)\bi like the band\s+([A-Za-z0-9&\'".\- ]{2,60})',
            r'(?i)\bi like\s+([A-Za-z0-9&\'".\- ]{2,60})',
            r'(?i)\b(?:song|track|album)\b\s+"([^"]+)"',
            r'(?i)\b(?:song|track|album)\b\s+([A-Za-z0-9&\'".\- ]{2,60})',
            r'(?i)"([^"]+)"',
        ]

        for turn in recent_turns:
            for source_text in (turn.get("user", ""), turn.get("ai", "")):
                text = (source_text or "").strip()
                if not text:
                    continue
                for pattern in patterns:
                    for match in re.finditer(pattern, text):
                        value = self._clean_media_query(match.group(1))
                        if not value:
                            continue
                        lowered = value.lower()
                        if lowered in seen:
                            continue
                        seen.add(lowered)
                        candidates.append(value)
        return candidates

    def _collect_recent_references(self) -> list[str]:
        recent_turns = self.memory.get_recent_turns(limit=8)
        candidates: list[str] = []
        seen: set[str] = set()

        for value in (
            self._last_tool_state.get("last_topic", ""),
            self._last_tool_state.get("last_artist", ""),
            self._last_tool_state.get("last_song", ""),
            self._last_tool_state.get("last_album", ""),
            self._last_tool_state.get("seed_query", ""),
        ):
            cleaned = self._clean_media_query(value)
            if cleaned and len(cleaned) >= 3 and cleaned.lower() not in seen:
                seen.add(cleaned.lower())
                candidates.append(cleaned)

        patterns = [
            r'(?i)\bi like the band\s+([A-Za-z0-9&\'".\- ]{2,60})',
            r'(?i)\bi like\s+([A-Za-z0-9&\'".\- ]{2,60})',
            r'(?i)\b(?:song|track|album|artist|band)\b\s+"([^"]+)"',
            r'(?i)\b(?:song|track|album|artist|band)\b\s+([A-Za-z0-9&\'".\- ]{2,60})',
            r'(?i)\b(?:about|on|for|wikipedia|spotify|youtube)\b\s+([A-Za-z0-9&\'".\- ]{2,60})',
            r'(?i)"([^"]+)"',
        ]

        for turn in recent_turns:
            for source_text in (turn.get("user", ""), turn.get("ai", "")):
                text = (source_text or "").strip()
                if not text:
                    continue
                for pattern in patterns:
                    for match in re.finditer(pattern, text):
                        value = self._clean_media_query(match.group(1))
                        if not value or len(value) < 3:
                            continue
                        lowered = value.lower()
                        if lowered in seen:
                            continue
                        seen.add(lowered)
                        candidates.append(value)
        return candidates

    def _best_recent_topic_reference(self) -> str | None:
        remembered = self._clean_media_query(self._last_tool_state.get("last_topic", ""))
        if remembered and len(remembered) >= 3:
            return remembered

        recent_turns = self.memory.get_recent_turns(limit=6)
        patterns = [
            r'(?i)\b(?:tell me about|who is|who was|what is|what was|about|on|for)\b\s+([A-Za-z0-9&\'".\- ]{3,80})',
            r'(?i)\b(?:band|artist|song|track|album)\b\s+([A-Za-z0-9&\'".\- ]{3,80})',
            r'(?i)"([^"]{3,80})"',
        ]
        for turn in reversed(recent_turns):
            user_text = (turn.get("user", "") or "").strip()
            if not user_text:
                continue
            for pattern in patterns:
                match = re.search(pattern, user_text)
                if not match:
                    continue
                value = self._clean_media_query(match.group(1))
                if value and len(value) >= 3:
                    return value

        references = self._collect_recent_references()
        return references[-1] if references else None

    def _resolve_recent_topic_query(self, query: str) -> str:
        cleaned = self._clean_media_query(query)
        cleaned = re.sub(r"(?i)\s+\b(?:on|in)\s+wikipedia\b$", "", cleaned).strip(" :,-?!\"'")
        ascii_cleaned = cleaned.lower().replace("ÃƒÂ¥", "a").replace("ÃƒÂ¤", "a").replace("ÃƒÂ¶", "o")
        if not cleaned:
            return self._best_recent_topic_reference() or ""

        referential_only = {
            "it",
            "that",
            "this",
            "him",
            "her",
            "them",
            "the person",
            "the author",
            "the writer",
            "the poet",
            "the painter",
            "the artist",
            "or such",
            "or something",
        }
        if ascii_cleaned in referential_only:
            return self._best_recent_topic_reference() or cleaned

        role_prefix_match = re.match(
            r"(?i)^(?:the\s+)?(?:person|author|writer|poet|painter|artist)\s+(.+)$",
            cleaned,
        )
        if role_prefix_match:
            stripped = self._clean_media_query(role_prefix_match.group(1))
            if stripped:
                return stripped

        return cleaned

    def _compose_music_seed(self, song: str, artist: str) -> str | None:
        song = self._clean_media_query(song)
        artist = self._clean_media_query(artist)
        if song and artist:
            return f"track:{song} artist:{artist}"
        if song:
            return f"track:{song}"
        if artist:
            return artist
        return None

    def _extract_spotify_state(self, query: str) -> dict[str, str]:
        cleaned = self._clean_media_query(query)
        state = {
            "last_artist": "",
            "last_song": "",
            "last_album": "",
            "last_topic": cleaned,
        }
        if not cleaned:
            return state

        song_match = re.search(r"(?i)\btrack:([^:]+?)(?:\s+artist:|$)", query)
        artist_match = re.search(r"(?i)\bartist:(.+)$", query)
        album_match = re.search(r"(?i)\balbum:([^:]+?)(?:\s+artist:|$)", query)

        if song_match:
            state["last_song"] = self._clean_media_query(song_match.group(1))
        if artist_match:
            state["last_artist"] = self._clean_media_query(artist_match.group(1))
        if album_match:
            state["last_album"] = self._clean_media_query(album_match.group(1))

        if state["last_album"] and state["last_artist"]:
            state["last_topic"] = f"{state['last_album']} by {state['last_artist']}"
        elif state["last_song"] and state["last_artist"]:
            state["last_topic"] = f"{state['last_song']} by {state['last_artist']}"
        elif state["last_song"]:
            state["last_topic"] = state["last_song"]
        elif state["last_artist"]:
            state["last_topic"] = state["last_artist"]
        elif state["last_album"]:
            state["last_topic"] = state["last_album"]

        return state
