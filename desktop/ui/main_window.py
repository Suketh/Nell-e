# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownLambdaType=false, reportMissingParameterType=false, reportArgumentType=false, reportCallIssue=false, reportAssignmentType=false, reportOptionalMemberAccess=false, reportOptionalCall=false, reportOptionalSubscript=false, reportOperatorIssue=false, reportAttributeAccessIssue=false, reportReturnType=false, reportIndexIssue=false, reportPossiblyUnboundVariable=false

import queue
import random
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from services.admin.session_logger import SessionLogger
from services.emotion.state import EmotionState
from services.gallery.library import GalleryLibrary
from services.audio.protocols import STTProtocol, TTSProtocol
from services.tools.web_duckduckgo import search as web_search, summarize_results
from services.audio.stt_factory import create_stt_service, preferred_stt_engine
from services.audio.factory import create_tts_service
from ui.admin_dialog import AdminDialog
from ui.chat_view import ChatView
from ui.composer_card import ComposerCard
from ui.header_card import HeaderCard
from ui.recorder_widget import RecorderWidget
from ui.theme import build_theme_tokens


class SettingsDialog(QDialog):
    def __init__(self, parent: "MainWindow") -> None:
        super().__init__(parent)
        self.window = parent
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setObjectName("settingsDialog")
        self.setMinimumWidth(380)
        self.setMinimumHeight(520)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        scroll = QScrollArea()
        scroll.setObjectName("settingsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(10)

        title = QLabel("Voice, speech, and safety")
        title.setObjectName("settingsTitle")
        subtitle = QLabel("Adjust Nellie's voice, speech input, conversation style, and system behavior.")
        subtitle.setObjectName("settingsSubtitle")
        subtitle.setWordWrap(True)
        content_layout.addWidget(title)
        content_layout.addWidget(subtitle)

        voice_section, voice_layout = self._section_card("Voice")

        engine_label = QLabel("Voice engine")
        engine_label.setObjectName("controlLabel")
        voice_layout.addWidget(engine_label)

        self.tts_engine = QComboBox()
        self.tts_engine.setObjectName("voiceProfile")
        self.tts_engine.currentIndexChanged.connect(self._on_tts_engine_changed)
        voice_layout.addWidget(self.tts_engine)

        voice_row = QWidget()
        voice_row.setObjectName("settingsRow")
        voice_layout.addWidget(voice_row)
        voice_row_layout = QHBoxLayout(voice_row)
        voice_row_layout.setContentsMargins(0, 0, 0, 0)
        voice_row_layout.setSpacing(10)
        voice_layout.setContentsMargins(0, 0, 0, 0)
        voice_label = QLabel("Voice")
        voice_label.setObjectName("controlLabel")
        self.voice_toggle = QPushButton()
        self.voice_toggle.setObjectName("secondaryButton")
        self.voice_toggle.setCheckable(True)
        self.voice_toggle.clicked.connect(self._on_voice_toggled)
        voice_row_layout.addWidget(voice_label)
        voice_row_layout.addStretch(1)
        voice_row_layout.addWidget(self.voice_toggle)

        volume_label = QLabel("Volume")
        volume_label.setObjectName("controlLabel")
        voice_layout.addWidget(volume_label)

        self.volume_slider = QSlider(Qt.Orientation.Horizontal)
        self.volume_slider.setObjectName("volumeSlider")
        self.volume_slider.setRange(0, 100)
        self.volume_slider.valueChanged.connect(self.window.change_volume)
        voice_layout.addWidget(self.volume_slider)

        voice_sample_label = QLabel("Voice sample")
        voice_sample_label.setObjectName("controlLabel")
        voice_layout.addWidget(voice_sample_label)

        self.voice_sample_select = QComboBox()
        self.voice_sample_select.setObjectName("voiceProfile")
        self.voice_sample_select.currentIndexChanged.connect(self._on_voice_sample_changed)
        voice_layout.addWidget(self.voice_sample_select)

        self.voice_hint = QLabel()
        self.voice_hint.setObjectName("settingsHint")
        self.voice_hint.setWordWrap(True)
        voice_layout.addWidget(self.voice_hint)

        content_layout.addWidget(voice_section)

        speech_section, speech_layout = self._section_card("Speech")

        stt_label = QLabel("Speech input")
        stt_label.setObjectName("controlLabel")
        speech_layout.addWidget(stt_label)

        self.stt_engine = QComboBox()
        self.stt_engine.setObjectName("voiceProfile")
        self.stt_engine.currentIndexChanged.connect(self._on_stt_engine_changed)
        speech_layout.addWidget(self.stt_engine)

        mic_label = QLabel("Microphone")
        mic_label.setObjectName("controlLabel")
        speech_layout.addWidget(mic_label)

        self.audio_input_select = QComboBox()
        self.audio_input_select.setObjectName("voiceProfile")
        self.audio_input_select.currentIndexChanged.connect(self._on_audio_input_changed)
        speech_layout.addWidget(self.audio_input_select)

        self.stt_hint = QLabel()
        self.stt_hint.setObjectName("settingsHint")
        self.stt_hint.setWordWrap(True)
        speech_layout.addWidget(self.stt_hint)

        self.refresh_stt_btn = QPushButton("Refresh Speech Runtime")
        self.refresh_stt_btn.setObjectName("secondaryButton")
        self.refresh_stt_btn.clicked.connect(self.window.refresh_speech_runtime)
        speech_layout.addWidget(self.refresh_stt_btn)

        self.start_voxtral_btn = QPushButton("Start Local Voxtral")
        self.start_voxtral_btn.setObjectName("secondaryButton")
        self.start_voxtral_btn.clicked.connect(self.window.start_local_voxtral)
        speech_layout.addWidget(self.start_voxtral_btn)

        content_layout.addWidget(speech_section)

        behavior_section, behavior_layout = self._section_card("Conversation")

        model_label = QLabel("Language model")
        model_label.setObjectName("controlLabel")
        behavior_layout.addWidget(model_label)

        self.model_select = QComboBox()
        self.model_select.setObjectName("voiceProfile")
        self.model_select.currentIndexChanged.connect(self._on_model_changed)
        behavior_layout.addWidget(self.model_select)

        self.model_hint = QLabel()
        self.model_hint.setObjectName("settingsHint")
        self.model_hint.setWordWrap(True)
        behavior_layout.addWidget(self.model_hint)

        language_label = QLabel("Language")
        language_label.setObjectName("controlLabel")
        behavior_layout.addWidget(language_label)

        self.language_select = QComboBox()
        self.language_select.setObjectName("voiceProfile")
        self.language_select.currentIndexChanged.connect(self._on_language_changed)
        behavior_layout.addWidget(self.language_select)

        theme_label = QLabel("Appearance")
        theme_label.setObjectName("controlLabel")
        behavior_layout.addWidget(theme_label)

        self.theme_select = QComboBox()
        self.theme_select.setObjectName("voiceProfile")
        self.theme_select.addItem("Light", "light")
        self.theme_select.addItem("Dark", "dark")
        self.theme_select.addItem("Crimson", "crimson")
        self.theme_select.addItem("Futurist", "futurist")
        self.theme_select.addItem("Classic", "classic")
        self.theme_select.currentIndexChanged.connect(self._on_theme_changed)
        behavior_layout.addWidget(self.theme_select)

        self.remember_toggle = QCheckBox("Remember chat between replies")
        self.remember_toggle.setObjectName("rememberToggle")
        self.remember_toggle.toggled.connect(self.window.set_remember_chat_enabled)
        behavior_layout.addWidget(self.remember_toggle)

        content_layout.addWidget(behavior_section)

        tools_section, tools_layout = self._section_card("Tools")
        tools_hint = QLabel("Enable or disable Nellie's individual capabilities.")
        tools_hint.setObjectName("settingsHint")
        tools_hint.setWordWrap(True)
        tools_layout.addWidget(tools_hint)

        self.calculator_toggle = QCheckBox("Calculator")
        self.calculator_toggle.setObjectName("rememberToggle")
        self.calculator_toggle.toggled.connect(self.window.set_calculator_enabled)
        tools_layout.addWidget(self.calculator_toggle)

        self.datetime_toggle = QCheckBox("Time and date")
        self.datetime_toggle.setObjectName("rememberToggle")
        self.datetime_toggle.toggled.connect(self.window.set_datetime_enabled)
        tools_layout.addWidget(self.datetime_toggle)

        self.weather_toggle = QCheckBox("Weather")
        self.weather_toggle.setObjectName("rememberToggle")
        self.weather_toggle.toggled.connect(self.window.set_weather_enabled)
        tools_layout.addWidget(self.weather_toggle)

        self.wikipedia_toggle = QCheckBox("Wikipedia")
        self.wikipedia_toggle.setObjectName("rememberToggle")
        self.wikipedia_toggle.toggled.connect(self.window.set_wikipedia_enabled)
        tools_layout.addWidget(self.wikipedia_toggle)

        self.web_search_toggle = QCheckBox("Web search")
        self.web_search_toggle.setObjectName("rememberToggle")
        self.web_search_toggle.toggled.connect(self.window.set_web_search_enabled)
        tools_layout.addWidget(self.web_search_toggle)

        self.web_fetch_toggle = QCheckBox("Web page reading")
        self.web_fetch_toggle.setObjectName("rememberToggle")
        self.web_fetch_toggle.toggled.connect(self.window.set_web_fetch_enabled)
        tools_layout.addWidget(self.web_fetch_toggle)

        self.youtube_toggle = QCheckBox("YouTube")
        self.youtube_toggle.setObjectName("rememberToggle")
        self.youtube_toggle.toggled.connect(self.window.set_youtube_enabled)
        tools_layout.addWidget(self.youtube_toggle)

        self.spotify_toggle = QCheckBox("Spotify")
        self.spotify_toggle.setObjectName("rememberToggle")
        self.spotify_toggle.toggled.connect(self.window.set_spotify_enabled)
        tools_layout.addWidget(self.spotify_toggle)

        content_layout.addWidget(tools_section)

        safety_section, safety_layout = self._section_card("Safety and Limits")

        self.pegi13_toggle = QCheckBox("PEGI-13 mode")
        self.pegi13_toggle.setObjectName("rememberToggle")
        self.pegi13_toggle.toggled.connect(self.window.set_pegi13_enabled)
        safety_layout.addWidget(self.pegi13_toggle)

        self.safety_filters_toggle = QCheckBox("Extra safety filters")
        self.safety_filters_toggle.setObjectName("rememberToggle")
        self.safety_filters_toggle.toggled.connect(self.window.set_safety_filters_enabled)
        safety_layout.addWidget(self.safety_filters_toggle)

        self.policy_hint = QLabel()
        self.policy_hint.setObjectName("settingsSubtitle")
        self.policy_hint.setWordWrap(True)
        safety_layout.addWidget(self.policy_hint)

        content_layout.addWidget(safety_section)

        actions_section, actions_section_layout = self._section_card("System")
        actions = QWidget()
        actions_layout = QVBoxLayout(actions)
        actions_layout.setContentsMargins(0, 4, 0, 0)
        actions_layout.setSpacing(8)

        self.clear_memory_btn = QPushButton("Clear Memory")
        self.clear_memory_btn.setObjectName("secondaryButton")
        self.clear_memory_btn.clicked.connect(self.window.clear_conversation_memory)

        self.clear_cache_btn = QPushButton("Clear TTS Cache")
        self.clear_cache_btn.setObjectName("secondaryButton")
        self.clear_cache_btn.clicked.connect(self.window.clear_tts_cache)

        self.admin_btn = QPushButton("Admin Monitor")
        self.admin_btn.setObjectName("secondaryButton")
        self.admin_btn.clicked.connect(self.window.open_admin_monitor)

        self.test_stt_btn = QPushButton("Test Speech Input")
        self.test_stt_btn.setObjectName("secondaryButton")
        self.test_stt_btn.clicked.connect(self.window.test_speech_input)

        actions_layout.addWidget(self.clear_memory_btn)
        actions_layout.addWidget(self.test_stt_btn)
        actions_layout.addWidget(self.clear_cache_btn)
        actions_layout.addWidget(self.admin_btn)
        actions_section_layout.addWidget(actions)
        content_layout.addWidget(actions_section)

        footer = QWidget()
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 8, 0, 0)
        footer_layout.addStretch(1)
        close_btn = QPushButton("Close")
        close_btn.setObjectName("primaryButton")
        close_btn.clicked.connect(self.accept)
        footer_layout.addWidget(close_btn)
        content_layout.addWidget(footer)
        content_layout.addStretch(1)

        scroll.setWidget(content)
        layout.addWidget(scroll)

        self.sync_from_window()

    def _section_card(self, title_text: str) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame()
        card.setObjectName("settingsSection")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(14, 14, 14, 14)
        card_layout.setSpacing(10)
        title = QLabel(title_text)
        title.setObjectName("sectionTitle")
        card_layout.addWidget(title)
        return card, card_layout

    def sync_from_window(self) -> None:
        self.voice_toggle.blockSignals(True)
        self.tts_engine.blockSignals(True)
        self.volume_slider.blockSignals(True)
        self.voice_sample_select.blockSignals(True)
        self.stt_engine.blockSignals(True)
        self.audio_input_select.blockSignals(True)
        self.model_select.blockSignals(True)
        self.language_select.blockSignals(True)
        self.theme_select.blockSignals(True)
        self.remember_toggle.blockSignals(True)
        self.calculator_toggle.blockSignals(True)
        self.datetime_toggle.blockSignals(True)
        self.weather_toggle.blockSignals(True)
        self.wikipedia_toggle.blockSignals(True)
        self.web_search_toggle.blockSignals(True)
        self.web_fetch_toggle.blockSignals(True)
        self.youtube_toggle.blockSignals(True)
        self.spotify_toggle.blockSignals(True)
        self.pegi13_toggle.blockSignals(True)
        self.safety_filters_toggle.blockSignals(True)

        enabled = bool(getattr(self.window.tts, "enabled", True))
        self.voice_toggle.setChecked(enabled)
        self.voice_toggle.setText("Voice On" if enabled else "Voice Off")
        self.tts_engine.clear()
        for key, label in self.window.available_tts_engines.items():
            self.tts_engine.addItem(label, key)
        tts_index = self.tts_engine.findData(self.window.current_tts_engine)
        if tts_index >= 0:
            self.tts_engine.setCurrentIndex(tts_index)
        self.volume_slider.setValue(getattr(self.window.tts, "master_volume", 100))
        self.voice_sample_select.clear()
        for sample_path, sample_label in self.window.available_voice_samples.items():
            self.voice_sample_select.addItem(sample_label, sample_path)
        sample_index = self.voice_sample_select.findData(self.window.current_voice_sample)
        if sample_index >= 0:
            self.voice_sample_select.setCurrentIndex(sample_index)
        engine_label = self.window.available_tts_engines.get(self.window.current_tts_engine, "Voice")
        self.voice_hint.setText(
            f"{engine_label} is active. Current voice sample: "
            f"{self.window.available_voice_samples.get(self.window.current_voice_sample, Path(self.window.current_voice_sample).stem)}."
        )
        self.stt_engine.clear()
        for key, label in self.window.available_stt_engines.items():
            self.stt_engine.addItem(label, key)
        stt_index = self.stt_engine.findData(self.window.current_stt_engine)
        if stt_index >= 0:
            self.stt_engine.setCurrentIndex(stt_index)
        self.audio_input_select.clear()
        for device_id, label in self.window.available_audio_inputs:
            self.audio_input_select.addItem(label, device_id)
        device_index = self.audio_input_select.findData(self.window.current_audio_input_device)
        if device_index >= 0:
            self.audio_input_select.setCurrentIndex(device_index)
        elif self.audio_input_select.count() > 0:
            self.audio_input_select.setCurrentIndex(0)
        if self.window.current_stt_engine == "voxtral_realtime":
            self.stt_hint.setText(self.window.describe_stt_settings())
        else:
            self.stt_hint.setText(self.window.describe_stt_settings())
        self.start_voxtral_btn.setEnabled(self.window.can_start_local_voxtral())
        self.model_select.clear()
        for model_id, model_label in self.window.available_text_models.items():
            self.model_select.addItem(model_label, model_id)
        model_index = self.model_select.findData(self.window.current_text_model)
        if model_index >= 0:
            self.model_select.setCurrentIndex(model_index)
        self.model_hint.setText(f"Active Ollama model: {self.window.current_text_model}")
        self.language_select.clear()
        for key, option in self.window.language_options.items():
            self.language_select.addItem(option.get("label", key), key)
        lang_index = self.language_select.findData(self.window.current_language)
        if lang_index >= 0:
            self.language_select.setCurrentIndex(lang_index)
        theme_index = self.theme_select.findData(self.window.current_theme)
        if theme_index >= 0:
            self.theme_select.setCurrentIndex(theme_index)
        self.remember_toggle.setChecked(self.window.remember_chat_enabled)
        self.calculator_toggle.setChecked(self.window.calculator_enabled)
        self.datetime_toggle.setChecked(self.window.datetime_enabled)
        self.weather_toggle.setChecked(self.window.weather_enabled)
        self.wikipedia_toggle.setChecked(self.window.wikipedia_enabled)
        self.web_search_toggle.setChecked(self.window.web_search_enabled)
        self.web_fetch_toggle.setChecked(self.window.web_fetch_enabled)
        self.youtube_toggle.setChecked(self.window.youtube_enabled)
        self.spotify_toggle.setChecked(self.window.spotify_enabled)
        self.pegi13_toggle.setChecked(self.window.pegi13_enabled)
        self.safety_filters_toggle.setChecked(self.window.safety_filters_enabled)
        self.policy_hint.setText(self.window.describe_policy_settings())

        self.voice_toggle.blockSignals(False)
        self.tts_engine.blockSignals(False)
        self.volume_slider.blockSignals(False)
        self.voice_sample_select.blockSignals(False)
        self.stt_engine.blockSignals(False)
        self.audio_input_select.blockSignals(False)
        self.model_select.blockSignals(False)
        self.language_select.blockSignals(False)
        self.theme_select.blockSignals(False)
        self.remember_toggle.blockSignals(False)
        self.calculator_toggle.blockSignals(False)
        self.datetime_toggle.blockSignals(False)
        self.weather_toggle.blockSignals(False)
        self.wikipedia_toggle.blockSignals(False)
        self.web_search_toggle.blockSignals(False)
        self.web_fetch_toggle.blockSignals(False)
        self.youtube_toggle.blockSignals(False)
        self.spotify_toggle.blockSignals(False)
        self.pegi13_toggle.blockSignals(False)
        self.safety_filters_toggle.blockSignals(False)

    def _on_voice_toggled(self) -> None:
        enabled = self.voice_toggle.isChecked()
        self.window.set_tts_enabled(enabled)
        self.voice_toggle.setText("Voice On" if enabled else "Voice Off")

    def _on_tts_engine_changed(self) -> None:
        key = self.tts_engine.currentData()
        if key:
            self.window.set_tts_engine(str(key))

    def _on_stt_engine_changed(self) -> None:
        key = self.stt_engine.currentData()
        if key:
            self.window.set_stt_engine(key)

    def _on_audio_input_changed(self) -> None:
        device = self.audio_input_select.currentData()
        self.window.set_audio_input_device(device)

    def _on_voice_sample_changed(self) -> None:
        sample = self.voice_sample_select.currentData()
        if sample:
            self.window.set_voice_sample(str(sample))

    def _on_language_changed(self) -> None:
        key = self.language_select.currentData()
        if key:
            self.window.set_language(key)

    def _on_model_changed(self) -> None:
        model = self.model_select.currentData()
        if model:
            self.window.set_text_model(str(model))

    def _on_theme_changed(self) -> None:
        key = self.theme_select.currentData()
        if key:
            self.window.set_theme(key)


class MainWindow(QMainWindow):
    chat_chunk = Signal(str)
    chat_started = Signal()
    reply_ready = Signal(int, str, str, str)
    mood_changed = Signal(str)
    avatar_expression_changed = Signal(str, str)
    ai_message = Signal(str)
    ai_image = Signal(str, str)
    stream_done = Signal(str)
    tts_status_changed = Signal(str)
    spoken_reply_ready = Signal(int, str, str, str)
    admin_log_line = Signal(str)
    speech_runtime_changed = Signal(bool, str)
    voxtral_ready = Signal()

    def __init__(
        self,
        conf: dict[str, Any],
        persona: dict[str, Any],
        ollama: Any,
        stt: STTProtocol,
        tts: TTSProtocol,
        memory: Any,
        backend: Any | None = None,
    ) -> None:
        super().__init__()
        self.setWindowTitle("Nellie")
        self.resize(560, 940)
        self.setMinimumSize(360, 520)
        self.conf = conf
        self.persona = persona
        self.ollama = ollama
        self.stt = stt
        self.tts = tts
        self.memory = memory
        self.backend = backend
        state_store = self.backend if self.backend is not None else self.memory
        self.emotion = state_store.load_emotion_state()
        self.current_mood = self.emotion.mood
        self.current_expression = "neutral"
        self.progression = self._load_progression_state()
        self._last_progression_flash_ts = 0.0
        self.remember_chat_enabled = state_store.load_app_state("remember_chat_enabled", "1") == "1"
        self.calculator_enabled = state_store.load_app_state("tool_calculator", "1") == "1"
        self.datetime_enabled = state_store.load_app_state("tool_datetime", "1") == "1"
        self.weather_enabled = state_store.load_app_state("tool_weather", "1") == "1"
        self.wikipedia_enabled = state_store.load_app_state("tool_wikipedia", "1") == "1"
        self.web_search_enabled = state_store.load_app_state("web_search_enabled", "0") == "1"
        self.web_fetch_enabled = state_store.load_app_state("tool_web_fetch", "1") == "1"
        self.youtube_enabled = state_store.load_app_state("tool_youtube", "0") == "1"
        self.spotify_enabled = state_store.load_app_state("tool_spotify", "0") == "1"
        ollama_conf = conf.get("ollama", {})
        configured_text_model = str(ollama_conf.get("text_model", "")).strip()
        self.available_text_models = {
            str(entry.get("id", "")).strip(): str(entry.get("label", entry.get("id", ""))).strip()
            for entry in ollama_conf.get("models", [])
            if isinstance(entry, dict) and str(entry.get("id", "")).strip()
        }
        if configured_text_model and configured_text_model not in self.available_text_models:
            self.available_text_models[configured_text_model] = configured_text_model
        stored_text_model = state_store.load_app_state("ollama_text_model")
        self.current_text_model = stored_text_model or configured_text_model
        if self.current_text_model not in self.available_text_models:
            self.current_text_model = configured_text_model
        self.conf.setdefault("ollama", {})["text_model"] = self.current_text_model
        if self.ollama is not None and hasattr(self.ollama, "text_model"):
            self.ollama.text_model = self.current_text_model
        self.available_tts_engines = {
            "chatterbox_turbo": "Chatterbox-Turbo",
            "xtts_tts": "XTTS v2",
        }
        project_root = Path(str(conf.get("_project_root", ".")))
        voices_dir = project_root / "assets" / "voices"
        self.available_voice_samples = {
            str(path).replace("\\", "/"): path.stem
            for path in sorted(voices_dir.glob("*"))
            if path.suffix.lower() in {".wav", ".mp3", ".flac", ".ogg", ".m4a"}
        }
        self.available_stt_engines = {
            "faster_whisper": "Local Whisper",
            "voxtral_realtime": "Voxtral Realtime (Advanced)",
        }
        self.available_audio_inputs = self._detect_audio_inputs()
        languages_conf = conf.get("languages", {})
        self.language_options = languages_conf.get("options", {}) or {
            "en": {
                "label": "English",
                "reply_language": "English",
                "stt_language": "en",
                "input_placeholder": "Write to Nellie...",
            }
        }
        default_language = languages_conf.get("default", "en")
        self.current_language = state_store.load_app_state("app_language", default_language) or default_language
        default_theme = str(conf.get("ui", {}).get("theme", "light")).lower()
        self.current_theme = state_store.load_app_state("theme", default_theme) or default_theme
        if self.current_theme not in {"light", "dark", "crimson", "futurist", "classic"}:
            self.current_theme = "light"
        stt_conf = conf.get("stt", {})
        config_stt_engine = preferred_stt_engine(stt_conf)
        stored_stt_engine = state_store.load_app_state("stt_engine")
        self.current_stt_engine = stored_stt_engine or config_stt_engine
        if self.current_stt_engine not in self.available_stt_engines:
            self.current_stt_engine = "faster_whisper"
            state_store.save_app_state("stt_engine", "faster_whisper")
        prefer_voxtral = bool(stt_conf.get("prefer_voxtral_when_configured", False))
        if (
            prefer_voxtral
            and config_stt_engine == "voxtral_realtime"
            and self.current_stt_engine == "faster_whisper"
        ):
            self.current_stt_engine = "voxtral_realtime"
            state_store.save_app_state("stt_engine", "voxtral_realtime")
        if self.current_stt_engine == "voxtral_realtime" and not self._voxtral_is_configured():
            self.current_stt_engine = "faster_whisper"
            state_store.save_app_state("stt_engine", "faster_whisper")
        self.conf.setdefault("stt", {})["engine"] = self.current_stt_engine
        tts_conf = conf.get("tts", {})
        config_tts_engine = tts_conf.get("engine", "chatterbox_turbo")
        stored_tts_engine = state_store.load_app_state("tts_engine")
        self.current_tts_engine = stored_tts_engine or config_tts_engine
        if self.current_tts_engine not in self.available_tts_engines:
            self.current_tts_engine = str(config_tts_engine)
            state_store.save_app_state("tts_engine", self.current_tts_engine)
        self.conf.setdefault("tts", {})["engine"] = self.current_tts_engine
        audio_conf = self.conf.setdefault("audio", {})
        stored_audio_input = state_store.load_app_state("audio_input_device")
        self.current_audio_input_device = None if stored_audio_input in {None, "", "__default__"} else stored_audio_input
        if self.current_audio_input_device is None:
            audio_conf["input_device"] = None
        else:
            try:
                audio_conf["input_device"] = int(self.current_audio_input_device)
            except Exception:
                audio_conf["input_device"] = self.current_audio_input_device
        configured_voice_sample = str(self.conf.get("tts", {}).get("voice_sample", "assets/voices/Nellie.wav")).replace("\\", "/")
        stored_voice_sample = state_store.load_app_state("tts_voice_sample")
        self.current_voice_sample = stored_voice_sample or configured_voice_sample
        if self.current_voice_sample not in self.available_voice_samples:
            self.current_voice_sample = configured_voice_sample
        self.conf.setdefault("tts", {})["voice_sample"] = self.current_voice_sample
        policies = conf.get("policies", {})
        romance_rating = str(policies.get("romance_rating", "pg13")).lower()
        self.pegi13_enabled = state_store.load_app_state(
            "pegi13_enabled",
            "1" if romance_rating == "pg13" else "0",
        ) != "0"
        self.safety_filters_enabled = state_store.load_app_state(
            "safety_filters_enabled",
            "1" if bool(policies.get("safety_filters", True)) else "0",
        ) != "0"
        self.gallery = GalleryLibrary(conf["paths"]["gallery_dir"])
        self._tts_runtime_label = "Voice ready."
        self._speech_runtime_label = ""
        self._speech_runtime_available = False
        self._speech_runtime_detail = ""
        self.backend_process: subprocess.Popen[str] | None = None
        self._voxtral_process: subprocess.Popen[str] | None = None
        self._voxtral_poll_thread: threading.Thread | None = None
        self._turn_count = 0
        self._reply_sequence = 0
        self._last_gallery_turn = -99
        self._tts_queue: queue.Queue[tuple[int, int, str | None, str | None]] = queue.Queue()
        self._tts_generation = 0
        self._tts_preload_thread: threading.Thread | None = None
        self._pending_tts_counts: dict[int, int] = {}
        self._pending_replies: dict[int, tuple[str, str, str]] = {}
        self._pending_reply_timeouts: dict[int, float] = {}
        self._pending_reply_lock = threading.Lock()
        self._reply_metrics: dict[int, dict[str, Any]] = {}
        logs_dir = Path(self.conf["paths"]["db_path"]).resolve().parent / "admin_logs"
        self.session_logger = SessionLogger(logs_dir)
        self.admin_dialog: AdminDialog | None = None
        threading.Thread(target=self._tts_worker, daemon=True).start()
        self._apply_language_settings()
        try:
            self._rebuild_stt_service()
        except Exception:
            self.current_stt_engine = "faster_whisper"
            self.conf.setdefault("stt", {})["engine"] = "faster_whisper"
            self._save_state("stt_engine", "faster_whisper")
            self._rebuild_stt_service()
        if self._supports_preload():
            self.tts = create_tts_service(self.conf)

        root = QWidget()
        root.setObjectName("appRoot")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        self.header_card = HeaderCard(conf["paths"]["moods_dir"])
        self.header_card.settings_clicked.connect(self.open_settings)

        self.chat = ChatView()

        self.recorder = RecorderWidget(
            on_transcript=lambda text: self.on_user_utterance(text, source="speech"),
            transcribe_func=self.stt.transcribe_bytes,
            conf=self.conf,
            event_callback=lambda event, payload: self.session_logger.record(event, **payload),
        )

        self.composer_card = ComposerCard(self.recorder, self._input_placeholder())
        self.text_input = self.composer_card.text_input
        self.text_input.returnPressed.connect(self.send_text_message)
        self.send_btn = self.composer_card.send_btn
        self.send_btn.clicked.connect(self.send_text_message)
        self.image_btn = self.composer_card.image_btn
        self.image_btn.clicked.connect(self.open_image)

        layout.addWidget(self.header_card)
        layout.addWidget(self.chat, 1)
        layout.addWidget(self.composer_card)

        self.main_scroll = QScrollArea()
        self.main_scroll.setObjectName("mainScroll")
        self.main_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.main_scroll.setWidgetResizable(True)
        self.main_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.main_scroll.setWidget(root)
        self.setCentralWidget(self.main_scroll)
        self._apply_theme()
        self.settings_dialog = SettingsDialog(self)
        self._maybe_prompt_initial_speech_setup(stored_stt_engine)

        self.avatar_expression_changed.connect(self.header_card.set_avatar_state)
        self.reply_ready.connect(self._finalize_reply)
        self.spoken_reply_ready.connect(self._publish_reply_after_voice)
        self.ai_message.connect(self.chat.add_ai)
        self.ai_image.connect(self.chat.add_ai_image)
        self.tts_status_changed.connect(self._set_tts_status)
        self.speech_runtime_changed.connect(self._on_speech_runtime_changed)
        self.voxtral_ready.connect(self._on_voxtral_ready)
        self.admin_log_line.connect(self._append_admin_log_line)
        self._sync_avatar_state()
        self._refresh_header_badges()
        self._refresh_header_progression()
        self._maybe_start_managed_voxtral()
        self._start_speech_runtime_heartbeat()
        if self._supports_preload():
            self._warm_tts_async()
        self._record_admin_event("session_started", status="ready", log_path=str(self.session_logger.path))

    def _state_store(self) -> Any:
        return self.backend if self.backend is not None else self.memory

    def _detect_audio_inputs(self) -> list[tuple[str | None, str]]:
        options: list[tuple[str | None, str]] = [(None, "System Default")]
        try:
            import sounddevice as sd  # type: ignore

            devices = sd.query_devices()
            for index, device in enumerate(devices):
                if int(device.get("max_input_channels", 0) or 0) <= 0:
                    continue
                name = str(device.get("name", f"Input {index}")).strip() or f"Input {index}"
                options.append((str(index), f"{name} [{index}]"))
        except Exception:
            pass
        return options

    def _load_state(self, key: str, default: str | None = None) -> str | None:
        return self._state_store().load_app_state(key, default)

    def _save_state(self, key: str, value: str) -> None:
        self._state_store().save_app_state(key, value)

    def _save_emotion(self) -> None:
        self._state_store().save_emotion_state(self.emotion)

    def _save_turn_record(self, user: str, ai: str, mood: str | None = None) -> None:
        self._state_store().save_turn(user=user, ai=ai, mood=mood, persona=self.persona)
        self.progression = self._load_progression_state()
        self._refresh_header_progression()

    def _clear_conversation_store(self) -> None:
        self._state_store().clear_conversation()
        self.progression = self._load_progression_state()
        self._refresh_header_progression()

    def _load_progression_state(self) -> dict[str, Any]:
        store = self._state_store()
        getter = getattr(store, "get_progression", None)
        if callable(getter):
            result = getter(self.persona)
            if isinstance(result, dict):
                return result
        return {
            "level": 1,
            "level_cap": 255,
            "progress_percent": 0,
            "xp_to_next": 0,
            "bond_factor": 0.0,
            "next_unlock": None,
        }

    def _refresh_header_progression(self) -> None:
        if not hasattr(self, "header_card"):
            return
        progression = self.progression or {}
        progression_conf = self.persona.get("progression", {}) if isinstance(self.persona.get("progression", {}), dict) else {}
        title = str(progression_conf.get("title", "Bond Level"))
        level = int(progression.get("level", 1) or 1)
        progress_percent = int(progression.get("progress_percent", 0) or 0)
        bond_factor = float(progression.get("bond_factor", 0.0) or 0.0)
        xp = int(progression.get("xp", 0) or 0)
        xp_to_next = int(progression.get("xp_to_next", 0) or 0)
        last_gain = int(progression.get("last_gain", 0) or 0)
        last_reason = str(progression.get("last_reason", "") or "").strip()
        last_gain_ts = float(progression.get("last_gain_ts", 0.0) or 0.0)
        last_gain_recent = bool(progression.get("last_gain_recent", False))
        next_unlock = progression.get("next_unlock", {}) if isinstance(progression.get("next_unlock", {}), dict) else {}
        next_unlock_label = str(next_unlock.get("label", "")).strip()
        hint = f"Bond {bond_factor:.2f}  XP {xp}  Next in {xp_to_next}"
        burst_text = ""
        if last_gain_recent and last_gain > 0:
            reason = f"  {last_reason}" if last_reason else ""
            hint = f"+{last_gain} XP{reason}"
            burst_text = self._progression_burst_text(last_gain, last_reason)
        next_text = f"Next: {next_unlock_label}" if next_unlock_label else ""
        self.header_card.set_progression(title, level, progress_percent, hint, next_text)
        if last_gain_recent and last_gain > 0 and last_gain_ts > self._last_progression_flash_ts:
            self._last_progression_flash_ts = last_gain_ts
            self.header_card.show_xp_burst(burst_text)

    def _progression_burst_text(self, gain: int, reason: str) -> str:
        cleaned = [part.strip() for part in str(reason or "").split(",") if part.strip()]
        preferred = [
            "shared vibe",
            "bonding",
            "curiosity",
            "playful spark",
            "interest in Nellie",
            "new memory",
            "deeper message",
            "longer share",
        ]
        chosen = next((item for item in preferred if item in cleaned), "")
        if not chosen and cleaned:
            chosen = cleaned[0]
        if not chosen:
            chosen = "Bond boost"
        return f"{chosen.title()} +{max(0, int(gain))} XP"

    def open_settings(self) -> None:
        self.settings_dialog.sync_from_window()
        self.settings_dialog.exec()

    def open_admin_monitor(self) -> None:
        if self.admin_dialog is None:
            self.admin_dialog = AdminDialog(self.session_logger.path, self)
            self.admin_dialog.clear_btn.clicked.connect(self._clear_admin_log_view)
            self.admin_dialog.finished.connect(self._close_admin_dialog)
        self.admin_dialog.set_lines(self.session_logger.lines())
        self.admin_dialog.show()
        self.admin_dialog.raise_()
        self.admin_dialog.activateWindow()

    def _close_admin_dialog(self, _result: int) -> None:
        self.admin_dialog = None

    def _clear_admin_log_view(self) -> None:
        self.session_logger.clear_view()
        if self.admin_dialog is not None:
            self.admin_dialog.set_lines([])

    def _append_admin_log_line(self, line: str) -> None:
        if self.admin_dialog is not None:
            self.admin_dialog.append_line(line)

    def _record_admin_event(self, event: str, **payload: Any) -> None:
        line = self.session_logger.record(event, **payload)
        self.admin_log_line.emit(line)

    def _mark_reply_metric(self, reply_id: int, key: str) -> None:
        metric = self._reply_metrics.setdefault(reply_id, {})
        metric[key] = time.perf_counter()

    def send_text_message(self) -> None:
        text = self.text_input.text().strip()
        if not text:
            return
        self.text_input.clear()
        self.on_user_utterance(text, source="text")

    def set_tts_enabled(self, enabled: bool) -> None:
        self.tts.set_enabled(enabled)
        self._set_tts_status("Voice ready." if enabled else "Voice muted.")
        self._refresh_header_badges()
        if enabled and self._supports_preload():
            self._warm_tts_async()
        if hasattr(self, "settings_dialog"):
            self.settings_dialog.sync_from_window()

    def _current_language_option(self) -> dict[str, Any]:
        return self.language_options.get(self.current_language, {})

    def _input_placeholder(self) -> str:
        return self._current_language_option().get("input_placeholder", "Write to Nellie...")

    def _response_language(self) -> str:
        return self._current_language_option().get("reply_language", "English")

    def _supports_preload(self, engine: str | None = None) -> bool:
        return (engine or self.current_tts_engine) in {"chatterbox_turbo", "xtts_tts"}

    def _is_sentence_chunk_tts(self) -> bool:
        return False

    def _apply_language_settings(self) -> None:
        stt_language = self._current_language_option().get("stt_language")
        if stt_language:
            self.stt.language = stt_language
            self.conf.setdefault("stt", {})["language"] = stt_language
        if hasattr(self, "text_input"):
            self.text_input.setPlaceholderText(self._input_placeholder())

    def set_tts_engine(self, key: str) -> None:
        if key not in self.available_tts_engines:
            return
        if key == self.current_tts_engine:
            return

        previous_engine = self.current_tts_engine
        previous_enabled = bool(getattr(self.tts, "enabled", True))

        self.conf.setdefault("tts", {})["engine"] = key
        self.current_tts_engine = key
        if self.backend is not None:
            self.backend.save_app_state("tts_engine", key)
        else:
            self._save_state("tts_engine", key)
        try:
            self._rebuild_tts_service()
        except Exception as e:
            self.current_tts_engine = previous_engine
            self.conf["tts"]["engine"] = previous_engine
            if self.backend is not None:
                self.backend.save_app_state("tts_engine", previous_engine)
            else:
                self._save_state("tts_engine", previous_engine)
            details = str(e).strip()
            self.ai_message.emit(f"[TTS engine unavailable] {details}")
            self._rebuild_tts_service()
        if previous_enabled:
            self._set_tts_status(f"{self.available_tts_engines.get(self.current_tts_engine, 'Voice')} selected.")
        if previous_enabled and self._supports_preload(key):
            self._warm_tts_async()
        self._refresh_header_badges()
        if hasattr(self, "settings_dialog"):
            self.settings_dialog.sync_from_window()

    def set_voice_sample(self, sample_path: str) -> None:
        normalized = str(sample_path or "").replace("\\", "/").strip()
        if normalized not in self.available_voice_samples:
            return
        if normalized == self.current_voice_sample:
            return

        previous_sample = self.current_voice_sample
        previous_enabled = bool(getattr(self.tts, "enabled", True))
        self.conf.setdefault("tts", {})["voice_sample"] = normalized
        self.current_voice_sample = normalized
        if self.backend is not None:
            self.backend.save_app_state("tts_voice_sample", normalized)
        else:
            self._save_state("tts_voice_sample", normalized)
        try:
            self._rebuild_tts_service()
        except Exception as e:
            self.current_voice_sample = previous_sample
            self.conf["tts"]["voice_sample"] = previous_sample
            if self.backend is not None:
                self.backend.save_app_state("tts_voice_sample", previous_sample)
            else:
                self._save_state("tts_voice_sample", previous_sample)
            self.ai_message.emit(f"[Voice sample unavailable] {e}")
            self._rebuild_tts_service()
            return

        label = self.available_voice_samples.get(normalized, Path(normalized).stem)
        if previous_enabled:
            self._set_tts_status(f"Voice sample switched to {label}.")
            if self._supports_preload():
                self._warm_tts_async()
        if hasattr(self, "settings_dialog"):
            self.settings_dialog.sync_from_window()

    def _set_tts_status(self, text: str) -> None:
        self._tts_runtime_label = str(text or "").strip()
        if hasattr(self, "header_card"):
            combined = self._tts_runtime_label
            if self._speech_runtime_label:
                combined = f"{self._tts_runtime_label}  {self._speech_runtime_label}"
            self.header_card.set_status(combined)

    def _refresh_header_badges(self) -> None:
        if not hasattr(self, "header_card"):
            return
        engine_label = self.available_tts_engines.get(self.current_tts_engine, "Voice")
        language_label = self.language_options.get(self.current_language, {}).get("label", self.current_language.upper())
        memory_label = "Memory on" if self.remember_chat_enabled else "Memory off"
        speech_label = self._speech_badge_text()
        mood_label = f"Mood: {self.current_mood.title()}"
        if self.current_expression and self.current_expression != self.current_mood:
            mood_label = f"{mood_label} / {self.current_expression.replace('_', ' ').title()}"
        self.header_card.set_badges(engine_label, language_label, memory_label, speech_label, mood_label)

    def _sync_avatar_state(
        self,
        mood: str | None = None,
        user_text: str = "",
        reply_text: str = "",
    ) -> None:
        resolved_mood = self._normalize_mood(mood) or self.current_mood or "neutral"
        self.current_mood = resolved_mood
        self.current_expression = self._infer_avatar_expression(user_text, reply_text, resolved_mood)
        self.mood_changed.emit(resolved_mood)
        self.avatar_expression_changed.emit(resolved_mood, self.current_expression)

    def _infer_avatar_expression(self, user_text: str, reply_text: str, mood: str) -> str:
        joined = f"{user_text} {reply_text}".lower()
        rules = [
            ("im_sorry", ["sorry", "apolog", "forgive", "my bad"]),
            ("aww", ["aww", "adorable", "sweet", "precious"]),
            ("lol", ["haha", "hehe", "lol", "lmao", "funny", "laugh"]),
            ("no_way", ["no way", "seriously", "can't be", "impossible"]),
            ("what", ["what?", "what ", "really?", "wait what", "excuse me"]),
            ("listening", ["i'm listening", "go on", "tell me more", "i hear you", "hear you"]),
            ("wait", ["hold on", "wait", "one sec", "just a second"]),
            ("your_sweet", ["sweetheart", "sweet of you", "that's sweet", "darling"]),
            ("small_flirt", ["flirt", "tease", "charming", "cute you"]),
            ("medium_flirt", ["kiss", "closer", "desire", "want you"]),
            ("surprized", ["surprised", "suddenly", "out of nowhere", "didn't expect"]),
            ("chocked", ["shocked", "stunned", "can't believe"]),
            ("annoyed", ["annoyed", "irritated", "stop that", "seriously now"]),
            ("anxious", ["nervous", "worried", "anxious", "uneasy"]),
            ("crying", ["cry", "tears", "heartbroken", "hurts"]),
            ("bored", ["bored", "nothing happening", "dragging"]),
            ("intrigued", ["interesting", "curious", "wonder", "why", "how"]),
        ]
        for expression, cues in rules:
            if any(cue in joined for cue in cues):
                return expression
        mood_fallbacks = {
            "thinking": "intrigued",
            "sceptical": "what",
            "happy": "warm_smile",
            "excited": "fun_reaction",
            "sensual": "medium_flirt",
            "sad": "crying",
            "tired": "bored",
            "angry": "annoyed",
            "bored": "bored",
            "neutral": "listening",
        }
        return mood_fallbacks.get(mood, "neutral")

    def describe_stt_settings(self) -> str:
        if self.current_stt_engine != "voxtral_realtime":
            prefer_voxtral = bool(self.conf.get("stt", {}).get("prefer_voxtral_when_configured", False))
            if prefer_voxtral:
                blocker = self._voxtral_runtime_blocker()
                if blocker:
                    return (
                        "Local Whisper is active right now. Voxtral Realtime is the preferred upgrade path, "
                        f"but the app is still falling back because {blocker}"
                    )
                return (
                    "Local Whisper is active right now. Voxtral Realtime is marked as the preferred speech path "
                    "when it is fully configured, so the app is currently falling back to Local Whisper."
                )
            return "Local Whisper is selected. It stays fully local and works without an API key."
        stt_conf = self.conf.get("stt", {})
        mode = str(stt_conf.get("voxtral_mode", "api")).strip().lower()
        if mode == "self_hosted":
            host = str(stt_conf.get("voxtral_self_hosted_url", "http://127.0.0.1:8000")).strip()
            enabled = bool(stt_conf.get("voxtral_self_hosted_enabled", False))
            autostart = bool(stt_conf.get("voxtral_self_hosted_autostart", False))
            blocker = self._voxtral_runtime_blocker()
            if blocker:
                return f"Voxtral Realtime is selected in self-hosted mode, but {blocker} It expects a local runtime at {host}."
            if not enabled:
                return (
                    f"Voxtral Realtime is set to self-hosted mode, but it is not armed yet. "
                    + (
                        "Autostart is enabled, so the app will try to launch it on startup once a launch command is configured. "
                        if autostart
                        else ""
                    )
                    + f"It expects a local runtime at {host}."
                )
            launch_ready = bool(str(stt_conf.get("voxtral_self_hosted_launch", "")).strip())
            if launch_ready:
                return (
                    f"Voxtral Realtime is set to self-hosted mode and can be started from inside the app. "
                    f"It will use {host} once the local runtime is armed."
                )
            return f"Voxtral Realtime is selected in self-hosted mode. It expects an OpenAI-compatible transcription endpoint at {host}."
        return "Voxtral Realtime is selected in API mode. It uses the configured Mistral endpoint and API key."

    def _speech_badge_text(self) -> str:
        if self.current_stt_engine == "voxtral_realtime":
            return "Speech: Voxtral Live" if self._speech_runtime_available else "Speech: Voxtral"
        return "Speech: Whisper"

    def _wsl_runtime_ready(self) -> tuple[bool, str]:
        stt_conf = self.conf.get("stt", {})
        if str(stt_conf.get("voxtral_mode", "api")).strip().lower() != "self_hosted":
            return False, "self-hosted mode is not selected."
        host_url = str(stt_conf.get("voxtral_self_hosted_url", "")).strip()
        parsed = urlparse(host_url) if host_url else None
        hostname = (parsed.hostname or "").strip().lower() if parsed else ""
        launch_command = str(stt_conf.get("voxtral_self_hosted_launch", "")).strip().lower()
        if hostname and hostname not in {"127.0.0.1", "localhost"}:
            return True, ""
        if hostname in {"127.0.0.1", "localhost"} and launch_command and "wsl" not in launch_command:
            return True, ""
        try:
            probe = subprocess.run(
                ["wsl", "-l", "-v"],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
        except FileNotFoundError:
            return False, "WSL is not available on this system."
        except Exception:
            return False, "WSL could not be checked right now."

        output = f"{probe.stdout}\n{probe.stderr}".lower()
        if probe.returncode == 0:
            return True, ""
        if "inte installerats" in output or "wsl.exe --install" in output:
            return False, "WSL2 is not installed yet."
        return False, "WSL2 is not ready yet."

    def _voxtral_runtime_blocker(self) -> str:
        stt_conf = self.conf.get("stt", {})
        mode = str(stt_conf.get("voxtral_mode", "api")).strip().lower()
        if mode == "self_hosted":
            wsl_ready, wsl_message = self._wsl_runtime_ready()
            if not wsl_ready:
                return wsl_message
            if not str(stt_conf.get("voxtral_self_hosted_url", "")).strip():
                return "the local Voxtral URL is empty."
            if not str(stt_conf.get("voxtral_self_hosted_launch", "")).strip():
                return "the local Voxtral launch command is not configured yet."
            if not bool(stt_conf.get("voxtral_self_hosted_enabled", False)):
                return "the local Voxtral runtime has not been armed yet."
            return ""
        if not str(stt_conf.get("voxtral_api_key", "")).strip():
            return "the Voxtral API key is missing."
        return ""

    def _refresh_stt_runtime_state(self) -> None:
        backend = getattr(self.stt, "backend", self.stt)
        if self.current_stt_engine == "voxtral_realtime":
            is_available = getattr(backend, "is_available", None)
            if callable(is_available) and is_available():
                self._speech_runtime_available = True
                self._speech_runtime_label = "Speech live via Voxtral."
                return
            self._speech_runtime_available = False
            blocker = self._voxtral_runtime_blocker()
            if blocker:
                self._speech_runtime_label = f"Speech fallback active. {blocker}"
            else:
                self._speech_runtime_label = "Speech fallback active."
            return
        prefer_voxtral = bool(self.conf.get("stt", {}).get("prefer_voxtral_when_configured", False))
        if prefer_voxtral:
            if self._speech_runtime_available:
                self._speech_runtime_label = "Speech local via Whisper. Voxtral is reachable and ready."
                return
            blocker = self._voxtral_runtime_blocker()
            if blocker:
                self._speech_runtime_label = f"Speech local via Whisper. Voxtral pending because {blocker}"
            else:
                self._speech_runtime_label = "Speech local via Whisper."
        else:
            self._speech_runtime_label = "Speech ready."

    def _should_probe_voxtral_runtime(self) -> bool:
        stt_conf = self.conf.get("stt", {})
        if str(stt_conf.get("voxtral_mode", "api")).strip().lower() != "self_hosted":
            return False
        if not str(stt_conf.get("voxtral_self_hosted_url", "")).strip():
            return False
        if self.current_stt_engine == "voxtral_realtime":
            return True
        return bool(stt_conf.get("prefer_voxtral_when_configured", False))

    def _probe_speech_runtime_async(self) -> None:
        if not self._should_probe_voxtral_runtime():
            return
        if self._voxtral_poll_thread is not None and self._voxtral_poll_thread.is_alive():
            return

        stt_conf = self.conf.get("stt", {})
        host = str(stt_conf.get("voxtral_self_hosted_url", "http://127.0.0.1:8000")).strip()

        def worker() -> None:
            available = False
            try:
                from services.audio.stt_voxtral import VoxtralSTT

                probe = VoxtralSTT(
                    model=str(stt_conf.get("voxtral_model", "voxtral-mini-latest")),
                    language=str(stt_conf.get("language", "en")),
                    base_url=str(stt_conf.get("voxtral_base_url", "https://api.mistral.ai")),
                    api_key=str(stt_conf.get("voxtral_api_key", "")),
                    mode="self_hosted",
                    self_hosted_url=host,
                    self_hosted_api_key=str(stt_conf.get("voxtral_self_hosted_api_key", "")),
                    timeout_sec=int(stt_conf.get("voxtral_timeout_sec", 120)),
                )
                available = probe.is_available()
            except Exception:
                available = False

            detail = f"Voxtral online at {host}." if available else f"Voxtral unreachable at {host}."
            self.speech_runtime_changed.emit(available, detail)

        self._voxtral_poll_thread = threading.Thread(target=worker, daemon=True)
        self._voxtral_poll_thread.start()

    def _start_speech_runtime_heartbeat(self) -> None:
        self._speech_runtime_timer = QTimer(self)
        self._speech_runtime_timer.setInterval(20000)
        self._speech_runtime_timer.timeout.connect(self._probe_speech_runtime_async)
        self._speech_runtime_timer.start()
        self._probe_speech_runtime_async()

    def _on_speech_runtime_changed(self, available: bool, detail: str) -> None:
        next_available = bool(available)
        next_detail = str(detail or "").strip()
        if self._speech_runtime_available == next_available and self._speech_runtime_detail == next_detail:
            return
        self._speech_runtime_available = bool(available)
        self._speech_runtime_detail = next_detail
        self._refresh_stt_runtime_state()
        self._set_tts_status(self._tts_runtime_label)
        self._refresh_header_badges()
        if hasattr(self, "settings_dialog") and self.settings_dialog.isVisible():
            self.settings_dialog.sync_from_window()

    def _on_voxtral_ready(self) -> None:
        self.conf.setdefault("stt", {})["voxtral_self_hosted_enabled"] = True
        if self.backend is not None:
            self.backend.save_app_state("stt_engine", "voxtral_realtime")
        else:
            self._save_state("stt_engine", "voxtral_realtime")
        self.current_stt_engine = "voxtral_realtime"
        try:
            self._rebuild_stt_service()
        except Exception:
            return
        self.ai_message.emit("[Speech runtime] Local Voxtral is live. Speech input switched to Voxtral.")

    def can_start_local_voxtral(self) -> bool:
        stt_conf = self.conf.get("stt", {})
        if self.backend is not None:
            try:
                return bool(self.backend.can_start_local_voxtral(stt_conf))
            except Exception:
                return False
        if str(stt_conf.get("voxtral_mode", "api")).strip().lower() != "self_hosted":
            return False
        wsl_ready, _ = self._wsl_runtime_ready()
        if not wsl_ready:
            return False
        return bool(str(stt_conf.get("voxtral_self_hosted_launch", "")).strip())

    def _should_autostart_local_voxtral(self) -> bool:
        stt_conf = self.conf.get("stt", {})
        return bool(stt_conf.get("voxtral_self_hosted_autostart", False)) and self.can_start_local_voxtral()

    def refresh_speech_runtime(self) -> None:
        self._refresh_stt_runtime_state()
        self._set_tts_status(self._tts_runtime_label)
        self._refresh_header_badges()
        if hasattr(self, "settings_dialog"):
            self.settings_dialog.sync_from_window()
        self.ai_message.emit(f"[Speech runtime] {self.describe_stt_settings()}")

    def start_local_voxtral(self) -> None:
        if not self.can_start_local_voxtral():
            blocker = self._voxtral_runtime_blocker() or "the local Voxtral launch command is not configured."
            self.ai_message.emit(f"[Speech runtime] Local Voxtral cannot start because {blocker}")
            return
        stt_conf = self.conf.get("stt", {})
        if self.backend is not None:
            try:
                result = self.backend.start_local_voxtral(stt_conf)
            except Exception as exc:
                self.ai_message.emit(f"[Speech runtime] Could not start local Voxtral: {exc}")
                return
            status = str(result.get("status", ""))
            if not bool(result.get("ok", False)) and status != "already_running":
                self.ai_message.emit(
                    f"[Speech runtime] Could not start local Voxtral: {result.get('detail', 'unknown error')}"
                )
                return
            if status == "already_running":
                self.ai_message.emit("[Speech runtime] Local Voxtral is already starting or running.")
            else:
                self.ai_message.emit("[Speech runtime] Starting local Voxtral in the background...")
            self._speech_runtime_label = "Speech runtime starting..."
            self._set_tts_status(self._tts_runtime_label)
            self._refresh_header_badges()
            self._poll_voxtral_availability()
            return
        if self._voxtral_process is not None and self._voxtral_process.poll() is None:
            self.ai_message.emit("[Speech runtime] Local Voxtral is already starting or running.")
            self._poll_voxtral_availability()
            return
        command = str(stt_conf.get("voxtral_self_hosted_launch", "")).strip()
        workdir = str(stt_conf.get("voxtral_self_hosted_workdir", "")).strip() or None
        try:
            self._voxtral_process = subprocess.Popen(
                command,
                cwd=workdir,
                shell=True,
                text=True,
            )
        except Exception as exc:
            self.ai_message.emit(f"[Speech runtime] Could not start local Voxtral: {exc}")
            return

        self.ai_message.emit("[Speech runtime] Starting local Voxtral in the background...")
        self._speech_runtime_label = "Speech runtime starting..."
        self._set_tts_status(self._tts_runtime_label)
        self._refresh_header_badges()
        self._poll_voxtral_availability()

    def _maybe_start_managed_voxtral(self) -> None:
        stt_conf = self.conf.get("stt", {})
        if not bool(stt_conf.get("prefer_voxtral_when_configured", False)):
            return
        if not self._should_autostart_local_voxtral():
            return
        self.start_local_voxtral()

    def _poll_voxtral_availability(self) -> None:
        if self._voxtral_poll_thread is not None and self._voxtral_poll_thread.is_alive():
            return

        stt_conf = self.conf.get("stt", {})

        def worker() -> None:
            if self.backend is not None:
                try:
                    probe = self.backend.probe_voxtral_runtime(stt_conf, attempts=10, delay_sec=1.2)
                    available = bool(probe.get("available", False))
                except Exception:
                    available = False
            else:
                backend = getattr(self.stt, "backend", self.stt)
                is_available = getattr(backend, "is_available", None)
                available = callable(is_available) and is_available()
                if not available:
                    from services.audio.stt_voxtral import VoxtralSTT

                    probe = VoxtralSTT(
                        model=str(stt_conf.get("voxtral_model", "voxtral-mini-latest")),
                        language=str(stt_conf.get("language", "en")),
                        base_url=str(stt_conf.get("voxtral_base_url", "https://api.mistral.ai")),
                        api_key=str(stt_conf.get("voxtral_api_key", "")),
                        mode="self_hosted",
                        self_hosted_url=str(stt_conf.get("voxtral_self_hosted_url", "http://127.0.0.1:8000")),
                        self_hosted_api_key=str(stt_conf.get("voxtral_self_hosted_api_key", "")),
                        timeout_sec=int(stt_conf.get("voxtral_timeout_sec", 120)),
                    )
                    for _ in range(10):
                        if probe.is_available():
                            available = True
                            break
                        time.sleep(1.2)
            if available:
                self.voxtral_ready.emit()
            else:
                self.speech_runtime_changed.emit(False, self._speech_runtime_detail or "Voxtral unreachable.")

        self._voxtral_poll_thread = threading.Thread(target=worker, daemon=True)
        self._voxtral_poll_thread.start()

    def _voxtral_is_configured(self) -> bool:
        stt_conf = self.conf.get("stt", {})
        mode = str(stt_conf.get("voxtral_mode", "api")).strip().lower()
        if mode == "self_hosted":
            return bool(stt_conf.get("voxtral_self_hosted_enabled", False)) and bool(
                str(stt_conf.get("voxtral_self_hosted_url", "")).strip()
            )
        return bool(str(stt_conf.get("voxtral_api_key", "")).strip())

    def _rebuild_tts_service(self) -> None:
        previous_service = self.tts
        previous_enabled = bool(getattr(previous_service, "enabled", True))
        previous_volume = int(getattr(previous_service, "master_volume", 100))
        next_service = create_tts_service(self.conf)
        next_service.set_enabled(previous_enabled)
        next_service.set_master_volume(previous_volume)
        self.tts = next_service
        old_backend = getattr(previous_service, "backend", None)
        clear_old_backend = getattr(old_backend, "clear_cache", None)
        if callable(clear_old_backend):
            clear_old_backend()

    def _rebuild_stt_service(self) -> None:
        self.stt = create_stt_service(self.conf)
        self._apply_language_settings()
        self._refresh_stt_runtime_state()
        self._set_tts_status(self._tts_runtime_label)
        self._refresh_header_badges()
        if hasattr(self, "recorder"):
            self.recorder.transcribe_func = self.stt.transcribe_bytes

    def set_stt_engine(self, key: str) -> None:
        if key not in self.available_stt_engines:
            return
        if key == self.current_stt_engine:
            return

        previous_engine = self.current_stt_engine
        self.conf.setdefault("stt", {})["engine"] = key
        self.current_stt_engine = key
        if self.backend is not None:
            self.backend.save_app_state("stt_engine", key)
        else:
            self._save_state("stt_engine", key)
        try:
            self._rebuild_stt_service()
        except Exception as e:
            self.current_stt_engine = previous_engine
            self.conf["stt"]["engine"] = previous_engine
            if self.backend is not None:
                self.backend.save_app_state("stt_engine", previous_engine)
            else:
                self._save_state("stt_engine", previous_engine)
            self.ai_message.emit(f"[Speech input unavailable] {e}")
            self._rebuild_stt_service()
        else:
            label = self.available_stt_engines.get(self.current_stt_engine, "Speech input")
            self.ai_message.emit(f"[Speech input] {label} selected.")
        if hasattr(self, "settings_dialog"):
            self.settings_dialog.sync_from_window()

    def _maybe_prompt_initial_speech_setup(self, stored_stt_engine: str | None) -> None:
        if stored_stt_engine:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Speech Input")
        dialog.setModal(True)
        dialog.setObjectName("settingsDialog")
        dialog.setMinimumWidth(360)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        title = QLabel("Choose speech input")
        title.setObjectName("settingsTitle")
        body = QLabel(
            "Use Local Whisper for the stable built-in speech path, or prepare Voxtral Realtime as the future self-hosted upgrade."
        )
        body.setObjectName("settingsSubtitle")
        body.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(body)

        chooser = QComboBox()
        chooser.setObjectName("voiceProfile")
        chooser.addItem("Local Whisper", "faster_whisper")
        chooser.addItem("Voxtral Realtime", "voxtral_realtime")
        current_index = chooser.findData(self.current_stt_engine)
        if current_index >= 0:
            chooser.setCurrentIndex(current_index)
        layout.addWidget(chooser)

        hint = QLabel("Recommended: Local Whisper now. Voxtral Realtime is the future upgrade path when your local runtime is in place.")
        hint.setObjectName("settingsHint")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        footer = QWidget()
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 8, 0, 0)
        footer_layout.addStretch(1)
        continue_btn = QPushButton("Continue")
        continue_btn.setObjectName("primaryButton")
        continue_btn.clicked.connect(dialog.accept)
        footer_layout.addWidget(continue_btn)
        layout.addWidget(footer)

        if dialog.exec():
            self.set_stt_engine(str(chooser.currentData() or "faster_whisper"))

    def _warm_tts_async(self) -> None:
        if not bool(getattr(self.tts, "enabled", True)):
            return
        backend = getattr(self.tts, "backend", None)
        ensure_loaded = getattr(backend, "_ensure_loaded", None)
        is_loaded = getattr(backend, "is_loaded", None)
        if not callable(ensure_loaded):
            return
        if callable(is_loaded) and is_loaded():
            self._set_tts_status("Voice ready.")
            return
        if self._tts_preload_thread and self._tts_preload_thread.is_alive():
            return

        engine_label = self.available_tts_engines.get(self.current_tts_engine, "Voice")

        def worker() -> None:
            self.tts_status_changed.emit(f"{engine_label} warming up in the background...")
            try:
                ensure_loaded()
                self.tts_status_changed.emit(f"{engine_label} voice model ready.")
            except Exception as e:
                self.tts_status_changed.emit(f"Voice preload error: {e}")

        self._tts_preload_thread = threading.Thread(target=worker, daemon=True)
        self._tts_preload_thread.start()

    def change_volume(self, value: int) -> None:
        self.tts.set_master_volume(value)
        if hasattr(self, "settings_dialog"):
            self.settings_dialog.sync_from_window()

    def set_language(self, key: str) -> None:
        if key not in self.language_options:
            return
        self.current_language = key
        if self.backend is not None:
            self.backend.save_app_state("app_language", key)
        else:
            self._save_state("app_language", key)
        self._apply_language_settings()
        self._refresh_header_badges()
        if (
            self.current_stt_engine == "faster_whisper"
            and self.current_language == "sv"
            and str(self.conf.get("stt", {}).get("model_size", "")).endswith(".en")
        ):
            self.ai_message.emit("Swedish is enabled. Speech recognition works best with a multilingual Whisper model such as `small` instead of `small.en`.")
        if hasattr(self, "settings_dialog"):
            self.settings_dialog.sync_from_window()

    def set_text_model(self, model: str) -> None:
        model_name = str(model or "").strip()
        if model_name not in self.available_text_models or model_name == self.current_text_model:
            return
        previous_model = self.current_text_model
        try:
            if self.backend is not None:
                selected = self.backend.set_text_model(model_name)
                if selected:
                    model_name = selected
                self.backend.save_app_state("ollama_text_model", model_name)
            elif self.ollama is not None and hasattr(self.ollama, "text_model"):
                self.ollama.text_model = model_name
                self._save_state("ollama_text_model", model_name)
            else:
                raise RuntimeError("The active backend does not support Ollama model switching.")
        except Exception as exc:
            self.ai_message.emit(f"[Model unavailable] {exc}")
            if hasattr(self, "settings_dialog"):
                self.settings_dialog.sync_from_window()
            return

        self.current_text_model = model_name
        self.conf.setdefault("ollama", {})["text_model"] = model_name
        self._record_admin_event("model_changed", previous=previous_model, current=model_name)
        self.ai_message.emit(
            f"[Language model] {self.available_text_models.get(model_name, model_name)} selected."
        )
        if hasattr(self, "settings_dialog"):
            self.settings_dialog.sync_from_window()

    def set_audio_input_device(self, device: Any) -> None:
        normalized = None if device in {None, "", "__default__"} else str(device)
        self.current_audio_input_device = normalized
        if normalized is None:
            self.conf.setdefault("audio", {})["input_device"] = None
            self._save_state("audio_input_device", "__default__")
            self.ai_message.emit("[Microphone] Using system default input device.")
        else:
            try:
                self.conf.setdefault("audio", {})["input_device"] = int(normalized)
            except Exception:
                self.conf.setdefault("audio", {})["input_device"] = normalized
            self._save_state("audio_input_device", normalized)
            label = next((name for key, name in self.available_audio_inputs if key == normalized), normalized)
            self.ai_message.emit(f"[Microphone] Input device set to {label}.")
        if hasattr(self, "settings_dialog"):
            self.settings_dialog.sync_from_window()

    def set_theme(self, key: str) -> None:
        theme = str(key or "").lower()
        if theme not in {"light", "dark", "crimson", "futurist", "classic"}:
            return
        self.current_theme = theme
        if self.backend is not None:
            self.backend.save_app_state("theme", theme)
        else:
            self._save_state("theme", theme)
        self._apply_theme()
        if hasattr(self, "settings_dialog"):
            self.settings_dialog.sync_from_window()

    def set_remember_chat_enabled(self, enabled: bool) -> None:
        self.remember_chat_enabled = bool(enabled)
        self._state_store().save_app_state(
            "remember_chat_enabled",
            "1" if self.remember_chat_enabled else "0",
        )
        self._refresh_header_badges()
        if hasattr(self, "settings_dialog"):
            self.settings_dialog.sync_from_window()

    def set_web_search_enabled(self, enabled: bool) -> None:
        self.web_search_enabled = bool(enabled)
        if self.backend is not None:
            self.backend.save_app_state("web_search_enabled", "1" if self.web_search_enabled else "0")
        else:
            self._save_state("web_search_enabled", "1" if self.web_search_enabled else "0")
        if hasattr(self, "settings_dialog"):
            self.settings_dialog.sync_from_window()

    def _save_tool_state(self, key: str, enabled: bool) -> None:
        value = "1" if enabled else "0"
        if self.backend is not None:
            self.backend.save_app_state(key, value)
        else:
            self._save_state(key, value)
        if hasattr(self, "settings_dialog"):
            self.settings_dialog.sync_from_window()

    def set_calculator_enabled(self, enabled: bool) -> None:
        self.calculator_enabled = bool(enabled)
        self._save_tool_state("tool_calculator", self.calculator_enabled)

    def set_datetime_enabled(self, enabled: bool) -> None:
        self.datetime_enabled = bool(enabled)
        self._save_tool_state("tool_datetime", self.datetime_enabled)

    def set_weather_enabled(self, enabled: bool) -> None:
        self.weather_enabled = bool(enabled)
        self._save_tool_state("tool_weather", self.weather_enabled)

    def set_wikipedia_enabled(self, enabled: bool) -> None:
        self.wikipedia_enabled = bool(enabled)
        self._save_tool_state("tool_wikipedia", self.wikipedia_enabled)

    def set_web_fetch_enabled(self, enabled: bool) -> None:
        self.web_fetch_enabled = bool(enabled)
        self._save_tool_state("tool_web_fetch", self.web_fetch_enabled)

    def set_youtube_enabled(self, enabled: bool) -> None:
        self.youtube_enabled = bool(enabled)
        self._save_tool_state("tool_youtube", self.youtube_enabled)

    def set_spotify_enabled(self, enabled: bool) -> None:
        self.spotify_enabled = bool(enabled)
        self._save_tool_state("tool_spotify", self.spotify_enabled)

    def test_speech_input(self) -> None:
        label = self.available_stt_engines.get(self.current_stt_engine, "Speech input")
        details = self.describe_stt_settings()
        device_label = next(
            (name for key, name in self.available_audio_inputs if key == self.current_audio_input_device),
            "System Default",
        )
        QMessageBox.information(
            self,
            "Speech Input Test",
            (
                f"Current speech input: {label}\n\n"
                f"Current microphone: {device_label}\n\n"
                f"{details}\n\n"
                "Hold the Talk button and say a short phrase like:\n"
                "\"Hello Nellie\"\n\n"
                "If the speech path is working, your transcript should appear directly in the chat input flow."
            ),
        )
        self.ai_message.emit(f"[Speech input test] {label} is armed. Hold to Talk and say a short phrase.")

    def set_pegi13_enabled(self, enabled: bool) -> None:
        self.pegi13_enabled = bool(enabled)
        if self.backend is not None:
            self.backend.save_app_state("pegi13_enabled", "1" if self.pegi13_enabled else "0")
        else:
            self._save_state("pegi13_enabled", "1" if self.pegi13_enabled else "0")
        if hasattr(self, "settings_dialog"):
            self.settings_dialog.sync_from_window()

    def set_safety_filters_enabled(self, enabled: bool) -> None:
        self.safety_filters_enabled = bool(enabled)
        if self.backend is not None:
            self.backend.save_app_state("safety_filters_enabled", "1" if self.safety_filters_enabled else "0")
        else:
            self._save_state("safety_filters_enabled", "1" if self.safety_filters_enabled else "0")
        if hasattr(self, "settings_dialog"):
            self.settings_dialog.sync_from_window()

    def current_policy_state(self) -> dict[str, bool]:
        return {
            "pegi13_enabled": self.pegi13_enabled,
            "romance_rating": "pg13" if self.pegi13_enabled else "mature",
            "safety_filters_enabled": self.safety_filters_enabled,
        }

    def describe_policy_settings(self) -> str:
        if self.pegi13_enabled:
            tone = "PEGI-13 is on, so romance stays mild and non-explicit."
        else:
            tone = "PEGI-13 is off, so Nellie may sound more mature and intimate, but still non-explicit."
        filters = (
            "Extra safety filters are on."
            if self.safety_filters_enabled
            else
            "Extra safety filters are off, but core safety limits still apply."
        )
        web = (
            "Web search is on for current facts."
            if self.web_search_enabled
            else
            "Web search is off."
        )
        return f"{tone} {filters} {web}"

    def _extract_tts_chunk(self, joined: str) -> tuple[str, str]:
        sentence_match = re.search(r"([^.?!]{12,}?[.?!])(\s|$)", joined)
        if sentence_match:
            sentence = sentence_match.group(1).strip()
            rest = joined[sentence_match.end(1):]
            return sentence, rest

        if not self._is_sentence_chunk_tts() and len(joined) >= 140:
            comma_match = re.search(r"^(.{60,140}?,)\s", joined)
            if comma_match:
                sentence = comma_match.group(1).strip()
                rest = joined[comma_match.end(1):]
                return sentence, rest
            space_index = joined.rfind(" ", 0, 130)
            if space_index > 70:
                sentence = joined[:space_index].strip()
                rest = joined[space_index + 1:]
                return sentence, rest

        return "", joined

    def _is_story_prompt(self, text: str) -> bool:
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

    def _build_spoken_reply(self, user_text: str, reply: str) -> str:
        del user_text
        text = str(reply or "").strip()
        if not text or self.current_tts_engine not in {"chatterbox_turbo", "xtts_tts"}:
            return text

        spoken = text
        spoken = re.sub(r"[*_`#~]+", "", spoken)
        spoken = re.sub(r"\s+", " ", spoken).strip()
        return spoken

    def _prepare_spoken_utterance(self, user_text: str, reply: str, mood: str) -> tuple[str, str]:
        if self.backend is not None:
            try:
                prepared = self.backend.prepare_spoken_utterance(
                    user_text=user_text,
                    reply=reply,
                    mood=mood,
                    current_tts_engine=self.current_tts_engine,
                    tts_conf=self.conf.get("tts", {}),
                    persona=self.persona,
                )
                return (
                    str(prepared.get("spoken_reply", "")),
                    str(prepared.get("reaction", "")),
                )
            except Exception as exc:
                self._record_admin_event("speech_prepare_error", error=str(exc))
        spoken_reply = self._build_spoken_reply(user_text, reply)
        reaction = self._hidden_reaction_for_text(user_text, spoken_reply, mood)
        return spoken_reply, reaction

    def remember_chat(self) -> bool:
        return self.remember_chat_enabled

    def clear_tts_cache(self) -> None:
        self.tts.clear_cache()
        QMessageBox.information(self, "TTS cache cleared", "Cached voice snippets were removed.")

    def clear_conversation_memory(self) -> None:
        answer = QMessageBox.question(
            self,
            "Clear memory",
            "Do you want Nellie to forget this conversation and reset her current emotional state?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return
        self._reset_tts_queue()
        self.tts.clear_cache()
        if self.backend is not None:
            self.backend.clear_conversation()
        else:
            self._clear_conversation_store()
        self.chat.clear_messages()
        self.emotion = EmotionState()
        self._turn_count = 0
        self._last_gallery_turn = -99
        self._sync_avatar_state(self.emotion.mood)
        self.ai_message.emit("I've cleared the conversation memory. We can start fresh.")

    def on_user_utterance(self, text: str, source: str = "text") -> None:
        if not text.strip():
            return
        if source == "speech":
            staged = self._maybe_stage_uncertain_speech(text)
            if staged:
                return
        self._reply_sequence += 1
        reply_id = self._reply_sequence
        self._reply_metrics[reply_id] = {"user_received": time.perf_counter()}
        self._record_admin_event("user_input", turn_id=reply_id, source=source, text=text)
        self._reset_tts_queue()
        self.emotion.apply_text(text)
        self.chat.add_user(text)
        self._sync_avatar_state(self.emotion.mood, user_text=text)
        self._refresh_header_badges()
        if self.backend is not None:
            threading.Thread(target=self._run_backend_turn, args=(reply_id, text, source), daemon=True).start()
            return
        context = ""
        if self.remember_chat():
            context = self._state_store().build_context(self.persona, k=4, max_chars=1000, per_turn_chars=220)
        threading.Thread(target=self._run_chat, args=(reply_id, text, context, source), daemon=True).start()

    def _maybe_stage_uncertain_speech(self, text: str) -> bool:
        cleaned = re.sub(r"\s+", " ", str(text or "").strip())
        normalized = re.sub(r"[^\w\s']", "", cleaned.casefold()).strip()
        words = [part for part in normalized.split() if part]
        trusted_short = {
            "hi",
            "hello",
            "hey",
            "yo",
            "hi nellie",
            "hello nellie",
            "hey nellie",
            "yes",
            "no",
            "okay",
            "ok",
            "thanks",
            "thank you",
            "continue",
            "go on",
            "stop",
            "help",
        }
        if normalized in trusted_short:
            return False
        if len(words) <= 2 and len(normalized) <= 18:
            self.text_input.setText(cleaned)
            self.text_input.setFocus()
            self.ai_message.emit(
                f"[Speech heard] {cleaned}\nPress Send if that is right, or try speaking again after choosing the correct microphone in Settings."
            )
            return True
        return False

    def _tools_enabled_dict(self) -> dict:
        return {
            "calculator": self.calculator_enabled,
            "datetime_local": self.datetime_enabled,
            "weather_lookup": self.weather_enabled,
            "wikipedia_search": self.wikipedia_enabled,
            "web_fetch": self.web_fetch_enabled,
            "youtube_control": self.youtube_enabled,
            "spotify_control": self.spotify_enabled,
        }

    def _try_handle_agent_action(self, reply_id: int, text: str) -> bool:
        if self.backend is None:
            return False
        result = self.backend.try_agent_action(text, tools_enabled=self._tools_enabled_dict())
        if not result or not result.get("handled"):
            return False
        self._record_admin_event(
            "agent_action",
            turn_id=reply_id,
            action=result.get("action"),
            query=result.get("query"),
            target=result.get("target"),
            status=result.get("status", "handled"),
        )
        return self._emit_agent_reply(
            reply_id,
            text,
            str(result.get("reply", "")),
            str(result.get("mood", "neutral")),
            str(result.get("action", "agent_action")),
        )


    def _emit_agent_reply(self, reply_id: int, user_text: str, reply: str, mood: str, action: str) -> bool:
        generation = self._tts_generation
        if reply:
            spoken, reaction = self._prepare_spoken_utterance(user_text, reply, mood)
            if reaction:
                self._enqueue_tts(reaction, generation, reply_id, mood="_reaction", prepared=True)
            self._enqueue_tts(spoken or reply, generation, reply_id, mood, prepared=True)
        self._record_admin_event("reply_ready", turn_id=reply_id, mood=mood, reply=reply)
        self.reply_ready.emit(reply_id, user_text, reply, mood)
        return True

    def _run_backend_turn(self, reply_id: int, text: str, source: str = "text") -> None:
        generation = self._tts_generation
        try:
            self._mark_reply_metric(reply_id, "ollama_start")
            result = self.backend.respond_turn(
                persona=self.persona,
                user_text=text,
                emotion_state=self.emotion.as_prompt_block(),
                policy_state=self.current_policy_state(),
                response_language=self._response_language(),
                input_source=source,
                remember_chat=self.remember_chat(),
                web_search_enabled=self.web_search_enabled,
                tools_enabled=self._tools_enabled_dict(),
            )
        except Exception as e:
            self._record_admin_event("backend_error", turn_id=reply_id, error=str(e))
            self.reply_ready.emit(reply_id, text, f"[Backend error] {e}", "neutral")
            return

        kind = str(result.get("kind", "chat"))
        if kind == "error":
            reply = str(result.get("reply", "[Backend error]"))
            self._record_admin_event("backend_error", turn_id=reply_id, error=result.get("error"), stage=result.get("stage"))
            self.reply_ready.emit(reply_id, text, reply, str(result.get("mood", "neutral")))
            return

        if kind == "agent":
            self._record_admin_event(
                "agent_action",
                turn_id=reply_id,
                action=result.get("action"),
                query=result.get("query"),
                target=result.get("target"),
                status=result.get("status", "handled"),
            )
            self._emit_agent_reply(
                reply_id,
                text,
                str(result.get("reply", "")),
                str(result.get("mood", "neutral")),
                str(result.get("action", "agent_action")),
            )
            return

        self._mark_reply_metric(reply_id, "ollama_end")
        started = self._reply_metrics.get(reply_id, {}).get("ollama_start")
        if started is not None:
            self._record_admin_event(
                "ollama_complete",
                turn_id=reply_id,
                duration_ms=round((time.perf_counter() - started) * 1000),
                reply=result.get("reply", ""),
            )
        web_query = str(result.get("web_query", "") or "")
        if web_query:
            self._record_admin_event(
                "web_search_complete",
                turn_id=reply_id,
                query=web_query,
                results=int(result.get("web_results", 0) or 0),
            )

        reply = self._clean_ai_reply(str(result.get("reply", "")))
        meta = result.get("meta", {})
        if not isinstance(meta, dict):
            meta = {}

        self.emotion.apply_reply(reply)
        mood = self._normalize_mood(meta.get("mood") or self._infer_mood_from_text(reply, fallback=self.emotion.mood))
        if mood:
            self.emotion.mood = mood
        self._sync_avatar_state(self.emotion.mood, user_text=text, reply_text=reply)
        spoken_reply, reaction = self._prepare_spoken_utterance(text, reply, self.emotion.mood)
        if reaction:
            self._enqueue_tts(reaction, generation, reply_id, mood="_reaction", prepared=True)
        enqueued = self._enqueue_tts(spoken_reply or reply, generation, reply_id, self.emotion.mood, prepared=True)
        self._record_admin_event("reply_ready", turn_id=reply_id, mood=self.emotion.mood, reply=reply)
        if enqueued:
            self.reply_ready.emit(reply_id, text, reply, self.emotion.mood)
        else:
            self._publish_reply(reply_id, text, reply, self.emotion.mood)

    def _run_chat(self, reply_id: int, text: str, context: str, source: str = "text") -> None:
        buffer = []
        generation = self._tts_generation
        reaction_enqueued = False
        web_context = ""
        query_text = text

        def on_chunk(chunk: str) -> None:
            nonlocal reaction_enqueued
            if not self._is_sentence_chunk_tts():
                return
            buffer.append(chunk)
            joined = "".join(buffer)
            sentence, rest = self._extract_tts_chunk(joined)
            if sentence:
                buffer.clear()
                buffer.append(rest)
                if not reaction_enqueued:
                    reaction = self._hidden_reaction_for_text(text, sentence, self.current_mood)
                    if reaction and self._enqueue_tts(reaction, generation, reply_id, mood="_reaction"):
                        reaction_enqueued = True
                self._enqueue_tts(sentence, generation, reply_id)

        try:
            if self._should_use_web_search(text):
                query_text = self._extract_web_query(text)
                self.ai_message.emit(f"Checking the web for: {query_text}")
                try:
                    results = web_search(query_text, k=5)
                    if results:
                        web_context = summarize_results(results)
                        self.ai_message.emit(f"Found {len(results)} web results.")
                    else:
                        self.ai_message.emit("I couldn't find usable web results for that query.")
                except Exception as search_error:
                    self.ai_message.emit(f"[Web search unavailable] {search_error}")
            self._mark_reply_metric(reply_id, "ollama_start")
            chat_backend = self.backend if self.backend is not None else self.ollama
            reply, meta = chat_backend.chat(
                self.persona,
                query_text,
                context=context,
                emotion_state=self.emotion.as_prompt_block(),
                stream_callback=on_chunk,
                policy_state=self.current_policy_state(),
                web_context=web_context,
                response_language=self._response_language(),
                input_source=source,
            )
        except Exception as e:
            self._record_admin_event("ollama_error", turn_id=reply_id, error=str(e))
            self.reply_ready.emit(reply_id, text, f"[Error contacting Ollama] {e}", "neutral")
            return
        ollama_start = self._reply_metrics.get(reply_id, {}).get("ollama_start")
        if ollama_start is not None:
            self._mark_reply_metric(reply_id, "ollama_end")
            self._record_admin_event(
                "ollama_complete",
                turn_id=reply_id,
                duration_ms=round((time.perf_counter() - ollama_start) * 1000),
                reply=reply,
            )
        reply = self._clean_ai_reply(reply)

        self.emotion.apply_reply(reply)
        model_mood = self._normalize_mood(meta.get("mood"))
        fallback_mood = self.emotion.mood
        if fallback_mood in {"thinking", "bored"}:
            fallback_mood = "neutral"
        inferred_mood = model_mood or self._infer_mood_from_text(reply, fallback=fallback_mood)
        if inferred_mood == "thinking" and not any(
            cue in (reply or "").lower() for cue in ["let me think", "thinking about", "what if", "reflect"]
        ):
            inferred_mood = "neutral"
        self.emotion.mood = inferred_mood
        mood = self.emotion.mood
        if not self._is_sentence_chunk_tts():
            spoken_reply = self._build_spoken_reply(text, reply)
            if not reaction_enqueued:
                reaction = self._hidden_reaction_for_text(text, spoken_reply, mood)
                if reaction and self._enqueue_tts(reaction, generation, reply_id, mood="_reaction"):
                    reaction_enqueued = True
            self._enqueue_tts(spoken_reply, generation, reply_id, mood)
        else:
            tail = "".join(buffer).strip()
            if tail:
                if not reaction_enqueued:
                    reaction = self._hidden_reaction_for_text(text, tail, mood)
                    if reaction and self._enqueue_tts(reaction, generation, reply_id, mood="_reaction"):
                        reaction_enqueued = True
                self._enqueue_tts(tail, generation, reply_id, mood)
        self._record_admin_event("reply_ready", turn_id=reply_id, mood=mood, reply=reply)
        self.reply_ready.emit(reply_id, text, reply, mood)

    def _clean_ai_reply(self, reply: str) -> str:
        text = str(reply or "").strip()
        if not text:
            return ""
        text = re.sub(r"^\s*Nellie\s*:\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"^\s*Assistant\s*:\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"^\s*AI\s*:\s*", "", text, flags=re.IGNORECASE)
        return text.strip()

    def _finalize_reply(self, reply_id: int, user_text: str, reply: str, mood: str) -> None:
        if isinstance(reply, bytes):
            reply = reply.decode("utf-8", errors="replace")
        if isinstance(user_text, bytes):
            user_text = user_text.decode("utf-8", errors="replace")
        if isinstance(mood, bytes):
            mood = mood.decode("utf-8", errors="replace")
        if reply.startswith("[Error contacting Ollama]"):
            self._publish_reply(reply_id, user_text, reply, mood)
            return
        if self._should_publish_text_immediately(reply):
            self._publish_reply(reply_id, user_text, reply, mood)
            return
        with self._pending_reply_lock:
            if self._pending_tts_counts.get(reply_id, 0) > 0:
                self._pending_replies[reply_id] = (user_text, reply, mood)
                self._start_pending_reply_timeout(reply_id)
                return
        self._publish_reply(reply_id, user_text, reply, mood)

    def _should_publish_text_immediately(self, reply: str) -> bool:
        if self.current_tts_engine not in {"chatterbox_turbo", "xtts_tts"}:
            return False
        text = str(reply or "").strip()
        if not text:
            return True
        words = text.split()
        if len(words) <= 4 and len(text) <= 28:
            return True
        return False

    def _publish_reply_after_voice(self, reply_id: int, user_text: str, reply: str, mood: str) -> None:
        self._publish_reply(reply_id, user_text, reply, mood)

    def _publish_reply(self, reply_id: int, user_text: str, reply: str, mood: str) -> None:
        with self._pending_reply_lock:
            self._pending_replies.pop(reply_id, None)
            self._pending_tts_counts.pop(reply_id, None)
            self._pending_reply_timeouts.pop(reply_id, None)
        metric = self._reply_metrics.pop(reply_id, None)
        if metric is not None:
            started = metric.get("user_received")
            ollama_end = metric.get("ollama_end")
            playback_start = metric.get("tts_playback_start")
            total_ms = round((time.perf_counter() - started) * 1000) if started is not None else None
            ollama_ms = round((ollama_end - started) * 1000) if started is not None and ollama_end is not None else None
            voice_start_ms = round((playback_start - started) * 1000) if started is not None and playback_start is not None else None
            self._record_admin_event(
                "reply_published",
                turn_id=reply_id,
                duration_ms=total_ms,
                mood=mood,
                reply=reply,
            )
            summary_parts = []
            if ollama_ms is not None:
                summary_parts.append(f"Ollama {ollama_ms} ms")
            if voice_start_ms is not None:
                summary_parts.append(f"Voice start {voice_start_ms} ms")
            if total_ms is not None:
                summary_parts.append(f"Total {total_ms} ms")
            if summary_parts:
                self._record_admin_event("turn_summary", turn_id=reply_id, status=" | ".join(summary_parts))
        self.ai_message.emit(reply)
        self._turn_count += 1
        self._sync_avatar_state(mood, user_text=user_text, reply_text=reply)
        self._refresh_header_badges()
        if self.remember_chat():
            if self.backend is not None:
                self.backend.save_turn(user=user_text, ai=reply, mood=mood, persona=self.persona)
                self.backend.save_emotion_state(self.emotion)
                self.progression = self._load_progression_state()
                self._refresh_header_progression()
            else:
                self._save_turn_record(user=user_text, ai=reply, mood=mood)
                self._save_emotion()
        self._maybe_post_gallery_image(reply)

    def open_image(self) -> None:
        image_path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose image",
            "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if not image_path:
            return
        self.chat.add_user(f"[Image] {image_path}")
        self.ai_message.emit("Analysing image...")
        threading.Thread(target=self._describe_image, args=(image_path,), daemon=True).start()

    def _describe_image(self, image_path: str) -> None:
        try:
            vision_backend = self.backend if self.backend is not None else self.ollama
            reply = vision_backend.vision(
                image_path,
                prompt="Describe this image, note the emotional tone, and give three useful insights.",
            )
        except Exception as e:
            self.ai_message.emit(f"[Image error] {e}")
            return

        self.ai_message.emit(reply or "[Image] No response from vision model.")
        self.emotion.apply_text(reply)
        self._sync_avatar_state(self.emotion.mood, reply_text=reply)
        self._refresh_header_badges()
        if self.remember_chat():
            if self.backend is not None:
                self.backend.save_emotion_state(self.emotion)
            else:
                self._save_emotion()
        self._maybe_post_gallery_image(reply)

    def _update_mood_from_text(self, text: str) -> None:
        self.emotion.apply_text(text)
        self._sync_avatar_state(self.emotion.mood, user_text=text)

    def _infer_mood_from_text(self, text: str, fallback: str = "neutral") -> str:
        text_l = (text or "").lower()
        mood_keywords = {
            "sensual": ["love", "kiss", "romantic", "date", "cute", "beautiful", "handsome", "desire", "sexy"],
            "happy": ["happy", "great", "fun", "smile", "laugh", "joy", "excited"],
            "angry": ["angry", "annoyed", "furious", "jealous", "hate", "frustrated"],
            "sceptical": ["really", "sure", "doubt", "sceptical", "skeptical", "unclear", "suspicious"],
            "thinking": ["what if", "let me think", "reflect"],
        }
        for mood, words in mood_keywords.items():
            if any(word in text_l for word in words):
                return mood
        return fallback

    def _normalize_mood(self, mood: str | None) -> str:
        mapping = {
            "curious": "thinking",
            "shy": "sensual",
            "flirty": "sensual",
            "caring": "neutral",
            "adventurous": "happy",
        }
        if not mood:
            return None
        return mapping.get(mood, mood)

    def _maybe_post_gallery_image(self, text: str) -> None:
        habits = self.persona.get("gallery_habits", {})
        probability = float(habits.get("show_images_prob", 0.12))
        triggers = [t.lower() for t in habits.get("triggers", []) if isinstance(t, str)]
        text_l = (text or "").lower()
        triggered = any(trigger in text_l for trigger in triggers)

        if self._turn_count - self._last_gallery_turn < 3:
            return
        if not triggered and random.random() > probability:
            return

        selected = self.gallery.choose_image(self.current_mood, text)
        if not selected:
            return

        has_topic_match = bool(selected.get("trigger_matches"))
        has_mood_match = bool(selected.get("mood_match"))
        if not has_topic_match and not has_mood_match:
            return
        if not has_topic_match and has_mood_match and random.random() > 0.15:
            return

        caption = selected.get("caption") or self._default_gallery_caption(
            selected.get("name", "this one")
        )
        self._last_gallery_turn = self._turn_count
        self.ai_image.emit(selected["path"], caption)

    def _default_gallery_caption(self, image_name: str) -> str:
        mood_captions = {
            "sensual": f"I felt like sharing {image_name} with you.",
            "happy": f"This one matches my mood today: {image_name}.",
            "angry": f"I needed a change of scene, so here is {image_name}.",
            "sceptical": f"{image_name} felt fitting somehow.",
            "thinking": f"I wanted to share {image_name} and see what you think.",
            "neutral": f"I wanted to share {image_name}.",
        }
        return mood_captions.get(self.current_mood, f"I wanted to share {image_name}.")

    def _should_use_web_search(self, text: str) -> bool:
        if not self.web_search_enabled:
            return False
        lower = (text or "").strip().lower()
        if lower.startswith("/search "):
            return True
        if re.fullmatch(
            r"(?:shall|should|can|could) we (?:try to )?(?:look up|search for|find) "
            r"(?:a |another )?(?:song|track|video|topic)(?: again)?[?.! ]*",
            lower,
        ):
            return False
        search_cues = [
            "search", "look up", "lookup", "find online", "on the internet",
            "browse", "web search", "latest", "current", "today", "news", "recent",
            "weather", "forecast", "temperature", "väder", "vädret", "prognos", "temperatur",
            "who is", "what is", "when is", "where is",
            "how many", "number of", "first album", "first record", "discography",
            "sök", "sok", "leta upp", "på nätet", "på natet", "senaste",
            "idag", "nyheter", "vem är", "vad är", "när är", "var är",
        ]
        return any(cue in lower for cue in search_cues)

    def _extract_web_query(self, text: str) -> str:
        stripped = (text or "").strip()
        if stripped.lower().startswith("/search "):
            stripped = stripped[8:].strip()
        return stripped or text

    def _enqueue_tts(self, text: str, generation: int, reply_id: int, mood: str | None = None, prepared: bool = False) -> None:
        if not getattr(self.tts, "enabled", True):
            return False
        resolved_mood = mood or self.current_mood
        if not prepared:
            text = self._prepare_tts_text(text, resolved_mood)
        if not text:
            return False
        with self._pending_reply_lock:
            self._pending_tts_counts[reply_id] = self._pending_tts_counts.get(reply_id, 0) + 1
        self._record_admin_event("tts_enqueued", turn_id=reply_id, mood=resolved_mood, text=text)
        self._tts_queue.put((generation, reply_id, text, resolved_mood))
        return True

    def _reset_tts_queue(self) -> None:
        self._tts_generation += 1
        while True:
            try:
                self._tts_queue.get_nowait()
            except queue.Empty:
                break
        with self._pending_reply_lock:
            self._pending_tts_counts.clear()
            self._pending_replies.clear()
            self._pending_reply_timeouts.clear()

    def _voice_first_timeout_seconds(self) -> float:
        if self.current_tts_engine in {"chatterbox_turbo", "xtts_tts"}:
            return 4.5
        return 10

    def _start_pending_reply_timeout(self, reply_id: int) -> None:
        if reply_id in self._pending_reply_timeouts:
            return
        self._pending_reply_timeouts[reply_id] = True
        delay = self._voice_first_timeout_seconds()

        def worker() -> None:
            threading.Event().wait(delay)
            pending_reply = None
            with self._pending_reply_lock:
                pending_reply = self._pending_replies.pop(reply_id, None)
                if pending_reply:
                    self._pending_tts_counts.pop(reply_id, None)
                self._pending_reply_timeouts.pop(reply_id, None)
            if pending_reply:
                self.tts_status_changed.emit("Voice is still working, so the text reply was shown first.")
                self.spoken_reply_ready.emit(reply_id, *pending_reply)

        threading.Thread(target=worker, daemon=True).start()

    def _tts_worker(self) -> None:
        while True:
            generation, reply_id, text, mood = self._tts_queue.get()
            if generation != self._tts_generation:
                continue
            pending_reply = None
            playback_started = False
            try:
                if not self._is_sentence_chunk_tts():
                    backend = getattr(self.tts, "backend", None)
                    is_loaded = getattr(backend, "is_loaded", None)
                    if callable(is_loaded) and not is_loaded():
                        engine_label = self.available_tts_engines.get(self.current_tts_engine, "Voice")
                        self.tts_status_changed.emit(f"{engine_label} loading voice model... the first line can take a while.")
                    else:
                        engine_label = self.available_tts_engines.get(self.current_tts_engine, "Voice")
                        self.tts_status_changed.emit(f"{engine_label} generating speech...")
                else:
                    self.tts_status_changed.emit("Speaking...")

                def on_playback_start() -> None:
                    nonlocal playback_started
                    if playback_started:
                        return
                    playback_started = True
                    self._mark_reply_metric(reply_id, "tts_playback_start")
                    tts_started_at = self._reply_metrics.get(reply_id, {}).get("ollama_start")
                    if tts_started_at is not None:
                        self._record_admin_event(
                            "tts_playback_start",
                            turn_id=reply_id,
                            duration_ms=round((time.perf_counter() - tts_started_at) * 1000),
                            text=text,
                        )
                    if not self._is_sentence_chunk_tts():
                        engine_label = self.available_tts_engines.get(self.current_tts_engine, "Voice")
                        self.tts_status_changed.emit(f"{engine_label} speaking...")
                    with self._pending_reply_lock:
                        pending_after_start = self._pending_replies.pop(reply_id, None)
                        if pending_after_start:
                            self._pending_reply_timeouts.pop(reply_id, None)
                    if pending_after_start:
                        self.spoken_reply_ready.emit(reply_id, *pending_after_start)

                self.tts.speak(text, mood=mood, on_playback_start=on_playback_start)
                self._record_admin_event("tts_complete", turn_id=reply_id, text=text, mood=mood)
                if not self._is_sentence_chunk_tts():
                    engine_label = self.available_tts_engines.get(self.current_tts_engine, "Voice")
                    self.tts_status_changed.emit(f"{engine_label} voice ready.")
                else:
                    self.tts_status_changed.emit("Voice ready.")
            except Exception as e:
                self.tts_status_changed.emit(f"Voice error: {e}")
                self._record_admin_event("tts_error", turn_id=reply_id, error=str(e))
                print(f"[TTS] {e}")
            finally:
                with self._pending_reply_lock:
                    remaining = self._pending_tts_counts.get(reply_id, 0) - 1
                    if remaining > 0:
                        self._pending_tts_counts[reply_id] = remaining
                    else:
                        self._pending_tts_counts.pop(reply_id, None)
                        pending_reply = self._pending_replies.pop(reply_id, None)
                if pending_reply:
                    self.spoken_reply_ready.emit(reply_id, *pending_reply)

    def _prepare_tts_text(self, text: str, mood: str | None = None) -> str:
        text = str(text or "")
        text = text.replace("\n", " ")
        text = text.replace("\u2026", ", ")
        text = text.replace("\u2019", "'")
        text = text.replace("\u2018", "'")
        text = text.replace("\u201c", '"')
        text = text.replace("\u201d", '"')
        text = text.replace("&", " and ")
        text = text.replace("@", " at ")
        text = text.replace("%", " percent ")
        text = re.sub(r"\[[^\]]*\]", " ", text)
        text = re.sub(r"\(([^)]*)\)", r" \1 ", text)
        text = re.sub(r"\bvs\.\b", "versus", text, flags=re.IGNORECASE)
        text = re.sub(r"\be\.g\.\b", "for example", text, flags=re.IGNORECASE)
        text = re.sub(r"\bi\.e\.\b", "that is", text, flags=re.IGNORECASE)
        text = re.sub(r"\betc\.\b", "etcetera", text, flags=re.IGNORECASE)
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
        text = self._shape_tts_sentences(text)
        text = self._shape_spoken_delivery(text, mood or "neutral")
        return text

    def _shape_tts_sentences(self, text: str) -> str:
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

    def _shape_spoken_delivery(self, text: str, mood: str) -> str:
        if not text:
            return ""
        speech_conf = self.conf.get("tts", {}).get("spoken_delivery", {})
        enabled = bool(speech_conf.get("enabled", True))
        if not enabled:
            return text
        ticks_conf = self.persona.get("style", {}).get("verbal_ticks", {})
        ticks_enabled = bool(ticks_conf.get("enabled", True))
        if not ticks_enabled:
            return text
        filler_probability = float(speech_conf.get("filler_probability", 0.10))
        thinking_probability = float(speech_conf.get("thinking_filler_probability", 0.20))
        laugh_probability = float(speech_conf.get("laugh_probability", 0.05))
        delivery_style = self._spoken_delivery_style(mood, text)
        style_overrides = {
            "soft": {"start_multiplier": 0.45, "laugh_multiplier": 0.15, "trim_commas": False, "shorten": False},
            "playful": {"start_multiplier": 1.10, "laugh_multiplier": 1.45, "trim_commas": False, "shorten": False},
            "thoughtful": {"start_multiplier": 0.85, "laugh_multiplier": 0.05, "trim_commas": False, "shorten": False},
            "flirty": {"start_multiplier": 0.35, "laugh_multiplier": 0.15, "trim_commas": True, "shorten": False},
            "sharp": {"start_multiplier": 0.08, "laugh_multiplier": 0.02, "trim_commas": True, "shorten": True},
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
                    filler = self._choose_spoken_filler(mood, delivery_style)
                    if filler:
                        sentence = f"{filler}, {sentence}"
            if delivery_style == "thoughtful" and index == 0 and "," not in sentence and len(sentence) > 36:
                sentence = re.sub(r"\b(just|really|kind of|sort of)\b", r", \1", sentence, count=1, flags=re.IGNORECASE)
                sentence = re.sub(r"\s+", " ", sentence).strip()
            if delivery_style == "playful" and index == 0 and sentence.endswith("."):
                sentence = sentence[:-1] + "!"
            laugh_threshold = laugh_probability * float(style_conf.get("laugh_multiplier", 1.0))
            if random.random() < laugh_threshold and mood in {"happy", "excited"}:
                sentence = f"{sentence} {self._choose_small_laugh()}"
            shaped.append(sentence)
        return " ".join(shaped)

    def _spoken_delivery_style(self, mood: str, text: str) -> str:
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

    def _choose_spoken_filler(self, mood: str, delivery_style: str = "soft") -> str:
        ticks_conf = self.persona.get("style", {}).get("verbal_ticks", {})
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

    def _choose_small_laugh(self) -> str:
        ticks_conf = self.persona.get("style", {}).get("verbal_ticks", {})
        laughs = ticks_conf.get("small_laughs", ["heh.", "ha.", "mm."])
        if not isinstance(laughs, list) or not laughs:
            laughs = ["heh.", "ha.", "mm."]
        return random.choice(laughs)

    def _hidden_reaction_for_text(self, user_text: str, reply_text: str, mood: str) -> str:
        if self._is_story_prompt(user_text):
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
            return random.choice(["ah", "oh"])
        if mood == "sensual":
            return random.choice(["mm", "oh"])
        return random.choice(["heh", "mm"])

    def _apply_theme(self) -> None:
        theme = getattr(self, "current_theme", "light")
        self._theme_tokens = build_theme_tokens(self.conf, theme)
        accent = self._theme_tokens.get("accent", self.conf.get("ui", {}).get("accent_color", "#FFD447"))
        if theme == "dark":
            root_bg = "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #120f0d, stop:0.36 #1b1512, stop:0.72 #231b18, stop:1 #2f241f)"
            card_bg = "rgba(33, 27, 23, 0.97)"
            section_bg = "rgba(41, 33, 29, 0.95)"
            border = "rgba(255, 234, 213, 0.11)"
            eyebrow_color = "#d9aa63"
            title_color = "#f6ecdf"
            subtitle_color = "#d1c0af"
            status_color = "#e6d7c7"
            badge_fg = "#efe0d0"
            badge_bg = "rgba(59, 48, 40, 0.96)"
            badge_border = "rgba(255, 234, 213, 0.11)"
            accent_badge_fg = "#2b1b11"
            avatar_note = "#d0beaa"
            chat_bg = "rgba(24, 20, 18, 0.96)"
            ai_bubble_bg = "#221c19"
            ai_bubble_fg = "#f1e8de"
            stream_fg = "#dfcab7"
            user_bubble_fg = "#261b13"
            image_frame_bg = "rgba(75, 59, 47, 0.76)"
            image_caption = "#efded0"
            image_footer = "#cbab86"
            input_bg = "rgba(37, 30, 26, 0.98)"
            input_fg = "#f4ebe3"
            composer_bg = "rgba(28, 23, 20, 0.96)"
            primary_bg = "#f2e1cf"
            primary_fg = "#22160f"
            primary_hover = "#f8ead9"
            secondary_bg = "rgba(66, 53, 44, 0.97)"
            secondary_fg = "#f3e8de"
            secondary_border = "rgba(255, 234, 213, 0.11)"
            control_fg = "#dbc6b1"
            slider_groove = "rgba(255, 234, 213, 0.18)"
            slider_handle = "#f2e1cf"
        elif theme == "crimson":
            accent = "#E4475E"
            root_bg = "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #170d10, stop:0.38 #281016, stop:0.72 #3a131b, stop:1 #541923)"
            card_bg = "rgba(39, 17, 23, 0.97)"
            section_bg = "rgba(51, 20, 28, 0.95)"
            border = "rgba(255, 219, 223, 0.12)"
            eyebrow_color = "#f2a1ab"
            title_color = "#fff0f1"
            subtitle_color = "#efc6cb"
            status_color = "#f4d7da"
            badge_fg = "#ffe1e4"
            badge_bg = "rgba(85, 32, 43, 0.96)"
            badge_border = "rgba(255, 219, 223, 0.12)"
            accent_badge_fg = "#2d0d13"
            avatar_note = "#e9bcc2"
            chat_bg = "rgba(29, 12, 18, 0.96)"
            ai_bubble_bg = "#2b1318"
            ai_bubble_fg = "#fff1f2"
            stream_fg = "#efc2c9"
            user_bubble_fg = "#2d1115"
            image_frame_bg = "rgba(104, 38, 51, 0.76)"
            image_caption = "#ffe2e5"
            image_footer = "#f1a7b2"
            input_bg = "rgba(47, 18, 24, 0.98)"
            input_fg = "#fff4f4"
            composer_bg = "rgba(34, 14, 19, 0.96)"
            primary_bg = "#ffe0e3"
            primary_fg = "#2d1015"
            primary_hover = "#ffe9eb"
            secondary_bg = "rgba(88, 34, 45, 0.97)"
            secondary_fg = "#fff1f2"
            secondary_border = "rgba(255, 219, 223, 0.12)"
            control_fg = "#f0c5cb"
            slider_groove = "rgba(255, 219, 223, 0.18)"
            slider_handle = "#ffe0e3"
        elif theme == "futurist":
            accent = "#5EF2D6"
            root_bg = "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #071218, stop:0.35 #0a1d24, stop:0.72 #102b32, stop:1 #163740)"
            card_bg = "rgba(11, 24, 30, 0.96)"
            section_bg = "rgba(15, 31, 39, 0.95)"
            border = "rgba(157, 241, 228, 0.15)"
            eyebrow_color = "#7CE8D7"
            title_color = "#E8FFFB"
            subtitle_color = "#A8D3CD"
            status_color = "#C8F1EB"
            badge_fg = "#D8FFF8"
            badge_bg = "rgba(21, 47, 55, 0.96)"
            badge_border = "rgba(157, 241, 228, 0.16)"
            accent_badge_fg = "#042C26"
            avatar_note = "#A9D6CF"
            chat_bg = "rgba(8, 19, 24, 0.97)"
            ai_bubble_bg = "#10242B"
            ai_bubble_fg = "#E9FFFB"
            stream_fg = "#BDE9E1"
            user_bubble_fg = "#032E29"
            image_frame_bg = "rgba(22, 58, 65, 0.78)"
            image_caption = "#D7FFFA"
            image_footer = "#7CE8D7"
            input_bg = "rgba(13, 30, 36, 0.98)"
            input_fg = "#F0FFFC"
            composer_bg = "rgba(9, 23, 29, 0.97)"
            primary_bg = "#5EF2D6"
            primary_fg = "#042822"
            primary_hover = "#82F7E1"
            secondary_bg = "rgba(18, 43, 50, 0.98)"
            secondary_fg = "#E8FFFB"
            secondary_border = "rgba(157, 241, 228, 0.16)"
            control_fg = "#B4DDD8"
            slider_groove = "rgba(157, 241, 228, 0.20)"
            slider_handle = "#5EF2D6"
        elif theme == "classic":
            accent = "#B38A54"
            root_bg = "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #f7f1e7, stop:0.4 #efe5d4, stop:0.72 #e5d7c0, stop:1 #dbc7a9)"
            card_bg = "rgba(251, 246, 238, 0.97)"
            section_bg = "rgba(247, 239, 228, 0.95)"
            border = "rgba(98, 77, 46, 0.14)"
            eyebrow_color = "#8D6A35"
            title_color = "#2E2418"
            subtitle_color = "#695644"
            status_color = "#5A493A"
            badge_fg = "#664F33"
            badge_bg = "rgba(252, 248, 241, 0.98)"
            badge_border = "rgba(98, 77, 46, 0.12)"
            accent_badge_fg = "#3F2E14"
            avatar_note = "#75604B"
            chat_bg = "rgba(252, 248, 242, 0.92)"
            ai_bubble_bg = "#FFFDF8"
            ai_bubble_fg = "#31261A"
            stream_fg = "#5D4830"
            user_bubble_fg = "#2F2418"
            image_frame_bg = "rgba(241, 231, 216, 0.9)"
            image_caption = "#453627"
            image_footer = "#92714A"
            input_bg = "rgba(255, 252, 246, 0.98)"
            input_fg = "#30251A"
            composer_bg = "rgba(250, 245, 237, 0.96)"
            primary_bg = "#2F2418"
            primary_fg = "#FFF9F0"
            primary_hover = "#403122"
            secondary_bg = "rgba(248, 240, 230, 0.98)"
            secondary_fg = "#5B452C"
            secondary_border = "rgba(98, 77, 46, 0.12)"
            control_fg = "#665033"
            slider_groove = "rgba(98, 77, 46, 0.16)"
            slider_handle = "#2F2418"
        else:
            root_bg = "qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #fffcf7, stop:0.34 #f8f1e6, stop:0.7 #efe4d6, stop:1 #eadac8)"
            card_bg = "rgba(255, 252, 247, 0.96)"
            section_bg = "rgba(255, 248, 241, 0.95)"
            border = "rgba(94, 72, 46, 0.12)"
            eyebrow_color = "#9b6c33"
            title_color = "#2f2218"
            subtitle_color = "#6d5947"
            status_color = "#59493b"
            badge_fg = "#70593d"
            badge_bg = "rgba(255, 253, 249, 0.97)"
            badge_border = "rgba(120, 92, 58, 0.11)"
            accent_badge_fg = "#3f2817"
            avatar_note = "#79614e"
            chat_bg = "rgba(255, 252, 248, 0.90)"
            ai_bubble_bg = "#fffdfa"
            ai_bubble_fg = "#31251b"
            stream_fg = "#5d4831"
            user_bubble_fg = "#2d2117"
            image_frame_bg = "rgba(250, 243, 235, 0.84)"
            image_caption = "#463525"
            image_footer = "#927152"
            input_bg = "rgba(255, 253, 249, 0.97)"
            input_fg = "#2d231a"
            composer_bg = "rgba(255, 251, 246, 0.95)"
            primary_bg = "#2f2218"
            primary_fg = "#fff9f1"
            primary_hover = "#3d2d20"
            secondary_bg = "rgba(255, 248, 240, 0.98)"
            secondary_fg = "#5a432c"
            secondary_border = "rgba(94, 72, 46, 0.12)"
            control_fg = "#685135"
            slider_groove = "rgba(94, 72, 46, 0.14)"
            slider_handle = "#2f2218"
        combo_bg = input_bg
        combo_fg = input_fg
        combo_popup_bg = ai_bubble_bg
        combo_popup_fg = ai_bubble_fg
        combo_hover_bg = "rgba(255, 212, 71, 0.18)" if theme == "light" else "rgba(255, 212, 71, 0.16)"
        check_bg = "rgba(255, 252, 247, 0.95)" if theme == "light" else "rgba(35, 29, 25, 0.98)"
        check_border = border
        self.setStyleSheet(
            f"""
            #appRoot {{
                background: {root_bg};
            }}
            #mainScroll, #mainScroll > QWidget > QWidget {{
                background: transparent;
                border: none;
            }}
            #headerCard, #avatarCard, #settingsDialog {{
                background-color: {card_bg};
                border: 1px solid {border};
                border-radius: 24px;
            }}
            #headerCard {{
                border-radius: 28px;
            }}
            #chatSurface {{
                background-color: {card_bg};
                border: 1px solid {border};
                border-radius: 26px;
            }}
            #settingsSection {{
                background-color: {section_bg};
                border: 1px solid {badge_border};
                border-radius: 20px;
            }}
            #settingsScroll {{
                background: transparent;
                border: none;
            }}
            #settingsScroll QScrollBar:vertical {{
                background: transparent;
                width: 12px;
                margin: 8px 0px 8px 6px;
            }}
            #settingsScroll QScrollBar::handle:vertical {{
                background: {slider_groove};
                border-radius: 6px;
                min-height: 32px;
            }}
            #settingsScroll QScrollBar::handle:vertical:hover {{
                background: {accent};
            }}
            #settingsScroll QScrollBar::add-line:vertical, #settingsScroll QScrollBar::sub-line:vertical,
            #settingsScroll QScrollBar::add-page:vertical, #settingsScroll QScrollBar::sub-page:vertical {{
                background: transparent;
                border: none;
                height: 0px;
            }}
            #headerEyebrow {{
                color: {eyebrow_color};
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.2em;
                text-transform: uppercase;
            }}
            #headerTitle, #settingsTitle {{
                color: {title_color};
                font-size: 32px;
                font-weight: 700;
            }}
            #sectionTitle {{
                color: {eyebrow_color};
                font-size: 12px;
                font-weight: 700;
                letter-spacing: 0.12em;
                text-transform: uppercase;
                margin-top: 0px;
            }}
            #headerSubtitle, #settingsSubtitle {{
                color: {subtitle_color};
                font-size: 13px;
            }}
            #avatarEyebrow {{
                color: {eyebrow_color};
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.18em;
                text-transform: uppercase;
            }}
            #avatarChip {{
                color: {badge_fg};
                background-color: {badge_bg};
                border: 1px solid {badge_border};
                border-radius: 12px;
                padding: 5px 10px;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 0.08em;
                text-transform: uppercase;
            }}
            #settingsHint {{
                color: {subtitle_color};
                font-size: 12px;
                line-height: 1.5em;
            }}
            #voiceProfile {{
                background-color: {combo_bg};
                color: {combo_fg};
                border: 1px solid {border};
                border-radius: 16px;
                padding: 11px 14px;
                font-size: 13px;
                min-height: 18px;
            }}
            #voiceProfile:hover, #voiceProfile:focus {{
                border: 1px solid {accent};
            }}
            #voiceProfile::drop-down {{
                border: none;
                width: 28px;
            }}
            #voiceProfile::down-arrow {{
                width: 10px;
                height: 10px;
            }}
            #voiceProfile QAbstractItemView {{
                background-color: {combo_popup_bg};
                color: {combo_popup_fg};
                border: 1px solid {badge_border};
                border-radius: 16px;
                outline: none;
                padding: 8px;
                selection-background-color: {combo_hover_bg};
                selection-color: {combo_popup_fg};
            }}
            #headerStatus {{
                color: {status_color};
                font-size: 12px;
                padding-top: 3px;
                padding-bottom: 2px;
            }}
            #headerMetaRow {{
                background: transparent;
            }}
            #metaBadge, #metaBadgeAccent {{
                border-radius: 12px;
                padding: 5px 10px;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 0.06em;
            }}
            #metaBadge {{
                color: {badge_fg};
                background-color: {badge_bg};
                border: 1px solid {badge_border};
            }}
            #metaBadgeAccent {{
                color: {accent_badge_fg};
                background-color: rgba(255, 212, 71, 0.72);
                border: 1px solid rgba(151, 111, 38, 0.18);
            }}
            #bondProgressWrap {{
                background: transparent;
            }}
            #bondProgressWrap[xpFlash="true"] {{
                background-color: rgba(255, 212, 71, 0.08);
                border-radius: 16px;
            }}
            #bondProgressTitle {{
                color: {eyebrow_color};
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.1em;
                text-transform: uppercase;
            }}
            #bondLevelBadge {{
                color: {badge_fg};
                background-color: {badge_bg};
                border: 1px solid {badge_border};
                border-radius: 12px;
                padding: 4px 10px;
                font-size: 10px;
                font-weight: 700;
                letter-spacing: 0.06em;
            }}
            #bondLevelBadge[xpFlash="true"] {{
                background-color: rgba(255, 212, 71, 0.88);
                color: {accent_badge_fg};
                border: 1px solid rgba(255, 212, 71, 0.42);
            }}
            #bondProgressBar {{
                min-height: 10px;
                max-height: 10px;
                border: 1px solid {badge_border};
                border-radius: 999px;
                background-color: {slider_groove};
            }}
            #bondProgressBar[xpFlash="true"] {{
                border: 1px solid rgba(255, 212, 71, 0.48);
                background-color: rgba(255, 212, 71, 0.18);
            }}
            #bondProgressBar::chunk {{
                border-radius: 999px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {accent},
                    stop:1 rgba(255, 212, 71, 0.72));
            }}
            #bondProgressHint, #bondProgressNext {{
                color: {subtitle_color};
                font-size: 11px;
                font-weight: 600;
            }}
            #bondProgressNext {{
                color: {eyebrow_color};
            }}
            #bondXpBurst {{
                color: {accent_badge_fg};
                background-color: rgba(255, 212, 71, 0.86);
                border: 1px solid rgba(255, 212, 71, 0.42);
                border-radius: 12px;
                padding: 4px 10px;
                font-size: 10px;
                font-weight: 800;
                letter-spacing: 0.04em;
            }}
            #headerPortrait {{
                background: transparent;
                border: none;
            }}
            #avatarFrame {{
                background: qradialgradient(cx:0.5, cy:0.38, radius:1.0,
                    fx:0.42, fy:0.28,
                    stop:0 rgba(255, 255, 255, 0.13),
                    stop:0.58 rgba(255, 255, 255, 0.045),
                    stop:1 rgba(255, 255, 255, 0.01));
                border: 1px solid {badge_border};
                border-radius: 24px;
            }}
            #avatarFrame[moodState="happy"], #avatarFrame[moodState="excited"] {{
                border: 1px solid rgba(255, 212, 71, 0.42);
            }}
            #avatarFrame[moodState="sensual"] {{
                border: 1px solid rgba(214, 124, 131, 0.42);
            }}
            #avatarFrame[moodState="thinking"], #avatarFrame[moodState="sceptical"] {{
                border: 1px solid rgba(147, 176, 185, 0.34);
            }}
            #avatarFrame[moodState="sad"], #avatarFrame[moodState="tired"] {{
                border: 1px solid rgba(151, 143, 168, 0.34);
            }}
            #avatarFrame[moodState="angry"] {{
                border: 1px solid rgba(219, 97, 80, 0.46);
            }}
            #avatarImage {{
                background: transparent;
                border-radius: 22px;
                padding: 0px;
            }}
            #avatarMood {{
                color: {title_color};
                font-size: 15px;
                font-weight: 700;
                letter-spacing: 0.06em;
            }}
            #avatarMood[moodState="happy"], #avatarMood[moodState="excited"] {{
                color: {eyebrow_color};
            }}
            #avatarMood[moodState="sensual"] {{
                color: {eyebrow_color};
            }}
            #avatarMood[moodState="sad"], #avatarMood[moodState="tired"] {{
                color: {subtitle_color};
            }}
            #avatarMood[moodState="angry"] {{
                color: {eyebrow_color};
            }}
            #avatarNote {{
                color: {avatar_note};
                font-size: 12px;
                line-height: 1.5em;
                padding: 0 8px;
            }}
            #chatEyebrow {{
                color: {eyebrow_color};
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.16em;
                text-transform: uppercase;
            }}
            #chatTitle {{
                color: {title_color};
                font-size: 21px;
                font-weight: 700;
            }}
            #chatSubtitle {{
                color: {subtitle_color};
                font-size: 12px;
                line-height: 1.45em;
            }}
            #chatList {{
                background-color: {chat_bg};
                border: none;
                border-radius: 18px;
                padding: 11px 7px 14px 7px;
                outline: none;
            }}
            #chatList::item {{
                border: none;
                margin: 0px;
                padding: 0px;
            }}
            #chatList QScrollBar:vertical {{
                background: transparent;
                width: 14px;
                margin: 10px 6px 10px 0px;
            }}
            #chatList QScrollBar::handle:vertical {{
                background: {slider_groove};
                border-radius: 7px;
                min-height: 36px;
            }}
            #chatList QScrollBar::handle:vertical:hover {{
                background: {accent};
            }}
            #chatList QScrollBar::add-line:vertical, #chatList QScrollBar::sub-line:vertical,
            #chatList QScrollBar::add-page:vertical, #chatList QScrollBar::sub-page:vertical {{
                background: transparent;
                border: none;
                height: 0px;
            }}
            #userBubble {{
                background-color: {accent};
                border: none;
                border-radius: 20px;
            }}
            #aiBubble, #imageCard {{
                background-color: {ai_bubble_bg};
                border: 1px solid {badge_border};
                border-radius: 20px;
            }}
            #userBubbleSender, #aiBubbleSender {{
                font-size: 11px;
                font-weight: 700;
                color: {eyebrow_color};
                letter-spacing: 0.06em;
                text-transform: uppercase;
            }}
            #userBubbleBody {{
                color: {user_bubble_fg};
                font-size: 15px;
                line-height: 1.62;
            }}
            #aiBubbleBody, #streamBubbleBody {{
                color: {ai_bubble_fg};
                font-size: 15px;
                line-height: 1.68;
            }}
            #streamBubbleBody {{
                color: {stream_fg};
                font-style: italic;
            }}
            #bubbleHint {{
                color: {subtitle_color};
                font-size: 11px;
                font-weight: 600;
                padding-top: 4px;
            }}
            #imageCardTitle {{
                color: {eyebrow_color};
                font-size: 12px;
                font-weight: 700;
                letter-spacing: 0.08em;
                text-transform: uppercase;
            }}
            #imageCardImage {{
                background-color: {image_frame_bg};
                border-radius: 18px;
                padding: 10px;
            }}
            #imageCardCaption {{
                color: {image_caption};
                font-size: 14px;
                line-height: 1.55;
            }}
            #imageCardFooter {{
                color: {image_footer};
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.1em;
                text-transform: uppercase;
            }}
            #previewDialog {{
                background-color: {card_bg};
                border: 1px solid {border};
                border-radius: 28px;
            }}
            #previewTitle {{
                color: {title_color};
                font-size: 24px;
                font-weight: 700;
            }}
            #previewBody, #previewCaption {{
                color: {ai_bubble_fg};
                font-size: 15px;
                line-height: 1.65;
                background-color: {ai_bubble_bg};
                border: 1px solid {badge_border};
                border-radius: 22px;
                padding: 18px;
            }}
            #previewImage {{
                background-color: {image_frame_bg};
                border-radius: 22px;
                padding: 12px;
            }}
            #messageInput {{
                background-color: {input_bg};
                border: 1px solid {border};
                border-radius: 18px;
                padding: 13px 16px;
                color: {input_fg};
                font-size: 15px;
                min-height: 22px;
            }}
            #composerCard {{
                background-color: {composer_bg};
                border: 1px solid {badge_border};
                border-radius: 21px;
            }}
            #composerTitle {{
                color: {eyebrow_color};
                font-size: 11px;
                font-weight: 700;
                letter-spacing: 0.1em;
                text-transform: uppercase;
            }}
            #composerHint {{
                color: {subtitle_color};
                font-size: 10px;
                font-weight: 600;
            }}
            #messageInput:focus {{
                border: 1px solid {accent};
            }}
            #primaryButton, #secondaryButton, #talkButton, #headerSettingsButton {{
                border-radius: 17px;
                padding: 10px 16px;
                font-size: 13px;
                font-weight: 700;
            }}
            #primaryButton {{
                background-color: {primary_bg};
                color: {primary_fg};
                border: none;
            }}
            #primaryButton:hover {{
                background-color: {primary_hover};
            }}
            #secondaryButton {{
                background-color: {secondary_bg};
                color: {secondary_fg};
                border: 1px solid {secondary_border};
            }}
            #headerSettingsButton {{
                background-color: {badge_bg};
                color: {badge_fg};
                border: 1px solid {badge_border};
                padding: 7px 13px;
                font-size: 11px;
            }}
            #talkButton {{
                background-color: {secondary_bg};
                color: {secondary_fg};
                border: 1px solid {secondary_border};
            }}
            #secondaryButton:hover, #talkButton:hover, #headerSettingsButton:hover {{
                background-color: {secondary_bg};
                border: 1px solid {accent};
            }}
            #primaryButton:pressed, #secondaryButton:pressed, #talkButton:pressed, #headerSettingsButton:pressed {{
                padding-top: 11px;
                padding-bottom: 9px;
            }}
            #controlLabel, #rememberToggle {{
                color: {control_fg};
                font-size: 13px;
                font-weight: 600;
            }}
            #rememberToggle {{
                spacing: 10px;
            }}
            #rememberToggle::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 9px;
                border: 1px solid {check_border};
                background-color: {check_bg};
            }}
            #rememberToggle::indicator:checked {{
                background-color: {accent};
                border: 1px solid rgba(166, 123, 34, 0.24);
            }}
            #volumeSlider::groove:horizontal {{
                height: 6px;
                background: {slider_groove};
                border-radius: 999px;
            }}
            #volumeSlider::handle:horizontal {{
                background: {slider_handle};
                width: 18px;
                margin: -6px 0;
                border-radius: 9px;
            }}
            """
        )
