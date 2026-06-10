import tempfile
import threading
import unittest
from pathlib import Path

from app import BACKEND_API_VERSION, CONFIG_PATH, PROJECT_ROOT, load_config, project_path
from llm.ollama_client import OllamaClient
from services.audio.factory import _default_mood_profiles
from services.audio.service import TTSService
from services.audio.tts_xtts import TTS as XttsBackend
from services.backend.local_adapter import LocalBackendAdapter
from services.backend.speech_prep import build_spoken_reply, prepare_tts_text
from services.emotion.state import EmotionState
from services.memory.sqlite_store import MemoryStore
from services.persona.human_presence import build_human_presence_instruction
from services.tools.weather_open_meteo import extract_location, format_weather, is_weather_query
from services.tools.web_duckduckgo import _prefer_wikipedia, _search_bing_rss, _wikipedia_query
from services.tools.browser_actions import extract_wikipedia_query, extract_youtube_query
from services.tools.calculator_safe import evaluate_expression, extract_expression
from services.tools.datetime_local import lookup_local_datetime
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
        self.assertEqual(BACKEND_API_VERSION, 2)


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
    def test_multiple_preferences_are_saved_without_overwriting(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = MemoryStore(Path(temp_dir) / "memory.db")
            store.capture_user_facts("I like old metal albums.")
            store.capture_user_facts("I like story-driven RPGs.")
            store.capture_user_facts("I don't like forced small talk.")
            store.capture_user_facts("I'm soon having a vacation.")
            store.db.commit()

            facts = dict(store.load_user_facts(limit=20))
            values = set(facts.values())
            self.assertIn("old metal albums", values)
            self.assertIn("story-driven RPGs", values)
            self.assertIn("forced small talk", values)
            self.assertIn("having a vacation", values)
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
