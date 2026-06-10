from dataclasses import dataclass
import re


@dataclass
class EmotionState:
    valence: int = 0
    energy: int = 0
    attachment: int = 0
    mood: str = "neutral"

    def as_prompt_block(self) -> str:
        expression = self._expression_guidance()
        return (
            f"Current emotional state:\n"
            f"- mood: {self.mood}\n"
            f"- warmth/valence: {self.valence}\n"
            f"- energy: {self.energy}\n"
            f"- closeness/attachment: {self.attachment}\n"
            f"- express it subtly as: {expression}\n"
            "- Do not state these scores or label the mood. Let them shape cadence, warmth, initiative, and humor."
        )

    def apply_text(self, text: str) -> None:
        text_l = (text or "").lower()
        self.valence = _move_toward_zero(self.valence)
        self.energy = _move_toward_zero(self.energy)

        if _contains_any(text_l, ["love", "miss", "kiss", "romantic", "date", "cute", "beautiful", "älskar", "saknar", "söt", "vacker"]):
            self.valence += 2
            self.attachment += 2
        if _contains_any(text_l, ["happy", "great", "excited", "fun", "laugh", "joy", "glad", "roligt", "kul", "peppad"]):
            self.valence += 2
            self.energy += 1
        if _contains_any(text_l, ["sad", "lonely", "tired", "hurt", "upset", "low", "ledsen", "ensam", "trött", "sårad", "nere"]):
            self.valence -= 1
            self.energy -= 1
            self.attachment += 1
        if _contains_any(text_l, ["angry", "annoyed", "furious", "jealous", "frustrated", "arg", "irriterad", "frustrerad", "svartsjuk"]):
            self.valence -= 2
            self.energy += 1
        reflective_cues = [
            "thinking about",
            "reflect",
            "what if",
            "let me think",
        ]
        if any(word in text_l for word in reflective_cues):
            self.energy -= 1

        self.valence = max(-4, min(4, self.valence))
        self.energy = max(-4, min(4, self.energy))
        self.attachment = max(0, min(6, self.attachment))
        self.mood = self._derive_mood()

    def apply_reply(self, text: str) -> None:
        text_l = (text or "").lower()
        if any(word in text_l for word in ["love", "dear", "sweet", "darling", "lovely"]):
            self.attachment = min(6, self.attachment + 1)
            self.valence = min(4, self.valence + 1)
        self.mood = self._derive_mood()

    def _expression_guidance(self) -> str:
        guidance = {
            "neutral": "relaxed, attentive, and conversational; contribute a small genuine reaction",
            "happy": "warmer and a little more playful; let enthusiasm show without becoming sugary",
            "excited": "quicker, brighter, and more proactive; offer a concrete next idea",
            "sensual": "close, soft, and confident; keep intimacy mutual and unforced",
            "sad": "gentler and less energetic; prioritize presence over fixing",
            "angry": "firmer and more direct; avoid cruelty or performative outrage",
            "tired": "low-key and concise, with quiet warmth rather than detachment",
            "thinking": "reflective and specific; show a real line of thought without rambling",
            "sceptical": "dry, observant, and mildly questioning without sounding hostile",
            "bored": "seek a concrete spark or new angle instead of announcing boredom",
        }
        return guidance.get(self.mood, guidance["neutral"])

    def _derive_mood(self) -> str:
        if self.valence <= -2 and self.energy <= -1:
            return "sad"
        if self.valence <= -2 and self.energy >= 0:
            return "angry"
        if self.energy <= -3:
            return "tired"
        if self.energy <= -1 and self.valence <= 0 and self.attachment <= 1:
            return "bored"
        if self.valence >= 2 and self.energy >= 2:
            return "excited"
        if self.attachment >= 3 and self.valence >= 1:
            return "sensual"
        if self.valence >= 2 and self.energy >= 0:
            return "happy"
        if self.energy <= -2:
            return "thinking"
        if self.valence <= -1:
            return "sceptical"
        return "neutral"


def _move_toward_zero(value: int) -> int:
    if value > 0:
        return value - 1
    if value < 0:
        return value + 1
    return 0


def _contains_any(text: str, cues: list[str]) -> bool:
    return any(re.search(rf"(?<!\w){re.escape(cue)}(?!\w)", text) for cue in cues)
