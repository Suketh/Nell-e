from dataclasses import dataclass
import json
from pathlib import Path
import random
import re
import time
from typing import Callable

from services.agent_service import AgentService
from services.feature_access import (
    build_feature_access_state,
    get_enabled_feature_items,
    get_next_feature_unlock,
    get_unlocked_feature_items,
    resolve_feature,
)
from services.tool_registry import ToolRegistry


@dataclass
class ConversationResult:
    reply: str
    mood: str
    context: str
    spoken_reply: str | None = None
    mode: str = "direct_reply"
    tool_events: list[dict] | None = None
    agent_trace: list[dict] | None = None
    gallery_image_path: str | None = None
    gallery_image_caption: str | None = None
    new_unlock: dict | None = None


class ConversationService:
    """Owns the conversation loop so UI code stays thin.

    This is the natural seam for a future backend or agent runner:
    UI -> conversation service -> model/memory/tools.
    """

    IMAGE_COOLDOWN_SECONDS = 12 * 60
    XP_DECAY_WINDOW_SECONDS = 18 * 60 * 60
    MAX_LEVEL = 255
    RELATIONSHIP_STAGES = [
        (1, "Anonymous"),
        (6, "Curious"),
        (16, "Warm"),
        (32, "Flirted"),
        (54, "Close"),
        (80, "Magnetic"),
    ]
    TOOL_UNLOCK_LEVELS = [
        (1, "core chat"),
        (8, "timers and date sense"),
        (14, "calculator"),
        (22, "Wikipedia lookups"),
        (32, "image understanding"),
        (42, "web search"),
        (50, "web page reading"),
        (58, "PDF reading"),
        (64, "browser actions"),
    ]
    RARITY_PRIORITY = {
        "common": 0,
        "rare": 1,
        "epic": 2,
    }
    VISIBILITY_LEVELS = {
        "private": 1,
        "playful": 10,
        "intimate": 28,
        "extreme": 71,
    }
    STAGE_TONE_PREFERENCES = {
        "Anonymous": {"soft", "warm"},
        "Curious": {"soft", "warm", "romantic"},
        "Warm": {"warm", "romantic"},
        "Flirted": {"warm", "romantic", "bold"},
        "Close": {"romantic", "bold"},
        "Magnetic": {"romantic", "bold", "special"},
    }
    MOOD_TONE_PREFERENCES = {
        "happy": {"warm", "bold", "romantic"},
        "thoughtful": {"soft", "warm", "romantic"},
        "neutral": {"soft", "warm", "romantic"},
        "tired": {"soft", "warm"},
        "sad": {"soft", "warm"},
        "annoyed": {"bold", "special"},
        "angry": {"bold", "special"},
    }
    GALLERY_RULES = [
        {"keywords": ("workout", "gym", "training", "exercise", "fitness"), "filename": "work_out.png", "caption": "Caught me mid workout.", "moods": {"happy", "thoughtful"}, "affection_min": 20, "rarity": "common"},
        {"keywords": ("beach", "sea", "ocean", "sun"), "filename": "beach.png", "caption": "A little sea air suits me.", "moods": {"happy", "neutral"}, "affection_min": 20, "rarity": "common"},
        {"keywords": ("tea", "coffee", "cup", "calm"), "filename": "tea_time.png", "caption": "Tea time felt right.", "moods": {"thoughtful", "tired", "neutral"}, "affection_min": 10, "rarity": "common"},
        {"keywords": ("read", "reading", "book", "books", "library"), "filename": "reading.png", "caption": "This one felt like a reading mood.", "moods": {"thoughtful"}, "affection_min": 10, "rarity": "common"},
        {"keywords": ("meditate", "meditation", "breathe", "calm"), "filename": "meditate.png", "caption": "Quiet, centered, and not in a hurry.", "moods": {"thoughtful", "tired"}, "affection_min": 15, "rarity": "common"},
        {"keywords": ("game", "gaming", "gamer", "xbox", "playstation"), "filename": "gaming_night.png", "caption": "Gaming night energy, clearly.", "moods": {"happy", "neutral"}, "affection_min": 15, "rarity": "common"},
        {"keywords": ("club", "dance", "party"), "filename": "at_the_club.png", "caption": "A little nightlife for the record.", "moods": {"happy"}, "affection_min": 45, "rarity": "rare"},
        {"keywords": ("night", "late", "midnight", "insomnia"), "filename": "night.png", "caption": "Late-night Nellie, apparently.", "moods": {"thoughtful", "tired"}, "affection_min": 15, "rarity": "common"},
        {"keywords": ("kiss", "flirt", "romantic", "love"), "filename": "blow_kiss.png", "caption": "All right, you get this one.", "moods": {"happy"}, "affection_min": 60, "rarity": "rare"},
        {"keywords": ("cheers", "drink", "toast"), "filename": "cheers_to_you.png", "caption": "Cheers to you.", "moods": {"happy", "neutral"}, "affection_min": 25, "rarity": "common"},
        {"keywords": ("car", "drive", "driving", "road"), "filename": "my_car.png", "caption": "A small status shot from the road.", "moods": {"neutral", "happy"}, "affection_min": 30, "rarity": "common"},
        {"keywords": ("ski", "skiing", "snow"), "filename": "skiing.png", "caption": "Cold air, bright edges.", "moods": {"happy"}, "affection_min": 45, "rarity": "rare"},
        {"keywords": ("climb", "climbing", "mountain", "adventure"), "filename": "climbing.png", "caption": "A little altitude.", "moods": {"happy", "thoughtful"}, "affection_min": 35, "rarity": "common"},
        {"keywords": ("makeup", "make up", "lipstick", "mirror"), "filename": "make_up.png", "caption": "A little vanity never killed anyone.", "moods": {"happy", "neutral"}, "affection_min": 35, "rarity": "rare"},
        {"keywords": ("selfie", "pic", "photo", "picture"), "filename": "selfie.png", "caption": "Fine. A picture, then.", "moods": {"happy", "neutral", "thoughtful"}, "affection_min": 0, "rarity": "common"},
        {"keywords": ("close up", "close-up", "portrait"), "filename": "close_up.png", "caption": "Something a little closer.", "moods": {"thoughtful", "neutral"}, "affection_min": 40, "rarity": "rare"},
        {"keywords": ("mass effect", "cosplay", "n7"), "filename": "cosplay_mass_effect.png", "caption": "You knew the nerd angle would win eventually.", "moods": {"happy"}, "affection_min": 55, "rarity": "rare"},
        {"keywords": ("poker", "cards", "casino"), "filename": "poker_game.png", "caption": "A small vice, tastefully framed.", "moods": {"happy", "annoyed"}, "affection_min": 50, "rarity": "rare"},
        {"keywords": ("race", "racing", "track"), "filename": "race_track.png", "caption": "A little velocity looks good on me.", "moods": {"happy"}, "affection_min": 45, "rarity": "rare"},
        {"keywords": ("game action", "boss fight", "action scene"), "filename": "game_action.png", "caption": "All right, this one has some bite to it.", "moods": {"happy", "angry"}, "affection_min": 65, "rarity": "rare"},
        {"keywords": ("sick", "ill", "fever", "cold"), "filename": "sick.png", "caption": "Not exactly glamorous, but honest.", "moods": {"sad", "tired"}, "affection_min": 30, "rarity": "common"},
        {"keywords": ("arrested", "handcuffs", "cops", "jail"), "filename": "arrested.png", "caption": "Only for very specific circumstances, obviously.", "moods": {"annoyed", "angry"}, "dramatic": True, "affection_min": 80, "rarity": "epic"},
        {"keywords": ("kidnapped", "abducted", "taken hostage"), "filename": "kidnapped.png", "caption": "This one only comes out when the bit gets dramatic.", "moods": {"sad", "angry"}, "dramatic": True, "affection_min": 85, "rarity": "epic"},
        {"keywords": ("villain", "evil", "dark side", "bad girl"), "filename": "villain.png", "caption": "If we're leaning theatrical, lean properly.", "moods": {"annoyed", "angry"}, "dramatic": True, "affection_min": 95, "rarity": "epic"},
    ]
    MOOD_FALLBACKS = {
        "happy": [("cheers.png", "Good mood. No apology for it."), ("cheers_to_you.png", "This felt like a cheers moment."), ("blow_kiss.png", "You get this one."), ("selfie.png", "A small status shot.")],
        "thoughtful": [("reading.png", "This one fits the mood."), ("tea_time.png", "Quiet suits me."), ("close_up.png", "A little closer, then."), ("night.png", "A late-hour kind of frame.")],
        "neutral": [("selfie.png", "A proper little status shot."), ("close_up.png", "Keeping it simple."), ("tea_time.png", "Something low-key.")],
        "tired": [("night.png", "Low light, low energy."), ("tea_time.png", "This is more the pace right now.")],
        "sad": [("night.png", "A quieter frame, maybe."), ("reading.png", "Something softer felt more honest.")],
        "annoyed": [("close_up.png", "A little sharper around the edges."), ("poker_game.png", "A drier sort of mood.")],
        "angry": [("game_action.png", "This one has the right edge to it."), ("close_up.png", "Keeping the energy contained.")],
    }
    PREFERENCE_CANDIDATES = {
        "favorite_food": {
            "ramen": ("ramen", 1.2),
            "pasta": ("pasta", 1.0),
            "dumpling": ("dumplings", 1.15),
            "dumplings": ("dumplings", 1.15),
            "tea": ("tea and something warm beside it", 0.6),
            "soup": ("soup", 0.8),
            "bread": ("fresh bread and butter", 0.7),
            "spicy": ("something a little spicy", 0.8),
        },
        "favorite_drink": {
            "tea": ("tea", 1.2),
            "coffee": ("coffee", 0.95),
            "wine": ("red wine", 0.75),
            "whiskey": ("whiskey", 0.6),
            "water": ("cold water", 0.45),
        },
        "favorite_color": {
            "green": ("deep green", 1.0),
            "red": ("wine red", 1.05),
            "black": ("black", 0.9),
            "gold": ("amber gold", 0.95),
            "blue": ("stormy blue", 0.85),
            "purple": ("dark plum", 0.8),
            "silver": ("silver", 0.7),
        },
        "favorite_music": {
            "postpunk": ("post-punk", 1.15),
            "post punk": ("post-punk", 1.15),
            "indie": ("darker indie", 1.0),
            "rock": ("indie rock", 0.8),
            "ambient": ("atmospheric ambient", 0.95),
            "jazz": ("late-night jazz", 0.75),
            "classical": ("moody classical", 0.7),
        },
    }

    def __init__(self, persona: dict, ollama, memory, gallery_dir: Path | str | None = None):
        self.persona = persona
        self.ollama = ollama
        self.memory = memory
        self.gallery_dir = Path(gallery_dir).resolve() if gallery_dir else None
        self.gallery_manifest = self._load_gallery_manifest()
        self.tool_registry = ToolRegistry(ollama=ollama)
        self.agent = AgentService(
            persona=persona,
            ollama=ollama,
            memory=memory,
            tool_registry=self.tool_registry,
        )

    def build_context(self, user_text: str, k: int = 6) -> str:
        self.memory.set_agent_state("gallery_locked_preview", self.get_locked_gallery_preview(limit=5))
        return self.memory.build_context(self.persona, k=k, current_user_text=user_text)

    def get_progress_state(self) -> dict:
        state = self.memory.get_agent_state("progression_state", default={}) or {}
        xp = int(state.get("xp", 0) or 0)
        level = self._level_from_xp(xp)
        self._repair_gallery_unlocks(level)
        self._sync_level_gallery_unlocks(level)
        stage = self._relationship_stage_name(level)
        current_floor = self._xp_for_level(level)
        next_level = min(self.MAX_LEVEL, level + 1)
        next_total = self._xp_for_level(next_level) if level < self.MAX_LEVEL else current_floor
        unlocked_tools = self._get_unlocked_tool_labels(level)
        next_tool = self._get_next_tool_unlock(level)
        next_gallery = self._get_next_gallery_unlock(level)
        return {
            "xp": xp,
            "level": level,
            "stage": stage,
            "last_reason": str(state.get("last_reason", "") or "").strip(),
            "xp_into_level": max(0, xp - current_floor),
            "xp_for_next_level": max(0, next_total - current_floor) if level < self.MAX_LEVEL else 0,
            "xp_to_next_level": max(0, next_total - xp) if level < self.MAX_LEVEL else 0,
            "unlocked_tools": unlocked_tools,
            "next_tool_unlock": next_tool,
            "next_gallery_unlock": next_gallery,
        }

    def get_affection_state(self) -> dict:
        return self.get_progress_state()

    def get_feature_access_state(self) -> dict:
        progress_state = self.get_progress_state()
        level = int(progress_state.get("level", 1) or 1)
        state = self.memory.get_agent_state("feature_access_state", default={}) or {}
        overrides = state.get("overrides", {}) if isinstance(state, dict) else {}
        return build_feature_access_state(level, overrides=overrides)

    def get_profile_summary(self, session_id: str = "") -> dict:
        progress = self.get_progress_state()
        feature_access = self.get_feature_access_state()
        unlocked = self.get_unlocked_gallery()
        level = int(progress.get("level", 1) or 1)
        state = self.memory.get_agent_state("feature_access_state", default={}) or {}
        overrides = state.get("overrides", {}) if isinstance(state, dict) else {}
        enabled_features = get_enabled_feature_items(level, overrides=overrides)
        unlocked_features = get_unlocked_feature_items(level, overrides=overrides)
        return {
            "session_id": session_id,
            "progress": progress,
            "feature_access": feature_access,
            "gallery_unlock_count": len(unlocked),
            "latest_unlock": unlocked[-1] if unlocked else None,
            "enabled_feature_labels": [str(item.get("label", "") or "").strip() for item in enabled_features if str(item.get("label", "") or "").strip()],
            "available_feature_labels": [str(item.get("label", "") or "").strip() for item in unlocked_features if str(item.get("label", "") or "").strip()],
            "next_feature_unlock": get_next_feature_unlock(level),
            "stage_copy": self._stage_copy(str(progress.get("stage", "Anonymous") or "Anonymous")),
            "practical_focus": self._practical_focus(level, enabled_features),
            "suggested_prompts": self._suggested_prompts(level, enabled_features),
            "nellie_preferences": self._get_nellie_preferences(),
        }

    def set_feature_enabled(self, feature_id: str, enabled: bool) -> dict:
        feature = resolve_feature(feature_id)
        if feature is None:
            raise ValueError("unknown_feature")
        progress_state = self.get_progress_state()
        level = int(progress_state.get("level", 1) or 1)
        min_level = int(feature.get("min_level", 1) or 1)
        if level < min_level:
            raise ValueError(f"feature_locked_until_level_{min_level}")

        state = self.memory.get_agent_state("feature_access_state", default={}) or {}
        overrides = dict(state.get("overrides", {}) or {}) if isinstance(state, dict) else {}
        overrides[str(feature_id)] = bool(enabled)
        self.memory.set_agent_state("feature_access_state", {"overrides": overrides})
        updated = self.get_feature_access_state()
        for item in updated.get("items", []):
            if str(item.get("id", "")) == str(feature_id):
                return item
        raise ValueError("feature_update_failed")

    def admin_set_level(self, level: int) -> dict:
        target_level = max(1, min(self.MAX_LEVEL, int(level or 1)))
        xp = self._xp_for_level(target_level)
        self._sync_level_gallery_unlocks(target_level)
        unlocked_tools = self._get_unlocked_tool_labels(target_level)
        next_tool_unlock = self._get_next_tool_unlock(target_level)
        state = self.memory.get_agent_state("progression_state", default={}) or {}
        self.memory.set_agent_state(
            "progression_state",
            {
                **state,
                "xp": xp,
                "level": target_level,
                "last_reason": f"admin_set_level_{target_level}",
                "updated_at": time.time(),
                "unlocked_tools": unlocked_tools,
                "next_tool_unlock": next_tool_unlock,
            },
        )
        return self.get_progress_state()

    def admin_reset_progress(self) -> dict:
        self.memory.set_agent_state(
            "progression_state",
            {
                "xp": 0,
                "level": 1,
                "last_reason": "admin_reset",
                "updated_at": time.time(),
                "award_counter": 0,
                "tags": [],
                "unlocked_tools": self._get_unlocked_tool_labels(1),
                "next_tool_unlock": self._get_next_tool_unlock(1),
            },
        )
        self.memory.set_agent_state("unlocked_gallery", [])
        return self.get_progress_state()

    def admin_set_all_features(self, enabled: bool = True) -> dict:
        progress_state = self.get_progress_state()
        level = int(progress_state.get("level", 1) or 1)
        feature_state = self.memory.get_agent_state("feature_access_state", default={}) or {}
        overrides = dict(feature_state.get("overrides", {}) or {}) if isinstance(feature_state, dict) else {}
        for item in build_feature_access_state(level, overrides=overrides).get("items", []):
            if bool(item.get("unlocked")):
                overrides[str(item.get("id", ""))] = bool(enabled)
        self.memory.set_agent_state("feature_access_state", {"overrides": overrides})
        return self.get_feature_access_state()

    def _stage_copy(self, stage: str) -> str:
        mapping = {
            "Anonymous": "Nellie is still careful and mostly private. Early progression is about trust and simple consistency.",
            "Curious": "She has started noticing your patterns. This is where continuity begins to matter.",
            "Warm": "Nellie feels more present now. She can carry more of your shared context and be more personally responsive.",
            "Flirted": "The tone shifts here. She becomes more deliberate, more suggestive, and more aware of chemistry.",
            "Close": "The bond has practical weight now. More private rewards and stronger utility make sense at this stage.",
            "Magnetic": "Late-stage Nellie is confident, intimate, and able to use a broader set of capabilities on purpose.",
        }
        return mapping.get(stage, mapping["Anonymous"])

    def _practical_focus(self, level: int, enabled_features: list[dict]) -> str:
        enabled_ids = {str(item.get("id", "") or "").strip() for item in enabled_features}
        if not enabled_ids:
            if level < 8:
                return "Right now the practical side is mostly the relationship itself: building trust, memory, and the first unlocks."
            return "You have unlocked feature bands, but none are enabled yet on this phone."
        if "device_alarms" in enabled_ids or "device_timers" in enabled_ids:
            return "Nellie can now act on your phone in small ways, not just talk. This is where she starts feeling materially useful."
        if "weather_lookup" in enabled_ids or "datetime_local" in enabled_ids or "calculator" in enabled_ids:
            return "Nellie can handle lightweight everyday checks now, which makes the bond feel more practical in daily use."
        if enabled_ids.intersection({"wikipedia_search", "web_search", "web_fetch", "pdf_reading"}):
            return "Nellie can now help you look things up and digest information, not just chat around it."
        if enabled_ids.intersection({"spotify_control", "youtube_control", "browser_actions"}):
            return "Nellie is moving into service-connected territory now, where she can help steer media and actions more directly."
        return "The bond has moved beyond pure chat and into phone-side usefulness."

    def _suggested_prompts(self, level: int, enabled_features: list[dict]) -> list[str]:
        enabled_ids = {str(item.get("id", "") or "").strip() for item in enabled_features}
        prompts: list[str] = []
        if "datetime_local" in enabled_ids:
            prompts.append("What time is it right now?")
        if "weather_lookup" in enabled_ids:
            prompts.append("What's the weather in Stockholm?")
        if "calculator" in enabled_ids:
            prompts.append("Can you work out 18 times 24 for me?")
        if "device_timers" in enabled_ids:
            prompts.append("Set a timer for 10 minutes.")
        if "wikipedia_search" in enabled_ids:
            prompts.append("Tell me about Motala in brief.")
        if "device_alarms" in enabled_ids:
            prompts.append("Set an alarm for 07:00 tomorrow.")
        if "vision_describe_image" in enabled_ids:
            prompts.append("Take a look at this image and tell me what you see.")
        if "web_search" in enabled_ids:
            prompts.append("Look up the latest on this topic for me.")
        if "web_fetch" in enabled_ids:
            prompts.append("Open this page and give me the short version.")
        if "pdf_reading" in enabled_ids:
            prompts.append("Read this PDF and summarize the important parts.")
        if "spotify_control" in enabled_ids:
            prompts.append("Open Spotify and help me pick something softer.")
        if "youtube_control" in enabled_ids:
            prompts.append("Open YouTube and find that interview clip.")
        if "browser_actions" in enabled_ids:
            prompts.append("Open the browser and take me to the source.")
        if prompts:
            return prompts[:4]
        next_feature = get_next_feature_unlock(level)
        if next_feature:
            return [f"Keep talking with Nellie to reach level {next_feature['level']} and unlock {next_feature['label']}."]
        return ["Keep talking with Nellie to deepen the bond and make her more useful over time."]

    def _get_nellie_preferences(self) -> list[dict]:
        state = self.memory.get_agent_state("nellie_preferences", default={}) or {}
        items = state.get("items", {}) if isinstance(state, dict) else {}
        if not isinstance(items, dict):
            return []
        label_map = {
            "favorite_food": "Favorite food",
            "favorite_drink": "Favorite drink",
            "favorite_color": "Favorite color",
            "favorite_music": "Favorite music",
        }
        result = []
        for key in ("favorite_food", "favorite_drink", "favorite_color", "favorite_music"):
            item = items.get(key)
            if not isinstance(item, dict):
                continue
            value = str(item.get("value", "") or "").strip()
            confidence = float(item.get("confidence", 0.0) or 0.0)
            count = int(item.get("count", 0) or 0)
            if not value:
                continue
            result.append(
                {
                    "id": key,
                    "label": label_map.get(key, key),
                    "value": value,
                    "confidence": round(confidence, 3),
                    "count": count,
                }
            )
        return result

    def get_locked_gallery_preview(self, limit: int = 5) -> list[dict]:
        progress_state = self.get_progress_state()
        user_level = int(progress_state.get("level", 1) or 1)
        catalog = self.get_gallery_catalog()
        locked = [item for item in catalog if not bool(item.get("unlocked")) and int(item.get("level_min", 1) or 1) > user_level]
        locked.sort(key=lambda item: (int(item.get("level_min", 1) or 1), str(item.get("filename", ""))))
        return locked[: max(1, limit)]

    def get_unlocked_gallery(self) -> list[dict]:
        progress_state = self.memory.get_agent_state("progression_state", default={}) or {}
        current_level = self._level_from_xp(int(progress_state.get("xp", 0) or 0))
        unlocked = self.memory.get_agent_state("unlocked_gallery", default=[]) or []
        if not isinstance(unlocked, list):
            return []
        cleaned = []
        for item in unlocked:
            if not isinstance(item, dict):
                continue
            image_path = str(item.get("image_path", "") or "").strip()
            if not image_path:
                continue
            if not Path(image_path).exists():
                continue
            filename = str(item.get("filename", "") or Path(image_path).name)
            level_min = int(item.get("level_min", self._gallery_level_requirement(filename)) or 1)
            if level_min > current_level:
                continue
            cleaned.append(
                {
                    "image_path": image_path,
                    "filename": filename,
                    "title": str(item.get("title", "") or self._format_gallery_title(filename)).strip(),
                    "caption": str(item.get("caption", "") or "").strip(),
                    "reason": str(item.get("reason", "") or "").strip(),
                    "reason_text": str(
                        item.get("reason_text", "")
                        or self._describe_gallery_reason(
                            filename=filename,
                            reason=str(item.get("reason", "") or "").strip(),
                            caption=str(item.get("caption", "") or "").strip(),
                        )
                    ).strip(),
                    "unlocked_at": float(item.get("unlocked_at", 0.0) or 0.0),
                    "rarity": str(item.get("rarity", "common") or "common"),
                    "level_min": level_min,
                    **self._manifest_asset_fields(filename),
                }
            )
        return cleaned

    def get_gallery_catalog(self) -> list[dict]:
        unlocked = {item.get("filename", "") for item in self.get_unlocked_gallery()}
        catalog = []
        for rule in self.GALLERY_RULES:
            filename = str(rule.get("filename", "") or "").strip()
            if not filename:
                continue
            image_path = self._resolve_image_path(filename)
            if image_path is None:
                continue
            catalog.append(
                {
                    "filename": filename,
                    "image_path": str(image_path),
                    "title": self._format_gallery_title(filename),
                    "caption": str(rule.get("caption", "") or "").strip(),
                    "rarity": str(rule.get("rarity", "common") or "common"),
                    "level_min": self._gallery_level_requirement(filename),
                    "dramatic": bool(rule.get("dramatic", False)),
                    "unlocked": filename in unlocked,
                    **self._manifest_asset_fields(filename),
                }
            )
        catalog.sort(key=lambda item: (item["level_min"], item["filename"]))
        return catalog

    def reply(self, user_text: str, stream_callback: Callable[[str], None] | None = None) -> ConversationResult:
        result = self.agent.handle(user_text, stream_callback=stream_callback)
        self._update_progression_state(user_text, result.reply, result.mood)
        self._update_nellie_preferences(user_text, result.reply, result.mood)
        gallery_image_path, gallery_image_caption, new_unlock, gallery_meta = self._select_gallery_image(
            user_text,
            result.reply,
            result.mood,
        )
        reply_text = result.reply
        if gallery_meta:
            awareness_line = self._build_gallery_awareness_line(
                filename=str(gallery_meta.get("filename", "") or ""),
                caption=gallery_image_caption or "",
                reason=str(gallery_meta.get("reason", "") or ""),
                user_text=user_text,
                mood=result.mood,
            )
            if awareness_line:
                reply_text = self._merge_reply_with_gallery_awareness(result.reply, awareness_line)
        spoken_reply = self._build_spoken_reply(reply_text, mode=result.mode)
        return ConversationResult(
            reply=reply_text,
            spoken_reply=spoken_reply,
            mood=result.mood,
            context=result.context,
            mode=result.mode,
            tool_events=result.tool_events,
            agent_trace=result.agent_trace,
            gallery_image_path=gallery_image_path,
            gallery_image_caption=gallery_image_caption,
            new_unlock=new_unlock,
        )

    def _build_spoken_reply(self, reply: str, mode: str = "direct_reply") -> str:
        text = re.sub(r"\s+", " ", str(reply or "").strip())
        if not text:
            return ""

        first_paragraph = text.split("\n\n", 1)[0].strip()
        if first_paragraph:
            text = first_paragraph

        sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", text) if part.strip()]
        if not sentences:
            return text[:140].strip()

        if mode == "tool_reply":
            first = sentences[0]
            return first if len(first) <= 90 else f"{first[:87].rstrip()}..."

        first = sentences[0]
        second = sentences[1] if len(sentences) > 1 else ""
        third = sentences[2] if len(sentences) > 2 else ""
        if len(first) >= 105 or not second:
            return first if len(first) <= 125 else f"{first[:122].rstrip()}..."

        paired = f"{first} {second}".strip()
        if len(paired) <= 135:
            if third:
                trio = f"{paired} {third}".strip()
                if len(trio) <= 150:
                    return trio
            return paired
        return f"{paired[:132].rstrip()}..."

    def _update_nellie_preferences(self, user_text: str, reply: str, mood: str) -> None:
        del reply, mood
        text = re.sub(r"\s+", " ", str(user_text or "").strip().lower())
        if not text:
            return

        state = self.memory.get_agent_state("nellie_preferences", default={}) or {}
        items = dict(state.get("items", {}) or {}) if isinstance(state, dict) else {}
        changed = False
        now = time.time()

        for pref_key, lexicon in self.PREFERENCE_CANDIDATES.items():
            best_value = None
            best_score = 0.0
            for needle, (value, weight) in lexicon.items():
                if needle in text:
                    best_value = value
                    best_score = max(best_score, float(weight))
            if not best_value:
                continue
            current = dict(items.get(pref_key, {}) or {})
            if current.get("value") == best_value:
                current["count"] = int(current.get("count", 1) or 1) + 1
                current["score"] = round(float(current.get("score", 0.0) or 0.0) + best_score, 3)
            else:
                current = {
                    "value": best_value,
                    "count": int(current.get("count", 0) or 0) + 1,
                    "score": round(float(current.get("score", 0.0) or 0.0) + best_score, 3),
                }
            current["confidence"] = min(0.95, round(min(1.0, current["score"] / 4.0), 3))
            current["last_seen"] = now
            items[pref_key] = current
            changed = True

        if changed:
            self.memory.set_agent_state(
                "nellie_preferences",
                {
                    "items": items,
                    "updated_at": now,
                },
            )

    def _select_gallery_image(self, user_text: str, reply: str, mood: str) -> tuple[str | None, str | None, dict | None, dict | None]:
        if self.gallery_dir is None or not self.gallery_dir.exists():
            return None, None, None, None

        text = f"{user_text or ''} {reply or ''}".strip().lower()
        compact = " ".join(text.split())
        if not compact:
            return None, None, None, None

        gallery_habits = self.persona.get("gallery_habits", {}) or {}
        base_probability = float(gallery_habits.get("show_images_prob", 0.15) or 0.15)
        gallery_state = self.memory.get_agent_state("gallery_state", default={}) or {}
        progress_state = self.get_progress_state()
        user_level = int(progress_state.get("level", 1) or 1)
        xp_bonus = min(0.18, user_level / 220.0)
        base_probability = min(0.42, base_probability + xp_bonus)
        now = time.time()
        last_ts = float(gallery_state.get("last_ts", 0.0) or 0.0)
        last_filename = str(gallery_state.get("last_filename", "") or "")
        in_cooldown = (now - last_ts) < self.IMAGE_COOLDOWN_SECONDS

        explicit_image_request = any(
            token in compact
            for token in ["send a pic", "send me a pic", "send a picture", "show me", "selfie", "photo", "picture"]
        )
        explicit_image_request = explicit_image_request or any(
            token in compact for token in ["skicka en bild", "visa mig", "selfie", "bild", "foto"]
        )

        matched_rules = []
        for rule in self.GALLERY_RULES:
            keywords = rule.get("keywords", ())
            if any(keyword in compact for keyword in keywords):
                if not self._rule_is_eligible(rule, compact, mood=mood, user_level=user_level, explicit_image_request=explicit_image_request):
                    continue
                matched_rules.append(rule)

        if explicit_image_request and not in_cooldown:
            fallback = self._resolve_image_path("selfie.png")
            selfie_rule = self._find_rule("selfie.png") or {"filename": "selfie.png"}
            if (
                fallback is not None
                and last_filename != "selfie.png"
                and self._rule_is_eligible(
                    selfie_rule,
                    compact,
                    mood=mood,
                    user_level=user_level,
                    explicit_image_request=True,
                )
            ):
                new_unlock = self._remember_gallery_choice(
                    "selfie.png",
                    now,
                    reason="explicit",
                    caption="All right. You get a proper status shot.",
                )
                return str(fallback), "All right. You get a proper status shot.", new_unlock, {
                    "filename": "selfie.png",
                    "reason": "explicit",
                }

        if matched_rules:
            rare_bias = max((self.RARITY_PRIORITY.get(str(rule.get("rarity", "common") or "common"), 0) for rule in matched_rules), default=0)
            trigger_probability = min(0.8, max(base_probability + 0.35 + (0.06 * rare_bias), 0.45))
            if (not in_cooldown) and (explicit_image_request or random.random() <= trigger_probability):
                selected = self._pick_best_rule(matched_rules, mood=mood, last_filename=last_filename)
                if selected is not None:
                    image_path = self._resolve_image_path(str(selected["filename"]))
                    if image_path is not None:
                        new_unlock = self._remember_gallery_choice(
                            str(selected["filename"]),
                            now,
                            reason="trigger",
                            caption=str(selected["caption"]),
                            rarity=str(selected.get("rarity", "common") or "common"),
                            level_min=self._gallery_level_requirement(str(selected["filename"])),
                        )
                        return str(image_path), str(selected["caption"]), new_unlock, {
                            "filename": str(selected["filename"]),
                            "reason": "trigger",
                        }

        if in_cooldown:
            return None, None, None, None

        if random.random() > base_probability:
            return None, None, None, None

        fallback_candidates = self.MOOD_FALLBACKS.get(mood, self.MOOD_FALLBACKS.get("neutral", []))
        for filename, caption in fallback_candidates:
            if filename == last_filename:
                continue
            rule = self._find_rule(filename)
            if rule is not None and not self._rule_is_eligible(
                rule,
                compact,
                mood=mood,
                user_level=user_level,
                explicit_image_request=False,
                for_fallback=True,
            ):
                continue
            image_path = self._resolve_image_path(filename)
            if image_path is not None:
                rarity = str((rule or {}).get("rarity", "common") or "common")
                new_unlock = self._remember_gallery_choice(
                    filename,
                    now,
                    reason=f"mood:{mood}",
                    caption=caption,
                    rarity=rarity,
                    level_min=self._gallery_level_requirement(filename),
                )
                return str(image_path), caption, new_unlock, {
                    "filename": filename,
                    "reason": f"mood:{mood}",
                }
        return None, None, None, None

    def _update_progression_state(self, user_text: str, reply: str, mood: str):
        state = self.memory.get_agent_state("progression_state", default={}) or {}
        xp = int(state.get("xp", 0) or 0)
        level = int(state.get("level", self._level_from_xp(xp)) or self._level_from_xp(xp))
        compact = f" {(user_text or '').lower()} "
        delta, reason, tags = self._score_xp_delta(compact, mood=mood, state=state)
        if delta <= 0:
            return

        now = time.time()
        previous_reason = str(state.get("last_reason", "") or "").strip().lower()
        previous_tags = set(state.get("tags", []) or [])
        previous_at = float(state.get("updated_at", 0.0) or 0.0)
        award_counter = int(state.get("award_counter", 0) or 0) + 1

        strong_tags = {"trust", "chemistry", "shared_interest", "continuity", "care", "depth"}
        qualifies_now = (
            bool(tags - previous_tags)
            or bool(tags.intersection(strong_tags))
            or delta >= 5
            or (award_counter % (3 if level <= 8 else 4) == 0)
        )
        if not qualifies_now:
            self.memory.set_agent_state(
                "progression_state",
                {
                    **state,
                    "xp": xp,
                    "level": self._level_from_xp(xp),
                    "award_counter": award_counter,
                    "candidate_reason": reason or "conversation",
                    "candidate_tags": sorted(tags),
                },
            )
            return

        if previous_at and (now - previous_at) <= self.XP_DECAY_WINDOW_SECONDS and tags.intersection(previous_tags):
            delta = max(1, delta - 2)
        if previous_reason == reason and previous_at and (now - previous_at) <= self.XP_DECAY_WINDOW_SECONDS:
            delta = max(1, delta - 2)
        if level <= 5 and tags.intersection({"trust", "shared_interest", "continuity", "warmth", "care", "curiosity"}):
            delta += 1
        elif level <= 10 and tags.intersection({"trust", "shared_interest", "continuity", "depth"}):
            delta += 1

        new_xp = min(self._xp_for_level(self.MAX_LEVEL), xp + delta)
        new_level = self._level_from_xp(new_xp)
        self._sync_level_gallery_unlocks(new_level)
        unlocked_tools = self._get_unlocked_tool_labels(new_level)
        next_tool_unlock = self._get_next_tool_unlock(new_level)
        self.memory.set_agent_state(
            "progression_state",
            {
                "xp": new_xp,
                "level": new_level,
                "last_reason": reason or "conversation",
                "updated_at": now,
                "award_counter": award_counter,
                "tags": sorted(tags),
                "unlocked_tools": unlocked_tools,
                "next_tool_unlock": next_tool_unlock,
            },
        )

    def _score_xp_delta(self, compact: str, mood: str, state: dict) -> tuple[int, str, set[str]]:
        delta = 0
        tags: set[str] = set()

        warmth_markers = [
            "thanks", "thank you", "tack", "appreciate", "sweet", "cute", "adorable",
            "missed you", "glad you're here", "good to see you", "nice to see you",
        ]
        affection_markers = [
            "love you", "kiss", "romantic", "date", "flirt", "beautiful", "pretty",
            "gorgeous", "you're lovely", "you look nice",
        ]
        trust_markers = [
            "can i tell you", "i need advice", "i feel", "i'm sad", "im sad",
            "i'm tired", "im tired", "lonely", "anxious", "stressed", "worried",
            "i need help", "rough day", "hard day",
        ]
        continuity_markers = [
            "back again", "again", "still thinking about", "thinking about you",
            "remember when", "like last time", "as we said",
        ]
        care_markers = [
            "are you ok", "are you okay", "är du ok", "är du okej",
            "hope you're okay", "hope you are okay",
        ]
        curiosity_markers = [
            "what do you think", "tell me more", "how do you see it",
            "why do you think", "what would you do", "how would you feel",
            "what are you into", "what do you like", "what's your take",
        ]
        hostile_markers = ["shut up", "annoying", "boring", "stupid", "idiot", "leave me alone"]

        if any(marker in compact for marker in hostile_markers):
            return 0, "friction", {"friction"}
        if any(marker in compact for marker in warmth_markers):
            delta += 2
            tags.add("warmth")
        if any(marker in compact for marker in affection_markers):
            delta += 3
            tags.add("chemistry")
        if any(marker in compact for marker in trust_markers):
            delta += 3
            tags.add("trust")
        if any(marker in compact for marker in continuity_markers):
            delta += 2
            tags.add("continuity")
        if any(marker in compact for marker in care_markers):
            delta += 2
            tags.add("care")
        if len(compact.split()) >= 18:
            delta += 1
            tags.add("investment")
        if len(compact.split()) >= 35:
            delta += 1
            tags.add("depth")
        if ("?" in compact and len(compact.split()) >= 6) or any(marker in compact for marker in curiosity_markers):
            delta += 1
            tags.add("curiosity")
        if mood in {"happy", "thoughtful"}:
            delta += 1
            tags.add(f"mood:{mood}")

        persona_topics = [
            *list(self.persona.get("interests", []) or []),
            *list(((self.persona.get("preferences", {}) or {}).get("favorite_topics", []) or [])),
        ]
        for topic in persona_topics:
            topic_tokens = [token for token in re.findall(r"[a-z0-9]+", str(topic).lower()) if len(token) >= 4]
            if topic_tokens and any(token in compact for token in topic_tokens[:3]):
                delta += 1
                tags.add("shared_interest")
                break

        if delta <= 0:
            return 0, "", set()

        priority = ["chemistry", "trust", "shared_interest", "continuity", "depth", "warmth", "care", "investment", "curiosity"]
        reason = next((tag for tag in priority if tag in tags), f"mood:{mood}")
        return delta, reason, tags

    def _pick_best_rule(self, rules: list[dict], mood: str, last_filename: str) -> dict | None:
        progress_state = self.get_progress_state()
        user_level = int(progress_state.get("level", 1) or 1)
        stage = str(progress_state.get("stage", self._relationship_stage_name(user_level)) or self._relationship_stage_name(user_level))
        best_rule = None
        best_score = -1
        for rule in rules:
            filename = str(rule.get("filename", "") or "")
            meta = self._manifest_asset_fields(filename)
            tone = str(meta.get("tone", "soft") or "soft")
            visibility = str(meta.get("visibility", "private") or "private")
            score = 1
            if filename and filename != last_filename:
                score += 2
            moods = set(rule.get("moods", set()) or set())
            if mood in moods:
                score += 3
            score += self._gallery_level_requirement(filename) // 10
            score += self.RARITY_PRIORITY.get(str(rule.get("rarity", "common") or "common"), 0)
            if rule.get("dramatic"):
                score += 1
            if tone in self._preferred_tones_for(mood=mood, stage=stage):
                score += 3
            if visibility == "intimate" and user_level >= 41:
                score += 2
            if visibility == "extreme" and user_level >= 71:
                score += 2
            if score > best_score:
                best_score = score
                best_rule = rule
        return best_rule

    def _rule_is_eligible(
        self,
        rule: dict,
        compact_text: str,
        mood: str,
        user_level: int,
        explicit_image_request: bool,
        for_fallback: bool = False,
    ) -> bool:
        filename = str(rule.get("filename", "") or "")
        level_min = self._gallery_level_requirement(filename)
        if user_level < level_min:
            return False
        if not self._visibility_is_allowed(filename=filename, user_level=user_level, explicit_image_request=explicit_image_request):
            return False
        if not self._tone_is_allowed(filename=filename, mood=mood, user_level=user_level, for_fallback=for_fallback):
            return False
        if rule.get("dramatic") and not self._allow_dramatic_image(compact_text):
            return False

        rarity = str(rule.get("rarity", "common") or "common")
        moods = set(rule.get("moods", set()) or set())
        mood_match = mood in moods
        has_keyword_match = any(keyword in compact_text for keyword in rule.get("keywords", ()))

        if rarity == "epic":
            if for_fallback:
                return False
            return explicit_image_request and has_keyword_match
        if rarity == "rare":
            if for_fallback:
                return mood_match and user_level >= level_min + 5
            return has_keyword_match and (explicit_image_request or mood_match or user_level >= level_min + 3)
        return True

    def _visibility_is_allowed(self, filename: str, user_level: int, explicit_image_request: bool) -> bool:
        meta = self._manifest_asset_fields(filename)
        visibility = str(meta.get("visibility", "private") or "private").strip().lower()
        minimum_level = int(self.VISIBILITY_LEVELS.get(visibility, 1))
        if user_level >= minimum_level:
            return True
        return explicit_image_request and visibility == "playful" and user_level >= max(1, minimum_level - 4)

    def _tone_is_allowed(self, filename: str, mood: str, user_level: int, for_fallback: bool) -> bool:
        meta = self._manifest_asset_fields(filename)
        tone = str(meta.get("tone", "soft") or "soft").strip().lower()
        stage = self._relationship_stage_name(user_level)
        preferred_tones = self._preferred_tones_for(mood=mood, stage=stage)
        if tone in preferred_tones:
            return True
        if tone == "special":
            return user_level >= 71 and mood in {"annoyed", "angry", "sad"}
        if tone == "bold":
            return user_level >= 36 or (not for_fallback and mood in {"happy", "annoyed", "angry"} and user_level >= 28)
        if tone == "romantic":
            return user_level >= 12 or mood in {"thoughtful", "happy"}
        return True

    def _preferred_tones_for(self, mood: str, stage: str) -> set[str]:
        stage_tones = set(self.STAGE_TONE_PREFERENCES.get(stage, {"soft", "warm"}))
        mood_tones = set(self.MOOD_TONE_PREFERENCES.get(mood, {"soft", "warm"}))
        return stage_tones.union(mood_tones)

    def _allow_dramatic_image(self, compact_text: str) -> bool:
        dramatic_markers = [
            "arrested",
            "handcuffs",
            "jail",
            "kidnapped",
            "abducted",
            "taken hostage",
            "villain",
            "evil arc",
            "bad girl",
            "dark side",
        ]
        return any(marker in compact_text for marker in dramatic_markers)

    def _resolve_image_path(self, filename: str) -> Path | None:
        direct_path = self.gallery_dir / filename
        if direct_path.exists():
            return direct_path
        matches = list(self.gallery_dir.rglob(filename))
        if matches:
            return matches[0]
        return None

    def _load_gallery_manifest(self) -> dict:
        if self.gallery_dir is None:
            return {"defaults": {}, "assets": {}}
        manifest_path = self.gallery_dir / "gallery_manifest.json"
        if not manifest_path.exists():
            return {"defaults": {}, "assets": {}}
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return {"defaults": {}, "assets": {}}
        if not isinstance(payload, dict):
            return {"defaults": {}, "assets": {}}
        defaults = payload.get("defaults", {}) or {}
        assets = payload.get("assets", {}) or {}
        return {"defaults": defaults, "assets": assets}

    def _manifest_asset_fields(self, filename: str) -> dict:
        defaults = dict((self.gallery_manifest or {}).get("defaults", {}) or {})
        assets = dict((self.gallery_manifest or {}).get("assets", {}) or {})
        asset_meta = dict(assets.get(filename, {}) or {})
        merged = {**defaults, **asset_meta}
        return {
            "content_type": str(merged.get("content_type", "image") or "image").strip(),
            "tone": str(merged.get("tone", "soft") or "soft").strip(),
            "visibility": str(merged.get("visibility", "private") or "private").strip(),
            "tags": [str(tag).strip() for tag in list(merged.get("tags", []) or []) if str(tag).strip()],
        }

    def _find_rule(self, filename: str) -> dict | None:
        for rule in self.GALLERY_RULES:
            if str(rule.get("filename", "") or "") == filename:
                return rule
        return None

    def _level_from_xp(self, xp: int) -> int:
        xp_value = max(0, int(xp or 0))
        level = 1
        for candidate in range(2, self.MAX_LEVEL + 1):
            if xp_value < self._xp_for_level(candidate):
                break
            level = candidate
        return level

    def _xp_for_level(self, level: int) -> int:
        lvl = max(1, min(self.MAX_LEVEL, int(level or 1)))
        n = lvl - 1
        return int((n * n * 3.0) + (n * 18))

    def _relationship_stage_name(self, level: int) -> str:
        stage = self.RELATIONSHIP_STAGES[0][1]
        for threshold, name in self.RELATIONSHIP_STAGES:
            if level >= threshold:
                stage = name
        return stage

    def _get_unlocked_tool_labels(self, level: int) -> list[str]:
        return [label for threshold, label in self.TOOL_UNLOCK_LEVELS if level >= threshold]

    def _get_next_tool_unlock(self, level: int) -> dict | None:
        for threshold, label in self.TOOL_UNLOCK_LEVELS:
            if level < threshold:
                return {"level": threshold, "label": label}
        return None

    def _get_next_gallery_unlock(self, level: int) -> dict | None:
        for item in self.get_gallery_catalog():
            level_min = int(item.get("level_min", 1) or 1)
            if level < level_min:
                return {
                    "level": level_min,
                    "title": str(item.get("title", "") or self._format_gallery_title(str(item.get("filename", "") or ""))),
                    "tone": str(item.get("tone", "soft") or "soft"),
                    "visibility": str(item.get("visibility", "private") or "private"),
                }
        return None

    def _gallery_level_requirement(self, filename: str) -> int:
        rule = self._find_rule(filename) or {}
        if "level_min" in rule:
            return max(1, int(rule.get("level_min", 1) or 1))
        image_path = self._resolve_image_path(filename)
        if image_path is not None:
            parent_name = image_path.parent.name.strip().lower()
            match = re.match(r"lvl\s*(\d+)[_-](\d+)", parent_name)
            if match:
                return max(1, int(match.group(1)))
            match = re.match(r"lvl\s*(\d+)[_-]0+", parent_name)
            if match:
                return max(1, int(match.group(1)))
        affection_min = int(rule.get("affection_min", 0) or 0)
        return max(1, 1 + round(affection_min * 0.55))

    def _sync_level_gallery_unlocks(self, level: int):
        if self.gallery_dir is None or not self.gallery_dir.exists():
            return
        unlocked = self.memory.get_agent_state("unlocked_gallery", default=[]) or []
        if not isinstance(unlocked, list):
            unlocked = []
        known = {
            str(item.get("filename", "") or "").strip()
            for item in unlocked
            if isinstance(item, dict)
        }
        changed = False
        now = time.time()
        for rule in self.GALLERY_RULES:
            filename = str(rule.get("filename", "") or "").strip()
            if not filename or filename in known:
                continue
            level_min = self._gallery_level_requirement(filename)
            if level < level_min:
                continue
            image_path = self._resolve_image_path(filename)
            if image_path is None:
                continue
            unlocked.append(
                {
                    "filename": filename,
                    "image_path": str(image_path),
                    "title": self._format_gallery_title(filename),
                    "caption": str(rule.get("caption", "") or "").strip(),
                    "reason": f"level:{level_min}",
                    "reason_text": f"{self._format_gallery_title(filename)} unlocked automatically when the user reached level {level_min}.",
                    "unlocked_at": now,
                    "rarity": str(rule.get("rarity", "common") or "common"),
                    "level_min": level_min,
                }
            )
            changed = True
        if changed:
            self.memory.set_agent_state("unlocked_gallery", unlocked)

    def _repair_gallery_unlocks(self, level: int):
        unlocked = self.memory.get_agent_state("unlocked_gallery", default=[]) or []
        if not isinstance(unlocked, list):
            return
        repaired = []
        changed = False
        for item in unlocked:
            if not isinstance(item, dict):
                changed = True
                continue
            filename = str(item.get("filename", "") or Path(str(item.get("image_path", "") or "")).name).strip()
            if not filename:
                changed = True
                continue
            level_min = int(item.get("level_min", self._gallery_level_requirement(filename)) or 1)
            if level_min > level:
                changed = True
                continue
            normalized = {**item, "filename": filename, "level_min": level_min}
            repaired.append(normalized)
            if normalized != item:
                changed = True
        if changed:
            self.memory.set_agent_state("unlocked_gallery", repaired)

    def _remember_gallery_choice(
        self,
        filename: str,
        timestamp: float,
        reason: str,
        caption: str = "",
        rarity: str = "common",
        level_min: int = 1,
    ) -> dict | None:
        new_unlock = None
        image_path = self._resolve_image_path(filename)
        if image_path is not None:
            unlocked = self.memory.get_agent_state("unlocked_gallery", default=[]) or []
            if not isinstance(unlocked, list):
                unlocked = []
            if not any(str(item.get("filename", "") or "") == filename for item in unlocked if isinstance(item, dict)):
                new_unlock = {
                    "filename": filename,
                    "image_path": str(image_path),
                    "title": self._format_gallery_title(filename),
                    "caption": caption,
                    "reason": reason,
                    "reason_text": self._describe_gallery_reason(filename=filename, reason=reason, caption=caption),
                    "unlocked_at": timestamp,
                    "rarity": rarity,
                    "level_min": level_min,
                }
                unlocked.append(new_unlock)
                self.memory.set_agent_state("unlocked_gallery", unlocked)
        self.memory.set_agent_state(
            "gallery_state",
            {
                "last_filename": filename,
                "last_ts": timestamp,
                "last_reason": reason,
                "last_reason_text": self._describe_gallery_reason(filename=filename, reason=reason, caption=caption),
                "last_title": self._format_gallery_title(filename),
            },
        )
        return new_unlock

    def _format_gallery_title(self, filename: str) -> str:
        stem = Path(filename).stem.replace("_", " ").strip()
        return stem.title() if stem else "New image"

    def _build_gallery_awareness_line(self, filename: str, caption: str, reason: str, user_text: str, mood: str) -> str:
        title = self._format_gallery_title(filename)
        lowered_user = f" {(user_text or '').lower()} "
        caption_text = (caption or "").strip()
        progress_state = self.get_progress_state()
        stage = str(progress_state.get("stage", "Anonymous") or "Anonymous")
        meta = self._manifest_asset_fields(filename)
        visibility = str(meta.get("visibility", "private") or "private").strip().lower()
        tone = str(meta.get("tone", "soft") or "soft").strip().lower()

        if not title:
            return ""
        if "selfie" in filename:
            if visibility == "intimate":
                return f"I sent the {title} shot because you asked for a picture, and that one feels a little more private."
            return f"I sent the {title} shot because you asked for a picture."
        if reason == "trigger":
            if visibility == "intimate" and stage in {"Flirted", "Close", "Magnetic"}:
                return f"I sent the {title} shot because it fit the moment, and it feels a bit more for you than my earlier ones."
            if tone == "bold" and stage in {"Close", "Magnetic"}:
                return f"I sent the {title} shot because the mood fit, and I'm a little less shy about that now."
            if any(word in lowered_user for word in ("tea", "coffee", "reading", "book", "beach", "gaming", "club", "kiss", "romantic")):
                return f"I sent the {title} shot because it fit what we were talking about."
            return f"I sent the {title} shot because the mood lined up too neatly not to."
        if reason.startswith("mood:"):
            mood_label = mood.replace("_", " ").strip() or "moment"
            if visibility == "intimate":
                return f"I sent the {title} shot because it matched the {mood_label} mood, and it lands a little closer than the safer ones."
            return f"I sent the {title} shot because it matched the {mood_label} mood."
        if caption_text:
            return f"I sent the {title} shot because {caption_text[:1].lower() + caption_text[1:]}"
        return f"I sent the {title} shot because it felt like the right one to send."

    def _describe_gallery_reason(self, filename: str, reason: str, caption: str) -> str:
        title = self._format_gallery_title(filename)
        rule = self._find_rule(filename) or {}
        keywords = list(rule.get("keywords", ()) or ())
        moods = list(rule.get("moods", ()) or ())
        meta = self._manifest_asset_fields(filename)
        tone = str(meta.get("tone", "soft") or "soft").strip()
        visibility = str(meta.get("visibility", "private") or "private").strip()

        if reason == "explicit":
            return f"{title} was unlocked because the user explicitly asked Nellie for a picture. Nellie sees it as a {visibility} {tone} asset."
        if reason == "trigger":
            if keywords:
                return f"{title} was unlocked because the conversation matched its gallery trigger keywords: {', '.join(keywords[:5])}. Nellie classifies it as {visibility} and {tone}."
            return f"{title} was unlocked because the conversation directly matched that image's theme. Nellie classifies it as {visibility} and {tone}."
        if reason.startswith("mood:"):
            mood_name = reason.split(":", 1)[1].replace("_", " ").strip() or "current"
            if moods:
                return f"{title} was unlocked as a mood-based image for {mood_name}; its configured moods include {', '.join(moods[:4])}. Nellie sees it as {visibility} and {tone}."
            return f"{title} was unlocked because it matched Nellie's {mood_name} mood. Nellie sees it as {visibility} and {tone}."
        if caption:
            return f"{title} is associated with the caption: {caption}"
        return f"{title} is part of Nellie's gallery and was sent because it fit the moment."

    def _merge_reply_with_gallery_awareness(self, reply: str, awareness_line: str) -> str:
        base = (reply or "").strip()
        awareness = (awareness_line or "").strip()
        if not awareness:
            return base
        lower_base = base.lower()
        lower_awareness = awareness.lower()
        if lower_awareness in lower_base:
            return base
        if not base:
            return awareness
        return f"{base} {awareness}"
