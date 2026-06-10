import sqlite3
import time
import re
from pathlib import Path
from threading import local
from typing import Any

from services.emotion.state import EmotionState

SCHEMA = """
CREATE TABLE IF NOT EXISTS turns (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL,
  user TEXT,
  ai TEXT,
  mood TEXT
);

CREATE TABLE IF NOT EXISTS app_state (
  key TEXT PRIMARY KEY,
  value TEXT
);

CREATE TABLE IF NOT EXISTS user_memory (
  key TEXT PRIMARY KEY,
  value TEXT,
  ts REAL
);

CREATE TABLE IF NOT EXISTS progression_state (
  key TEXT PRIMARY KEY,
  value TEXT
);

CREATE INDEX IF NOT EXISTS idx_turns_id_desc ON turns(id DESC);
CREATE INDEX IF NOT EXISTS idx_user_memory_ts_desc ON user_memory(ts DESC);
"""


class MemoryStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._thread_state = local()
        self.db.executescript(SCHEMA)
        self._backfill_preference_memory()
        self.db.commit()

    @property
    def db(self) -> sqlite3.Connection:
        connection = getattr(self._thread_state, "connection", None)
        if connection is None:
            connection = sqlite3.connect(self.db_path, timeout=15.0)
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            connection.execute("PRAGMA busy_timeout=15000")
            self._thread_state.connection = connection
        return connection

    def close(self) -> None:
        connection = getattr(self._thread_state, "connection", None)
        if connection is None:
            return
        connection.close()
        del self._thread_state.connection

    def save_app_state(self, key: str, value: str):
        self.db.execute(
            "INSERT INTO app_state(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )
        self.db.commit()

    def load_app_state(self, key: str, default: str | None = None):
        row = self.db.execute(
            "SELECT value FROM app_state WHERE key = ?",
            (key,),
        ).fetchone()
        if not row:
            return default
        return row[0]

    def save_turn(self, user: str, ai: str, mood: str | None = None, persona: dict[str, Any] | None = None):
        self.db.execute(
            "INSERT INTO turns (ts, user, ai, mood) VALUES (?, ?, ?, ?)",
            (time.time(), user, ai, mood),
        )
        facts = self.capture_user_facts(user)
        self._award_progression_for_turn(user=user, ai=ai, new_fact_count=len(facts), persona=persona)
        self.db.commit()

    def capture_user_facts(self, text: str) -> list[tuple[str, str]]:
        facts = self._extract_user_facts(text)
        for key, value in facts:
            self._save_user_fact(key, value)
        return facts

    def _backfill_preference_memory(self) -> None:
        marker = self.db.execute(
            "SELECT value FROM app_state WHERE key = ?",
            ("preference_memory_backfill_v2",),
        ).fetchone()
        if marker:
            return
        rows = self.db.execute(
            "SELECT user FROM turns ORDER BY id DESC LIMIT 200"
        ).fetchall()
        for (user_text,) in rows:
            for key, value in self._extract_user_facts(str(user_text or "")):
                self._save_user_fact(key, value)
        self.db.execute(
            "INSERT INTO app_state(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            ("preference_memory_backfill_v2", "1"),
        )

    def _save_user_fact(self, key: str, value: str) -> None:
        value = str(value or "").strip()
        if not value:
            return
        self.db.execute(
            "INSERT INTO user_memory(key, value, ts) VALUES(?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, ts=excluded.ts",
            (key, value[:240], time.time()),
        )

    def _save_progression_value(self, key: str, value: str) -> None:
        self.db.execute(
            "INSERT INTO progression_state(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value)),
        )

    def _load_progression_value(self, key: str, default: str) -> str:
        row = self.db.execute(
            "SELECT value FROM progression_state WHERE key = ?",
            (key,),
        ).fetchone()
        if not row:
            return default
        return str(row[0])

    def _load_progression_xp(self) -> int:
        try:
            return max(0, int(self._load_progression_value("bond_xp", "0")))
        except Exception:
            return 0

    def _save_progression_xp(self, xp: int) -> None:
        self._save_progression_value("bond_xp", str(max(0, int(xp))))

    def _xp_for_level(self, level: int) -> int:
        if level <= 1:
            return 0
        step = level - 1
        return int((14 * (step ** 1.42)) + (step * 10))

    def _level_from_xp(self, xp: int, level_cap: int = 255) -> int:
        clamped_xp = max(0, int(xp))
        level = 1
        while level < max(1, int(level_cap)) and clamped_xp >= self._xp_for_level(level + 1):
            level += 1
        return level

    def _count_user_facts(self) -> int:
        row = self.db.execute("SELECT COUNT(*) FROM user_memory").fetchone()
        return int(row[0]) if row else 0

    def _count_turns(self) -> int:
        row = self.db.execute("SELECT COUNT(*) FROM turns").fetchone()
        return int(row[0]) if row else 0

    def _user_interest_score(self, user_text: str) -> int:
        lowered = str(user_text or "").casefold()
        cues = [
            "what do you like",
            "what music do you like",
            "what are you into",
            "tell me about yourself",
            "what kind of",
            "what do you want",
            "what are your",
            "how are you",
            "do you like",
            "who are you",
            "what's your",
            "whats your",
        ]
        return sum(1 for cue in cues if cue in lowered)

    def _trigger_bonus(self, user_text: str, persona: dict[str, Any] | None = None) -> tuple[int, list[str]]:
        progression_conf = (persona or {}).get("progression", {}) if isinstance((persona or {}).get("progression", {}), dict) else {}
        xp_rules = progression_conf.get("xp_rules", {}) if isinstance(progression_conf.get("xp_rules", {}), dict) else {}
        custom_interest = [str(v).casefold() for v in xp_rules.get("interest_triggers", []) if str(v).strip()]
        custom_relationship = [str(v).casefold() for v in xp_rules.get("relationship_triggers", []) if str(v).strip()]
        custom_knowledge = [str(v).casefold() for v in xp_rules.get("knowledge_triggers", []) if str(v).strip()]
        lowered = str(user_text or "").casefold()
        bonus = 0
        reasons: list[str] = []

        interest_triggers = custom_interest or [
            "metal", "punk", "gaming", "games", "rpg", "roleplaying", "fantasy", "science fiction", "lore",
        ]
        relationship_triggers = custom_relationship or [
            "my name is", "remember that", "my favorite", "i like", "what do you like", "tell me about yourself",
        ]
        knowledge_triggers = custom_knowledge or [
            "why", "how", "explain", "what do you think", "what kind of", "tell me more",
        ]

        if any(trigger in lowered for trigger in interest_triggers):
            bonus += 3
            reasons.append("shared vibe")
        if any(trigger in lowered for trigger in relationship_triggers):
            bonus += 3
            reasons.append("bonding")
        if any(trigger in lowered for trigger in knowledge_triggers):
            bonus += 2
            reasons.append("curiosity")
        if re.search(r"[!?]{2,}|:\)|=\)|<3|haha|lol|hehe|heh", lowered):
            bonus += 2
            reasons.append("playful spark")
        return bonus, reasons

    def _award_progression_for_turn(
        self,
        user: str,
        ai: str,
        new_fact_count: int = 0,
        persona: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        user_text = str(user or "")
        ai_text = str(ai or "")
        xp_gain = 3
        reasons: list[str] = ["turn"]
        if len(user_text.strip()) >= 24:
            xp_gain += 1
            reasons.append("deeper message")
        if len(user_text.strip()) >= 80:
            xp_gain += 1
            reasons.append("longer share")
        if len(ai_text.strip()) >= 80:
            xp_gain += 1
        curiosity_bonus = min(4, self._user_interest_score(user_text) * 2)
        if curiosity_bonus:
            xp_gain += curiosity_bonus
            reasons.append("interest in Nellie")
        fact_bonus = max(0, int(new_fact_count)) * 6
        if fact_bonus:
            xp_gain += fact_bonus
            reasons.append("new memory")
        trigger_bonus, trigger_reasons = self._trigger_bonus(user_text, persona=persona)
        if trigger_bonus:
            xp_gain += trigger_bonus
            reasons.extend(trigger_reasons)
        current_xp = self._load_progression_xp()
        new_xp = current_xp + xp_gain
        self._save_progression_xp(new_xp)
        self._save_progression_value("last_xp_gain", str(xp_gain))
        self._save_progression_value("last_xp_reason", ", ".join(dict.fromkeys(reasons)))
        self._save_progression_value("last_xp_ts", str(time.time()))
        return {"xp_gain": xp_gain, "xp_total": new_xp, "reasons": reasons}

    def get_progression(self, persona: dict[str, Any] | None = None) -> dict[str, Any]:
        progression_conf = (persona or {}).get("progression", {})
        level_cap = max(1, int(progression_conf.get("level_cap", 255) or 255))
        xp = self._load_progression_xp()
        level = self._level_from_xp(xp, level_cap=level_cap)
        level_start_xp = self._xp_for_level(level)
        next_level = min(level_cap, level + 1)
        next_level_xp = self._xp_for_level(next_level) if level < level_cap else level_start_xp
        span = max(1, next_level_xp - level_start_xp)
        progress_in_level = max(0, xp - level_start_xp)
        progress_percent = 100 if level >= level_cap else int((progress_in_level / span) * 100)
        unlocks = progression_conf.get("unlocks", []) if isinstance(progression_conf.get("unlocks", []), list) else []
        unlocked = [entry for entry in unlocks if int(entry.get("level", 9999) or 9999) <= level]
        next_unlock = next(
            (
                entry for entry in unlocks
                if int(entry.get("level", 9999) or 9999) > level
            ),
            None,
        )
        familiarity = min(1.0, self._count_user_facts() / 18.0)
        shared_history = min(1.0, self._count_turns() / 120.0)
        bond_factor = round((familiarity * 0.55) + (shared_history * 0.45), 3)
        last_gain = 0
        try:
            last_gain = max(0, int(self._load_progression_value("last_xp_gain", "0")))
        except Exception:
            last_gain = 0
        last_reason = self._load_progression_value("last_xp_reason", "")
        try:
            last_ts = float(self._load_progression_value("last_xp_ts", "0"))
        except Exception:
            last_ts = 0.0
        return {
            "xp": xp,
            "level": level,
            "level_cap": level_cap,
            "progress_percent": progress_percent,
            "level_start_xp": level_start_xp,
            "next_level_xp": next_level_xp,
            "xp_into_level": progress_in_level,
            "xp_to_next": max(0, next_level_xp - xp),
            "familiarity": familiarity,
            "shared_history": shared_history,
            "bond_factor": bond_factor,
            "last_gain": last_gain,
            "last_reason": last_reason,
            "last_gain_ts": last_ts,
            "last_gain_recent": (time.time() - last_ts) <= 18.0 if last_ts else False,
            "unlocked_keys": [str(entry.get("key", "")) for entry in unlocked if str(entry.get("key", "")).strip()],
            "next_unlock": next_unlock if isinstance(next_unlock, dict) else None,
        }

    def _extract_user_facts(self, user_text: str) -> list[tuple[str, str]]:
        text = (user_text or "").strip()
        lowered = text.lower()
        facts: list[tuple[str, str]] = []

        name_match = re.search(r"\bmy name is ([A-Za-z][A-Za-z '-]{1,40})", text, flags=re.IGNORECASE)
        if name_match:
            facts.append(("user_name", name_match.group(1).strip()))
        else:
            alt_name_match = re.search(
                r"\b(?:remember me(?: now)?(?: by)?(?: my)? name|call me)\s*,?\s*([A-Za-z][A-Za-z '-]{1,40})",
                text,
                flags=re.IGNORECASE,
            )
            if alt_name_match:
                facts.append(("user_name", alt_name_match.group(1).strip()))

        likes_match = re.search(r"\bi like ([^.!?]{3,120})", text, flags=re.IGNORECASE)
        if likes_match:
            value = likes_match.group(1).strip(" .!?,")
            facts.append((self._memory_key("likes", value), value))

        swedish_likes = re.search(r"\bjag (?:gillar|tycker om|älskar) ([^.!?]{3,120})", text, flags=re.IGNORECASE)
        if swedish_likes:
            value = swedish_likes.group(1).strip(" .!?,")
            facts.append((self._memory_key("likes", value), value))

        dislikes_match = re.search(
            r"\b(?:i (?:do not|don't) like|i dislike|i hate|jag (?:gillar inte|ogillar|hatar)) ([^.!?]{3,120})",
            text,
            flags=re.IGNORECASE,
        )
        if dislikes_match:
            value = dislikes_match.group(1).strip(" .!?,")
            facts.append((self._memory_key("dislikes", value), value))

        favorite_match = re.search(
            r"\bmy favorite ([a-zA-Z _-]{2,40}) is ([^.!?]{2,120})",
            text,
            flags=re.IGNORECASE,
        )
        if favorite_match:
            category = favorite_match.group(1).strip().lower().replace(" ", "_")
            facts.append((f"favorite_{category}", favorite_match.group(2).strip(" .!?,")))

        swedish_favorite = re.search(
            r"\bmin favorit(?:\s+([A-Za-zÅÄÖåäö _-]{2,40}))? är ([^.!?]{2,120})",
            text,
            flags=re.IGNORECASE,
        )
        if swedish_favorite:
            category = (swedish_favorite.group(1) or "sak").strip().casefold().replace(" ", "_")
            facts.append((f"favorite_{category}", swedish_favorite.group(2).strip(" .!?,")))

        prefers_match = re.search(r"\bi(?:'m| am)? more of a ([^.!?]{3,80})", text, flags=re.IGNORECASE)
        if prefers_match:
            value = prefers_match.group(1).strip(" .!?,")
            facts.append((self._memory_key("preference", value), value))

        preference_match = re.search(
            r"\b(?:i prefer|i would rather|i'd rather|jag föredrar|jag vill hellre) ([^.!?]{3,140})",
            text,
            flags=re.IGNORECASE,
        )
        if preference_match:
            value = preference_match.group(1).strip(" .!?,")
            facts.append((self._memory_key("preference", value), value))

        music_match = re.search(
            r"\b(i like bands like|i like artists like|i listen to|i'm into|im into) ([^.!?]{3,140})",
            lowered,
            flags=re.IGNORECASE,
        )
        if music_match:
            value = music_match.group(2).strip(" .!?,")
            facts.append((self._memory_key("music", value), value))

        swedish_music = re.search(
            r"\b(?:jag lyssnar på|jag är inne på) ([^.!?]{3,140})",
            lowered,
            flags=re.IGNORECASE,
        )
        if swedish_music:
            value = swedish_music.group(1).strip(" .!?,")
            facts.append((self._memory_key("music", value), value))

        work_match = re.search(r"\bi work (?:as|with|in) ([^.!?]{3,120})", text, flags=re.IGNORECASE)
        if work_match:
            facts.append(("user_work", work_match.group(1).strip(" .!?,")))

        place_match = re.search(r"\bi live in ([^.!?]{2,120})", text, flags=re.IGNORECASE)
        if place_match:
            facts.append(("user_location", place_match.group(1).strip(" .!?,")))

        from_match = re.search(r"\bi(?:'m| am)? from ([^.!?]{2,120})", text, flags=re.IGNORECASE)
        if from_match:
            facts.append(("user_origin", from_match.group(1).strip(" .!?,")))

        hobby_match = re.search(
            r"\bmy hobbies are ([^.!?]{3,140})",
            text,
            flags=re.IGNORECASE,
        )
        if hobby_match:
            facts.append(("user_hobbies", hobby_match.group(1).strip(" .!?,")))

        habit_match = re.search(
            r"\b(?:i usually|i normally|i tend to|jag brukar|jag tenderar att) ([^.!?]{3,140})",
            text,
            flags=re.IGNORECASE,
        )
        if habit_match:
            value = habit_match.group(1).strip(" .!?,")
            facts.append((self._memory_key("habit", value), value))

        plan_match = re.search(
            r"\b(?:i(?:'m| am|m) (?:soon |going to |planning to )|jag ska snart |jag planerar att )([^.!?]{3,140})",
            text,
            flags=re.IGNORECASE,
        )
        if plan_match:
            value = plan_match.group(1).strip(" .!?,")
            facts.append((self._memory_key("plan", value), value))

        into_match = re.search(
            r"\bi(?:'m| am)? really into ([^.!?]{3,140})",
            text,
            flags=re.IGNORECASE,
        )
        if into_match:
            facts.append(("user_interest_focus", into_match.group(1).strip(" .!?,")))

        if re.search(r"\bi(?:'m| am) your (administrator|admin)\b", lowered, flags=re.IGNORECASE):
            facts.append(("user_role", "administrator"))
        else:
            role_match = re.search(r"\bmy role is ([^.!?]{2,80})", text, flags=re.IGNORECASE)
            if role_match:
                facts.append(("user_role", role_match.group(1).strip(" .!?,")))

        return list(dict.fromkeys(facts))

    def _memory_key(self, prefix: str, value: str) -> str:
        slug = re.sub(r"[^a-z0-9åäö]+", "_", value.casefold()).strip("_")[:48] or "detail"
        return f"{prefix}_{slug}"

    def load_user_facts(self, limit: int = 8) -> list[tuple[str, str]]:
        rows = self.db.execute(
            "SELECT key, value FROM user_memory ORDER BY ts DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [(str(key), str(value)) for key, value in rows]

    def add_user_memory_note(self, note: str) -> str:
        cleaned = re.sub(r"\s+", " ", str(note or "")).strip(" .!?")
        if not cleaned:
            return ""
        slug = re.sub(r"[^a-z0-9]+", "_", cleaned.casefold()).strip("_")[:40] or "note"
        key = f"remembered_{slug}"
        self._save_user_fact(key, cleaned)
        self._award_progression_for_turn(user=cleaned, ai="", new_fact_count=1)
        self.db.commit()
        return cleaned

    def forget_user_memory(self, query: str) -> int:
        cleaned = re.sub(r"\s+", " ", str(query or "")).strip(" .!?").casefold()
        if not cleaned:
            return 0
        rows = self.db.execute("SELECT key, value FROM user_memory").fetchall()
        matches = [(key, value) for key, value in rows if cleaned in str(value).casefold() or cleaned in str(key).casefold()]
        for key, _ in matches:
            self.db.execute("DELETE FROM user_memory WHERE key = ?", (key,))
        if matches:
            self.db.commit()
        return len(matches)

    def summarize_user_memory(self, limit: int = 8) -> list[str]:
        facts = self.load_user_facts(limit=limit)
        labels = {
            "user_name": "Your name",
            "user_work": "You work with",
            "user_location": "You live in",
            "user_origin": "You are from",
            "user_hobbies": "Your hobbies",
            "user_interest_focus": "You are really into",
            "user_role": "Your role",
        }
        lines: list[str] = []
        for key, value in reversed(facts):
            if key.startswith("favorite_"):
                category = key.removeprefix("favorite_").replace("_", " ")
                label = f"Your favorite {category}"
            elif key.startswith("likes_"):
                label = "You like"
            elif key.startswith("dislikes_"):
                label = "You dislike"
            elif key.startswith("preference_"):
                label = "You prefer"
            elif key.startswith("music_"):
                label = "Your music taste includes"
            elif key.startswith("habit_"):
                label = "You usually"
            elif key.startswith("plan_"):
                label = "You plan to"
            else:
                label = labels.get(key, key.replace("_", " "))
            lines.append(f"{label}: {value}")
        return lines

    def get_user_fact(self, key: str) -> str | None:
        row = self.db.execute(
            "SELECT value FROM user_memory WHERE key = ?",
            (key,),
        ).fetchone()
        if not row:
            return None
        value = str(row[0] or "").strip()
        return value or None

    def latest_turn(self) -> tuple[str, str, str] | None:
        row = self.db.execute(
            "SELECT user, ai, mood FROM turns ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        user, ai, mood = row
        return str(user or ""), str(ai or ""), str(mood or "")

    def build_context(
        self,
        persona: dict[str, Any] | None,
        k: int = 4,
        max_chars: int = 1200,
        per_turn_chars: int = 280,
    ) -> str:
        cur = self.db.execute("SELECT user, ai FROM turns ORDER BY id DESC LIMIT ?", (k,))
        newest_first = cur.fetchall()
        turn_blocks: list[str] = []
        for user, ai in newest_first:
            user_text = (user or "").strip().replace("\n", " ")
            ai_text = (ai or "").strip().replace("\n", " ")
            if per_turn_chars > 0:
                user_text = user_text[:per_turn_chars]
                ai_text = ai_text[:per_turn_chars]
            turn_blocks.append(f"USER: {user_text}\nNELLIE: {ai_text}")

        blocks: list[str] = []
        user_facts = self.load_user_facts(limit=12)
        if user_facts:
            user_lines = [
                f"- {self._memory_label(key)}: {value}"
                for key, value in reversed(user_facts)
            ]
            fact_block = "STABLE USER DETAILS:\n" + "\n".join(user_lines)
            blocks.append(fact_block[:360])
        progression = self.get_progression(persona)
        blocks.append(
            f"RELATIONSHIP: level {progression['level']}, bond {progression['bond_factor']}."
        )

        prefix = "\n\n".join(blocks)
        remaining = max_chars - len(prefix) - 24 if max_chars > 0 else 10**9
        selected_turns: list[str] = []
        for block in turn_blocks:
            cost = len(block) + (2 if selected_turns else 0)
            if selected_turns and cost > remaining:
                break
            if not selected_turns and cost > remaining:
                selected_turns.append(block[-max(0, remaining):])
                break
            selected_turns.append(block)
            remaining -= cost
        selected_turns.reverse()
        if selected_turns:
            blocks.append("RECENT CONVERSATION:\n" + "\n\n".join(selected_turns))
        return "\n\n".join(blocks)

    def _memory_label(self, key: str) -> str:
        if key.startswith("likes_"):
            return "likes"
        if key.startswith("dislikes_"):
            return "dislikes"
        if key.startswith("preference_"):
            return "prefers"
        if key.startswith("music_"):
            return "music taste"
        if key.startswith("habit_"):
            return "habit"
        if key.startswith("plan_"):
            return "upcoming plan"
        if key.startswith("favorite_"):
            return key.removeprefix("favorite_").replace("_", " ") + " favorite"
        return key.replace("_", " ")

    def save_emotion_state(self, state: EmotionState):
        payload = f"{state.valence}|{state.energy}|{state.attachment}|{state.mood}"
        self.save_app_state("emotion_state", payload)

    def load_emotion_state(self) -> EmotionState:
        payload = self.load_app_state("emotion_state")
        if not payload:
            return EmotionState()
        try:
            valence, energy, attachment, mood = payload.split("|", 3)
            return EmotionState(
                valence=int(valence),
                energy=int(energy),
                attachment=int(attachment),
                mood=mood or "neutral",
            )
        except Exception:
            return EmotionState()

    def clear_conversation(self):
        self.db.execute("DELETE FROM turns")
        self.db.execute("DELETE FROM user_memory")
        self.db.execute("DELETE FROM progression_state")
        self.db.execute("DELETE FROM app_state WHERE key = ?", ("emotion_state",))
        self.db.commit()
