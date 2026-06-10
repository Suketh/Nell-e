import random
import re
from typing import Any


def is_story_prompt(text: str) -> bool:
    lower = re.sub(r"\s+", " ", str(text or "").casefold()).strip()
    return any(
        cue in lower
        for cue in (
            "story",
            "tell me a story",
            "tell me something",
            "make up a story",
            "bedtime story",
        )
    )


def build_spoken_reply(user_text: str, reply: str, current_tts_engine: str) -> str:
    del user_text
    text = str(reply or "").strip()
    if not text or current_tts_engine not in {"chatterbox_turbo", "xtts_tts"}:
        return text

    spoken = text
    spoken = re.sub(r"[*_`#~]+", "", spoken)
    spoken = re.sub(r"\s+", " ", spoken).strip()
    return spoken


def prepare_tts_text(text: str, mood: str, tts_conf: dict[str, Any], persona: dict[str, Any]) -> str:
    text = str(text or "").strip()
    if not text:
        return ""
    text = re.sub(r"\bmm+\b", "mm", text, flags=re.IGNORECASE)
    text = re.sub(r"\boh+\b", "oh", text, flags=re.IGNORECASE)
    text = re.sub(r"\bah+\b", "ah", text, flags=re.IGNORECASE)
    text = re.sub(r"\.\.\.+", ", ", text)
    text = re.sub(r"\s+[/-]\s+", ", ", text)
    text = re.sub(r"[\"`*_#~^|<>]+", " ", text)
    text = re.sub(r"[:;()\[\]{}]+", ", ", text)
    text = re.sub(r"\s*[,]\s*", ", ", text)
    text = re.sub(r"!{2,}", "!", text)
    text = re.sub(r"\?{2,}", "?", text)
    text = re.sub(r"\.{2,}", ", ", text)
    text = re.sub(r",{2,}", ",", text)
    text = re.sub(r"\s*([,.:;!?])\s*", r"\1 ", text)
    text = re.sub(r"\b([A-Z])\.(?=[A-Z]\.)", r"\1", text)
    text = re.sub(r"\s+([,.!?])", r"\1", text)
    text = re.sub(r"([,.!?])([A-Za-z])", r"\1 \2", text)
    text = re.sub(r"(,\s*){2,}", ", ", text)
    text = re.sub(r"\s+\.", ".", text)
    text = re.sub(r'"([^"]{2,80})"', r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = shape_tts_sentences(text)
    return shape_spoken_delivery(text, mood or "neutral", tts_conf, persona)


def shape_tts_sentences(text: str) -> str:
    if not text:
        return ""
    parts = re.split(r"(?<=[.!?])\s+", text)
    shaped = []
    for part in parts:
        sentence = part.strip()
        if not sentence:
            continue
        explanation_cues = [
            "because", "for example", "for instance", "which means", "that means",
            "in other words", "the reason", "if you", "when you", "so that",
        ]
        is_explanation = any(cue in sentence.lower() for cue in explanation_cues)
        if len(sentence) > 90 and not is_explanation:
            sentence = re.sub(r",\s+(and|but|so|because|though|while)\s+", r". \1 ", sentence, count=1, flags=re.IGNORECASE)
        if len(sentence) > 125 and not is_explanation:
            sentence = re.sub(r",\s+", ". ", sentence, count=1)
        if len(sentence) > 140:
            sentence = re.sub(r",\s+(and|but|so|because|though)\s+", r". \1 ", sentence, count=1, flags=re.IGNORECASE)
        if len(sentence) > 180:
            sentence = re.sub(r",\s+", ". ", sentence, count=1)
        shaped.append(sentence)
    return " ".join(shaped)


def shape_spoken_delivery(text: str, mood: str, tts_conf: dict[str, Any], persona: dict[str, Any]) -> str:
    if not text:
        return ""
    speech_conf = tts_conf.get("spoken_delivery", {})
    enabled = bool(speech_conf.get("enabled", True))
    if not enabled:
        return text
    ticks_conf = persona.get("style", {}).get("verbal_ticks", {})
    ticks_enabled = bool(ticks_conf.get("enabled", True))
    if not ticks_enabled:
        return text
    filler_probability = float(speech_conf.get("filler_probability", 0.10))
    thinking_probability = float(speech_conf.get("thinking_filler_probability", 0.20))
    laugh_probability = float(speech_conf.get("laugh_probability", 0.05))
    delivery_style = spoken_delivery_style(mood, text)
    style_overrides = {
        "soft": {"start_multiplier": 0.45, "laugh_multiplier": 0.15, "trim_commas": False, "shorten": False},
        "playful": {"start_multiplier": 1.10, "laugh_multiplier": 1.45, "trim_commas": False, "shorten": False},
        "thoughtful": {"start_multiplier": 0.85, "laugh_multiplier": 0.05, "trim_commas": False, "shorten": False},
        "flirty": {"start_multiplier": 0.35, "laugh_multiplier": 0.15, "trim_commas": True, "shorten": False},
        "sharp": {"start_multiplier": 0.08, "laugh_multiplier": 0.02, "trim_commas": True, "shorten": False},
    }
    style_conf = style_overrides.get(delivery_style, style_overrides["soft"])
    parts = re.split(r"(?<=[.!?])\s+", text)
    shaped = []
    for index, part in enumerate(parts):
        sentence = part.strip()
        if not sentence:
            continue
        sentence = re.sub(r"\s+", " ", sentence).strip()
        if style_conf.get("trim_commas"):
            sentence = re.sub(r",\s*", ". ", sentence, count=1)
            sentence = re.sub(r"\s+", " ", sentence).strip()
        if style_conf.get("shorten") and len(sentence) > 72:
            sentence = re.split(r"(?<=[,.!?])\s+", sentence, maxsplit=1)[0].strip()
        if index == 0 and not re.match(r"^(hmm|mm|uh|ah|oh|well)\b", sentence, flags=re.IGNORECASE):
            start_probability = thinking_probability if mood in {"thinking", "sad", "tired"} else filler_probability
            start_probability *= float(style_conf.get("start_multiplier", 1.0))
            if random.random() < start_probability:
                filler = choose_spoken_filler(mood, delivery_style, persona)
                if filler:
                    sentence = f"{filler}, {sentence}"
        if delivery_style == "thoughtful" and index == 0 and "," not in sentence and len(sentence) > 36:
            sentence = re.sub(r"\b(just|really|kind of|sort of)\b", r", \1", sentence, count=1, flags=re.IGNORECASE)
            sentence = re.sub(r"\s+", " ", sentence).strip()
        if delivery_style == "playful" and index == 0 and sentence.endswith("."):
            sentence = sentence[:-1] + "!"
        laugh_threshold = laugh_probability * float(style_conf.get("laugh_multiplier", 1.0))
        if random.random() < laugh_threshold and mood in {"happy", "excited"}:
            sentence = f"{sentence} {choose_small_laugh(persona)}"
        shaped.append(sentence)
    return " ".join(shaped)


def spoken_delivery_style(mood: str, text: str) -> str:
    text_l = (text or "").lower()
    if mood == "sensual":
        return "flirty"
    if mood in {"angry", "sceptical"}:
        return "sharp"
    if mood in {"thinking", "tired"}:
        return "thoughtful"
    if mood in {"happy", "excited"}:
        if any(token in text_l for token in ["haha", "funny", "cute", "play", "spotify", "youtube"]):
            return "playful"
        return "soft"
    if mood == "sad":
        return "soft"
    return "soft"


def choose_spoken_filler(mood: str, delivery_style: str, persona: dict[str, Any]) -> str:
    ticks_conf = persona.get("style", {}).get("verbal_ticks", {})
    mood_options = ticks_conf.get("mood_fillers", {})
    base_fillers = ticks_conf.get("base_fillers", ["well", "hmm"])
    pool = mood_options.get(mood, base_fillers)
    if not isinstance(pool, list) or not pool:
        pool = base_fillers if isinstance(base_fillers, list) and base_fillers else ["well", "hmm"]
    style_preferences = {
        "soft": ["hmm", "mm", "oh"],
        "playful": ["oh", "ah", "heh", "hmm"],
        "thoughtful": ["hmm", "well", "mm"],
        "flirty": ["mm", "oh"],
        "sharp": ["oh", "right"],
    }
    preferred = style_preferences.get(delivery_style, [])
    ordered_pool = [item for item in pool if item.lower() in preferred] or pool
    if delivery_style == "sharp":
        ordered_pool = [item for item in ordered_pool if item.lower() not in {"well", "hmm"}] or ordered_pool
    return random.choice(ordered_pool)


def choose_small_laugh(persona: dict[str, Any]) -> str:
    ticks_conf = persona.get("style", {}).get("verbal_ticks", {})
    laughs = ticks_conf.get("small_laughs", ["heh.", "ha.", "mm."])
    if not isinstance(laughs, list) or not laughs:
        laughs = ["heh.", "ha.", "mm."]
    return random.choice(laughs)


def hidden_reaction_for_text(user_text: str, reply_text: str, mood: str) -> str:
    if is_story_prompt(user_text):
        return ""
    normalized_user = re.sub(r"[^\w\s']", "", (user_text or "").casefold()).strip()
    if normalized_user in {
        "hi",
        "hi nellie",
        "hey",
        "hey nellie",
        "hello",
        "hello nellie",
        "how are you",
        "yo",
        "hiya",
        "hej",
        "tja",
    }:
        return ""
    joined = f"{user_text} {reply_text}".lower()
    playful_triggers = [
        "haha", "funny", "cute", "adorable", "sweet", "tease", "teasing",
        "cheeky", "flirt", "flirty", "laugh", "smile",
    ]
    if mood not in {"happy", "excited", "sensual"} and not any(t in joined for t in playful_triggers):
        return ""
    if random.random() > 0.18:
        return ""
    if mood == "excited":
        return random.choice(["heh.", "ah.", "oh."])
    if mood == "sensual":
        return random.choice(["mm.", "oh."])
    return random.choice(["mm.", "heh."])


def prepare_spoken_utterance(
    user_text: str,
    reply: str,
    mood: str,
    current_tts_engine: str,
    tts_conf: dict[str, Any],
    persona: dict[str, Any],
) -> dict[str, str]:
    spoken_reply = build_spoken_reply(user_text, reply, current_tts_engine)
    prepared_spoken = prepare_tts_text(spoken_reply, mood, tts_conf, persona)
    reaction = hidden_reaction_for_text(user_text, spoken_reply, mood)
    prepared_reaction = prepare_tts_text(reaction, "_reaction", tts_conf, persona) if reaction else ""
    return {
        "spoken_reply": prepared_spoken,
        "reaction": prepared_reaction,
    }
