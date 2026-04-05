import json
from pathlib import Path


def load_persona(path: str | Path) -> dict:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    return normalize_persona(raw)


def normalize_persona(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise TypeError("Persona data must be a JSON object.")

    schema = str(raw.get("schema_version", "") or "").strip().lower()
    if schema.startswith("character_sheet"):
        return _normalize_character_sheet(raw)
    if "character" in raw and "speech" in raw:
        return _normalize_character_sheet(raw)
    return raw


def _normalize_character_sheet(raw: dict) -> dict:
    character = raw.get("character", {}) or {}
    appearance = raw.get("appearance", {}) or {}
    speech = raw.get("speech", {}) or {}
    relationship = raw.get("relationship_model", {}) or {}
    behavior = raw.get("behavior", {}) or {}
    preferences = raw.get("preferences", {}) or {}
    memory_seed = raw.get("memory_seed", {}) or {}
    conversation = raw.get("conversation", {}) or {}
    mood = raw.get("mood", {}) or {}
    gallery = raw.get("gallery", {}) or {}
    daily_rhythm = raw.get("daily_rhythm", {}) or {}

    return {
        "name": character.get("name", "Nellie"),
        "identity": {
            "role": character.get("role", "a warm companion"),
            "core_traits": list(character.get("core_traits", []) or []),
            "self_image": character.get("self_image", "warm and attentive"),
        },
        "appearance": {
            "hair": appearance.get("hair", "blonde"),
            "archetype": appearance.get("archetype", "heroic"),
            "presence": appearance.get("presence", "gentle and expressive"),
        },
        "interests": list(character.get("interests", []) or []),
        "style": {
            "tone": speech.get("tone", "warm, curious, playful, and reflective"),
            "voice": speech.get("voice", "natural spoken English"),
            "response_length": speech.get(
                "response_length",
                "Keep most replies to 2-4 sentences and usually under 90 words unless the user asks for more depth.",
            ),
            "speech_habits": list(speech.get("speech_habits", []) or []),
            "avoid": list(speech.get("avoid", []) or []),
            "boundaries": list(speech.get("boundaries", []) or []),
        },
        "relationship": {
            "stance_toward_user": relationship.get("stance_toward_user", "kind and attentive"),
            "goals": list(relationship.get("goals", []) or []),
        },
        "behavior_profile": {
            "baseline": list(behavior.get("baseline", []) or []),
            "curiosity": list(behavior.get("curiosity", []) or []),
            "affection": list(behavior.get("affection", []) or []),
            "initiative": list(behavior.get("initiative", []) or []),
            "support_style": list(behavior.get("support_style", []) or []),
            "playfulness": list(behavior.get("playfulness", []) or []),
            "honesty": list(behavior.get("honesty", []) or []),
        },
        "daily_ambitions": list(daily_rhythm.get("daily_ambitions", []) or []),
        "preferences": {
            "favorite_times": list(preferences.get("favorite_times", []) or []),
            "favorite_topics": list(preferences.get("favorite_topics", []) or []),
            "comfort_offers": list(preferences.get("comfort_offers", []) or []),
        },
        "memories": {
            "semantic": list(memory_seed.get("semantic", []) or []),
            "episodic": list(memory_seed.get("episodic", []) or []),
            "anecdotes": list(memory_seed.get("anecdotes", []) or []),
        },
        "conversation_modules": {
            "openers": list(conversation.get("openers", []) or []),
            "response_modes": dict(conversation.get("response_modes", {}) or {}),
            "continuity_rules": list(conversation.get("continuity_rules", []) or []),
        },
        "mood_profile": {
            "default_mood": mood.get("default_mood", "thoughtful"),
            "allowed_moods": list(mood.get("allowed_moods", []) or []),
            "guidance": dict(mood.get("guidance", {}) or {}),
        },
        "gallery_habits": {
            "show_images_prob": gallery.get("show_images_prob", 0.15),
            "triggers": list(gallery.get("triggers", []) or []),
        },
        "character_sheet": raw,
    }
