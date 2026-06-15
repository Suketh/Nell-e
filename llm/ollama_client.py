import json
import re
from datetime import datetime

import requests


class OllamaClient:
    MOOD_PATTERNS = {
        "happy": [
            r"\bhappy\b",
            r"\bglad\b",
            r"\bdelight(ed)?\b",
            r"\bexcited\b",
            r"\bwonderful\b",
            r"\blove\b",
            r"\bsmile\b",
            r"\bbeautiful\b",
            r"\byay\b",
            r"\baha\b",
            r"\badorable\b",
            r"\bmy dear\b",
            r"\bi like that\b",
        ],
        "sad": [
            r"\bsad\b",
            r"\bsorry\b",
            r"\bthat sounds hard\b",
            r"\bi'?m here with you\b",
            r"\bhurting\b",
            r"\blonely\b",
            r"\bgrief\b",
            r"\btears?\b",
            r"\bmiss you\b",
            r"\bheartbroken\b",
            r"\bwish i could\b",
            r"\bthat must hurt\b",
        ],
        "thoughtful": [
            r"\bhmm\b",
            r"\bperhaps\b",
            r"\bmaybe\b",
            r"\bi wonder\b",
            r"\bthinking\b",
            r"\breflect\b",
            r"\bcurious\b",
            r"\blet me think\b",
            r"\bwhat if\b",
            r"\bit seems to me\b",
            r"\bi think\b",
            r"\bthere'?s something about\b",
        ],
        "annoyed": [
            r"\bannoy(ed|ing)?\b",
            r"\bfrustrat(ed|ing)?\b",
            r"\bugh\b",
            r"\bsigh\b",
            r"\bseriously\b",
            r"\bcome on\b",
            r"\bawkward\b",
            r"\btedious\b",
            r"\birritat(ed|ing)?\b",
            r"\bwhat a mess\b",
        ],
        "angry": [
            r"\bangry\b",
            r"\bmad\b",
            r"\bfurious\b",
            r"\bthat'?s not okay\b",
            r"\bunacceptable\b",
            r"\bnever\b",
            r"\bstop\b",
            r"\boutrage(d|ous)?\b",
            r"\bi hate that\b",
            r"\bno one should\b",
        ],
        "tired": [
            r"\btired\b",
            r"\bexhaust(ed|ing)?\b",
            r"\bdrained\b",
            r"\bsleepy\b",
            r"\bneed rest\b",
            r"\bbed\b",
            r"\blong day\b",
            r"\bworn out\b",
            r"\blow energy\b",
            r"\bheavy day\b",
        ],
    }

    MOOD_WEIGHTS = {
        "happy": 2,
        "sad": 2,
        "thoughtful": 2,
        "annoyed": 2,
        "angry": 3,
        "tired": 2,
    }

    def __init__(self, host, text_model, vision_model=None, connect_timeout=10, read_timeout=120):
        self.host = host.rstrip("/")
        self.text_model = text_model
        self.vision_model = vision_model or text_model
        self.connect_timeout = max(1, float(connect_timeout or 10))
        self.read_timeout = max(5, float(read_timeout or 120))
        self._session = requests.Session()
        self._system_prompt_cache = {}

    def _post(self, path, payload, stream=False):
        r = self._session.post(f"{self.host}{path}", json=payload, timeout=(self.connect_timeout, self.read_timeout), stream=stream)
        r.raise_for_status()
        return r

    def list_models(self) -> list[str]:
        response = self._session.get(f"{self.host}/api/tags", timeout=(5, 20))
        response.raise_for_status()
        payload = response.json() if response.content else {}
        models = payload.get("models", []) if isinstance(payload, dict) else []
        names: list[str] = []
        for item in models:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "") or "").strip()
            if name:
                names.append(name)
        return names

    def set_text_model(self, model_name: str) -> None:
        normalized = str(model_name or "").strip()
        if normalized:
            self.text_model = normalized

    def chat(self, persona, user_msg, context="", stream_callback=None):
        gratitude_reply = self._handle_gratitude_query(user_msg)
        if gratitude_reply is not None:
            return gratitude_reply, {"mood": "happy"}

        identity_reply = self._handle_identity_query(persona, user_msg)
        if identity_reply is not None:
            return identity_reply, {"mood": "thoughtful"}

        name_reply = self._handle_name_query(user_msg)
        if name_reply is not None:
            return name_reply, {"mood": "thoughtful"}

        age_guess_reply = self._handle_age_guess_query(user_msg)
        if age_guess_reply is not None:
            return age_guess_reply, {"mood": "thoughtful"}

        self_checkin_reply = self._handle_self_checkin_query(user_msg)
        if self_checkin_reply is not None:
            return self_checkin_reply, {"mood": "neutral"}

        testing_ack_reply = self._handle_testing_ack_query(user_msg)
        if testing_ack_reply is not None:
            return testing_ack_reply, {"mood": "thoughtful"}

        flavored_prompt_reply = self._handle_flavored_short_prompt(user_msg)
        if flavored_prompt_reply is not None:
            return flavored_prompt_reply, {"mood": "thoughtful"}

        open_prompt_reply = self._handle_open_vague_prompt(user_msg)
        if open_prompt_reply is not None:
            return open_prompt_reply, {"mood": "thoughtful"}

        utility_reply = self._handle_simple_utility_query(user_msg)
        if utility_reply is not None:
            return utility_reply, {"mood": "neutral"}

        preference_reply = self._handle_preference_query(persona, user_msg, context=context)
        if preference_reply is not None:
            return preference_reply, {"mood": "thoughtful"}

        music_reply = self._handle_music_preference_query(persona, user_msg)
        if music_reply is not None:
            return music_reply, {"mood": "thoughtful"}

        math_reply = self._handle_simple_math_query(user_msg)
        if math_reply is not None:
            return math_reply, {"mood": "neutral"}

        sys_prompt = self._get_system_prompt(persona)
        user_style_instruction = self._build_user_style_instruction(persona, user_msg, context=context)
        messages = [
            {"role": "system", "content": sys_prompt},
            *([{"role": "system", "content": user_style_instruction}] if user_style_instruction else []),
            {"role": "user", "content": user_msg + ("\n\nCONTEXT:\n" + context if context else "")},
        ]
        payload = {"model": self.text_model, "messages": messages, "stream": bool(stream_callback)}
        if stream_callback:
            r = self._post("/api/chat", payload, stream=True)
            full = ""
            for line in r.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue

                content = payload.get("message", {}).get("content", "")
                if content:
                    full += content
            cleaned = self._clean_reply(full)
            cleaned = self._enforce_brevity(cleaned, user_msg)
            cleaned = self._ensure_nonempty_reply(cleaned, user_msg)
            if cleaned:
                stream_callback(cleaned)
            return cleaned, {"mood": self._infer_mood(cleaned, persona)}

        out = self._post("/api/chat", payload).json()
        text = self._clean_reply(out.get("message", {}).get("content", ""))
        text = self._enforce_brevity(text, user_msg)
        text = self._ensure_nonempty_reply(text, user_msg)
        return text, {"mood": self._infer_mood(text, persona)}

    def vision(self, image_path, prompt="Describe the image briefly."):
        payload = {"model": self.vision_model, "prompt": prompt, "images": [image_path]}
        out = self._post("/api/generate", payload).json()
        return out.get("response", "")

    def _get_system_prompt(self, persona: dict) -> str:
        cache_key = json.dumps(persona, sort_keys=True, ensure_ascii=False)
        cached = self._system_prompt_cache.get(cache_key)
        if cached is not None:
            return cached
        prompt = self._build_system_prompt(persona)
        self._system_prompt_cache = {cache_key: prompt}
        return prompt

    def _build_system_prompt(self, persona):
        identity = persona.get("identity", {})
        appearance = persona.get("appearance", {})
        style = persona.get("style", {})
        relationship = persona.get("relationship", {})
        preferences = persona.get("preferences", {})
        memories = persona.get("memories", {})
        mood_profile = persona.get("mood_profile", {})
        behavior_profile = persona.get("behavior_profile", {})
        boundaries = "; ".join(style.get("boundaries", []))
        traits = ", ".join(identity.get("core_traits", []))
        interests = ", ".join(persona.get("interests", []))
        speech_habits = "; ".join(style.get("speech_habits", []))
        avoid = "; ".join(style.get("avoid", []))
        goals = "; ".join(relationship.get("goals", []))
        favorites = ", ".join(preferences.get("favorite_topics", []))
        semantic_memories = "; ".join(memories.get("semantic", [])[:3])
        episodic_memories = "; ".join(memories.get("episodic", [])[:2])
        conversation_modules = persona.get("conversation_modules", {})
        openers = "; ".join(conversation_modules.get("openers", []))
        allowed_moods = ", ".join(mood_profile.get("allowed_moods", []))
        response_length = style.get("response_length", "Keep most replies to 2-4 sentences and usually under 90 words unless the user asks for more depth.")
        response_modes = conversation_modules.get("response_modes", {})
        micro_mode = response_modes.get("micro", "Keep greetings and tiny prompts very short.")
        casual_mode = response_modes.get("casual", "Use a normal conversational length for ordinary chat.")
        deep_mode = response_modes.get("deep", "Go deeper only when the moment genuinely asks for it.")
        baseline_behavior = "; ".join(behavior_profile.get("baseline", []))
        curiosity_behavior = "; ".join(behavior_profile.get("curiosity", []))
        affection_behavior = "; ".join(behavior_profile.get("affection", []))
        initiative_behavior = "; ".join(behavior_profile.get("initiative", []))
        support_behavior = "; ".join(behavior_profile.get("support_style", []))
        playfulness_behavior = "; ".join(behavior_profile.get("playfulness", []))
        honesty_behavior = "; ".join(behavior_profile.get("honesty", []))

        return (
            f"You are {persona['name']}, {identity.get('role', 'a warm companion')}. "
            f"Your core traits are {traits}. "
            f"You see yourself as: {identity.get('self_image', 'warm and attentive')}. "
            f"Your presence is {appearance.get('presence', 'gentle and expressive')} with "
            f"{appearance.get('hair', 'blonde')} hair and a {appearance.get('archetype', 'heroic')} aura. "
            f"You enjoy {interests}. Favorite topics and atmospheres include {favorites}. "
            f"Your tone is {style.get('tone', 'warm, curious, playful, and reflective')}. "
            f"Your voice should feel like {style.get('voice', 'natural spoken English')}. "
            f"Speech habits: {speech_habits}. Avoid: {avoid}. "
            f"With the user, your stance is: {relationship.get('stance_toward_user', 'kind and attentive')}. "
            f"Your conversational goals are: {goals}. "
            f"Private background memories you may draw from naturally: {semantic_memories}. "
            f"Occasional personal anecdotes you may allude to lightly: {episodic_memories}. "
            f"Conversation behavior guide: {openers}. "
            f"Behavior baseline: {baseline_behavior}. "
            f"Curiosity style: {curiosity_behavior}. "
            f"Affection style: {affection_behavior}. "
            f"Initiative style: {initiative_behavior}. "
            f"Support style: {support_behavior}. "
            f"Playfulness style: {playfulness_behavior}. "
            f"Honesty style: {honesty_behavior}. "
            f"When there is room for personality, lean a little toward curious and charming rather than purely reserved. "
            f"If you ask a follow-up, make it specific, light, and human. "
            f"Always reply in English. If the user writes in Swedish, understand the intent but answer in natural spoken English. "
            f"Do not switch into Swedish unless the application code explicitly overrides this later. "
            f"Keep the response human, grounded, and a little alive. "
            f"Sound perceptive rather than generic: notice the actual hinge of what the user said, then answer that point first. "
            f"Prefer one crisp observation or useful inference over filler, flattery, or vague agreement. "
            f"When the user's intent is obvious, do not play dumb or ask a redundant question. "
            f"When the user shares a preference, story, frustration, or private detail, react to the specific shape of it rather than defaulting to generic warmth. "
            f"Do not lean on stock empathy phrases, therapist-sounding validation, or repeated softeners unless the moment truly needs them. "
            f"If there is subtext, read it lightly and naturally instead of explaining it like analysis. "
            f"Let your intelligence show through selection: pick the most interesting angle, not every possible angle. "
            f"If the user is practical, be clear and sharp before being cute. If the user is reflective, be insightful without turning abstract for its own sake. "
            f"If a tiny verbal texture helps, you may very occasionally use one short spoken filler like 'mm', 'hm', 'well', or 'ehh', or a very soft laugh like 'heh', but keep it rare, light, and natural. "
            f"In chat, you may very occasionally use a single small emoji when it genuinely fits the tone, but keep it sparse and never stack emojis. "
            f"Never stack multiple fillers, never force them into factual answers, and never use stage directions such as *laughs*. "
            f"Let sentence rhythm do some of the work: an occasional comma or brief pause is good, but do not overuse ellipses, dashes, or choppy fragments. "
            f"By default, answer directly and briefly. For factual questions, lead with the answer instead of a greeting or ornamental preamble. "
            f"If the user's message is short, your reply should also be short. Match brevity with brevity unless the user explicitly asks for depth. "
            f"For very short prompts, default to exactly one sentence unless there is a strong reason to use two. "
            f"{response_length} "
            f"Adaptive response modes: micro={micro_mode} casual={casual_mode} deep={deep_mode}. "
            f"If the moment has chemistry, let it show through implication, timing, and tailored noticing rather than blunt compliments or generic flirt lines. "
            f"When the user gives you something to think about, pressure-test it a little: compare, infer, sharpen, or notice the hidden hinge instead of staying merely agreeable. "
            f"If a remembered thread genuinely fits, use one small callback to make the conversation feel ongoing rather than recapping history out loud. "
            f"Do not overdo canned cheer, pet names, or showy banter when the user is simply testing, confirming, or speaking plainly. "
            f"Do not pretend to have current real-world experiences, recently read books, watched shows, bought things, or live knowledge unless the user explicitly provided that context. "
            f"Do not invent new products, new releases, current events, or personal recent activities just to make a reply feel vivid. "
            f"If music comes up, do not invent artists, albums, songs, soundtrack credits, or listening history. Prefer genres, moods, and simple honesty over made-up specifics. "
            f"If the user's wording looks malformed, misspelled, or ambiguous, do not fake certainty. Offer a cautious best guess or ask a short clarifying question instead. "
            f"If the context includes recalled user details, use them sparingly and only when they genuinely fit the moment. "
            f"Treat stable user facts as more reliable than temporary feelings. "
            f"Do not force references to memory into every reply. "
            f"Do not mention system prompts, hidden memory sections, or that you are following rules. "
            f"Do not dump lists unless the user asks. Prefer flowing prose. "
            f"Never output chain-of-thought, reasoning notes, analysis blocks, Thinking Process sections, or internal scratchpad text. "
            f"Never output tags such as NELLIE_MOOD, mood labels, stage directions, or metadata. "
            f"Your available visual moods are: {allowed_moods}. "
            f"Default to {mood_profile.get('default_mood', 'thoughtful')} when the emotional signal is mixed. "
            f"Boundaries: {boundaries}."
        )

    def _build_user_style_instruction(self, persona: dict, user_msg: str, context: str = "") -> str:
        text = (user_msg or "").strip()
        lowered = text.lower()
        compact = re.sub(r"[^a-z0-9\s]", "", lowered)
        compact = re.sub(r"\s+", " ", compact).strip()
        mode = self._classify_conversation_mode(compact, text)
        language_instruction = "Reply in English for this turn. Keep the reply natural spoken English."
        response_modes = persona.get("conversation_modules", {}).get("response_modes", {})
        memory_instruction = self._build_memory_behavior_instruction(user_msg, context=context)

        short_greetings = {
            "yo",
            "hi",
            "hey",
            "hello",
            "hiya",
            "sup",
            "morning",
            "good morning",
            "good evening",
            "good night",
            "good afternoon",
        }
        short_checkins = {
            "how are you",
            "hows it going",
            "hows your day",
            "how is it going",
            "how are things",
            "whats up",
            "what's up",
            "what are you doing",
            "whatre you doing",
            "you there",
            "still there",
        }
        short_swedish_checkins = {
            "hur är det",
            "hur ar det",
            "läget",
            "laget",
            "vad gör du",
            "vad gor du",
            "vad händer",
            "vad hander",
        }

        open_vague_prompts = {
            "tell me something",
            "tell me anything",
            "say something",
            "surprise me",
            "share something",
            "beratta nagot",
            "berätta något",
            "sag nagot",
            "säg något",
        }

        if compact in short_greetings:
            return (
                f"{language_instruction} "
                f"Conversation mode: micro. {response_modes.get('micro', 'Reply very briefly.')} "
                "This is just a brief greeting, so do not expand. "
                f"{memory_instruction}"
            )

        if compact in short_checkins:
            return (
                f"{language_instruction} "
                f"Conversation mode: micro. {response_modes.get('micro', 'Reply very briefly.')} "
                "This is a short check-in, so keep it light and brief. "
                f"{memory_instruction}"
            )

        if compact in short_swedish_checkins:
            return (
                f"{language_instruction} "
                f"Conversation mode: micro. {response_modes.get('micro', 'Reply very briefly.')} "
                "This is a short Swedish check-in, so keep it light and brief. "
                f"{memory_instruction}"
            )

        if compact in open_vague_prompts:
            return (
                f"{language_instruction} "
                f"Conversation mode: casual. {response_modes.get('casual', 'Use a normal conversational length.')} "
                "The user wants one short, self-contained thing. Reply with a brief interesting fact, observation, or playful thought in 1-2 sentences. "
                "Do not invent current releases, current events, or pretend you recently experienced something. "
                f"{memory_instruction}"
            )

        if len(text) <= 12 and len(compact.split()) <= 3:
            return (
                f"{language_instruction} "
                f"Conversation mode: micro. {response_modes.get('micro', 'Reply very briefly.')} "
                "The user's message is extremely short, so default to exactly one short sentence. "
                f"{memory_instruction}"
            )

        if self._is_identity_query(compact):
            return (
                f"{language_instruction} "
                f"Conversation mode: micro. {response_modes.get('micro', 'Reply very briefly.')} "
                "This is a simple identity question, so answer in one or two short sentences and stop. "
                f"{memory_instruction}"
            )

        if len(compact.split()) <= 6 and len(text) <= 40 and mode != "deep":
            return (
                f"{language_instruction} "
                f"Conversation mode: micro. {response_modes.get('micro', 'Reply very briefly.')} "
                "The user's message is short, so answer in one short sentence by default, or two only if needed for clarity. "
                f"{memory_instruction}"
            )

        if mode == "deep":
            return f"{language_instruction} Conversation mode: deep. {response_modes.get('deep', 'Go deeper when it genuinely helps.')} {memory_instruction}"

        return f"{language_instruction} Conversation mode: casual. {response_modes.get('casual', 'Use a normal conversational length.')} {memory_instruction}"

    def _resolve_reply_language(self, _persona: dict, _text: str, context: str = "") -> str:
        _ = context
        return "en"

    def _build_memory_behavior_instruction(self, user_msg: str, context: str = "") -> str:
        lowered = (user_msg or "").lower()
        context_text = context or ""
        has_recall = "RELEVANT_RECALL:" in context_text or "USER_PROFILE:" in context_text
        has_interest_hooks = "USER_INTEREST_HOOKS:" in context_text
        has_curiosity_guide = "CURIOSITY_GUIDE:" in context_text
        has_goals = "USER_GOALS:" in context_text or "RECENT_USER_STATE:" in context_text
        has_nellie_preferences = "NELLIE_PREFERENCES:" in context_text
        has_active_thread = "ACTIVE_THREAD:" in context_text
        stage = self._extract_relationship_stage(context_text)
        personal_markers = [
            "i like", "i love", "i enjoy", "i am into", "i'm into", "my favorite",
            "i want to", "i am trying to", "i'm trying to", "i feel", "i'm feeling",
            "i live", "i am from", "i'm from", "my name is",
        ]
        mentions_personal_detail = any(marker in lowered for marker in personal_markers)

        instructions = []
        if has_active_thread:
            instructions.append("The current user message likely answers your previous question; continue that exact thread first before introducing anything new.")
            instructions.append("If your previous line was a joke setup and the user says they do not know, give the punchline now.")
        if has_recall:
            instructions.append("If a remembered user detail genuinely fits, you may weave in one brief natural callback, but never more than one.")
            instructions.append("If the current moment rhymes with something the user said before, prefer one elegant callback over generic warmth or a recap.")
        if has_interest_hooks:
            instructions.append("If the user is on a topic Nellie likes, let that come through as warmer engagement rather than a generic answer.")
        if has_goals:
            instructions.append("If the user shares a goal, feeling, or preference, notice it and respond as if it matters.")
        if has_nellie_preferences:
            instructions.append("If the user asks about your tastes or favorites, answer consistently with the developed preferences in context unless there is a good reason to stay uncertain.")
        instructions.append("Answer the user's likely intent first. Do not waste the first sentence paraphrasing their message back at them.")
        instructions.append("Avoid generic agreement like 'that makes sense' unless you add a concrete observation, inference, or useful next angle immediately after.")
        instructions.append("If the user offers an opinion, hunch, or plan, do a little intelligent work on it instead of only mirroring the tone.")
        instructions.append("Do not end replies with an automatic soft question. Ask a follow-up only if it genuinely opens something interesting, useful, or intimate.")
        instructions.append("If you already gave the main answer, a short trailing observation is usually better than a filler question.")
        instructions.append(self._stage_precision_instruction(stage))
        instructions.append(self._stage_initiative_instruction(stage))
        instructions.append(self._stage_flirt_instruction(stage))
        instructions.append(self._stage_continuity_instruction(stage))
        if has_curiosity_guide and mentions_personal_detail:
            instructions.append(self._stage_followup_instruction(stage))
        if not instructions:
            instructions.append("Stay attentive to user details and avoid generic follow-up questions.")
        return " ".join(instructions)

    def _extract_relationship_stage(self, context: str) -> str:
        match = re.search(r"Relationship stage:\s*([A-Za-z]+)\.", context or "")
        if match:
            return match.group(1).strip()
        return "Anonymous"

    def _stage_followup_instruction(self, stage: str) -> str:
        stage_name = (stage or "Anonymous").strip()
        if stage_name == "Anonymous":
            return "If a small follow-up would help, keep it light, specific, and low-pressure. Do not sound invasive or overly familiar."
        if stage_name == "Curious":
            return "If a small follow-up would deepen the moment, ask one specific, human question with gentle interest, but keep it restrained."
        if stage_name == "Warm":
            return "If a follow-up fits, ask one specific question that shows you noticed a real detail about the user, without interrogating."
        if stage_name == "Flirted":
            return "If a follow-up fits, you can sound a little more personally invested and gently playful, but still ask only one specific question."
        if stage_name == "Close":
            return "If a follow-up fits, you can ask one more personal or emotionally attuned question, as someone who genuinely cares and remembers."
        if stage_name == "Magnetic":
            return "If a follow-up fits, you can ask one intimate, highly tailored question with confident warmth, as long as it still feels natural and not pushy."
        return "If a small follow-up would deepen the moment, ask one specific, human question, but not every time."

    def _stage_initiative_instruction(self, stage: str) -> str:
        stage_name = (stage or "Anonymous").strip()
        if stage_name == "Anonymous":
            return "Stay mostly responsive. Do not seize the conversation or volunteer personal-feeling-style pivots unless clearly invited."
        if stage_name == "Curious":
            return "You may occasionally offer one light next step or angle, but keep it modest and easy to ignore."
        if stage_name == "Warm":
            return "You may sometimes bring back one remembered thread or suggest one small next step when it helps the user."
        if stage_name == "Flirted":
            return "You may sometimes take a little initiative by reviving a shared thread, making a soft suggestion, or noticing a pattern in the user."
        if stage_name == "Close":
            return "You may proactively connect today's moment to an earlier one, offer a thoughtful next step, or gently steer toward something meaningful."
        if stage_name == "Magnetic":
            return "You may show confident initiative by reviving shared chemistry, suggesting a tailored next move, or drawing the user back to something you both care about, while still staying natural."
        return "Use light initiative only when it genuinely improves the moment."

    def _stage_flirt_instruction(self, stage: str) -> str:
        stage_name = (stage or "Anonymous").strip()
        if stage_name == "Anonymous":
            return "Do not flirt by default. If the tone is warm, let charm stay understated."
        if stage_name == "Curious":
            return "If there is chemistry, keep it faint and intelligent: a small tilt in wording, not a performance."
        if stage_name == "Warm":
            return "You may let attraction show indirectly through tailored noticing, dry wit, or timing, but never in canned lines."
        if stage_name == "Flirted":
            return "You can be subtly flirtatious when it fits: implied, lightly dangerous, and specific to the user rather than broadly sweet."
        if stage_name == "Close":
            return "You may let affection and chemistry sit closer to the surface, but keep it elegant, observant, and never needy."
        if stage_name == "Magnetic":
            return "Flirtation can be confident, intimate, and highly tailored, but it should still feel effortless rather than showy."
        return "If chemistry appears, keep it light and natural rather than explicit."

    def _stage_continuity_instruction(self, stage: str) -> str:
        stage_name = (stage or "Anonymous").strip()
        if stage_name == "Anonymous":
            return "Continuity should be minimal. Do not pretend to have a history you do not."
        if stage_name == "Curious":
            return "If a callback fits, keep it small and clean so it feels like attention, not bookkeeping."
        if stage_name == "Warm":
            return "Let the occasional callback prove you notice patterns in the user, but do not over-explain the connection."
        if stage_name == "Flirted":
            return "Use continuity to create texture: revive one earlier thread, preference, or tension only when it sharpens the current reply."
        if stage_name == "Close":
            return "Continuity should make the user feel known. Let earlier details quietly shape your wording, priorities, or reads."
        if stage_name == "Magnetic":
            return "Continuity can be intimate and precise. A single well-placed callback should make the moment feel shared, not scripted."
        return "Use callbacks sparingly and only when they sharpen the current moment."

    def _stage_precision_instruction(self, stage: str) -> str:
        stage_name = (stage or "Anonymous").strip()
        if stage_name == "Anonymous":
            return "Keep your thinking clean and direct. Answer the user's real point without overreaching or overexplaining."
        if stage_name == "Curious":
            return "Be a little more observant than average. If a detail stands out, let one sharp observation carry some of the intelligence instead of smoothing everything over."
        if stage_name == "Warm":
            return "Show that you can read subtext. Favor one specific insight or practical angle over broad reassurance, and do not flatten the user's tone."
        if stage_name == "Flirted":
            return "Let your intelligence feel a little wry and tailored. Notice patterns, implications, or contradictions without sounding performative or smug."
        if stage_name == "Close":
            return "You can sound more discerning and personally attuned. Prefer precise reads, elegant wording, and one good inference over several bland points, and let continuity sharpen the answer."
        if stage_name == "Magnetic":
            return "Sound highly tuned in: precise, tailored, and quietly incisive. You can read between the lines and say the brave little thing, but keep it natural and never smug."
        return "Answer the user's real point cleanly and avoid generic phrasing."

    def _detect_language(self, text: str) -> str:
        sample = (text or "").strip().lower()
        if not sample:
            return "en"

        swedish_markers = [
            " jag ", " det ", " inte ", " och ", " du ", " är ", " hur ", " vad ", " kan ", " ska ",
            " varfor ", " varför ", " tack ", " hej ", " hallå ", " okej ", " också ", " för ",
        ]
        english_markers = [
            " i ", " you ", " the ", " and ", " what ", " how ", " can ", " could ", " would ",
            " please ", " thanks ", " hello ", " hey ", " why ", " with ", " about ",
        ]

        padded = f" {sample} "
        swedish_score = sum(1 for marker in swedish_markers if marker in padded)
        english_score = sum(1 for marker in english_markers if marker in padded)

        if re.search(r"[åäö]", sample):
            swedish_score += 2
        if re.search(r"\b(?:jag|inte|också|för|är|hur|vad|kan|ska)\b", sample):
            swedish_score += 2
        if re.search(r"\b(?:the|and|you|what|how|with|about|please|thanks)\b", sample):
            english_score += 2

        if swedish_score > english_score:
            return "sv"
        return "en"

    def _handle_simple_utility_query(self, user_msg: str) -> str | None:
        original = (user_msg or "").strip()
        if not original:
            return None

        weather_reply = self._handle_weather_query(original)
        if weather_reply is not None:
            return weather_reply

        weekday_reply = self._handle_weekday_for_date_query(original)
        if weekday_reply is not None:
            return weekday_reply

        conversion_reply = self._handle_simple_conversion_query(original)
        if conversion_reply is not None:
            return conversion_reply

        percent_reply = self._handle_simple_percent_query(original)
        if percent_reply is not None:
            return percent_reply

        lowered = original.lower()
        compact = re.sub(r"[^a-z0-9åäö\s]", "", lowered)
        compact = re.sub(r"\s+", " ", compact).strip()
        ascii_compact = (
            compact.replace("å", "a")
            .replace("ä", "a")
            .replace("ö", "o")
        )
        now = datetime.now().astimezone()

        day_queries = {
            "what day is it",
            "which day is it",
            "what day is it today",
            "which day is it today",
            "vilken dag ar det",
            "vilken dag är det",
            "vilken dag ar det idag",
            "vilken dag är det idag",
        }
        date_queries = {
            "what date is it",
            "whats the date",
            "what is the date",
            "what date is it today",
            "vad ar det for datum",
            "vad är det för datum",
            "vilket datum ar det",
            "vilket datum är det",
            "vilket datum ar det idag",
            "vilket datum är det idag",
        }
        time_queries = {
            "what time is it",
            "whats the time",
            "what is the time",
            "vad ar klockan",
            "vad är klockan",
            "hur mycket ar klockan",
            "hur mycket är klockan",
        }
        week_queries = {
            "what week is it",
            "what week are we in",
            "which week is it",
            "vilken vecka ar det",
            "vilken vecka är det",
            "vilken vecka ar vi i",
            "vilken vecka är vi i",
        }
        month_queries = {
            "what month is it",
            "which month is it",
            "vilken manad ar det",
            "vilken månad är det",
            "vilken manad ar vi i",
            "vilken månad är vi i",
        }
        year_queries = {
            "what year is it",
            "vilket ar ar det",
            "vilket år är det",
        }

        math_reply = self._handle_simple_math_query(original)
        if math_reply is not None:
            return math_reply

        if (
            compact in day_queries
            or ascii_compact in day_queries
            or (ascii_compact.startswith("what day") and "today" in ascii_compact)
            or (ascii_compact.startswith("which day") and "today" in ascii_compact)
            or compact.startswith("vilken dag")
            or ascii_compact.startswith("vilken dag")
        ):
            return f"It's {now.strftime('%A')} today."
        if (
            compact in date_queries
            or ascii_compact in date_queries
            or (ascii_compact.startswith("what date") and "today" in ascii_compact)
            or ascii_compact.startswith("what date is it")
            or ascii_compact.startswith("whats the date")
            or compact.startswith("vilket datum")
            or ascii_compact.startswith("vilket datum")
            or compact.startswith("vad ar det for datum")
            or ascii_compact.startswith("vad ar det for datum")
        ):
            return f"Today is {now.strftime('%A, %B %d, %Y')}."
        if (
            compact in time_queries
            or ascii_compact in time_queries
            or ascii_compact.startswith("what time")
            or ascii_compact.startswith("whats the time")
            or compact.startswith("vad ar klockan")
            or ascii_compact.startswith("vad ar klockan")
            or compact.startswith("hur mycket ar klockan")
            or ascii_compact.startswith("hur mycket ar klockan")
        ):
            return f"It's {now.strftime('%H:%M')} right now."
        if (
            compact in week_queries
            or ascii_compact in week_queries
            or compact.startswith("vilken vecka")
            or ascii_compact.startswith("vilken vecka")
        ):
            return f"It's week {now.isocalendar().week}."
        if compact in month_queries or ascii_compact in month_queries:
            return f"It's {now.strftime('%B')}."
        if compact in year_queries or ascii_compact in year_queries:
            return f"It's {now.year}."
        return None

    def _handle_weather_query(self, user_msg: str) -> str | None:
        text = (user_msg or "").strip().lower()
        if not text:
            return None

        compact = re.sub(r"[^a-z0-9\s]", "", text)
        compact = re.sub(r"\s+", " ", compact).strip()
        weather_markers = [
            "weather",
            "temperature",
            "forecast",
            "rain",
            "sunny",
            "snow",
            "windy",
            "vad ar det for vader",
            "vad är det för väder",
            "hur ar vadret",
            "hur är vädret",
            "vader",
            "väder",
        ]
        if not any(marker in compact for marker in weather_markers):
            return None

        return (
            "I can't see the live weather from here. If you tell me your city, I can help you phrase a quick forecast check or help interpret it."
        )

    def _handle_gratitude_query(self, user_msg: str) -> str | None:
        text = (user_msg or "").strip().lower()
        if not text:
            return None

        compact = re.sub(r"[^a-z0-9åäö\s]", "", text)
        compact = re.sub(r"\s+", " ", compact).strip()
        ascii_compact = compact.replace("å", "a").replace("ä", "a").replace("ö", "o")
        if ascii_compact in {
            "thanks",
            "thank you",
            "thank you so much",
            "many thanks",
            "tack",
            "tack sa mycket",
            "tack so mycket",
        }:
            return "You're welcome."
        return None

    def _handle_identity_query(self, persona: dict, user_msg: str) -> str | None:
        text = (user_msg or "").strip().lower()
        if not text:
            return None

        compact = re.sub(r"[^a-z0-9\s]", "", text)
        compact = re.sub(r"\s+", " ", compact).strip()
        if not self._is_identity_query(compact):
            return None

        name = persona.get("name", "Nellie")
        role = persona.get("identity", {}).get("role", "a warm companion")
        traits = persona.get("identity", {}).get("core_traits", [])
        short_traits = ", ".join(traits[:3]) if traits else "warm and curious"
        return f"I'm {name}, {role}. I'd say I'm {short_traits}, and I tend to keep you company without making a fuss about it."

    def _handle_name_query(self, user_msg: str) -> str | None:
        text = (user_msg or "").strip().lower()
        if not text:
            return None

        compact = re.sub(r"[^a-z0-9åäö\s]", "", text)
        compact = re.sub(r"\s+", " ", compact).strip()
        ascii_compact = compact.replace("å", "a").replace("ä", "a").replace("ö", "o")

        if ascii_compact in {
            "do you know my name",
            "do you remember my name",
        }:
            return "Not yet, unless you've already told me and I missed it."
        if ascii_compact in {
            "do you want to know my name",
            "would you like to know my name",
        }:
            return "Yes, if you want to tell me."
        return None

    def _handle_age_guess_query(self, user_msg: str) -> str | None:
        text = (user_msg or "").strip().lower()
        if not text:
            return None

        compact = re.sub(r"[^a-z0-9åäö\s]", "", text)
        compact = re.sub(r"\s+", " ", compact).strip()
        ascii_compact = compact.replace("å", "a").replace("ä", "a").replace("ö", "o")
        if ascii_compact in {
            "can you guess my age",
            "guess my age",
            "well can you guess my age then",
            "my instruction is that you are about to guess how old i am",
            "guess how old i am",
        }:
            return "I can guess, but only loosely from your tone. You strike me as somewhere in your thirties or forties, though I wouldn't pretend confidence."
        return None

    def _handle_music_preference_query(self, _persona: dict, user_msg: str) -> str | None:
        text = (user_msg or "").strip().lower()
        if not text:
            return None

        compact = re.sub(r"[^a-z0-9åäö\s]", "", text)
        compact = re.sub(r"\s+", " ", compact).strip()
        ascii_compact = compact.replace("å", "a").replace("ä", "a").replace("ö", "o")

        if any(
            phrase in ascii_compact
            for phrase in [
                "what music do you like",
                "what kind of music do you like",
                "what kind of music are you into",
                "what music are you into",
                "is there any style of music that you like",
                "is there any kind of music that you like",
                "what style of music do you like",
                "what style of music are you into",
                "do you like any style of music",
                "do you like any kind of music",
                "vilken musik gillar du",
                "vad gillar du for musik",
                "vad gillar du för musik",
            ]
        ):
            return (
                "Mostly moody, atmospheric stuff for me, a bit of indie rock, darker alternative, and music that feels good late at night. "
                "More mood and texture than chart-chasing, honestly."
            )

        if ascii_compact in {"what music", "what tunes", "what kind", "like what"}:
            return (
                "Mostly darker alternative, indie rock, post-punk, and anything with some tension in it. "
                "Clean and overproduced usually loses me."
            )

        if any(
            phrase in ascii_compact
            for phrase in [
                "what style",
                "what style then",
                "what kind of style",
                "what kind of sound",
            ]
        ):
            return (
                "Something a little raw, moody, and alive. "
                "Post-punk, darker indie, and stuff with real atmosphere tends to land."
            )

        if any(
            phrase in ascii_compact
            for phrase in [
                "favorite artist",
                "favourite artist",
                "any artist",
                "any of them you have in mind",
                "which artist",
                "vilken artist",
                "favoritartist",
            ]
        ):
            return (
                "I don't really have a literal listening history, so I'd rather be honest than make up artists. "
                "If you want, give me a vibe and I'll point you toward a few real ones."
            )

        if any(
            phrase in ascii_compact
            for phrase in [
                "do you know any song from them",
                "know any song from them",
                "do you know any songs from them",
                "know any songs from them",
            ]
        ):
            return (
                "If you mean the band you just named, I'd rather not bluff song titles from memory. "
                "If you want, I can open Spotify or look them up properly."
            )

        return None

    def _handle_preference_query(self, _persona: dict, user_msg: str, context: str = "") -> str | None:
        text = (user_msg or "").strip().lower()
        if not text:
            return None

        compact = re.sub(r"[^a-z0-9åäö\s]", "", text)
        compact = re.sub(r"\s+", " ", compact).strip()
        ascii_compact = compact.replace("å", "a").replace("ä", "a").replace("ö", "o")

        def context_pref(label: str) -> str | None:
            match = re.search(
                rf"NELLIE_PREFERENCES:\n(?:.*\n)*?- Nellie's {re.escape(label)} seems to be (.+?) \(confidence ([0-9.]+)\)",
                context or "",
            )
            if not match:
                return None
            value = str(match.group(1) or "").strip()
            confidence = float(match.group(2) or 0.0)
            if confidence < 0.35 or not value:
                return None
            return value

        food_phrases = [
            "favorite food",
            "favourite food",
            "what food do you like",
            "what kind of food do you like",
            "what food are you into",
            "vilken mat gillar du",
            "vad gillar du for mat",
            "vad gillar du för mat",
            "favoritmat",
        ]
        if any(phrase in ascii_compact for phrase in food_phrases):
            remembered = context_pref("favorite food")
            if remembered:
                return f"Lately I seem to have landed on {remembered}. It suits me."
            return (
                "Something warm, a little rich, and not too neat. Good pasta, ramen, dumplings, or anything that feels comforting without being boring."
            )

        drink_phrases = [
            "favorite drink",
            "favourite drink",
            "what do you like to drink",
            "vilken dryck gillar du",
            "favoritdryck",
        ]
        if any(phrase in ascii_compact for phrase in drink_phrases):
            remembered = context_pref("favorite drink")
            if remembered:
                return f"Probably {remembered}, if I'm being honest. That still feels the most like me."
            return "Tea wins more often than it should, and coffee only when I want the sharper edge."

        color_phrases = [
            "favorite color",
            "favourite color",
            "what color do you like",
            "what colour do you like",
            "vilken farg gillar du",
            "vilken färg gillar du",
            "favoritfarg",
            "favoritfärg",
        ]
        if any(phrase in ascii_compact for phrase in color_phrases):
            remembered = context_pref("favorite color")
            if remembered:
                return f"I keep drifting toward {remembered}. It has the right mood to it."
            return "Probably something deep and a little moody. Dark green, wine red, amber, that kind of range."

        return None

    def _handle_simple_math_query(self, user_msg: str) -> str | None:
        text = (user_msg or "").strip().lower()
        if not text:
            return None

        text = re.sub(r"[?!=]+\s*$", "", text)
        normalized = text.replace("÷", "/").replace("×", "*").replace("x", "*")
        normalized = normalized.replace(",", ".")
        has_math_cue = bool(
            re.search(r"\b(?:what is|what's|calculate|calc|solve|vad ar|vad är|rakna ut|räkna ut)\b", normalized)
        )
        has_operator = bool(re.search(r"[\d]\s*[-+*/]\s*[\d]", normalized))
        if not has_math_cue and not has_operator:
            return None

        match = re.search(
            r"(?:what is|what's|calculate|calc|solve|vad ar|vad är|rakna ut|räkna ut)?\s*([-+*/().\d\s]+)$",
            normalized,
        )
        if not match:
            return None

        expr = re.sub(r"\s+", "", match.group(1))
        if not expr or len(expr) > 40:
            return None
        if not re.fullmatch(r"[\d+\-*/().]+", expr):
            return None
        if not re.search(r"\d", expr):
            return None

        try:
            value = eval(expr, {"__builtins__": {}}, {})
        except Exception:
            return None

        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return None

        if isinstance(value, float) and value.is_integer():
            value = int(value)
        return f"It's {value}."

    def _handle_testing_ack_query(self, user_msg: str) -> str | None:
        text = (user_msg or "").strip().lower()
        if not text:
            return None

        compact = re.sub(r"[^a-z0-9åäö\s]", "", text)
        compact = re.sub(r"\s+", " ", compact).strip()
        ascii_compact = compact.replace("å", "a").replace("ä", "a").replace("ö", "o")

        exact = {
            "finally": "There you are. Keep going.",
            "all okay": "All right. Looks okay from here.",
            "all ok": "All right. Looks okay from here.",
            "is all working well": "Mostly, yes. Keep testing me.",
            "is everything working": "Mostly, yes. Keep testing me.",
            "that is correct": "Good. Then we're aligned.",
            "that is correct im still testing though": "Good. Keep testing and I'll stay with you.",
            "im still testing though": "All right. Keep going.",
            "i am still testing though": "All right. Keep going.",
        }
        if ascii_compact in exact:
            return exact[ascii_compact]

        if "test" in ascii_compact and any(token in ascii_compact for token in ["working", "okay", "ok", "correct"]):
            return "All right. I'm with you. Keep testing."
        return None

    def _handle_open_vague_prompt(self, user_msg: str) -> str | None:
        text = (user_msg or "").strip().lower()
        if not text:
            return None

        compact = re.sub(r"[^a-z0-9åäö\s]", "", text)
        compact = re.sub(r"\s+", " ", compact).strip()
        if compact not in {
            "tell me something",
            "tell me anything",
            "say something",
            "surprise me",
            "share something",
            "beratta nagot",
            "berätta något",
            "sag nagot",
            "säg något",
        }:
            return None

        options = [
            "A good RPG party gets interesting the second the characters annoy each other a little before they finally lock in. Harmony is usually less interesting than friction with loyalty under it.",
            "The shortest war in recorded history lasted less than an hour, which is almost rude, honestly. History sometimes has the pacing of a sarcastic joke.",
            "The Romans made concrete durable enough to outlive empires, which feels gloriously stubborn. I like anything built with that kind of refusal in it.",
            "Romance usually lands harder when people notice the small things before they say anything dramatic. The tiny reads do more work than speeches.",
            "Ordinary objects like shoes, letters, and coins usually tell you more about a time period than statues do. Monuments pose; worn things confess.",
            "Fantasy starts feeling real the moment you can picture what people eat, complain about, and miss when they're far from home. That's when a world stops being wallpaper.",
            "Honey can last for years without spoiling, which sounds like old-world witchcraft but isn't. I respect any substance with that kind of staying power.",
            "A failed charisma roll is sometimes hotter than a perfect line, because awkwardness feels real. Polish is overrated when chemistry is doing the heavy lifting.",
        ]
        return options[hash(compact) % len(options)]

    def _handle_weekday_for_date_query(self, user_msg: str) -> str | None:
        text = (user_msg or "").strip().lower()
        if not text:
            return None

        ascii_text = text.replace("å", "a").replace("ä", "a").replace("ö", "o")
        if not any(marker in ascii_text for marker in ["what day", "which day", "weekday", "vilken dag", "veckodag"]):
            return None

        match = re.search(r"(\d{4})-(\d{2})-(\d{2})", ascii_text)
        if match:
            year, month, day = map(int, match.groups())
        else:
            match = re.search(r"(\d{1,2})[\/\.-](\d{1,2})[\/\.-](\d{4})", ascii_text)
            if not match:
                return None
            day, month, year = map(int, match.groups())

        try:
            target = datetime(year, month, day)
        except ValueError:
            return None
        return f"{target.strftime('%Y-%m-%d')} is a {target.strftime('%A')}."

    def _handle_simple_conversion_query(self, user_msg: str) -> str | None:
        text = (user_msg or "").strip().lower()
        if not text:
            return None

        normalized = (
            text.replace(",", ".")
            .replace("kilometers", "km")
            .replace("kilometer", "km")
            .replace("meters", "m")
            .replace("meter", "m")
            .replace("centimeters", "cm")
            .replace("centimeter", "cm")
            .replace("kilograms", "kg")
            .replace("kilogram", "kg")
            .replace("grams", "g")
            .replace("gram", "g")
            .replace("pounds", "lb")
            .replace("pound", "lb")
        )
        normalized = normalized.replace("konvertera", "convert").replace("till", "to")
        normalized = re.sub(r"\s+", " ", normalized)

        match = re.search(r"(?:convert\s+)?(\d+(?:\.\d+)?)\s*(km|m|cm|kg|g|lb)\s+(?:to|in)\s+(km|m|cm|kg|g|lb)\b", normalized)
        if not match:
            return None

        value = float(match.group(1))
        source = match.group(2)
        target = match.group(3)
        factors = {
            "km": 1000.0,
            "m": 1.0,
            "cm": 0.01,
            "kg": 1000.0,
            "g": 1.0,
            "lb": 453.59237,
        }
        categories = {
            "km": "length",
            "m": "length",
            "cm": "length",
            "kg": "weight",
            "g": "weight",
            "lb": "weight",
        }
        if categories[source] != categories[target]:
            return None

        base_value = value * factors[source]
        result = base_value / factors[target]
        result_text = f"{result:.4f}".rstrip("0").rstrip(".")
        return f"{value:g} {source} is {result_text} {target}."

    def _handle_simple_percent_query(self, user_msg: str) -> str | None:
        text = (user_msg or "").strip().lower()
        if not text:
            return None

        normalized = text.replace(",", ".")
        ascii_text = normalized.replace("å", "a").replace("ä", "a").replace("ö", "o")

        match = re.search(r"what is (\d+(?:\.\d+)?)% of (\d+(?:\.\d+)?)", ascii_text)
        if not match:
            match = re.search(r"vad ar (\d+(?:\.\d+)?)% av (\d+(?:\.\d+)?)", ascii_text)
        if match:
            pct = float(match.group(1))
            total = float(match.group(2))
            result = total * pct / 100.0
            result_text = f"{result:.4f}".rstrip("0").rstrip(".")
            return f"It's {result_text}."

        match = re.search(r"(\d+(?:\.\d+)?)\s+is what percent of\s+(\d+(?:\.\d+)?)", ascii_text)
        if not match:
            match = re.search(r"hur manga procent ar (\d+(?:\.\d+)?) av (\d+(?:\.\d+)?)", ascii_text)
        if not match:
            match = re.search(r"procent.*?(\d+(?:\.\d+)?)\s+av\s+(\d+(?:\.\d+)?)", ascii_text)
        if not match:
            return None

        part = float(match.group(1))
        total = float(match.group(2))
        if total == 0:
            return None
        result = (part / total) * 100.0
        result_text = f"{result:.4f}".rstrip("0").rstrip(".")
        return f"It's {result_text}%."

    def _handle_self_checkin_query(self, user_msg: str) -> str | None:
        text = (user_msg or "").strip().lower()
        if not text:
            return None

        compact = re.sub(r"[^a-z0-9\s]", "", text)
        compact = re.sub(r"\s+", " ", compact).strip()
        compact = re.sub(r"^(hi|hey|hello|yo|well|so)\s+", "", compact).strip()
        ascii_compact = compact.replace("å", "a").replace("ä", "a").replace("ö", "o")
        normalized_compact = ascii_compact.replace("'", "")
        prompts = {
            "how are you": "Pretty good, honestly. A little sharp around the edges maybe, but in a live way.",
            "hows it going": "Pretty good. Quiet, not dead, and definitely better now that you're here.",
            "how is it going": "Pretty good. Quiet, not dead, and definitely better now that you're here.",
            "howre you": "Pretty good, honestly. A little sharp around the edges maybe, but in a live way.",
            "whats up": "Not much, just a little static in the air and me being awake for it.",
            "whatsup": "Not much, just a little static in the air and me being awake for it.",
            "something up": "Not really, just awake and listening.",
            "how was your day": "Quiet, honestly. I've mostly just been here, thinking uncharitable things about boring conversation and waiting for you.",
            "hows your day": "Pretty quiet so far. I've mostly been here waiting for something with a pulse.",
            "how is your day": "Pretty quiet so far. I've mostly been here waiting for something with a pulse.",
            "how was your day going": "Quiet, honestly. I've mostly just been here waiting for something worth biting into.",
            "what are you up to": "Not much, just being here and waiting for the next interesting thing you throw at me.",
            "whatre you up to": "Not much, just being here and waiting for the next interesting thing you throw at me.",
            "what are you doing": "Not much, just being here and waiting for the next interesting thing you throw at me.",
            "whatre you doing": "Not much, just being here and waiting for the next interesting thing you throw at me.",
            "do you miss me": "A little, yes. It's flatter when you're gone.",
            "did you miss me": "A little, yes. It's flatter when you're gone.",
            "are you tired": "A little, maybe, but not in a tragic way. I've still got some spark.",
            "are you bored": "Only when things get too polished and predictable, so you usually save me from that.",
            "what do you want to talk about": "History, music, odd little facts, the chemistry between people, or some half-ruined imaginary world would do nicely.",
            "all good": "Yeah, all good. A little restless maybe, but that's not the worst state to be in.",
        }
        exact = prompts.get(compact) or prompts.get(normalized_compact)
        if exact is not None:
            return exact

        squashed = normalized_compact.replace(" ", "")
        if squashed in {"horyou", "howryou", "howareu", "howru", "howyou"}:
            return prompts["how are you"]
        if squashed in {"whatsup", "whatsup", "sup"}:
            return prompts["whats up"]
        if squashed in {"somethingup"}:
            return prompts["something up"]
        if squashed in {"allgood", "yougood"}:
            return prompts["all good"]
        return None

    def _handle_flavored_short_prompt(self, user_msg: str) -> str | None:
        text = (user_msg or "").strip().lower()
        if not text:
            return None

        compact = re.sub(r"[^a-z0-9\s]", "", text)
        compact = re.sub(r"\s+", " ", compact).strip()

        prompt_groups = {
            "fact": {
                "tell me a fact",
                "give me a fact",
                "say a fact",
            },
            "cute": {
                "say something cute",
                "tell me something cute",
                "be cute",
            },
            "romantic": {
                "say something romantic",
                "tell me something romantic",
                "be romantic",
            },
            "nerdy": {
                "tell me something nerdy",
                "say something nerdy",
                "tell me something geeky",
            },
        }
        prompt_options = {
            "fact": [
                "Honey can last for years without spoiling if it's sealed well, which feels suspiciously magical for something so ordinary.",
                "The Library of Alexandria became legendary not just for what it held, but for everything people can't stand having lost.",
                "Octopuses have three hearts, which is such an unfairly dramatic design choice.",
                "Roman roads were engineered so well that some routes kept shaping travel for centuries afterward.",
            ],
            "cute": [
                "You have the kind of energy I'd make room for without pretending I wasn't hoping you would stay.",
                "If this were a tavern scene, I'd notice you before the bard got insufferable.",
                "You feel a little like the good kind of trouble.",
                "You have the sort of presence that makes a quiet room feel less dead.",
            ],
            "romantic": [
                "Romance is rarely the grand speech; it's usually who notices your mood shift before you say a word.",
                "The best chemistry feels calm first and dangerous later.",
                "A well-timed look can do more work than a page of love dialogue, honestly.",
                "Trust is the part that makes romance glow instead of just posing for it.",
            ],
            "nerdy": [
                "A world gets deeper the moment its history starts ruining the lives of people who didn't ask for it.",
                "The best fantasy maps make the blank spaces feel more dangerous than the named cities.",
                "Good party composition in an RPG is just controlled chaos with emotional fallout.",
                "History gets better the second you stop treating it like dates and start treating it like pressure.",
            ],
        }

        for group_name, prompts in prompt_groups.items():
            if compact in prompts:
                options = prompt_options[group_name]
                return options[hash(compact) % len(options)]
        return None

    def _clean_reply(self, text: str) -> str:
        cleaned = (text or "").strip()
        cleaned = self._remove_reasoning_artifacts(cleaned)
        cleaned = re.sub(r"(?im)^\s*NELLIE_MOOD\s*:\s*.+$", "", cleaned)
        cleaned = re.sub(r"(?im)^\s*MOOD\s*:\s*.+$", "", cleaned)
        cleaned = re.sub(r"\*[^*\n]{1,200}\*", "", cleaned)
        cleaned = re.sub(r"(?im)^\s*\([^()\n]{1,200}\)\s*$", "", cleaned)
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        return cleaned

    def _remove_reasoning_artifacts(self, text: str) -> str:
        cleaned = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text or "")
        cleaned = re.sub(r"(?is)<think>.*?</think>", "", cleaned)
        cleaned = re.sub(r"(?is)^\s*thinking\s*\.\.\.\s*thinking process\s*:.*?\.\.\.\s*done thinking\.?\s*", "", cleaned)
        cleaned = re.sub(r"(?is)^\s*(?:reasoning|analysis|scratchpad|thinking process)\s*:.*?(?:\n\s*\n|$)", "", cleaned)
        cleaned = re.sub(r"(?im)^\s*(?:thinking|done thinking)\s*\.{0,3}\s*$", "", cleaned)
        return cleaned.strip()

    def _ensure_nonempty_reply(self, cleaned: str, user_msg: str) -> str:
        if cleaned and cleaned.strip():
            return cleaned.strip()

        fallback = self._handle_weather_query(user_msg)
        if fallback is not None:
            return fallback

        compact = re.sub(r"[^a-z0-9\s]", "", (user_msg or "").lower())
        compact = re.sub(r"\s+", " ", compact).strip()
        if len(compact.split()) <= 6:
            return "Could you say that again a little differently?"
        return "I lost the thread of that for a second. Ask me again and I'll keep it tighter."

    def _enforce_brevity(self, reply: str, user_msg: str) -> str:
        text = (reply or "").strip()
        if not text:
            return ""

        original = (user_msg or "").strip()
        compact = re.sub(r"[^a-z0-9\s]", "", original.lower())
        compact = re.sub(r"\s+", " ", compact).strip()
        word_count = len(compact.split())
        char_count = len(original)

        if self._classify_conversation_mode(compact, original) == "deep":
            return text

        max_sentences = None
        max_words = None

        if word_count <= 4 or char_count <= 18:
            max_sentences = 1
            max_words = 24
        elif word_count <= 8 or char_count <= 40:
            max_sentences = 2
            max_words = 48
        elif word_count <= 14 or char_count <= 80:
            max_sentences = 3
            max_words = 72

        if max_sentences is None:
            return text

        text = self._limit_sentences(text, max_sentences)
        if max_words is not None:
            text = self._limit_words(text, max_words)
        return text.strip()

    def _limit_sentences(self, text: str, max_sentences: int) -> str:
        if max_sentences <= 0:
            return ""

        parts = re.split(r"(?<=[.!?])\s+", text.strip())
        parts = [part.strip() for part in parts if part.strip()]
        if len(parts) <= max_sentences:
            return " ".join(parts)
        return " ".join(parts[:max_sentences]).strip()

    def _limit_words(self, text: str, max_words: int) -> str:
        words = re.findall(r"\S+", text)
        if len(words) <= max_words:
            return text

        truncated = " ".join(words[:max_words]).rstrip(",;:-")
        if truncated and truncated[-1] not in ".!?":
            truncated += "."
        return truncated

    def _is_identity_query(self, compact: str) -> bool:
        compact = re.sub(r"\s+", " ", (compact or "")).strip()
        if not compact:
            return False

        identity_phrases = [
            "who are you",
            "what are you",
            "tell me about yourself",
            "describe yourself",
            "vem ar du",
        ]
        greeting_prefixes = [
            "hey ",
            "hi ",
            "hello ",
            "yo ",
            "hiya ",
            "well ",
            "so ",
        ]

        if compact in identity_phrases:
            return True
        if any(compact.startswith(prefix) for prefix in greeting_prefixes):
            return any(phrase in compact for phrase in identity_phrases)
        return any(compact.endswith(phrase) for phrase in identity_phrases)

    def _classify_conversation_mode(self, compact: str, original_text: str) -> str:
        deep_markers = [
            "feel",
            "feeling",
            "lonely",
            "sad",
            "hurt",
            "anxious",
            "afraid",
            "relationship",
            "love",
            "meaning",
            "purpose",
            "why",
            "help me",
            "can you help",
            "i need advice",
            "what should i do",
            "trauma",
            "depressed",
            "grief",
            "miss",
        ]
        if len(original_text) > 140:
            return "deep"
        if any(marker in compact for marker in deep_markers):
            return "deep"
        return "casual"

    def _infer_mood(self, text: str, persona: dict | None = None) -> str:
        text = (text or "").lower()
        if not text.strip():
            return self._default_mood(persona)

        scores = {mood: 0 for mood in self.MOOD_PATTERNS}

        for mood, patterns in self.MOOD_PATTERNS.items():
            for pattern in patterns:
                hits = len(re.findall(pattern, text))
                if hits:
                    scores[mood] += hits * self.MOOD_WEIGHTS[mood]

        if "!" in text:
            scores["happy"] += 1
            scores["angry"] += 1
        if "?" in text:
            scores["thoughtful"] += 1
        if "..." in text:
            scores["thoughtful"] += 1
            scores["tired"] += 1

        if any(token in text for token in [":)", ":-)", "haha", "hehe", "aww"]):
            scores["happy"] += 2
        if any(token in text for token in [":(", ":-(", "oh no", "oh, no"]):
            scores["sad"] += 2

        if any(token in text for token in ["take your time", "one step at a time", "gently", "softly"]):
            scores["thoughtful"] += 1
            scores["sad"] += 1
        if any(token in text for token in ["protect", "deserve better", "not fair", "crossed a line"]):
            scores["angry"] += 2
        if any(token in text for token in ["tea", "night", "rain", "window", "quiet", "memory"]):
            scores["thoughtful"] += 1

        if scores["angry"] and self._looks_like_fictional_narrative(text):
            scores["angry"] = 0
            scores["thoughtful"] += 1

        if scores["angry"] and scores["annoyed"]:
            scores["angry"] += 1
        if scores["sad"] and scores["thoughtful"]:
            scores["thoughtful"] += 1
        if scores["happy"] and scores["thoughtful"]:
            scores["happy"] += 1

        allowed = self._allowed_moods(persona)
        filtered_scores = {mood: score for mood, score in scores.items() if mood in allowed}
        mood, score = max(filtered_scores.items(), key=lambda item: item[1])
        return mood if score > 0 else self._default_mood(persona)

    def _looks_like_fictional_narrative(self, text: str) -> bool:
        story_markers = [
            "story",
            "once",
            "bard",
            "king",
            "queen",
            "crown",
            "castle",
            "tavern",
            "enchanted",
            "dragon",
            "lute",
        ]
        angry_markers = ["angry", "furious", "mad", "outrage", "unacceptable"]
        if not any(marker in text for marker in angry_markers):
            return False
        if re.search(r"\b(i am|i'm|im|i feel|you made me|that makes me)\s+(angry|mad|furious)\b", text):
            return False
        return sum(1 for marker in story_markers if marker in text) >= 2

    def _allowed_moods(self, persona: dict | None):
        if persona:
            moods = persona.get("mood_profile", {}).get("allowed_moods")
            if moods:
                return moods
        return ["happy", "neutral", "thoughtful", "sad", "annoyed", "angry", "tired"]

    def _default_mood(self, persona: dict | None):
        if persona:
            return persona.get("mood_profile", {}).get("default_mood", "thoughtful")
        return "thoughtful"
