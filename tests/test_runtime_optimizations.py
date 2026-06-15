import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from app import BACKEND_API_VERSION, CONFIG_PATH, PROJECT_ROOT, configure_audio_output, load_config, project_path
from llm.ollama_client import OllamaClient
from services.audio.factory import _default_mood_profiles
from services.audio.service import TTSService
from services.audio.tts_xtts import TTS as XttsBackend
from services.backend.local_adapter import LocalBackendAdapter
from services.backend.speech_prep import build_spoken_reply, prepare_tts_text, sanitize_assistant_reply
from services.emotion.state import EmotionState
from services.memory.sqlite_store import MemoryStore
from services.persona.human_presence import build_human_presence_instruction
from services.persona.normalize import normalize_persona
from services.tools.weather_open_meteo import extract_location, format_weather, is_weather_query
from services.tools.web_duckduckgo import _prefer_wikipedia, _search_bing_rss, _wikipedia_query
from services.tools.browser_actions import extract_wikipedia_query, extract_youtube_query
from services.tools.spotify import (
    extract_spotify_query,
    extract_spotify_suggestion,
    is_spotify_choice_request,
)
from services.tools.calculator_safe import evaluate_expression, extract_expression
from services.tools.datetime_local import lookup_local_datetime
from ui.main_window import MainWindow
from services.tools.web_fetch import extract_url


class RuntimePathTests(unittest.TestCase):
    def test_config_and_relative_paths_are_rooted_at_project(self) -> None:
        conf = load_config()

        self.assertEqual(CONFIG_PATH, PROJECT_ROOT / "config.yaml")
        self.assertEqual(conf["_project_root"], str(PROJECT_ROOT))
        self.assertEqual(project_path("data/memory.db"), PROJECT_ROOT / "data" / "memory.db")
        self.assertEqual(Path(conf["paths"]["db_path"]), PROJECT_ROOT / "data" / "memory.db")
        self.assertEqual(Path(conf["tts"]["voice_sample"]), PROJECT_ROOT / "assets" / "voices" / "Nellie.wav")
        self.assertEqual(
            Path(conf["tts"]["chatterbox_python"]),
            PROJECT_ROOT / ".venv_chatterbox" / "Scripts" / "python.exe",
        )
        self.assertEqual(conf["tts"]["engine"], "chatterbox_turbo")
        self.assertIsNone(conf["audio"]["input_device"])
        self.assertIsNone(conf["audio"]["output_device"])
        self.assertEqual(BACKEND_API_VERSION, 5)

    def test_audio_output_can_be_pinned_without_changing_input(self) -> None:
        fake_sounddevice = MagicMock()
        fake_sounddevice.default.device = [6, 3]
        with patch.dict("sys.modules", {"sounddevice": fake_sounddevice}):
            configure_audio_output({"audio": {"output_device": 19}})

        self.assertEqual(fake_sounddevice.default.device, (6, 19))

    def test_audio_device_lists_separate_microphones_and_speakers(self) -> None:
        fake_sounddevice = MagicMock()
        fake_sounddevice.query_devices.return_value = [
            {"name": "Microphone", "max_input_channels": 1, "max_output_channels": 0},
            {"name": "Headset", "max_input_channels": 1, "max_output_channels": 2},
            {"name": "Speakers", "max_input_channels": 0, "max_output_channels": 2},
        ]
        with patch.dict("sys.modules", {"sounddevice": fake_sounddevice}):
            inputs, outputs = MainWindow._detect_audio_devices(None)

        self.assertEqual(
            inputs,
            [(None, "System Default"), ("0", "Microphone [0]"), ("1", "Headset [1]")],
        )
        self.assertEqual(
            outputs,
            [(None, "System Default"), ("1", "Headset [1]"), ("2", "Speakers [2]")],
        )


class MemoryStoreConcurrencyTests(unittest.TestCase):
    def test_threads_use_independent_connections(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemoryStore(Path(temp_dir) / "memory.db")
            main_connection = store.db
            worker_connections: list[object] = []
            errors: list[BaseException] = []

            def worker(index: int) -> None:
                try:
                    worker_connections.append(store.db)
                    store.save_app_state(f"worker_{index}", str(index))
                except BaseException as exc:
                    errors.append(exc)
                finally:
                    store.close()

            threads = [threading.Thread(target=worker, args=(index,)) for index in range(6)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            self.assertEqual(errors, [])
            self.assertTrue(all(connection is not main_connection for connection in worker_connections))
            for index in range(6):
                self.assertEqual(store.load_app_state(f"worker_{index}"), str(index))
            store.close()


class ModelSelectionTests(unittest.TestCase):
    def test_persona_normalizes_visual_self_image(self) -> None:
        persona = normalize_persona(
            {
                "name": "Nellie",
                "appearance": {
                    "hair": "blonde",
                    "style_notes": "not-a-list",
                },
            }
        )

        self.assertEqual(persona["appearance"]["representation"], "designed digital avatar")
        self.assertEqual(persona["appearance"]["style_notes"], [])

    def test_ollama_prompt_contains_visual_identity_boundaries(self) -> None:
        client = OllamaClient(
            host="http://localhost:11434",
            text_model="hermes3:8b",
        )
        persona = normalize_persona(
            {
                "name": "Nellie",
                "appearance": {
                    "hair": "long blonde hair",
                    "eyes": "light green",
                    "features": "a calm confident gaze",
                },
            }
        )

        prompt = client._build_system_prompt(persona)

        self.assertIn("Visual self-image", prompt)
        self.assertIn("long blonde hair", prompt)
        self.assertIn("light green", prompt)
        self.assertIn("not a claim that you have a biological human body", prompt)

    def test_music_preferences_are_canonical_in_prompt_and_style(self) -> None:
        client = OllamaClient(
            host="http://localhost:11434",
            text_model="hermes3:8b",
        )
        persona = normalize_persona(
            {
                "name": "Nellie",
                "preferences": {
                    "music": {
                        "core_taste": ["metal"],
                        "favorite_track": "Heaven and Hell by Black Sabbath",
                        "signature_tracks": ["Schism by Tool"],
                    }
                },
            }
        )

        prompt = client._build_system_prompt(persona)
        favorite_instruction = client._response_style_instruction("What is your favorite music?")
        activity_instruction = client._response_style_instruction("What are you up to?")

        self.assertIn("Heaven and Hell by Black Sabbath", prompt)
        self.assertIn("Never replace them with an improvised favorite", prompt)
        self.assertIn("canonical music preferences", favorite_instruction)
        self.assertIn("Do not claim you were listening to music", activity_instruction)

    def test_code_access_questions_require_real_tool_results(self) -> None:
        client = OllamaClient(
            host="http://localhost:11434",
            text_model="hermes3:8b",
        )
        prompt = client._build_system_prompt(normalize_persona({"name": "Nellie"}))
        instruction = client._response_style_instruction(
            "Can you take a look at your own code and tell me what you see?"
        )

        self.assertIn("Never claim that you inspected", prompt)
        self.assertIn("Do not mime tool use", prompt)
        self.assertIn("Do not claim or act out that you inspected files", instruction)
        self.assertIn("warm companion tone", instruction)

    def test_casual_status_question_uses_targeted_token_budget(self) -> None:
        class FakeResponse:
            def json(self) -> dict:
                return {"message": {"content": "I'm focused and present."}}

        client = OllamaClient(
            host="http://localhost:11434",
            text_model="hermes3:8b",
            runtime={"num_predict": 220},
        )
        captured: dict = {}

        def fake_post(_path: str, payload: dict, stream: bool = False):
            del stream
            captured.update(payload)
            return FakeResponse()

        client._post = fake_post
        client.chat(normalize_persona({"name": "Nellie"}), "How are you this morning?")

        self.assertEqual(captured["options"]["num_predict"], 64)

    def test_config_exposes_installed_gemma4_model(self) -> None:
        conf = load_config()
        models = {entry["id"] for entry in conf["ollama"]["models"]}

        self.assertIn("gemma4:latest", models)

    def test_local_backend_switches_text_model(self) -> None:
        class FakeLlm:
            text_model = "old-model"

        llm = FakeLlm()
        adapter = LocalBackendAdapter(llm=llm, memory=None)

        self.assertEqual(adapter.set_text_model("gemma4:latest"), "gemma4:latest")
        self.assertEqual(llm.text_model, "gemma4:latest")

    def test_gemma4_disables_hidden_thinking_by_default(self) -> None:
        conf = load_config()
        client = OllamaClient(
            host=conf["ollama"]["host"],
            text_model="gemma4:latest",
            runtime=conf["ollama_runtime"],
        )

        self.assertFalse(client.runtime["think"])


class HumanPresenceTests(unittest.TestCase):
    def test_canned_quick_replies_are_disabled(self) -> None:
        conf = load_config()

        self.assertFalse(conf["ollama_runtime"]["quick_replies"])
        self.assertGreater(conf["ollama_runtime"]["temperature"], 0.5)
        self.assertGreaterEqual(conf["ollama_runtime"]["num_predict"], 200)

    def test_personal_share_gets_reaction_and_contribution_guidance(self) -> None:
        instruction = build_human_presence_instruction(
            "I think this album is brilliant.",
            context="USER: I listened to it last night.",
            emotion_state="mood: happy",
            persona={"behavior_parameters": {"initiative": 0.7, "wit": 0.8}},
        )

        self.assertIn("contribute one relevant thought", instruction)
        self.assertIn("shared something personal", instruction)
        self.assertIn("take a little initiative", instruction)
        self.assertIn("dry humor", instruction)

    def test_short_reaction_stays_on_previous_exchange(self) -> None:
        instruction = build_human_presence_instruction(
            "haha",
            context="NELLIE: I would pick a grimy record shop over a resort.",
            persona={"behavior_parameters": {}},
        )

        self.assertIn("reaction to the immediately previous exchange", instruction)
        self.assertIn("better than interrogating", instruction)
        self.assertIn("Do not ask any question", instruction)

        typo_instruction = build_human_presence_instruction(
            "sonds good enough",
            context="NELLIE: I would choose a lived-in city with record shops.",
            persona={"behavior_parameters": {}},
        )
        self.assertIn("reaction to the immediately previous exchange", typo_instruction)

    def test_emotion_cues_use_whole_words_and_decay(self) -> None:
        state = EmotionState(valence=3, energy=2, attachment=1)
        state.apply_text("The flower is blue.")

        self.assertEqual(state.valence, 2)
        self.assertEqual(state.energy, 1)
        self.assertEqual(state.attachment, 1)

        state.apply_text("I feel lonely and tired.")
        self.assertLess(state.energy, 1)
        self.assertIn("express it subtly", state.as_prompt_block())


class SpeechCompletenessTests(unittest.TestCase):
    def test_stage_directions_and_dangling_marker_are_removed(self) -> None:
        source = (
            "*smirks* I can help think through improvements. "
            "*gives the impression of scrolling through code* "
            "I have not actually inspected the files. *g"
        )

        cleaned = sanitize_assistant_reply(source)
        spoken = build_spoken_reply("What do you see?", source, "chatterbox_turbo")

        self.assertEqual(
            cleaned,
            "I can help think through improvements. I have not actually inspected the files.",
        )
        self.assertEqual(spoken, cleaned)

    def test_tts_preparation_preserves_english_comma_grammar(self) -> None:
        source = (
            "Oh, I was thinking about music, but I was not listening to anything. "
            "What matters is the answer, whether it is short or long."
        )

        prepared = prepare_tts_text(
            source,
            "neutral",
            {"spoken_delivery": {"enabled": False}},
            {},
        )

        self.assertIn("Oh, I was thinking", prepared)
        self.assertIn("answer, whether", prepared)
        self.assertNotIn("Oh. I was", prepared)
        self.assertNotIn("answer. whether", prepared)

    def test_long_voice_text_is_split_without_losing_the_ending(self) -> None:
        class FakeTtsBackend:
            def __init__(self) -> None:
                self.spoken: list[str] = []

            def speak(self, text: str, **_options) -> None:
                self.spoken.append(text)

        backend = FakeTtsBackend()
        service = TTSService(backend)
        ending = "This final sentence must remain intact."
        text = (
            "This is a fairly long first sentence with several clauses, and it needs to be spoken clearly, "
            "without forcing the voice model to generate an entire oversized paragraph in one pass. "
            "A second sentence adds enough material to require another synthesis segment. "
            + ending
        )

        service.speak(text)

        self.assertGreater(len(backend.spoken), 1)
        self.assertTrue(all(len(chunk) <= 260 for chunk in backend.spoken))
        self.assertTrue(backend.spoken[-1].endswith(ending))

    def test_mood_profile_forwards_expression_temperature(self) -> None:
        class FakeTtsBackend:
            def __init__(self) -> None:
                self.options = {}

            def speak(self, _text: str, **options) -> None:
                self.options = options

        backend = FakeTtsBackend()
        service = TTSService(backend, _default_mood_profiles({}))

        service.speak("That is genuinely lovely!", mood="happy")

        self.assertEqual(backend.options["temperature"], 0.78)
        self.assertEqual(backend.options["rate"], "+5%")

    def test_xtts_speak_forwards_temperature_to_synthesis(self) -> None:
        backend = XttsBackend(speaker_wav="missing.wav")
        captured = {}

        def fake_synthesize(**options):
            captured.update(options)
            return b"RIFF"

        backend.synthesize_audio = fake_synthesize

        import sys
        from unittest.mock import MagicMock, patch

        soundfile = MagicMock()
        soundfile.read.return_value = ([0.0], 24000)
        sounddevice = MagicMock()
        with patch.dict(sys.modules, {"soundfile": soundfile, "sounddevice": sounddevice}):
            backend.speak("That is genuinely lovely!", mood="happy", rate="+5%", temperature=0.78)

        self.assertEqual(captured["temperature"], 0.78)
        self.assertEqual(captured["rate"], "+5%")

    def test_expressive_punctuation_is_preserved_for_tts(self) -> None:
        spoken = prepare_tts_text(
            "Really?? That is great!!",
            "neutral",
            {"spoken_delivery": {"enabled": False}},
            {},
        )

        self.assertEqual(spoken, "Really? That is great!")

    def test_long_spoken_reply_keeps_its_ending(self) -> None:
        reply = (
            "This is the first sentence with enough detail to make the reply long. "
            "This is the second sentence and it should still be spoken clearly. "
            "This is the third sentence, followed by more context that used to be cut. "
            "This is the fourth sentence and the final marker must remain audible. FINAL MARKER."
        )

        spoken = build_spoken_reply("Tell me what you think.", reply, "xtts_tts")

        self.assertIn("FINAL MARKER.", spoken)
        self.assertEqual(spoken, reply)

    def test_sharp_delivery_does_not_drop_the_rest_of_a_sentence(self) -> None:
        text = (
            "I disagree with that premise, because the evidence points elsewhere "
            "and the final clause must remain present."
        )

        spoken = prepare_tts_text(
            text,
            "sceptical",
            {"spoken_delivery": {"enabled": True, "filler_probability": 0, "laugh_probability": 0}},
            {"style": {"verbal_ticks": {"enabled": True}}},
        )

        self.assertIn("the final clause must remain present.", spoken)


class OnlineToolTests(unittest.TestCase):
    def test_grounded_presence_and_music_answers_do_not_improvise(self) -> None:
        adapter = LocalBackendAdapter(llm=None, memory=None)
        persona = {
            "runtime_time": {"time_of_day": "morning"},
            "runtime_daily_state": {"focus": "Offer one concrete useful idea"},
            "preferences": {
                "music": {
                    "favorite_track": "Heaven and Hell by Black Sabbath",
                    "core_taste": ["hard rock", "metal"],
                }
            },
        }

        status = adapter._grounded_presence_reply("How are you this morning?", persona)
        activity = adapter._grounded_presence_reply("What are you up to?", persona)
        favorite = adapter._canonical_music_reply("What is your favorite music?", persona)
        spotify = adapter._favorite_spotify_request("Play me your favorite tune on Spotify.", persona)

        self.assertIn("steady and present", status)
        self.assertIn("offer one concrete useful idea", activity)
        self.assertIn("Heaven and Hell by Black Sabbath", favorite)
        self.assertEqual(spotify, "Heaven and Hell by Black Sabbath")
        self.assertNotIn("Willie Nelson", " ".join((status, activity, favorite)))

    def test_safe_calculator_accepts_arithmetic_and_rejects_code(self) -> None:
        self.assertEqual(extract_expression("calculate (12 + 3) * 2"), "(12 + 3) * 2")
        self.assertEqual(evaluate_expression("(12 + 3) * 2"), "30")
        with self.assertRaises(ValueError):
            evaluate_expression("__import__('os').getcwd()")
        with self.assertRaises(ValueError):
            evaluate_expression("2 ** 999")

    def test_datetime_and_url_tools_extract_structured_values(self) -> None:
        local = lookup_local_datetime()
        self.assertRegex(local["time"], r"^\d{2}:\d{2}$")
        self.assertRegex(local["date"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertEqual(
            extract_url("Please summarize https://example.com/article?x=1."),
            "https://example.com/article?x=1",
        )

    def test_contextual_browser_actions_keep_artist_subject(self) -> None:
        context = (
            "USER: how many records has Willie Nelson produced?\n"
            "NELLIE: You might want to check Wikipedia."
        )
        self.assertEqual(extract_wikipedia_query("can you look it up on wikipedia?", context), "Willie Nelson")
        self.assertEqual(extract_youtube_query("can you start youtube for me?", context), "Willie Nelson")
        self.assertEqual(extract_wikipedia_query("Open Wikipedia for me.", context), "Willie Nelson")
        self.assertEqual(extract_youtube_query("Show me a video about Willie Nelson."), "willie nelson")
        self.assertEqual(extract_youtube_query("Show me the video.", context), "Willie Nelson")

    def test_spotify_followup_uses_requested_track(self) -> None:
        spotify_prompt = (
            "USER: Why don't you try to find something on Spotify for me?\n"
            "NELLIE: What are you looking to listen to?"
        )
        self.assertEqual(
            extract_spotify_query(
                "I would like to listen to Heaven and Hell by Black Sabbath.",
                spotify_prompt,
            ),
            "Heaven and Hell by Black Sabbath",
        )

        confirmation_context = (
            f"{spotify_prompt}\n"
            "USER: I would like to listen to Heaven and Hell by Black Sabbath.\n"
            "NELLIE: I can open that up for you right now."
        )
        self.assertEqual(
            extract_spotify_query("Yeah, go ahead.", confirmation_context),
            "Heaven and Hell Black Sabbath",
        )
        self.assertEqual(
            extract_spotify_query(
                "Why don't you try to find Heaven and Hell by Black Sabbath on Spotify?"
            ),
            "heaven and hell by black sabbath",
        )
        self.assertEqual(
            extract_spotify_query("Yes, please, go ahead.", confirmation_context),
            "Heaven and Hell Black Sabbath",
        )
        direct_confirmation_context = (
            "USER: Why don't you try to find Heaven and Hell by Black Sabbath on Spotify?\n"
            "NELLIE: I can open that up for you right now."
        )
        self.assertEqual(
            extract_spotify_query("Yes, please, go ahead.", direct_confirmation_context),
            "Heaven and Hell by Black Sabbath",
        )
        natural_context = (
            'USER: Go ahead and play me one of your favorite tunes.\n'
            'NELLIE: How about "Heaven and Hell" by Black Sabbath?'
        )
        self.assertEqual(
            extract_spotify_query("Why don't you start it up on Spotify for me?", natural_context),
            "Heaven and Hell Black Sabbath",
        )
        self.assertEqual(
            extract_spotify_query("Can you start up Spotify with Black Sabbath and Heaven and Hell?"),
            "black sabbath and heaven and hell",
        )
        self.assertEqual(
            extract_spotify_query("Let's try again.", natural_context),
            "Heaven and Hell Black Sabbath",
        )

    def test_vague_search_planning_question_does_not_trigger_web_lookup(self) -> None:
        adapter = LocalBackendAdapter(llm=None, memory=None)
        self.assertFalse(adapter._should_use_web_search("Shall we try to look up a song again?"))

    def test_spotify_improvisation_extracts_model_choice(self) -> None:
        self.assertTrue(
            is_spotify_choice_request(
                "Just improvise. You choose.",
                "USER: Why don't you improvise and play me a song that you like?",
            )
        )
        self.assertTrue(is_spotify_choice_request("Play me one of your favorite tunes."))
        self.assertEqual(
            extract_spotify_suggestion(
                "I'll play something with raw energy. How about some early Joy Division? It fits."
            ),
            "early Joy Division",
        )
        self.assertEqual(
            extract_spotify_query(
                "Go ahead.",
                "USER: Play me a song that you like.\n"
                "NELLIE: How about some early Joy Division?",
            ),
            "early Joy Division",
        )

        conf = load_config()
        client = OllamaClient(
            host=conf["ollama"]["host"],
            text_model=conf["ollama"]["text_model"],
            runtime=conf["ollama_runtime"],
        )
        instruction = client._response_style_instruction(
            "Why don't you improvise and play me a song that you like?"
        )
        self.assertIn("Choose one concrete song or artist now", instruction)
        self.assertIn("Do not ask for a genre, mood, vibe, or confirmation", instruction)

    def test_favorite_tune_request_runs_spotify_action_before_chat(self) -> None:
        persona = {
            "preferences": {
                "music": {
                    "favorite_track": "Heaven and Hell by Black Sabbath",
                }
            }
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            memory = MemoryStore(Path(temp_dir) / "memory.db")
            adapter = LocalBackendAdapter(llm=None, memory=memory)
            try:
                with patch(
                    "services.backend.local_adapter.open_spotify_query",
                    return_value=(True, "spotify:search:test"),
                ):
                    result = adapter.respond_turn(
                        persona=persona,
                        user_text="Go ahead and play me one of your favorite tunes.",
                        tools_enabled={"spotify_control": True},
                    )
            finally:
                memory.close()

        self.assertEqual(result["kind"], "agent")
        self.assertEqual(result["action"], "spotify_play")
        self.assertEqual(result["query"], "Heaven and Hell by Black Sabbath")
        self.assertEqual(result["status"], "opened")

    def test_web_grounding_retry_detects_tool_denial(self) -> None:
        conf = load_config()
        client = OllamaClient(
            host=conf["ollama"]["host"],
            text_model=conf["ollama"]["text_model"],
            runtime=conf["ollama_runtime"],
        )
        self.assertTrue(client._needs_web_grounding_retry("The results don't give a specific number."))
        self.assertTrue(client._needs_web_grounding_retry("None provide a specific kilometer distance."))
        self.assertFalse(client._needs_web_grounding_retry("The estimated distance is about 1,600 km."))

    def test_weather_query_extracts_location(self) -> None:
        self.assertTrue(is_weather_query("what weather is it in Motala today?"))
        self.assertEqual(extract_location("what weather is it in Motala today?"), "Motala")
        self.assertEqual(extract_location("hur är vädret i Linköping just nu?"), "Linköping")

    def test_weather_response_uses_structured_values(self) -> None:
        reply = format_weather(
            {
                "name": "Motala",
                "country": "Sweden",
                "temperature": 18.2,
                "feels_like": 17.1,
                "humidity": 62,
                "weather_code": 2,
                "wind_speed": 11.4,
                "today_min": 9.0,
                "today_max": 19.0,
                "precipitation_probability": 20,
            }
        )
        self.assertIn("18.2°C", reply)
        self.assertIn("partly cloudy", reply)
        self.assertIn("9 to 19°C", reply)

    def test_bing_rss_fallback_parses_results(self) -> None:
        class FakeResponse:
            text = (
                "<?xml version='1.0'?><rss><channel><item>"
                "<title>Example result</title><link>https://example.com/weather</link>"
                "<description>Current conditions.</description>"
                "</item></channel></rss>"
            )

            def raise_for_status(self) -> None:
                return

        class FakeRequests:
            @staticmethod
            def get(*_args, **_kwargs):
                return FakeResponse()

        results = _search_bing_rss(FakeRequests(), "weather", 3)
        self.assertEqual(results[0]["domain"], "example.com")

    def test_wikipedia_query_keeps_artist_and_discography_topic(self) -> None:
        self.assertEqual(
            _wikipedia_query("Willie Nelson discography number of studio albums released"),
            "Willie Nelson discography",
        )
        self.assertEqual(_wikipedia_query("Willie Nelson first studio album"), "Willie Nelson")
        self.assertTrue(_prefer_wikipedia("Willie Nelson first studio album"))
        self.assertFalse(_prefer_wikipedia("latest news in Sweden today"))

    def test_web_query_corrects_common_search_typos(self) -> None:
        adapter = LocalBackendAdapter(llm=None, memory=None)
        query = adapter._extract_web_query(
            "what is the dinstace beteen Rivendel and the Gates of Mordor"
        )
        self.assertEqual(query, "Rivendell the Gates of Mordor distance kilometres")

    def test_music_count_query_becomes_discography_search(self) -> None:
        adapter = LocalBackendAdapter(llm=None, memory=None)
        query = adapter._extract_web_query("how many records have Willie Nelson produced?")
        self.assertEqual(query, "Willie Nelson discography number of studio albums released")

    def test_music_followups_keep_recent_artist_subject(self) -> None:
        class FakeMemory:
            @staticmethod
            def build_context(*_args, **_kwargs):
                return (
                    "USER: how many records has Willie Nelson produced?\n"
                    "NELLIE: I can look that up."
                )

            @staticmethod
            def latest_turn():
                return (
                    "how many records has Willie Nelson produced?",
                    "I can look that up.",
                    "neutral",
                )

        adapter = LocalBackendAdapter(llm=None, memory=FakeMemory())

        self.assertEqual(
            adapter._followup_web_query("number of records"),
            "Willie Nelson discography number of studio albums released",
        )
        self.assertEqual(
            adapter._followup_web_query("what's his first album?"),
            "Willie Nelson first studio album",
        )
        self.assertEqual(
            adapter._followup_web_query("just give me anything from him, maybe a good song"),
            "Willie Nelson best known songs official discography",
        )

    def test_short_confirmation_resumes_weather_lookup(self) -> None:
        class FakeMemory:
            @staticmethod
            def latest_turn():
                return (
                    "Yo Nellie",
                    "Do you still want me to look up the weather for Motala?",
                    "neutral",
                )

        adapter = LocalBackendAdapter(llm=None, memory=FakeMemory())
        self.assertEqual(adapter._followup_web_query("yes pleace"), "weather in Motala today")


class PreferenceMemoryTests(unittest.TestCase):
    def test_context_cutoff_keeps_old_turns_out_of_new_replies(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemoryStore(Path(temp_dir) / "memory.db")
            try:
                store.save_turn("Old misunderstanding", "The audio connection is broken.")
                store.save_app_state("conversation_context_cutoff", str(datetime.now().timestamp() + 1))
                context = store.build_context({}, k=4)
            finally:
                store.close()

            self.assertNotIn("Old misunderstanding", context)
            self.assertIn("fresh conversation", context)

    def test_daily_ambitions_are_stable_for_the_day_and_rotate(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemoryStore(Path(temp_dir) / "memory.db")
            persona = {
                "profile": {"id": "nellie"},
                "daily_ambitions": ["one", "two", "three", "four"],
            }
            day_one = datetime(2026, 6, 15, 9, 0, tzinfo=timezone.utc)
            same_day = datetime(2026, 6, 15, 20, 0, tzinfo=timezone.utc)
            day_two = day_one + timedelta(days=1)

            first = store.get_daily_state(persona, day_one)
            later = store.get_daily_state(persona, same_day)
            tomorrow = store.get_daily_state(persona, day_two)

            self.assertEqual(first["focus"], later["focus"])
            self.assertEqual(first["ambitions"], later["ambitions"])
            self.assertNotEqual(first["focus"], tomorrow["focus"])
            store.close()

    def test_old_turns_are_marked_as_an_earlier_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemoryStore(Path(temp_dir) / "memory.db")
            store.save_turn("I was upset.", "I hear you.")
            old_timestamp = datetime.now().astimezone().timestamp() - (72 * 3600)
            store.db.execute("UPDATE turns SET ts = ?", (old_timestamp,))
            store.db.commit()

            context = store.build_context({}, k=4, max_chars=1200)

            self.assertIn("EARLIER CONVERSATION", context)
            self.assertIn("do not continue its mood", context)
            self.assertIn("CURRENT LOCAL TIME", context)
            store.close()

    def test_swedish_preferences_are_saved_as_structured_memory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemoryStore(Path(temp_dir) / "memory.db")
            store.save_turn("Jag älskar svensk punk.", "Bra smak.")

            memories = store.load_structured_memories()

            self.assertTrue(any(item["value"] == "svensk punk" for item in memories))
            matching = next(item for item in memories if item["value"] == "svensk punk")
            self.assertEqual(matching["category"], "preference")
            self.assertTrue(matching["confirmed"])
            store.close()

    def test_sensitive_extracted_memory_requires_explicit_consent(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemoryStore(Path(temp_dir) / "memory.db")
            item = {
                "category": "identity",
                "value": "My exact address is Example Street 1",
                "confidence": 0.99,
                "sensitive": True,
            }

            self.assertEqual(store.save_extracted_memories([item]), 0)
            self.assertEqual(
                store.save_extracted_memories([item], explicit_sensitive_consent=True),
                1,
            )
            self.assertTrue(store.load_structured_memories()[0]["sensitive"])
            store.close()

    def test_only_approved_feedback_is_exportable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemoryStore(Path(temp_dir) / "memory.db")
            store.save_feedback("Question", "Good answer", 1, model="hermes3:8b")
            store.save_feedback("Question", "Bad answer", -1, model="hermes3:8b")
            store.save_feedback(
                "Question",
                "Weak answer",
                -1,
                correction="Corrected answer",
                model="hermes3:8b",
            )

            approved = store.approved_feedback()

            self.assertEqual(len(approved), 2)
            self.assertEqual(approved[1]["correction"], "Corrected answer")
            store.close()

    def test_multiple_preferences_are_saved_without_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemoryStore(Path(temp_dir) / "memory.db")
            store.capture_user_facts("I like old metal albums.")
            store.capture_user_facts("I like story-driven RPGs.")
            store.capture_user_facts("I don't like forced small talk.")
            store.capture_user_facts("I'm soon having a vacation.")
            store.capture_user_facts("I love local AI projects.")
            store.capture_user_facts("I would love to hear Heaven and Hell by Black Sabbath on Spotify.")
            store.db.commit()

            facts = dict(store.load_user_facts(limit=20))
            values = set(facts.values())
            self.assertIn("old metal albums", values)
            self.assertIn("story-driven RPGs", values)
            self.assertIn("forced small talk", values)
            self.assertIn("having a vacation", values)
            self.assertIn("local AI projects", values)
            self.assertIn("Heaven and Hell by Black Sabbath", values)
            store.close()

    def test_context_prioritizes_latest_turns_over_persona_text(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemoryStore(Path(temp_dir) / "memory.db")
            for index in range(6):
                store.save_turn(
                    user=f"user turn {index}",
                    ai=f"reply {index}",
                    persona={"identity": {"summary": "X" * 5000}},
                )

            context = store.build_context(
                {"identity": {"summary": "X" * 5000}},
                k=5,
                max_chars=500,
                per_turn_chars=80,
            )

            self.assertIn("user turn 5", context)
            self.assertIn("reply 5", context)
            self.assertNotIn("X" * 100, context)
            self.assertLessEqual(len(context), 500)
            store.close()


if __name__ == "__main__":
    unittest.main()
