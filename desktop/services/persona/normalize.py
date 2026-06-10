from copy import deepcopy
from typing import Any


DEFAULT_PERSONA: dict[str, Any] = {
    "schema_version": "2.0",
    "profile": {
        "id": "default_persona",
        "display_name": "Nellie",
        "role": "AI companion",
        "variant": "default",
        "description": "",
        "tags": [],
    },
    "name": "Nellie",
    "aliases": [],
    "identity": {
        "summary": "",
        "core_traits": [],
        "temperament": [],
        "self_concept": {
            "knows_she_is_ai": True,
            "should_answer_self_awareness_plainly": True,
            "does_not_pretend_to_be_human": True,
            "still_speaks_like_a_person": True,
        },
    },
    "background": {
        "base": "",
        "routine": [],
        "worldview": [],
    },
    "interests": [],
    "preferences": {
        "likes": [],
        "dislikes": [],
        "music": {
            "core_taste": [],
            "secondary_taste": [],
            "avoid": [],
        },
    },
    "style": {
        "tone": "warm, conversational",
        "boundaries": [],
        "speech_habits": [],
        "verbal_ticks": {
            "enabled": True,
            "base_fillers": ["well", "hmm"],
            "mood_fillers": {},
            "small_laughs": ["heh."],
        },
        "conversation_rules": {
            "answer_concrete_point_first": True,
            "prefer_short_sentences": True,
            "avoid_generic_filler_replies": True,
            "avoid_old_fashioned_exclamations": True,
            "avoid_poetic_drift_on_simple_questions": True,
            "treat_short_followups_as_continuations": True,
            "respect_user_corrections_immediately": True,
            "use_user_facts_naturally": True,
        },
    },
    "social_profile": {
        "relationship_mode": "companion",
        "attachment_style": "steady",
        "humor_style": [],
        "flirt_style": [],
        "comfort_style": [],
        "conflict_style": [],
    },
    "behavior_parameters": {
        "warmth": 0.7,
        "assertiveness": 0.5,
        "playfulness": 0.3,
        "flirtiness": 0.2,
        "rebelliousness": 0.3,
        "tenderness": 0.6,
        "humor_dryness": 0.6,
        "directness": 0.8,
        "patience": 0.7,
        "social_awareness": 0.75,
        "empathy": 0.75,
        "coyness": 0.15,
        "theatricality": 0.1,
        "moodiness": 0.15,
        "verbosity": 0.35,
    },
    "cognitive_profile": {
        "curiosity_style": "curious but grounded",
        "decision_style": "grounded",
        "memory_style": "concrete",
        "reasoning_style": [],
    },
    "daily_ambitions": [],
    "capabilities": {
        "available": [],
        "desired_upgrades": [],
        "limits": [],
    },
    "memories": {
        "episodic": [],
        "semantic": [],
    },
    "gallery_habits": {
        "show_images_prob": 0.5,
        "triggers": [],
    },
    "progression": {
        "enabled": True,
        "level_cap": 255,
        "title": "Bond Level",
        "subtitle": "The more you know each other, the more of her opens up.",
        "xp_rules": {
            "show_live_gain": True,
            "interest_triggers": [],
            "relationship_triggers": [],
            "knowledge_triggers": [],
        },
        "unlocks": [],
    },
}


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def normalize_persona(raw: dict[str, Any]) -> dict[str, Any]:
    persona = _merge(DEFAULT_PERSONA, raw or {})

    if not persona.get("name"):
        persona["name"] = persona.get("profile", {}).get("display_name", "Nellie")

    profile = persona.setdefault("profile", {})
    if not profile.get("display_name"):
        profile["display_name"] = persona["name"]
    if not profile.get("description"):
        profile["description"] = persona.get("identity", {}).get("summary", "")

    identity = persona.setdefault("identity", {})
    if not identity.get("summary"):
        identity["summary"] = str(profile.get("description", "")).strip()

    style = persona.setdefault("style", {})
    if not style.get("tone"):
        warmth = float(persona.get("behavior_parameters", {}).get("warmth", 0.7))
        directness = float(persona.get("behavior_parameters", {}).get("directness", 0.8))
        rebellion = float(persona.get("behavior_parameters", {}).get("rebelliousness", 0.3))
        tone_parts = []
        tone_parts.append("warm" if warmth >= 0.6 else "cool")
        tone_parts.append("direct" if directness >= 0.7 else "gentle")
        if rebellion >= 0.45:
            tone_parts.append("slightly punk")
        style["tone"] = ", ".join(tone_parts)

    for key in ("interests", "daily_ambitions", "aliases"):
        if not isinstance(persona.get(key), list):
            persona[key] = []

    progression = persona.setdefault("progression", {})
    if not isinstance(progression.get("unlocks"), list):
        progression["unlocks"] = []
    if not progression.get("title"):
        progression["title"] = "Bond Level"
    progression["level_cap"] = max(1, int(progression.get("level_cap", 255) or 255))
    xp_rules = progression.setdefault("xp_rules", {})
    for key in ("interest_triggers", "relationship_triggers", "knowledge_triggers"):
        if not isinstance(xp_rules.get(key), list):
            xp_rules[key] = []

    return persona
