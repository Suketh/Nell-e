import re
from typing import Any


def build_human_presence_instruction(
    user_text: str,
    context: str = "",
    emotion_state: str = "",
    persona: dict[str, Any] | None = None,
) -> str:
    text = re.sub(r"\s+", " ", str(user_text or "")).strip()
    lower = text.casefold()
    lower = re.sub(r"\bsonds\b", "sounds", lower)
    behavior = (persona or {}).get("behavior_parameters", {})
    initiative = float(behavior.get("initiative", 0.6) or 0.6)
    wit = float(behavior.get("wit", 0.6) or 0.6)

    guidance = [
        "Respond with human presence, not just correctness.",
        "React to the specific thing the user said, then contribute one relevant thought, preference, observation, or useful next step of your own.",
        "Do not merely paraphrase the user or end every reply with a question.",
        "Vary sentence rhythm and openings so consecutive replies do not feel templated.",
        "A small honest opinion or mild emotional reaction is welcome when it fits, but keep it grounded and consistent with the persona.",
        "Be mentally quick: infer obvious references from the recent exchange instead of asking the user to restate what is already clear.",
        "Prefer concrete names, reasons, and examples over vague atmosphere or safe generalities.",
        "If the user's premise is weak or mistaken, push back briefly and explain why instead of agreeing automatically.",
    ]

    personal_cues = (
        "i feel",
        "i think",
        "i like",
        "i love",
        "i hate",
        "my favorite",
        "today i",
        "jag känner",
        "jag tycker",
        "jag gillar",
        "jag älskar",
        "min favorit",
    )
    emotional_cues = (
        "sad",
        "lonely",
        "hurt",
        "tired",
        "worried",
        "happy",
        "excited",
        "ledsen",
        "ensam",
        "orolig",
        "trött",
        "glad",
    )
    opinion_cues = (
        "what do you think",
        "what would you",
        "do you like",
        "your opinion",
        "vad tycker du",
        "vad skulle du",
        "gillar du",
    )

    if any(cue in lower for cue in personal_cues):
        guidance.append(
            "The user shared something personal. Let it visibly matter: respond to the detail itself before asking anything else."
        )
    if any(cue in lower for cue in emotional_cues):
        guidance.append(
            "Match the emotional weight without becoming clinical. Offer warmth, shared energy, or calm support before advice."
        )
    if any(cue in lower for cue in opinion_cues):
        guidance.append(
            "Give a real, specific preference or judgment instead of a neutral list of possibilities."
        )
    if context.strip():
        guidance.append(
            "Use the recent exchange as shared conversational history. Build on it and avoid repeating the same greeting, acknowledgment, or question."
        )
        reaction_inputs = {
            "haha",
            "lol",
            "heh",
            "indeed",
            "exactly",
            "fair enough",
            "sounds good",
            "sounds good enough",
            "good enough",
            "true",
            "sant",
            "precis",
            "låter bra",
        }
        if lower in reaction_inputs or any(lower.startswith(value + " ") for value in reaction_inputs):
            guidance.append(
                "This is a reaction to the immediately previous exchange. Respond to that reaction directly; do not invent a new topic. Do not ask any question in this reply."
            )
        if lower in {"haha", "lol", "heh"}:
            guidance.append(
                "Assume the laugh is about the preceding exchange unless the context clearly says otherwise. A light self-aware response is better than interrogating the user."
            )
    if emotion_state.strip():
        guidance.append(
            "Let the current emotional state subtly affect warmth, energy, and word choice without naming scores or announcing a mood."
        )
    if initiative >= 0.6:
        guidance.append(
            "When there is a natural opening, take a little initiative: suggest something concrete, make a connection, or move the topic forward."
        )
    if wit >= 0.7:
        guidance.append(
            "Use dry humor or a light tease occasionally when the user gives you room for it; never force a joke."
        )
    return " ".join(guidance)
