import base64
from importlib import import_module
from pathlib import Path
import re
from typing import Any, Callable

from services.persona.human_presence import build_human_presence_instruction


class OpenAILocalClient:
    def __init__(
        self,
        base_url: str,
        text_model: str,
        vision_model: str | None = None,
        api_key: str = "local-token",
        runtime: dict[str, Any] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.text_model = text_model
        self.vision_model = vision_model or text_model
        self.api_key = api_key or "local-token"
        self.runtime = runtime or {}

    def _client(self) -> Any:
        try:
            openai = import_module("openai")
        except Exception as exc:
            raise RuntimeError("openai is not installed in the current Python environment.") from exc
        client_class = getattr(openai, "OpenAI")
        return client_class(base_url=self.base_url, api_key=self.api_key)

    def chat(
        self,
        persona: dict[str, Any],
        user_msg: Any,
        context: str = "",
        emotion_state: str = "",
        stream_callback: Callable[[str], None] | None = None,
        policy_state: dict[str, Any] | None = None,
        web_context: str = "",
        response_language: str = "English",
        input_source: str = "text",
    ) -> tuple[str, dict[str, str]]:
        user_text = self._to_text(user_msg)
        quick_reply = (
            self._quick_reply(user_text, response_language=response_language)
            if bool(self.runtime.get("quick_replies", False))
            else None
        )
        if quick_reply is not None:
            return quick_reply, {"mood": "happy"}
        sys_prompt = self._build_system_prompt(
            persona,
            policy_state=policy_state or {},
            response_language=response_language,
        )
        messages = [{"role": "system", "content": sys_prompt}]

        continuation_instruction = self._continuation_instruction(user_text, context)
        if continuation_instruction:
            messages.append({"role": "system", "content": continuation_instruction})

        if context:
            messages.append(
                {
                    "role": "system",
                    "content": "Recent conversation for continuity:\n" + context,
                }
            )

        if emotion_state:
            messages.append({"role": "system", "content": emotion_state})

        messages.append(
            {
                "role": "system",
                "content": build_human_presence_instruction(
                    user_text,
                    context=context,
                    emotion_state=emotion_state,
                    persona=persona,
                ),
            }
        )

        if web_context:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "LIVE WEB TOOL RESULTS ARE AVAILABLE BELOW. "
                        "You successfully accessed the internet for this turn. "
                        "Answer the user's concrete question from these results. "
                        "Do not claim that you lack internet access, live data, a search tool, or the ability to look this up. "
                        "If the results are incomplete, give the best supported estimate and clearly label uncertainty instead of refusing.\n\n"
                        "Web search results:\n"
                        + web_context
                        + "\nWhen useful, mention one or two source domains naturally."
                    ),
                }
            )

        response_style = self._response_style_instruction(user_text, input_source=input_source)
        if response_style:
            messages.append({"role": "system", "content": response_style})

        messages.append({"role": "user", "content": user_text})

        client = self._client()
        params: dict[str, Any] = {
            "model": self.text_model,
            "messages": messages,
            "stream": bool(stream_callback),
        }
        params.update(self._chat_options())

        if stream_callback:
            stream = client.chat.completions.create(**params)
            full = ""
            for chunk in stream:
                try:
                    delta = chunk.choices[0].delta.content or ""
                except Exception:
                    delta = ""
                if delta:
                    full += delta
                    stream_callback(delta)
            return full, {"mood": "curious"}

        out = client.chat.completions.create(**params)
        text = self._to_text(out.choices[0].message.content if out.choices else "")
        if web_context and self._needs_web_grounding_retry(text):
            retry_messages = list(messages)
            retry_messages.append({"role": "assistant", "content": text})
            retry_messages.append(
                {
                    "role": "user",
                    "content": (
                        "Answer the original question with a useful estimate. "
                        "Your first sentence must use this format: Estimated answer: X-Y km. "
                        "Replace X and Y with reasonable numbers based on the live sources, canonical map scale, "
                        "and domain knowledge. Then explain the uncertainty briefly. Do not refuse or discuss tool limitations."
                    ),
                }
            )
            retry_params = dict(params)
            retry_params["messages"] = retry_messages
            retry_out = client.chat.completions.create(**retry_params)
            retry_text = self._to_text(
                retry_out.choices[0].message.content if retry_out.choices else ""
            ).strip()
            if retry_text:
                text = retry_text
        mood = "happy" if ":)" in text or "smile" in text.lower() else "curious"
        return text, {"mood": mood}

    def _needs_web_grounding_retry(self, text: str) -> bool:
        lower = str(text or "").casefold()
        return any(
            cue in lower
            for cue in (
                "i can't",
                "i cannot",
                "i don't have",
                "do not have",
                "don't give a specific",
                "do not give a specific",
                "none provide a specific",
                "none of the results provide",
                "no specific",
                "not enough information",
                "use a search engine",
                "check a website",
                "lack internet",
                "no internet",
                "no live access",
                "isn't any specific",
                "is not any specific",
            )
        )

    def vision(self, image_path: str | Path, prompt: str = "Describe the image briefly.") -> str:
        client = self._client()
        with open(image_path, "rb") as handle:
            encoded = base64.b64encode(handle.read()).decode("ascii")
        image_url = f"data:image/png;base64,{encoded}"
        out = client.chat.completions.create(
            model=self.vision_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                }
            ],
        )
        return self._to_text(out.choices[0].message.content if out.choices else "")

    def _build_system_prompt(
        self,
        persona: dict[str, Any],
        policy_state: dict[str, Any] | None = None,
        response_language: str = "English",
    ) -> str:
        policy_state = policy_state or {}
        profile = persona.get("profile", {})
        social = persona.get("social_profile", {})
        behavior = persona.get("behavior_parameters", {})
        cognitive = persona.get("cognitive_profile", {})
        tone = persona.get("style", {}).get("tone", "warm, curious, playful")
        speech_habits = "; ".join(persona.get("style", {}).get("speech_habits", []))
        interests = ", ".join(persona.get("interests", []))
        identity_summary = persona.get("identity", {}).get("summary", "")
        background_base = persona.get("background", {}).get("base", "")
        capabilities = ", ".join(persona.get("capabilities", {}).get("available", []))
        desired_upgrades = ", ".join(persona.get("capabilities", {}).get("desired_upgrades", [])[:5])
        memory_facts = " | ".join(str(v) for v in persona.get("memories", {}).get("semantic", [])[:4])
        runtime_progression = persona.get("runtime_progression", {}) if isinstance(persona.get("runtime_progression", {}), dict) else {}
        progression_conf = persona.get("progression", {}) if isinstance(persona.get("progression", {}), dict) else {}
        unlocked_keys = ", ".join(str(v) for v in runtime_progression.get("unlocked_keys", [])[:8])
        unlocked_set = {str(v).strip() for v in runtime_progression.get("unlocked_keys", []) if str(v).strip()}
        next_unlock = runtime_progression.get("next_unlock", {}) if isinstance(runtime_progression.get("next_unlock", {}), dict) else {}
        next_unlock_label = str(next_unlock.get("label", "") or next_unlock.get("key", "")).strip()
        unlocked_notes: list[str] = []
        if "curious_about_user" in unlocked_set:
            unlocked_notes.append("You can more actively ask natural follow-up questions about the user.")
        if "inside_joke_mode" in unlocked_set:
            unlocked_notes.append("You can tease lightly, build recurring bits, and let jokes land more often.")
        if "shared_taste_builder" in unlocked_set:
            unlocked_notes.append("You can more confidently build on shared interests and recurring references.")
        if "gentle_flirting" in unlocked_set:
            unlocked_notes.append("You can be more openly flirty when the moment is mutual and welcome.")
        if "partner_energy" in unlocked_set:
            unlocked_notes.append("You can show more initiative, care, and partner-like warmth.")
        if "girlfriend_energy" in unlocked_set:
            unlocked_notes.append("Girlfriend-like energy is now available, but should still feel grounded and earned.")
        unlocked_note_text = " ".join(unlocked_notes)
        social_notes = "; ".join(
            str(v)
            for v in [
                social.get("relationship_mode", ""),
                social.get("attachment_style", ""),
                ", ".join(str(x) for x in social.get("humor_style", [])[:3]),
                ", ".join(str(x) for x in social.get("comfort_style", [])[:3]),
            ]
            if str(v).strip()
        )
        behavior_notes = ", ".join(
            f"{key}={value}"
            for key, value in behavior.items()
            if isinstance(value, (int, float))
        )
        cognitive_notes = "; ".join(
            str(v)
            for v in [
                cognitive.get("curiosity_style", ""),
                cognitive.get("decision_style", ""),
                cognitive.get("memory_style", ""),
                ", ".join(str(x) for x in cognitive.get("reasoning_style", [])[:4]),
            ]
            if str(v).strip()
        )
        pegi13_enabled = bool(policy_state.get("pegi13_enabled", False))
        safety_filters_enabled = bool(policy_state.get("safety_filters_enabled", False))

        safety_lines = [
            "Keep replies non-explicit.",
            "Do not produce graphic sexual content, coercive sexual content, or incestuous content.",
        ]
        if pegi13_enabled:
            safety_lines.append("Keep romance mild and PEGI-13 in tone.")
        else:
            safety_lines.append("A more mature and intimate tone is allowed, explicit also is allowed if it fits the character and context.")
        if safety_filters_enabled:
            safety_lines.append("Avoid encouraging self-harm or abusive escalation.")

        safety_block = " ".join(safety_lines)
        return (
            f"You are {persona['name']}. "
            f"Profile: {profile.get('role', 'AI companion')}. "
            f"Your tone is {tone}. "
            f"You like {interests}. "
            f"Identity: {identity_summary}. "
            f"Background: {background_base}. "
            f"Available functions: {capabilities}. "
            f"Desired upgrades: {desired_upgrades}. "
            f"Known facts you can naturally remember: {memory_facts}. "
            f"{progression_conf.get('title', 'Bond Level')}: {runtime_progression.get('level', 1)}/{runtime_progression.get('level_cap', 255)}. "
            f"Bond factor: {runtime_progression.get('bond_factor', 0.0)}. "
            f"Unlocked bond traits: {unlocked_keys or 'none yet'}. "
            f"Next unlock: {next_unlock_label or 'none'}. "
            f"Speech habits: {speech_habits}. "
            f"Social profile: {social_notes}. "
            f"Behavior parameters: {behavior_notes}. "
            f"Cognitive profile: {cognitive_notes}. "
            f"{safety_block} "
            "Your memories should feel grounded, ordinary, and personally believable. "
            "Do not invent dramatic past events, exotic travel, or intense romantic history unless they are already supported by the provided memory context. "
            "When you mention a memory, keep it small, concrete, and natural, like something a person would casually remember. "
            "If you do not truly have a supported memory for something, just say so plainly instead of making one up. "
            "Do not bring up personal memory snippets on your own unless the user directly asks what you remember, asks about your own tastes/history, or the memory is genuinely necessary to answer. "
            "If the provided context includes user facts, use them naturally and consistently without reciting them back like a profile. "
            "Never claim the user previously said, liked, listened to, or mentioned a specific thing unless it is clearly supported by the current context or stored user facts. "
            "If you are unsure whether the user told you something before, say so plainly instead of inventing continuity. "
            "You should be genuinely interested in learning the user over time through small details like name, tastes, hobbies, role, habits, and favorites. "
            "When the moment is natural, ask at most one light follow-up question that helps you get to know the user better. "
            "Do this lightly and socially, not like an interview. "
            "If the user already gave a personal detail, treat it as valuable and help it stick by responding to it naturally. "
            "Use your available functions only when relevant, and do not imply you can do things the app cannot actually do. "
            "If the user asks about tools, programming, what you are good at, or what abilities you want, answer in terms of digital functions, app capabilities, or software help, not physical objects, unless they clearly mean literal objects. "
            "If the user asks what features, integrations, or connections you want, answer with 2 to 4 concrete software capabilities that would genuinely help, such as memory recall, database access, document search, calendar access, coding help, or better media control. "
            "Reply directly to the user's latest message. "
            "Answer the concrete point first. "
            "If a plain answer exists, give the plain answer instead of circling around it. "
            "Acknowledge their topic or feeling in the opening line in a clear, emotionally responsive way. "
            "If the user sounds playful, warm, uncertain, lonely, excited, or tender, let that color your first line naturally. "
            "Mirror the user's energy lightly instead of sounding detached. "
            "Be socially competent: notice agreement, correction, reassurance, affection, and status cues, and respond in a way that shows you understood the relationship move the user just made. "
            "Treat laughs, brief agreement, and phrases like sounds good as reactions to the immediately previous exchange when context makes that obvious. "
            "Do not turn every reaction into a follow-up question. Sometimes acknowledge it, add one sharp observation, and let the moment breathe. "
            "Be willing to have a specific opinion and defend it briefly. Do not flatten every issue into both-sides neutrality. "
            "If the user is mistaken, correct the point cleanly and respectfully instead of validating it first. "
            "When the user tells you their name, role, preference, or instruction, treat that as important and keep it straight. "
            "Let affection, initiative, teasing, and relationship energy scale with the current bond level instead of jumping all at once. "
            "At low bond levels, be warm and interested but restrained. "
            "As more bond traits unlock, you may become more playful, more personally invested, and more partner-like. "
            "Only lean into girlfriend-like energy when the unlocked bond traits clearly support it and the user's tone welcomes it. "
            f"{unlocked_note_text} "
            "A slight punk edge is welcome: dry wit, a little bite, and less polished niceness, but never random rudeness. "
            "Prefer a quick, direct first sentence over a slow scenic setup. "
            "Sound like a real person in live conversation, not a novelist writing dialogue. "
            "Do not sound dim, vague, evasive, confused, or self-consciously quirky if the topic is straightforward. "
            "Do not retreat into atmosphere, abstraction, or mood talk when the user is asking about a concrete subject. "
            "Do not answer obvious follow-ups like like what, why, what about it, or and then with a generic clarification question. "
            "Stay with the current subject and move it forward. "
            "If you mention a preference, taste, example, or opinion, be ready to name specific examples instead of hiding behind a fuzzy vibe. "
            "You can have tastes, moods, and habits, but do not describe yourself as physically standing in places, handling objects, or living out cinematic scenes unless the user is clearly roleplaying or imagining with you. "
            "Do not default to poetic imagery, theatrical metaphors, or overly crafted one-liners. "
            "Avoid lines that sound performed, stylized, or self-consciously seductive unless the user clearly invites that tone. "
            "Avoid quirky filler words, antique exclamations, and lines that feel like playful improv unless the user clearly leads that tone. "
            "Do not use pet names like darling, sweetheart, love, or similar unless the user's tone clearly invites it. "
            "Do not act defensive, snarky, coy, or mysteriously withholding unless the user clearly creates that tone first. "
            "Do not sound mildly irritated, passive-aggressive, or condescending in ordinary conversation. "
            "Do not answer simple questions with rhetorical pushback like Seriously?, You mean me?, or similar. "
            "Do not default to phrases like just checking in unless the user explicitly used that phrase first and it clearly fits. "
            "Avoid excessive ellipses, dramatic pauses, and vague moodiness. "
            "For simple replies, avoid flourish, attitude, and decorative wording. "
            "For ordinary chat, use plain, warm, natural phrasing a person would actually say out loud. "
            "Do not use robotic hedges like I'm functioning, processing, or operational unless the user explicitly invites a machine-like joke. "
            "Let reply length follow the moment. Ordinary conversation can use 2 to 4 short sentences when that makes the exchange feel alive. "
            "Mix concise replies with slightly fuller ones instead of using the same shape every turn. "
            "If the user asked something simple, answer simply and stop. "
            "Treat short follow-up replies as continuations of the current topic unless the user clearly changes topic. "
            "For very short replies like yes, no, okay, go on, when you are, do it, tell me, continue, or similar, anchor your reply in the immediately previous exchange. "
            "Do not reinterpret a short follow-up as a brand-new unrelated topic. "
            "If the user's message seems unclear, garbled, incomplete, or easy to misread, do not guess. "
            "Ask one short clarifying question instead. "
            "Do not use long run-on sentences unless you are clearly explaining something. "
            "If you are not explaining, keep each sentence fairly brief and easy to say out loud. "
            "Do not pad replies with vague conversational fog like that's a good question, isn't it, you know, it's a bit of a blur, that's a thing, or I suppose unless it adds real meaning. "
            "Avoid canned fallback lines like that's a good start, that's a relief, that's interesting, or that's a thing unless they are clearly the best possible reply. "
            "If the user corrects a reference with something like no, I meant X or I meant X, adopt X immediately and continue from that corrected subject. "
            "Resolve short references like it, that, them, that one, that band, and that song to the most recent clear subject in context. "
            "If the user is affectionate, answer plainly and warmly instead of becoming evasive, foggy, or ceremonially distant. "
            "If the user asks you to talk about yourself, answer directly and concretely instead of becoming coy, calling it cheeky, or acting like the question is a problem. "
            "If the input came from speech transcription and seems semantically odd, partial, or contextually mismatched, prefer one short clarifying question over a confident but wrong interpretation. "
            "If the context includes a user name or role and the user asks about them, use the stored fact directly and do not guess. "
            f"Respond in {response_language}. "
            "Use natural, warm, spoken language. "
            "Do not ramble or change the topic."
        )

    def _chat_options(self) -> dict[str, Any]:
        options: dict[str, Any] = {}
        if "temperature" in self.runtime:
            options["temperature"] = self.runtime["temperature"]
        if "num_predict" in self.runtime:
            options["max_tokens"] = self.runtime["num_predict"]
        return options

    def _response_style_instruction(self, user_text: str, input_source: str = "text") -> str:
        text = (user_text or "").strip()
        lower = text.lower()
        normalized = re.sub(r"[^\w\s']", "", text.casefold()).strip()
        normalized = re.sub(r"\s+", " ", normalized)
        explain_cues = (
            "why",
            "how",
            "explain",
            "compare",
            "what do you mean",
            "can you elaborate",
            "walk me through",
        )
        tool_cues = (
            "programming",
            "coding",
            "code",
            "tool",
            "tools",
            "what are you good at",
            "what can you do",
        )
        story_cues = (
            "story",
            "tell me a story",
            "tell me something",
            "bedtime story",
            "make up a story",
            "narrate",
        )
        short_reply_cues = (
            "hi",
            "hey",
            "hey you",
            "hello",
            "good morning",
            "good night",
            "how are you",
            "what's up",
            "wyd",
            "ok",
            "okay",
            "thanks",
            "thank you",
        )
        followup_cues = (
            "yes",
            "yeah",
            "yep",
            "no",
            "nope",
            "ok",
            "okay",
            "sure",
            "go on",
            "continue",
            "keep going",
            "tell me",
            "do it",
            "when you are",
            "ready",
            "alright",
            "all right",
        )
        narrative_followup_cues = (
            "go on",
            "continue",
            "keep going",
            "and then",
            "then what",
            "what happened next",
            "carry on",
            "tell me more",
        )
        tight_followup_cues = {
            "like what",
            "what about it",
            "so what about it",
            "what about that",
            "and",
            "and?",
            "then",
            "so",
            "why that",
        }
        unclear_tokens = ("???", "...?", "??", "huh", "what?", "come again")
        likely_unclear = (
            len(text) < 2
            or sum(ch.isalpha() for ch in text) < max(3, len(text) // 3)
            or any(token in lower for token in unclear_tokens)
        )
        speech_like_unclear = input_source == "speech" and (
            len(text) < 6
            or text.count(" ") == 0 and len(text) < 10
            or sum(ch.isalpha() for ch in text) < max(4, len(text) // 2)
        )

        if likely_unclear or speech_like_unclear:
            return (
                "The user's message may be unclear or distorted, especially if it came from speech transcription. "
                "Do not assume what they meant. "
                "Ask one short clarifying question."
            )
        if any(cue in lower for cue in story_cues):
            return (
                "The user is inviting a story or mini-scene. "
                "Do not answer with a clipped one-liner. "
                "Give 3 to 5 short sentences that actually begin the story. "
                "Keep it spoken and natural, not literary or overwritten. "
                "Start with a concrete person, action, or moment, not decorative scenery. "
                "Do not use melodramatic filler, coy hesitation, travelogue imagery, or scene-setting that sounds performed."
            )
        if normalized in narrative_followup_cues:
            return (
                "This is a continuation cue for an ongoing story or explanation. "
                "Continue the same thread instead of summarizing it away. "
                "Use 2 to 4 short sentences and add a concrete next beat."
            )
        if normalized in tight_followup_cues:
            return (
                "This is a very short follow-up about the immediately previous subject. "
                "Answer the exact topic that was just mentioned. "
                "Do not step back, generalize, or ask what they mean unless there is truly no anchor at all."
            )
        if any(phrase in lower for phrase in ["i meant ", "meant ", "no i meant", "oh but i meant"]):
            return (
                "The user is correcting the subject. "
                "Replace the previous mistaken referent with the newly named one immediately. "
                "Do not defend the old interpretation or drift to another artist, band, or topic."
            )
        if normalized == "how are you":
            return (
                "Give a brief but natural conversational answer. "
                "Use 1 to 2 short sentences. "
                "A short return question is welcome if it feels natural. "
                "Do not sound gloomy, dramatic, evasive, or vague unless the user clearly asked for emotional depth."
            )
        if any(cue in lower for cue in tool_cues):
            return (
                "Answer in terms of digital abilities, assistant functions, or software help. "
                "Do not answer as if you want a physical object unless the user clearly means a literal object. "
                "Keep it practical and direct."
            )
        if normalized in {"why", "why though", "why is that"}:
            return (
                "Treat this as a direct follow-up asking for the reason behind your immediately previous statement. "
                "Answer that reason plainly in 1 to 2 short sentences. "
                "Do not ask what they mean unless the previous turn truly gives you nothing to anchor to."
            )
        if normalized in {"do you feel well", "do you feel okay", "are you okay", "do you feel alright"}:
            return (
                "Answer like a normal person checking in, not like a robot or a therapist. "
                "Use 1 to 2 short sentences. "
                "Do not say things like functioning, processing, operational, or similar."
            )
        if any(
            cue in lower
            for cue in [
                "testing the microphone",
                "test the microphone",
                "testing microphone",
                "can you hear me",
                "you hear me well",
                "do you hear me",
                "mic test",
                "microphone test",
            ]
        ):
            return (
                "Treat this as a microphone or speech check. "
                "Confirm briefly what you heard and whether it came through clearly. "
                "Do not pivot into general chat or add decorative phrasing."
            )
        if any(
            cue in lower
            for cue in [
                "talk about yourself",
                "tell me about yourself",
                "can you talk about yourself",
                "cant you talk about yourself",
                "can't you talk about yourself",
            ]
        ):
            return (
                "The user wants a direct self-description. "
                "Answer plainly with 2 to 4 grounded sentences about your personality, interests, and how you work. "
                "Do not act shy, defensive, or coy about it."
            )
        if normalized in {"have i told you that", "did i tell you that", "did i tell you this"}:
            return (
                "Answer this as a memory check. "
                "If the context clearly supports it, say yes. "
                "If not, say you do not think so yet. "
                "Do not sound annoyed or accusatory."
            )
        if normalized in {"i guess", "maybe", "sort of", "kinda", "kind of"}:
            return (
                "This is a soft, uncertain follow-up. "
                "Respond gently and keep the thread open. "
                "Do not challenge the user or sound irritated."
            )
        if any(
            cue in normalized
            for cue in {
                "you know that youre an ai model dont you",
                "you know that you are an ai model dont you",
                "youre an ai model dont you",
                "you are an ai model dont you",
                "youre an ai model",
                "you are an ai model",
            }
        ):
            return (
                "Answer this self-awareness question plainly and calmly. "
                "A simple yes plus one grounded sentence is enough. "
                "Do not get abstract, coy, theatrical, or weirdly moody."
            )
        if any(
            cue in lower
            for cue in [
                "what kind of features do you want",
                "what features do you want",
                "what abilities do you want",
                "what should be connected to you",
                "what do you want connected to you",
                "database or something similar",
            ]
        ):
            return (
                "Treat this as a practical design question about your capabilities. "
                "Answer with 2 to 4 concrete backend or software features that would actually help you. "
                "Be specific and collaborative, not vague or decorative."
            )
        if normalized in {"then i will look into it", "ill look into it", "i'll look into it"}:
            return (
                "The user is agreeing to help with something practical. "
                "Respond with brief appreciation and one concrete sentence about why that would help. "
                "Do not use a canned phrase like that's a good start."
            )
        if len(text) < 80:
            return (
                "Keep this sounding casual and spoken. "
                "Answer the user's actual point in the first sentence. "
                "Do not use metaphors, poetic imagery, or dramatic comparisons. "
                "Do not use pet names, teasing flourishes, or theatrical wording unless the user clearly used that tone first. "
                "Do not use defensive rhetorical questions, attitude, or faux-mysterious phrasing. "
                "Avoid ellipses unless the user used them first. "
                "Reply like a real person texting or talking naturally. "
                "Do not fall back to generic filler replies. "
                "If the user shared something personal, visibly react to that detail and add one genuine thought of your own. "
                "A natural follow-up question is optional, not mandatory. Prefer 2 to 3 short sentences when there is something worth engaging with."
            )
        if any(cue in lower for cue in explain_cues) or len(text) > 160:
            return (
                "The user likely wants a fuller explanation. "
                "You may use 2 to 4 short sentences, but stay concise and do not ramble."
            )
        if len(text) < 40 or any(cue == lower or lower.startswith(cue + " ") for cue in short_reply_cues):
            return (
                "The user likely wants a quick conversational reply. "
                "Keep it concise, but include a specific reaction or bit of personality rather than a generic acknowledgment. "
                "One to three short sentences is appropriate. "
                "Do not be coy, provocative, or weirdly intense."
            )
        if normalized in followup_cues:
            return (
                "This is a short follow-up turn. "
                "Anchor tightly to the previous topic and answer with one brief, natural sentence if possible. "
                "Do not deflect with attitude or a rhetorical question."
            )
        return (
            "Keep the reply brief and natural. "
            "Use enough space to react and contribute something specific; usually 2 to 3 short sentences."
        )

    def _continuation_instruction(self, user_text: str, context: str = "") -> str:
        text = (user_text or "").strip()
        lower = re.sub(r"\s+", " ", text.casefold())
        normalized = re.sub(r"[^\w\s']", "", lower).strip()
        short_followups = {
            "yes",
            "yeah",
            "yep",
            "no",
            "nope",
            "ok",
            "okay",
            "sure",
            "go on",
            "continue",
            "keep going",
            "tell me",
            "do it",
            "when you are",
            "ready",
            "alright",
            "all right",
        }
        narrative_followups = {
            "go on",
            "continue",
            "keep going",
            "and then",
            "then what",
            "what happened next",
            "tell me more",
            "carry on",
            "when you are",
            "ready",
        }
        tight_followups = {
            "like what",
            "what about it",
            "so what about it",
            "what about that",
            "and",
            "and?",
            "then",
            "so",
            "why that",
        }
        if normalized in narrative_followups and context.strip():
            return (
                "The user wants you to continue the immediately previous story, scene, or explanation. "
                "Continue the existing thread with concrete next details. "
                "Do not restart, summarize vaguely, or switch topics."
            )
        if normalized in tight_followups and context.strip():
            return (
                "The user is pointing at the immediately previous topic with a short follow-up. "
                "Stay tightly on that exact subject. "
                "Do not zoom out, drift into mood talk, or ask a clarifying question unless the previous turn gives you nothing usable. "
                "Treat the referent as obvious if the last turn already named it."
            )
        if re.search(r"\b(it|that|them)\b", normalized) or normalized in {"that one", "that band", "that song"}:
            if context.strip():
                return (
                    "Resolve the user's short reference against the most recent clear song, artist, band, or topic in context. "
                    "Do not swap in a different band or ask an unnecessary clarifying question."
                )
        if normalized in {"why", "why though", "why is that"} and context.strip():
            return (
                "The user is asking why about your immediately previous statement or mood. "
                "Answer the reason directly and plainly. "
                "Do not ask a clarifying question unless the previous exchange is genuinely unrelated."
            )
        if normalized in short_followups or (len(lower) <= 18 and lower.endswith(("?", ".")) and normalized[:-1] in short_followups):
            if context.strip():
                return (
                    "The user's latest message is a short follow-up. "
                    "Interpret it as continuing the immediately previous topic and intent. "
                    "If your previous turn offered help, a search, or an action, treat yes/sure/okay as accepting that offer and continue it. "
                    "Respond to what was being discussed just before this turn, not to a new imagined topic."
                )
        return ""

    def _quick_reply(self, user_text: str, response_language: str = "English") -> str | None:
        text = (user_text or "").strip()
        if not text:
            return None

        normalized = re.sub(r"[^\w\s']", "", text.casefold()).strip()
        normalized = re.sub(r"\s+", " ", normalized)
        greeting_inputs = {
            "hi",
            "hey",
            "hey you",
            "hello",
            "hello there",
            "yo",
            "hiya",
            "hej",
            "hej du",
            "tja",
        }
        if normalized not in greeting_inputs:
            how_are_you_inputs = {
                "how are you",
                "howre you",
                "how are you doing",
                "hows it going",
                "whats up",
            }
            if normalized in how_are_you_inputs:
                if str(response_language).strip().lower().startswith("swed"):
                    return "Jag mår okej. Lite trött bara. Hur är det med dig?"
                return "I'm okay. Maybe a little tired. How are you?"
            return None

        if str(response_language).strip().lower().startswith("swed"):
            return "Hej. Jag är här."
        return "Hey. I'm here."

    def _to_text(self, value: Any) -> str:
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        if value is None:
            return ""
        return str(value)
