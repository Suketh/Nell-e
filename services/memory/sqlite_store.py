import json
from pathlib import Path
from queue import Empty, Queue
import re
import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS turns (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL,
  user TEXT,
  ai TEXT,
  mood TEXT
);

CREATE TABLE IF NOT EXISTS user_memories (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL,
  category TEXT,
  kind TEXT,
  memory TEXT UNIQUE,
  weight REAL DEFAULT 1.0,
  last_seen REAL
);

CREATE TABLE IF NOT EXISTS agent_state (
  key TEXT PRIMARY KEY,
  value TEXT,
  ts REAL
);
"""


class MemoryStore:
    PERSONA_SECTION_LIMITS = {
        "semantic": 2,
        "episodic": 1,
        "anecdotes": 1,
        "goals": 2,
        "speech_habits": 3,
        "continuity_rules": 2,
        "mood_guidance": 3,
        "curiosity": 3,
        "user_interest_hooks": 3,
    }

    MEMORY_PATTERNS = [
        ("name", "stable", r"\bmy name is\s+([A-Z][a-z]+)\b"),
        ("location", "stable", r"\bi live in\s+([A-Za-z][A-Za-z\s,'-]{1,40})"),
        ("location", "stable", r"\bi'?m from\s+([A-Za-z][A-Za-z\s,'-]{1,40})"),
        ("work", "stable", r"\bi work as\s+(?:an?\s+)?([A-Za-z][A-Za-z\s-]{1,40}?)(?=,|\.|!|\?| and\b| but\b| because\b|$)"),
        ("work", "stable", r"\bi am\s+(?:an?\s+)?([A-Za-z][A-Za-z\s-]{1,40}?)(?=,|\.|!|\?| and\b| but\b| because\b|$)"),
        ("study", "stable", r"\bi study\s+([A-Za-z][A-Za-z\s-]{1,40}?)(?=,|\.|!|\?| and\b| but\b| because\b|$)"),
        ("likes", "stable", r"\bi like\s+([A-Za-z0-9 ,'-]{2,60}?)(?=,|\.|!|\?| and\b i\b| but\b| because\b|$)"),
        ("likes", "stable", r"\bi love\s+([A-Za-z0-9 ,'-]{2,60}?)(?=,|\.|!|\?| and\b i\b| but\b| because\b|$)"),
        ("likes", "stable", r"\bi enjoy\s+([A-Za-z0-9 ,'-]{2,60}?)(?=,|\.|!|\?| and\b i\b| but\b| because\b|$)"),
        ("likes", "stable", r"\b(?:i am|i'?m)\s+into\s+([A-Za-z0-9 ,'-]{2,60}?)(?=,|\.|!|\?| and\b i\b| but\b| because\b|$)"),
        ("favorite", "stable", r"\bmy favorite\s+([A-Za-z][A-Za-z\s-]{1,20})\s+is\s+([A-Za-z0-9 ,'-]{2,40})"),
        ("pet", "stable", r"\bi have\s+(?:a|an)\s+(cat|dog|rabbit|bird|horse)\b"),
        ("relationship", "stable", r"\bmy (boyfriend|girlfriend|partner|wife|husband)\b"),
        ("feeling", "transient", r"\bi feel\s+([A-Za-z][A-Za-z\s-]{1,30}?)(?=,|\.|!|\?| and\b| but\b| because\b|$)"),
        ("feeling", "transient", r"\bi'?m feeling\s+([A-Za-z][A-Za-z\s-]{1,30}?)(?=,|\.|!|\?| and\b| but\b| because\b|$)"),
        ("goal", "priority", r"\bi want to\s+([A-Za-z][A-Za-z0-9 ,'-]{2,60}?)(?=,|\.|!|\?| and\b i\b| but\b| because\b|$)"),
        ("goal", "priority", r"\b(?:i am|i'?m)\s+trying to\s+([A-Za-z][A-Za-z0-9 ,'-]{2,60}?)(?=,|\.|!|\?| and\b i\b| but\b| because\b|$)"),
    ]

    STOP_PHRASES = {
        "fine",
        "okay",
        "ok",
        "good",
        "bad",
        "tired",
        "happy",
        "sad",
    }

    CATEGORY_WEIGHTS = {
        "name": 4.0,
        "location": 2.5,
        "work": 2.5,
        "study": 2.5,
        "likes": 2.0,
        "interest_hook": 3.25,
        "favorite": 3.0,
        "pet": 2.5,
        "relationship": 2.5,
        "goal": 3.0,
        "feeling": 1.0,
    }

    def __init__(self, db_path: Path):
        self._lock = threading.RLock()
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self._write_queue = Queue()
        self._closed = False
        with self._lock:
            self.db.execute("PRAGMA journal_mode=WAL")
            self.db.executescript(SCHEMA)
        self._writer = threading.Thread(target=self._writer_loop, daemon=True)
        self._writer.start()

    def save_turn(self, user: str, ai: str, mood: str | None = None):
        if self._closed:
            return
        self._write_queue.put(("save_turn", user, ai, mood))

    def close(self):
        if self._closed:
            return
        self._closed = True
        self._write_queue.put(("shutdown",))
        self._writer.join(timeout=1.5)
        with self._lock:
            self.db.close()

    def clear_all(self):
        self._drain_pending_writes()
        with self._lock:
            self.db.execute("DELETE FROM turns")
            self.db.execute("DELETE FROM user_memories")
            self.db.execute("DELETE FROM agent_state")
            self.db.commit()

    def build_context(self, persona, k=6, current_user_text=""):
        self._drain_pending_writes()
        self.set_agent_state("persona_interest_topics", self._persona_interest_topics(persona))
        history_limit = max(2, min(k, 4))
        with self._lock:
            cur = self.db.execute("SELECT user, ai, mood FROM turns ORDER BY id DESC LIMIT ?", (history_limit,))
            pairs = list(reversed(cur.fetchall()))
        speaker_name = self._persona_speaker_name(persona)
        history_lines = []
        for user, ai, mood in pairs:
            history_lines.append(f"USER: {user}\n{speaker_name}: {ai}")

        memories = persona.get("memories", {})
        style = persona.get("style", {})
        relationship = persona.get("relationship", {})
        conversation_modules = persona.get("conversation_modules", {})
        mood_profile = persona.get("mood_profile", {})

        compact_user_text = self._compact_text(current_user_text)
        recalled = self._fetch_relevant_memories(compact_user_text, limit=4)
        sections = []

        stable_memories = self._fetch_user_memories(kind="stable", limit=4)
        priority_memories = self._fetch_user_memories(kind="priority", exclude_category="interest_hook", limit=3)
        transient_memories = self._fetch_user_memories(kind="transient", limit=2, recent_only_days=3)
        interest_hook_memories = self._fetch_user_memories(category="interest_hook", limit=3)
        agent_state = self.get_agent_state("last_tool_state", default={}) or {}
        gallery_state = self.get_agent_state("gallery_state", default={}) or {}
        unlocked_gallery = self.get_agent_state("unlocked_gallery", default=[]) or []
        progression_state = self.get_agent_state("progression_state", default={}) or {}
        nellie_preferences = self.get_agent_state("nellie_preferences", default={}) or {}

        if recalled:
            sections.append("RELEVANT_RECALL:\n" + "\n".join(f"- {item}" for item in recalled))
        if stable_memories:
            sections.append("USER_PROFILE:\n" + "\n".join(f"- {item}" for item in stable_memories))
        if priority_memories:
            sections.append("USER_GOALS:\n" + "\n".join(f"- {item}" for item in priority_memories))
        if transient_memories:
            sections.append("RECENT_USER_STATE:\n" + "\n".join(f"- {item}" for item in transient_memories))
        if interest_hook_memories:
            sections.append("USER_INTEREST_HOOKS:\n" + "\n".join(f"- {item}" for item in interest_hook_memories))
        if agent_state:
            focus_lines = []
            if agent_state.get("tool_name"):
                focus_lines.append(f"- Last tool used: {agent_state['tool_name']}")
            if agent_state.get("target"):
                focus_lines.append(f"- Current target: {agent_state['target']}")
            if agent_state.get("seed_query"):
                focus_lines.append(f"- Last focus/query: {agent_state['seed_query']}")
            if agent_state.get("last_source_type"):
                focus_lines.append(f"- Last source type: {agent_state['last_source_type']}")
            if agent_state.get("last_topic"):
                focus_lines.append(f"- Last topic: {agent_state['last_topic']}")
            if agent_state.get("last_source_title"):
                focus_lines.append(f"- Last source title: {agent_state['last_source_title']}")
            if agent_state.get("last_source_url"):
                focus_lines.append(f"- Last source URL: {agent_state['last_source_url']}")
            if agent_state.get("last_weather_summary"):
                focus_lines.append(f"- Last weather summary: {agent_state['last_weather_summary']}")
            if agent_state.get("last_artist"):
                focus_lines.append(f"- Last artist in focus: {agent_state['last_artist']}")
            if agent_state.get("last_song"):
                focus_lines.append(f"- Last song in focus: {agent_state['last_song']}")
            if agent_state.get("last_album"):
                focus_lines.append(f"- Last album in focus: {agent_state['last_album']}")
            followups = agent_state.get("last_followup_options") or []
            if followups:
                focus_lines.append(f"- Suggested follow-ups: {', '.join(str(item) for item in followups[:4])}")
            if focus_lines:
                sections.append("RECENT_AGENT_STATE:\n" + "\n".join(focus_lines))

        gallery_sections = self._build_gallery_sections(
            unlocked_gallery=unlocked_gallery,
            gallery_state=gallery_state,
            current_user_text=compact_user_text,
        )
        sections.extend(gallery_sections)
        progression_sections = self._build_progression_sections(progression_state=progression_state)
        sections.extend(progression_sections)
        preference_sections = self._build_nellie_preference_sections(nellie_preferences=nellie_preferences)
        sections.extend(preference_sections)

        persona_sections = self._build_persona_sections(
            memories=memories,
            style=style,
            relationship=relationship,
            conversation_modules=conversation_modules,
            mood_profile=mood_profile,
            current_user_text=compact_user_text,
            recalled=recalled,
        )
        sections.extend(persona_sections)

        if history_lines:
            sections.extend(
                self._build_active_thread_sections(
                    current_user_text=current_user_text,
                    recent_pairs=pairs,
                    speaker_name=speaker_name,
                )
            )
            sections.append("RECENT_CHAT:\n" + "\n\n".join(history_lines))

        return "\n\n".join(sections)

    def _persona_speaker_name(self, persona: dict) -> str:
        persona = persona or {}
        character = persona.get("character", {}) if isinstance(persona.get("character"), dict) else {}
        name = str(persona.get("name", "") or character.get("name", "") or "ASSISTANT").strip()
        name = re.sub(r"[^A-Za-z0-9 _'-]", "", name).strip()
        return name.upper() or "ASSISTANT"

    def _build_active_thread_sections(self, *, current_user_text: str, recent_pairs: list, speaker_name: str) -> list[str]:
        if not recent_pairs:
            return []

        user_text = re.sub(r"\s+", " ", (current_user_text or "").strip())
        if not user_text:
            return []

        last_user, last_ai, _last_mood = recent_pairs[-1]
        last_ai = re.sub(r"\s+", " ", (last_ai or "").strip())
        if not last_ai or "?" not in last_ai:
            return []

        compact = re.sub(r"[^a-z0-9\s]", " ", user_text.lower())
        compact = re.sub(r"\s+", " ", compact).strip()
        squashed = compact.replace(" ", "")
        word_count = len(compact.split())
        continuation_replies = {
            "yes",
            "yeah",
            "yep",
            "sure",
            "ok",
            "okay",
            "no",
            "nope",
            "maybe",
            "i dont know",
            "i do not know",
            "dont know",
            "no idea",
            "not sure",
            "go on",
            "continue",
            "why",
            "what",
            "really",
        }
        uncertainty_replies = {"idontknow", "idonotknow", "dontknow", "noidea", "notsure"}
        looks_like_continuation = compact in continuation_replies or squashed in uncertainty_replies or word_count <= 5
        if not looks_like_continuation:
            return []

        lines = [
            f"- Your previous message as {speaker_name} asked: {last_ai}",
            "- The user's current message is likely answering that previous question, not starting a new topic.",
            "- Continue the same thread first. Do not act confused or ask what is unclear unless the previous question itself was unclear.",
        ]
        if re.search(r"(?i)\bwhy did\b", last_ai) and (compact in {"i dont know", "i do not know", "dont know", "no idea", "not sure"} or squashed in uncertainty_replies):
            lines.append("- This looks like a joke setup; give the punchline now instead of asking another clarification question.")
        if last_user:
            previous_user_text = re.sub(r"\s+", " ", str(last_user)).strip()
            lines.append(f"- The turn before that was the user saying: {previous_user_text}")
        return ["ACTIVE_THREAD:\n" + "\n".join(lines)]

    def _build_nellie_preference_sections(self, nellie_preferences: dict) -> list[str]:
        items = (nellie_preferences or {}).get("items", {}) if isinstance(nellie_preferences, dict) else {}
        if not isinstance(items, dict) or not items:
            return []

        label_map = {
            "favorite_food": "favorite food",
            "favorite_drink": "favorite drink",
            "favorite_color": "favorite color",
            "favorite_music": "favorite music",
        }
        lines = []
        for key in ("favorite_food", "favorite_drink", "favorite_color", "favorite_music"):
            item = items.get(key)
            if not isinstance(item, dict):
                continue
            value = str(item.get("value", "") or "").strip()
            confidence = float(item.get("confidence", 0.0) or 0.0)
            if not value or confidence < 0.35:
                continue
            lines.append(f"- Nellie's {label_map.get(key, key)} seems to be {value} (confidence {confidence:.2f})")
        if not lines:
            return []
        return ["NELLIE_PREFERENCES:\n" + "\n".join(lines)]

    def get_turn_log(self, limit: int = 200) -> str:
        self._drain_pending_writes()
        with self._lock:
            rows = self.db.execute(
                "SELECT ts, user, ai, mood FROM turns ORDER BY id DESC LIMIT ?",
                (max(1, limit),),
            ).fetchall()

        rows.reverse()
        if not rows:
            return "No conversation history yet."

        lines = []
        for ts, user, ai, mood in rows:
            stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts or time.time()))
            lines.append(f"[{stamp}] USER")
            lines.append((user or "").strip())
            lines.append("")
            mood_suffix = f" | mood={mood}" if mood else ""
            lines.append(f"[{stamp}] NELLIE{mood_suffix}")
            lines.append((ai or "").strip())
            lines.append("")
            lines.append("-" * 48)
            lines.append("")
        return "\n".join(lines).strip()

    def get_recent_turns(self, limit: int = 6) -> list[dict[str, str]]:
        self._drain_pending_writes()
        with self._lock:
            rows = self.db.execute(
                "SELECT ts, user, ai, mood FROM turns ORDER BY id DESC LIMIT ?",
                (max(1, limit),),
            ).fetchall()

        rows.reverse()
        turns = []
        for ts, user, ai, mood in rows:
            turns.append(
                {
                    "ts": str(ts or ""),
                    "user": user or "",
                    "ai": ai or "",
                    "mood": mood or "",
                }
            )
        return turns

    def get_agent_state(self, key: str, default=None):
        self._drain_pending_writes()
        with self._lock:
            row = self.db.execute(
                "SELECT value FROM agent_state WHERE key = ?",
                (key,),
            ).fetchone()
        if not row:
            return default
        value = row[0]
        try:
            return json.loads(value)
        except Exception:
            return default if value is None else value

    def set_agent_state(self, key: str, value):
        payload = json.dumps(value, ensure_ascii=False)
        now = time.time()
        with self._lock:
            self.db.execute(
                """
                INSERT INTO agent_state (key, value, ts) VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, ts = excluded.ts
                """,
                (key, payload, now),
            )
            self.db.commit()

    def _extract_and_store_user_memories(self, user_text: str, ts: float):
        text = (user_text or "").strip()
        if not text:
            return

        compact = re.sub(r"\s+", " ", text)
        lowered = compact.lower()

        for category, kind, pattern in self.MEMORY_PATTERNS:
            match = re.search(pattern, compact, flags=re.IGNORECASE)
            if not match:
                continue

            memory = self._format_memory(category, match, lowered)
            if memory:
                self._upsert_memory(category, kind, memory, ts)
        self._extract_interest_hooks(lowered, ts)

    def _format_memory(self, category: str, match: re.Match, lowered_text: str) -> str | None:
        groups = [self._clean_fragment(group) for group in match.groups() if group]
        groups = [group for group in groups if group]
        if not groups:
            return None

        if category == "favorite" and len(groups) == 2:
            subject, value = groups
            return f"User's favorite {subject.lower()} is {value}."

        value = groups[0]
        if value.lower() in self.STOP_PHRASES:
            return None

        if category == "name":
            return f"User's name is {value}."
        if category == "location":
            return f"User lives in or is from {value}."
        if category == "work":
            if self._looks_like_identity_statement(value, lowered_text):
                return None
            return f"User works as {value}."
        if category == "study":
            return f"User studies {value}."
        if category == "likes":
            return f"User enjoys {value}."
        if category == "pet":
            article = "an" if value[:1].lower() in "aeiou" else "a"
            return f"User has {article} {value}."
        if category == "relationship":
            return f"User mentioned having a {value}."
        if category == "feeling":
            return f"User recently felt {value}."
        if category == "goal":
            return f"User wants to {value}."
        return None

    def _looks_like_identity_statement(self, value: str, lowered_text: str) -> bool:
        if not value:
            return True
        if lowered_text.startswith("i am ") or lowered_text.startswith("i'm "):
            first = value.split()[0].lower()
            return first in {
                "into",
                "happy",
                "sad",
                "tired",
                "fine",
                "okay",
                "ok",
                "good",
                "bad",
                "here",
                "ready",
                "bored",
            }
        return False

    def _upsert_memory(self, category: str, kind: str, memory: str, ts: float):
        with self._lock:
            existing = self.db.execute(
                "SELECT id, weight FROM user_memories WHERE memory = ?",
                (memory,),
            ).fetchone()
            bump = 0.5 if kind != "priority" else 0.75
            if existing:
                memory_id, weight = existing
                self.db.execute(
                    "UPDATE user_memories SET weight = ?, last_seen = ? WHERE id = ?",
                    (min(weight + bump, 6.0), ts, memory_id),
                )
                return

            base_weight = self.CATEGORY_WEIGHTS.get(category, 1.0)
            self.db.execute(
                "INSERT OR IGNORE INTO user_memories (ts, category, kind, memory, weight, last_seen) VALUES (?, ?, ?, ?, ?, ?)",
                (ts, category, kind, memory, base_weight, ts),
            )

    def _fetch_user_memories(self, kind: str | None = None, category: str | None = None, exclude_category: str | None = None, limit=8, recent_only_days: int | None = None):
        query = "SELECT memory FROM user_memories"
        clauses = []
        params = []

        if kind:
            clauses.append("kind = ?")
            params.append(kind)
        if category:
            clauses.append("category = ?")
            params.append(category)
        if exclude_category:
            clauses.append("category != ?")
            params.append(exclude_category)
        if recent_only_days is not None:
            cutoff = time.time() - (recent_only_days * 86400)
            clauses.append("last_seen >= ?")
            params.append(cutoff)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY weight DESC, last_seen DESC, id DESC LIMIT ?"
        params.append(limit)

        with self._lock:
            cur = self.db.execute(query, tuple(params))
            return [row[0] for row in cur.fetchall()]

    def _fetch_relevant_memories(self, current_user_text: str, limit=4):
        text = self._compact_text(current_user_text)
        tokens = {token for token in text.split() if len(token) >= 4}
        if not tokens:
            return []

        with self._lock:
            rows = self.db.execute(
                "SELECT memory, weight, kind, last_seen FROM user_memories ORDER BY weight DESC, last_seen DESC"
            ).fetchall()

        ranked = []
        for memory, weight, kind, last_seen in rows:
            memory_text = re.sub(r"[^a-z0-9\s]", " ", memory.lower())
            matches = sum(1 for token in tokens if token in memory_text)
            if not matches:
                continue
            score = matches * 2.0 + float(weight)
            if kind == "priority":
                score += 1.0
            if kind == "transient":
                score -= 0.5
            ranked.append((score, memory))

        ranked.sort(key=lambda item: item[0], reverse=True)
        seen = []
        for _, memory in ranked:
            if memory not in seen:
                seen.append(memory)
            if len(seen) >= limit:
                break
        return seen

    def _clean_fragment(self, value: str) -> str:
        value = re.sub(r"\s+", " ", (value or "").strip())
        value = re.sub(r"[.?!,;:]+$", "", value)
        return value.strip(" '\"")

    def _persona_interest_topics(self, persona: dict) -> list[dict]:
        interests = [str(item).strip() for item in list(persona.get("interests", []) or []) if str(item).strip()]
        preferences = persona.get("preferences", {}) or {}
        interests.extend(
            str(item).strip()
            for item in list(preferences.get("favorite_topics", []) or [])
            if str(item).strip()
        )
        topics = []
        seen = set()
        for label in interests:
            lowered = label.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            tokens = [token for token in re.findall(r"[a-z0-9]+", lowered) if len(token) >= 4][:4]
            if not tokens:
                continue
            topics.append({"label": label, "tokens": tokens})
        return topics

    def _extract_interest_hooks(self, lowered_text: str, ts: float):
        topics = self.get_agent_state("persona_interest_topics", default=[]) or []
        padded = f" {lowered_text or ''} "
        for topic in topics:
            if not isinstance(topic, dict):
                continue
            label = str(topic.get("label", "") or "").strip()
            tokens = [str(token).strip().lower() for token in list(topic.get("tokens", []) or []) if str(token).strip()]
            if not label or not tokens:
                continue
            if not any(f" {token} " in padded for token in tokens):
                continue
            self._upsert_memory("interest_hook", "priority", f"User engaged Nellie on a topic she likes: {label}.", ts)

    def _build_persona_sections(
        self,
        *,
        memories: dict,
        style: dict,
        relationship: dict,
        conversation_modules: dict,
        mood_profile: dict,
        current_user_text: str,
        recalled: list[str],
    ) -> list[str]:
        sections = []
        cue_score = len(recalled) + len(current_user_text.split())

        if semantic := memories.get("semantic", []):
            sections.append(
                "PERSONA_MEMORY:\n"
                + "\n".join(f"- {item}" for item in semantic[: self.PERSONA_SECTION_LIMITS["semantic"]])
            )

        if cue_score >= 3 and (episodic := memories.get("episodic", [])):
            sections.append(
                "PERSONA_ANECDOTES:\n"
                + "\n".join(f"- {item}" for item in episodic[: self.PERSONA_SECTION_LIMITS["episodic"]])
            )

        if cue_score >= 5 and (extra_anecdotes := memories.get("anecdotes", [])):
            sections.append(
                "CONVERSATION_HOOKS:\n"
                + "\n".join(f"- {item}" for item in extra_anecdotes[: self.PERSONA_SECTION_LIMITS["anecdotes"]])
            )

        if goals := relationship.get("goals", []):
            sections.append(
                "RELATIONSHIP_GOALS:\n"
                + "\n".join(f"- {item}" for item in goals[: self.PERSONA_SECTION_LIMITS["goals"]])
            )

        if cue_score >= 3 and (speech_habits := style.get("speech_habits", [])):
            sections.append(
                "VOICE_GUIDE:\n"
                + "\n".join(f"- {item}" for item in speech_habits[: self.PERSONA_SECTION_LIMITS["speech_habits"]])
            )

        if cue_score >= 6 and (continuity_rules := conversation_modules.get("continuity_rules", [])):
            sections.append(
                "CONTINUITY_RULES:\n"
                + "\n".join(
                    f"- {item}" for item in continuity_rules[: self.PERSONA_SECTION_LIMITS["continuity_rules"]]
                )
            )

        curiosity_rules = list(conversation_modules.get("curiosity", []) or [])
        if not curiosity_rules:
            curiosity_rules = [
                "Be genuinely curious about the user and notice one specific detail worth following up on.",
                "Store user details that reveal preferences, goals, emotional state, routines, or recurring interests.",
                "When the user touches a topic Nellie enjoys, remember it and let that continuity shape later replies.",
            ]
        if cue_score >= 2:
            sections.append(
                "CURIOSITY_GUIDE:\n"
                + "\n".join(
                    f"- {item}" for item in curiosity_rules[: self.PERSONA_SECTION_LIMITS["curiosity"]]
                )
            )

        mood_guidance = mood_profile.get("guidance", {})
        if cue_score >= 4 and mood_guidance:
            guidance_items = list(mood_guidance.items())[: self.PERSONA_SECTION_LIMITS["mood_guidance"]]
            sections.append("MOOD_GUIDE:\n" + "\n".join(f"- {mood}: {desc}" for mood, desc in guidance_items))

        return sections

    def _build_gallery_sections(
        self,
        *,
        unlocked_gallery,
        gallery_state: dict,
        current_user_text: str,
    ) -> list[str]:
        sections = []
        unlocked_gallery = [item for item in (unlocked_gallery or []) if isinstance(item, dict)]
        if not unlocked_gallery and not gallery_state:
            return sections

        compact = current_user_text or ""
        gallery_query = any(
            token in compact
            for token in [
                "gallery",
                "image",
                "images",
                "picture",
                "pictures",
                "photo",
                "photos",
                "selfie",
                "unlock",
                "unlocked",
                "bild",
                "bilder",
                "foto",
                "galleri",
                "låst",
                "last upp",
                "låst upp",
            ]
        )

        if gallery_state:
            last_title = str(gallery_state.get("last_title", "") or "").strip()
            last_reason_text = str(gallery_state.get("last_reason_text", "") or "").strip()
            last_reason = str(gallery_state.get("last_reason", "") or "").strip()
            last_lines = []
            if last_title:
                last_lines.append(f"- Last gallery image sent: {last_title}.")
            if last_reason_text:
                last_lines.append(f"- Why it was sent: {last_reason_text}")
            elif last_reason:
                last_lines.append(f"- Trigger source: {last_reason}.")
            if last_lines:
                sections.append("RECENT_GALLERY_STATE:\n" + "\n".join(last_lines))

        if unlocked_gallery:
            unlocked_sorted = sorted(
                unlocked_gallery,
                key=lambda item: float(item.get("unlocked_at", 0.0) or 0.0),
                reverse=True,
            )
            overview = [f"- Nellie currently knows {len(unlocked_sorted)} gallery images are unlocked for the user."]
            sections.append("GALLERY_AWARENESS:\n" + "\n".join(overview))

            if gallery_query:
                detail_lines = []
                for item in unlocked_sorted[:8]:
                    title = str(item.get("title", "") or item.get("filename", "") or "Image").strip()
                    rarity = str(item.get("rarity", "common") or "common").strip()
                    caption = str(item.get("caption", "") or "").strip()
                    reason_text = str(item.get("reason_text", "") or "").strip()
                    tone = str(item.get("tone", "") or "").strip()
                    visibility = str(item.get("visibility", "") or "").strip()
                    line = f"- {title} [{rarity}]"
                    if tone:
                        line += f" tone={tone}"
                    if visibility:
                        line += f" visibility={visibility}"
                    if caption:
                        line += f": {caption}"
                    if reason_text:
                        line += f" Reason: {reason_text}"
                    detail_lines.append(line)
                if detail_lines:
                    sections.append("UNLOCKED_GALLERY_DETAILS:\n" + "\n".join(detail_lines))

        progression_state = self.get_agent_state("progression_state", default={}) or {}
        current_level = int(progression_state.get("level", 1) or 1)
        upcoming_lines = []
        catalog_preview = self.get_agent_state("gallery_locked_preview", default=[]) or []
        if gallery_query and isinstance(catalog_preview, list):
            for item in catalog_preview[:5]:
                if not isinstance(item, dict):
                    continue
                title = str(item.get("title", "") or item.get("filename", "") or "Image").strip()
                level_min = int(item.get("level_min", 1) or 1)
                tone = str(item.get("tone", "") or "").strip()
                visibility = str(item.get("visibility", "") or "").strip()
                if level_min <= current_level:
                    continue
                line = f"- {title} stays locked until about level {level_min}."
                if visibility:
                    line += f" It reads as {visibility}"
                if tone:
                    line += f" and {tone}"
                line += "."
                upcoming_lines.append(line)
        if upcoming_lines:
            sections.append("LOCKED_GALLERY_PREVIEW:\n" + "\n".join(upcoming_lines))

        return sections

    def _build_progression_sections(self, *, progression_state: dict) -> list[str]:
        if not progression_state:
            return []
        xp = int(progression_state.get("xp", 0) or 0)
        level = int(progression_state.get("level", 1) or 1)
        unlocked_tools = list(progression_state.get("unlocked_tools", []) or [])
        next_tool = progression_state.get("next_tool_unlock") or {}
        stage = "Anonymous"
        if level >= 80:
            stage = "Magnetic"
        elif level >= 54:
            stage = "Close"
        elif level >= 32:
            stage = "Flirted"
        elif level >= 16:
            stage = "Warm"
        elif level >= 6:
            stage = "Curious"

        stage_guidance = {
            "Anonymous": "Nellie should stay somewhat private, observant, and more suggestive than direct.",
            "Curious": "Nellie can show clearer interest and continuity, but remains restrained and a bit careful.",
            "Warm": "Nellie can sound more familiar, attentive, and quietly affectionate.",
            "Flirted": "Nellie can become noticeably more charming and softly flirtatious, still mostly in subtext.",
            "Close": "Nellie can speak like a trusted romantic companion with stronger continuity and warmth.",
            "Magnetic": "Nellie can be highly intimate in tone, playful, and confidently partner-like while staying within her boundaries.",
        }

        return [
            "RELATIONSHIP_PROGRESSION:\n"
            + "\n".join(
                [
                    f"- User XP: {xp}.",
                    f"- User level: {level}.",
                    f"- Relationship stage: {stage}.",
                    f"- Guidance: {stage_guidance.get(stage, stage_guidance['Anonymous'])}",
                    *([f"- Unlocked agent functions: {', '.join(str(item) for item in unlocked_tools[:6])}."] if unlocked_tools else []),
                    *([f"- Next agent unlock: {next_tool.get('label')} at level {int(next_tool.get('level', 1) or 1)}."] if isinstance(next_tool, dict) and next_tool.get("label") else []),
                ]
            )
        ]

    def _compact_text(self, text: str) -> str:
        return re.sub(r"[^a-z0-9\s]", " ", (text or "").lower())

    def _drain_pending_writes(self):
        while True:
            try:
                job = self._write_queue.get_nowait()
            except Empty:
                break
            try:
                self._process_write_job(job)
            finally:
                self._write_queue.task_done()

    def _writer_loop(self):
        while True:
            job = self._write_queue.get()
            try:
                if not self._process_write_job(job):
                    return
            finally:
                self._write_queue.task_done()

    def _process_write_job(self, job) -> bool:
        action = job[0]
        if action == "shutdown":
            return False
        if action != "save_turn":
            return True

        _, user, ai, mood = job
        now = time.time()
        with self._lock:
            self.db.execute(
                "INSERT INTO turns (ts, user, ai, mood) VALUES (?, ?, ?, ?)",
                (now, user, ai, mood),
            )
            self._extract_and_store_user_memories(user, now)
            self.db.commit()
        return True
