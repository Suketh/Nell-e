from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QSize, Qt, Signal, QTimer
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QBoxLayout,
    QComboBox,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from ui.chat_view import ChatView
from ui.chat_controller import DesktopChatController
from ui.gallery_controller import DesktopGalleryController
from ui.mood_avatar import MoodAvatar
from ui.main_window_logs import build_combined_log
from ui.profile_controller import DesktopProfileController
from ui.recorder_widget import RecorderWidget
from ui.settings_controller import DesktopSettingsController
from ui.startup_controller import DesktopStartupController
from services.conversation_service import ConversationService

import queue
import threading


class MainWindow(QMainWindow):
    THEME_PRESETS = {
        "light": {
            "bg_start": "#f5efe8",
            "bg_mid": "#eee4d4",
            "bg_end": "#dcc8ad",
            "card_bg": "rgba(255, 250, 243, 0.84)",
            "card_border": "rgba(97, 70, 37, 0.12)",
            "card_glow": "rgba(108, 77, 42, 0.12)",
            "avatar_ring": "rgba(162, 111, 61, 0.35)",
            "avatar_bg": "rgba(255, 245, 232, 0.92)",
            "avatar_outer_ring": "rgba(255, 249, 241, 0.55)",
            "title": "#3f2b19",
            "subtitle": "#7a5d3f",
            "status": "#8a6e52",
            "eyebrow": "#a26f3d",
            "eyebrow_bg": "rgba(162, 111, 61, 0.10)",
            "divider": "rgba(97, 70, 37, 0.12)",
            "chat_bg": "rgba(255, 251, 246, 0.80)",
            "chat_border": "rgba(97, 70, 37, 0.10)",
            "chat_scroll_track": "rgba(109, 81, 53, 0.08)",
            "chat_scroll_thumb": "rgba(109, 81, 53, 0.34)",
            "chat_scroll_thumb_hover": "rgba(109, 81, 53, 0.48)",
            "assistant_bg": "#fff8f1",
            "assistant_border": "rgba(122, 93, 63, 0.16)",
            "assistant_sheen": "rgba(255, 255, 255, 0.22)",
            "assistant_speaker": "#7f5b38",
            "assistant_text": "#39281b",
            "user_bg": "#3f2f23",
            "user_border": "rgba(63, 47, 35, 0.20)",
            "user_sheen": "rgba(255, 240, 220, 0.12)",
            "user_speaker": "#e9c9a3",
            "user_text": "#fff7ef",
            "input_shell": "rgba(255, 255, 255, 0.24)",
            "input_bg": "rgba(255, 251, 246, 0.94)",
            "input_text": "#332316",
            "input_border": "rgba(97, 70, 37, 0.12)",
            "input_focus": "rgba(162, 111, 61, 0.45)",
            "send_bg": "#a26f3d",
            "send_hover": "#8e6033",
            "send_pressed": "#7c522a",
            "send_text": "#fff9f2",
            "theme_chip_bg": "rgba(255, 248, 239, 0.92)",
            "theme_chip_text": "#6d5135",
            "theme_chip_active": "#3f2f23",
            "theme_chip_active_text": "#fff7ef",
            "theme_chip_hover": "rgba(109, 81, 53, 0.14)",
            "clear_chip_bg": "rgba(109, 81, 53, 0.10)",
            "clear_chip_hover": "rgba(109, 81, 53, 0.16)",
            "clear_chip_pressed": "rgba(109, 81, 53, 0.22)",
            "clear_chip_text": "#6d5135",
            "record_bg": "rgba(255, 250, 243, 0.84)",
            "record_border": "rgba(97, 70, 37, 0.12)",
            "record_rec_bg": "rgba(255, 239, 236, 0.95)",
            "record_rec_border": "rgba(176, 83, 63, 0.24)",
            "record_busy_bg": "rgba(248, 243, 234, 0.95)",
            "record_busy_border": "rgba(162, 111, 61, 0.20)",
            "record_btn_bg": "#b05a47",
            "record_btn_hover": "#9a4d3d",
            "record_btn_pressed": "#853f32",
            "record_btn_text": "#fff8f5",
            "record_status": "#6e553d",
        },
        "red": {
            "bg_start": "#2d1418",
            "bg_mid": "#6e2430",
            "bg_end": "#d46b57",
            "card_bg": "rgba(40, 14, 20, 0.78)",
            "card_border": "rgba(255, 205, 192, 0.14)",
            "card_glow": "rgba(255, 124, 102, 0.16)",
            "avatar_ring": "rgba(255, 132, 107, 0.56)",
            "avatar_bg": "rgba(73, 22, 28, 0.92)",
            "avatar_outer_ring": "rgba(255, 230, 223, 0.24)",
            "title": "#fff1ec",
            "subtitle": "#f1b8aa",
            "status": "#ffd0c4",
            "eyebrow": "#ffb29f",
            "eyebrow_bg": "rgba(255, 124, 102, 0.14)",
            "divider": "rgba(255, 205, 192, 0.14)",
            "chat_bg": "rgba(36, 13, 18, 0.72)",
            "chat_border": "rgba(255, 216, 206, 0.10)",
            "chat_scroll_track": "rgba(255, 216, 206, 0.08)",
            "chat_scroll_thumb": "rgba(255, 170, 149, 0.34)",
            "chat_scroll_thumb_hover": "rgba(255, 170, 149, 0.50)",
            "assistant_bg": "#fff1eb",
            "assistant_border": "rgba(164, 79, 63, 0.24)",
            "assistant_sheen": "rgba(255, 255, 255, 0.20)",
            "assistant_speaker": "#b45c48",
            "assistant_text": "#401a18",
            "user_bg": "#ff7c66",
            "user_border": "rgba(255, 124, 102, 0.28)",
            "user_sheen": "rgba(255, 232, 225, 0.14)",
            "user_speaker": "#ffe3dc",
            "user_text": "#fff9f7",
            "input_shell": "rgba(255, 255, 255, 0.10)",
            "input_bg": "rgba(255, 246, 242, 0.96)",
            "input_text": "#3c1718",
            "input_border": "rgba(171, 80, 72, 0.20)",
            "input_focus": "rgba(255, 124, 102, 0.52)",
            "send_bg": "#ff7c66",
            "send_hover": "#eb6b55",
            "send_pressed": "#d95a45",
            "send_text": "#fff8f6",
            "theme_chip_bg": "rgba(255, 241, 235, 0.92)",
            "theme_chip_text": "#7e4139",
            "theme_chip_active": "#ff7c66",
            "theme_chip_active_text": "#fff9f7",
            "theme_chip_hover": "rgba(255, 217, 207, 0.18)",
            "clear_chip_bg": "rgba(255, 217, 207, 0.12)",
            "clear_chip_hover": "rgba(255, 217, 207, 0.20)",
            "clear_chip_pressed": "rgba(255, 217, 207, 0.28)",
            "clear_chip_text": "#ffd6ca",
            "record_bg": "rgba(40, 14, 20, 0.78)",
            "record_border": "rgba(255, 205, 192, 0.14)",
            "record_rec_bg": "rgba(92, 27, 35, 0.96)",
            "record_rec_border": "rgba(255, 132, 107, 0.34)",
            "record_busy_bg": "rgba(70, 20, 29, 0.96)",
            "record_busy_border": "rgba(255, 167, 144, 0.24)",
            "record_btn_bg": "#ff7c66",
            "record_btn_hover": "#eb6b55",
            "record_btn_pressed": "#d95a45",
            "record_btn_text": "#fff8f6",
            "record_status": "#ffd6ca",
        },
        "dark": {
            "bg_start": "#0c0911",
            "bg_mid": "#1c1520",
            "bg_end": "#43301f",
            "card_bg": "rgba(24, 18, 24, 0.90)",
            "card_border": "rgba(244, 214, 170, 0.18)",
            "card_glow": "rgba(201, 145, 82, 0.24)",
            "avatar_ring": "rgba(229, 184, 118, 0.46)",
            "avatar_bg": "rgba(33, 24, 30, 0.98)",
            "avatar_outer_ring": "rgba(245, 219, 181, 0.14)",
            "title": "#fbf3e8",
            "subtitle": "#ccb8a0",
            "status": "#e3cfb4",
            "eyebrow": "#efc78e",
            "eyebrow_bg": "rgba(239, 199, 142, 0.16)",
            "divider": "rgba(244, 214, 170, 0.14)",
            "chat_bg": "rgba(17, 12, 17, 0.84)",
            "chat_border": "rgba(244, 214, 170, 0.10)",
            "chat_scroll_track": "rgba(244, 214, 170, 0.08)",
            "chat_scroll_thumb": "rgba(239, 199, 142, 0.34)",
            "chat_scroll_thumb_hover": "rgba(239, 199, 142, 0.52)",
            "assistant_bg": "#2a1f24",
            "assistant_border": "rgba(239, 199, 142, 0.16)",
            "assistant_sheen": "rgba(255, 244, 228, 0.06)",
            "assistant_speaker": "#efc78e",
            "assistant_text": "#f8efe4",
            "user_bg": "#a47142",
            "user_border": "rgba(244, 214, 170, 0.28)",
            "user_sheen": "rgba(255, 240, 214, 0.10)",
            "user_speaker": "#f7dec0",
            "user_text": "#fff9f4",
            "input_shell": "rgba(255, 255, 255, 0.05)",
            "input_bg": "rgba(28, 21, 27, 0.98)",
            "input_text": "#faf1e6",
            "input_border": "rgba(239, 199, 142, 0.14)",
            "input_focus": "rgba(239, 199, 142, 0.42)",
            "send_bg": "#d4a063",
            "send_hover": "#c28f53",
            "send_pressed": "#a97742",
            "send_text": "#1a1210",
            "theme_chip_bg": "rgba(37, 27, 35, 0.96)",
            "theme_chip_text": "#e0c8aa",
            "theme_chip_active": "#d4a063",
            "theme_chip_active_text": "#180f0d",
            "theme_chip_hover": "rgba(239, 199, 142, 0.16)",
            "clear_chip_bg": "rgba(224, 200, 170, 0.08)",
            "clear_chip_hover": "rgba(224, 200, 170, 0.14)",
            "clear_chip_pressed": "rgba(224, 200, 170, 0.20)",
            "clear_chip_text": "#e0c8aa",
            "record_bg": "rgba(24, 18, 24, 0.90)",
            "record_border": "rgba(244, 214, 170, 0.14)",
            "record_rec_bg": "rgba(62, 26, 31, 0.96)",
            "record_rec_border": "rgba(204, 120, 101, 0.26)",
            "record_busy_bg": "rgba(33, 24, 30, 0.98)",
            "record_busy_border": "rgba(239, 199, 142, 0.18)",
            "record_btn_bg": "#cf7c66",
            "record_btn_hover": "#bd6d58",
            "record_btn_pressed": "#9d5644",
            "record_btn_text": "#fff7f3",
            "record_status": "#e3cfb4",
        },
    }

    ai_stream_start = Signal()
    ai_stream_chunk = Signal(str)
    ai_stream_done = Signal(str, object)
    ai_stream_error = Signal(str)
    voice_status_update = Signal(str)
    listening_status_update = Signal(str, bool)
    voice_catalog_update = Signal(object, str)
    VIEWPORT_PRESETS = {
        "mobile": {"size": (440, 920), "min_size": (420, 860), "avatar": 104, "subtitle_width": 388},
        "max": {"size": (1320, 980), "min_size": (980, 820), "avatar": 148, "subtitle_width": 520},
    }

    def __init__(self, conf, persona, ollama, stt, tts, memory=None, conversation=None):
        super().__init__()
        self.setWindowTitle("Nellie")
        self.resize(480, 900)
        self.conf = conf
        self.persona = persona
        self.ollama = ollama
        self.stt = stt
        self.tts = tts
        self.memory = memory
        self.conversation = self._build_conversation(conversation)
        self.current_theme = self._normalize_theme(conf.get("ui", {}).get("theme", "light"))
        self.current_viewport_mode = self._normalize_viewport_mode(conf.get("ui", {}).get("viewport_mode", "mobile"))
        self.profile_controller = DesktopProfileController(self)
        self.gallery_controller = DesktopGalleryController(self)
        self.chat_controller = DesktopChatController(self)
        self.settings_controller = DesktopSettingsController(self)
        self.startup_controller = DesktopStartupController(self)

        root = QWidget()
        root.setObjectName("appRoot")
        layout = QVBoxLayout(root)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(14)

        header = QFrame()
        header.setObjectName("headerCard")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 16, 18, 16)
        header_layout.setSpacing(14)

        self.avatar = MoodAvatar(conf["paths"]["moods_dir"])
        self.avatar.setObjectName("moodAvatar")
        self.eyebrow_label = QLabel("AFTER HOURS EDITION")
        self.eyebrow_label.setObjectName("eyebrowLabel")
        self.eyebrow_label.setAlignment(Qt.AlignCenter)
        self.title_label = QLabel("Nellie")
        self.title_label.setObjectName("titleLabel")
        self.title_label.setTextFormat(Qt.RichText)
        self.subtitle_label = QLabel("Private, poised, and ready to talk")
        self.subtitle_label.setObjectName("subtitleLabel")
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setMaximumWidth(280)
        self.loading_label = QLabel("Launching Nellie... 1%")
        self.loading_label.setObjectName("loadingLabel")
        self.loading_label.setWordWrap(True)
        self.loading_label.setTextFormat(Qt.RichText)
        self.profile_label = QLabel("")
        self.profile_label.setObjectName("profileLabel")
        self.profile_label.setWordWrap(True)
        self.affection_card = QFrame()
        self.affection_card.setObjectName("affectionCard")
        affection_layout = QVBoxLayout(self.affection_card)
        affection_layout.setContentsMargins(12, 10, 12, 10)
        affection_layout.setSpacing(6)
        self.affection_header = QLabel("Relationship")
        self.affection_header.setObjectName("affectionHeader")
        self.affection_level_label = QLabel("Level 1 • Anonymous")
        self.affection_level_label.setObjectName("affectionLevelLabel")
        self.affection_progress = QProgressBar()
        self.affection_progress.setObjectName("affectionProgress")
        self.affection_progress.setTextVisible(False)
        self.affection_progress.setRange(0, 100)
        self.affection_scale = QLabel("")
        self.affection_scale.setObjectName("affectionScale")
        self.affection_scale.setTextFormat(Qt.RichText)
        self.affection_scale.setWordWrap(True)
        self.affection_hint = QLabel("Talk in ways Nellie genuinely likes and the gallery and agent functions open up over time.")
        self.affection_hint.setObjectName("affectionHint")
        self.affection_hint.setWordWrap(True)
        affection_layout.addWidget(self.affection_header)
        affection_layout.addWidget(self.affection_level_label)
        affection_layout.addWidget(self.affection_progress)
        affection_layout.addWidget(self.affection_scale)
        affection_layout.addWidget(self.affection_hint)
        self.theme_buttons = {}
        self.clear_memory_btn = QPushButton("Clear memory")
        self.clear_memory_btn.setObjectName("clearMemoryButton")
        self.clear_memory_btn.clicked.connect(self._clear_conversation_memory)
        self.view_log_btn = QPushButton("View log")
        self.view_log_btn.setObjectName("fxToggleButton")
        self.view_log_btn.setToolTip("Open the saved conversation log so it can be copied or exported.")
        self.view_log_btn.clicked.connect(self._open_conversation_log)
        self.gallery_btn = QPushButton("Gallery")
        self.gallery_btn.setObjectName("fxToggleButton")
        self.gallery_btn.setToolTip("Open the status images Nellie has unlocked so far.")
        self.gallery_btn.clicked.connect(self._open_unlocked_gallery)
        self.gallery_icon_btn = QPushButton("")
        self.gallery_icon_btn.setObjectName("fxIconButton")
        self.gallery_icon_btn.setToolTip("Open Nellie's unlocked gallery.")
        self.gallery_icon_btn.setIcon(self.style().standardIcon(QStyle.SP_DirIcon))
        self.gallery_icon_btn.setIconSize(QSize(16, 16))
        self.gallery_icon_btn.clicked.connect(self._open_unlocked_gallery)
        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setObjectName("fxIconButton")
        self.settings_btn.setToolTip("Open Nellie's settings and extra controls.")
        self.settings_btn.clicked.connect(self._open_settings_dialog)
        self.mobile_mode_btn = QPushButton("Mobile")
        self.mobile_mode_btn.setObjectName("fxToggleButton")
        self.mobile_mode_btn.setCheckable(True)
        self.mobile_mode_btn.setAutoExclusive(True)
        self.mobile_mode_btn.setToolTip("Use a narrow mobile-sized viewport to check compact layout behavior.")
        self.mobile_mode_btn.clicked.connect(lambda checked: checked and self._set_viewport_mode("mobile"))
        self.max_mode_btn = QPushButton("Max")
        self.max_mode_btn.setObjectName("fxToggleButton")
        self.max_mode_btn.setCheckable(True)
        self.max_mode_btn.setAutoExclusive(True)
        self.max_mode_btn.setToolTip("Use a maximized desktop viewport to check wide layout behavior.")
        self.max_mode_btn.clicked.connect(lambda checked: checked and self._set_viewport_mode("max"))
        self.voice_demo_btn = QPushButton("Voice demo")
        self.voice_demo_btn.setObjectName("fxToggleButton")
        self.voice_demo_btn.clicked.connect(self._play_voice_demo)
        self.language_combo = QComboBox()
        self.language_combo.setObjectName("themeButton")
        self.language_combo.setMinimumWidth(126)
        self.language_combo.addItem("Auto", "auto")
        self.language_combo.addItem("Svenska", "sv")
        self.language_combo.addItem("English", "en")
        self.language_combo.setToolTip("Choose whether Nellie should auto-detect, or listen in Swedish or English.")
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        self.voice_combo = QComboBox()
        self.voice_combo.setObjectName("themeButton")
        self.voice_combo.setMinimumWidth(190)
        self.voice_combo.setToolTip("Choose the active voice preset for Nellie.")
        self.voice_combo.currentIndexChanged.connect(self._on_voice_changed)
        self.ssml_lite_btn = QPushButton("SSML-lite")
        self.ssml_lite_btn.setObjectName("fxToggleButton")
        self.ssml_lite_btn.setCheckable(True)
        self.ssml_lite_btn.setToolTip("Experimental voice pacing: supports light pause/filler markup for TTS.")
        self.ssml_lite_btn.clicked.connect(self._toggle_ssml_lite)
        self.agent_debug_btn = QPushButton("Agent debug")
        self.agent_debug_btn.setObjectName("fxToggleButton")
        self.agent_debug_btn.setCheckable(True)
        self.agent_debug_btn.setToolTip("Show the latest agent trace and tool activity.")
        self.agent_debug_btn.toggled.connect(self._toggle_agent_debug_panel)
        self.header_divider = QFrame()
        self.header_divider.setObjectName("headerDivider")
        self.header_divider.setFrameShape(QFrame.HLine)
        self.agent_debug_panel = QFrame()
        self.agent_debug_panel.setObjectName("agentDebugPanel")
        self.agent_debug_panel.setVisible(False)
        agent_debug_layout = QVBoxLayout(self.agent_debug_panel)
        agent_debug_layout.setContentsMargins(12, 12, 12, 12)
        agent_debug_layout.setSpacing(8)
        self.agent_debug_title = QLabel("Agent Trace")
        self.agent_debug_title.setObjectName("agentDebugTitle")
        self.agent_debug_chips = QLabel("No activity")
        self.agent_debug_chips.setObjectName("agentDebugChips")
        self.agent_debug_chips.setTextFormat(Qt.RichText)
        self.agent_debug_chips.setWordWrap(True)
        self.agent_debug_text = QPlainTextEdit()
        self.agent_debug_text.setObjectName("agentDebugText")
        self.agent_debug_text.setReadOnly(True)
        self.agent_debug_text.setPlainText("No agent activity yet.")
        self.agent_debug_chips.setText(self._chip_html("no activity", "neutral"))
        agent_debug_layout.addWidget(self.agent_debug_title)
        agent_debug_layout.addWidget(self.agent_debug_chips)
        agent_debug_layout.addWidget(self.agent_debug_text)
        self.profile_panel = QFrame()
        self.profile_panel.setObjectName("controlStrip")
        profile_panel_layout = QVBoxLayout(self.profile_panel)
        profile_panel_layout.setContentsMargins(12, 12, 12, 12)
        profile_panel_layout.setSpacing(8)
        self.profile_panel_title = QLabel("Client profile")
        self.profile_panel_title.setObjectName("agentDebugTitle")
        self.profile_panel_summary = QLabel("")
        self.profile_panel_summary.setObjectName("galleryCardCaption")
        self.profile_panel_summary.setWordWrap(True)
        profile_actions = QHBoxLayout()
        profile_actions.setContentsMargins(0, 0, 0, 0)
        profile_actions.setSpacing(8)
        self.profile_switch_btn = QPushButton("Switch profile")
        self.profile_switch_btn.setObjectName("fxToggleButton")
        self.profile_switch_btn.clicked.connect(self._switch_profile_dialog)
        self.profile_create_btn = QPushButton("New profile")
        self.profile_create_btn.setObjectName("fxToggleButton")
        self.profile_create_btn.clicked.connect(self._create_profile_dialog)
        self.profile_rename_btn = QPushButton("Rename")
        self.profile_rename_btn.setObjectName("fxToggleButton")
        self.profile_rename_btn.clicked.connect(self._rename_profile_dialog)
        self.profile_delete_btn = QPushButton("Delete")
        self.profile_delete_btn.setObjectName("fxToggleButton")
        self.profile_delete_btn.clicked.connect(self._delete_profile_dialog)
        profile_actions.addWidget(self.profile_switch_btn, 0)
        profile_actions.addWidget(self.profile_create_btn, 0)
        profile_actions.addWidget(self.profile_rename_btn, 0)
        profile_actions.addWidget(self.profile_delete_btn, 0)
        profile_actions.addStretch(1)
        profile_panel_layout.addWidget(self.profile_panel_title)
        profile_panel_layout.addWidget(self.profile_panel_summary)
        profile_panel_layout.addLayout(profile_actions)
        self.control_strip = QFrame()
        self.control_strip.setObjectName("controlStrip")
        control_strip_layout = QVBoxLayout(self.control_strip)
        control_strip_layout.setContentsMargins(12, 12, 12, 12)
        control_strip_layout.setSpacing(8)
        control_strip_layout.addLayout(self._build_theme_switcher())
        control_strip_layout.addLayout(self._build_viewport_switcher())
        control_strip_layout.addLayout(self._build_control_row())
        self.settings_host = QWidget()
        self.settings_host.setVisible(False)
        settings_host_layout = QVBoxLayout(self.settings_host)
        settings_host_layout.setContentsMargins(0, 0, 0, 0)
        settings_host_layout.setSpacing(8)
        settings_host_layout.addWidget(self.profile_panel)
        settings_host_layout.addWidget(self.control_strip)
        settings_host_layout.addWidget(self.agent_debug_panel)
        self._settings_host_layout = settings_host_layout

        self.utility_strip = QFrame()
        self.utility_strip.setObjectName("utilityStrip")
        self.utility_strip.setMaximumWidth(164)
        utility_strip_layout = QHBoxLayout(self.utility_strip)
        utility_strip_layout.setContentsMargins(8, 7, 8, 7)
        utility_strip_layout.setSpacing(6)
        utility_strip_layout.addWidget(self.gallery_icon_btn, 0)
        utility_strip_layout.addWidget(self.settings_btn, 0)

        title_stack = QVBoxLayout()
        title_stack.setContentsMargins(0, 0, 0, 0)
        title_stack.setSpacing(8)
        title_stack.addWidget(self.eyebrow_label)
        title_stack.addWidget(self.title_label)
        title_stack.addWidget(self.subtitle_label)
        title_stack.addWidget(self.loading_label)
        title_stack.addWidget(self.profile_label)
        title_stack.addWidget(self.affection_card)
        title_stack.addWidget(self.utility_strip, 0, Qt.AlignRight)
        title_stack.addWidget(self.header_divider)

        self.chat = ChatView()
        self.chat.setObjectName("chatView")

        self.input_card = QFrame()
        self.input_card.setObjectName("inputCard")
        input_row = QHBoxLayout()
        input_row.setContentsMargins(10, 10, 10, 10)
        input_row.setSpacing(10)

        self.input = QLineEdit()
        self.input.setObjectName("messageInput")
        self.input.setPlaceholderText("Write to Nellie...")
        self.input.returnPressed.connect(self._submit_text)

        self.send_btn = QPushButton("Send")
        self.send_btn.setObjectName("sendButton")
        self.send_btn.clicked.connect(self._submit_text)

        input_row.addWidget(self.input, 1)
        input_row.addWidget(self.send_btn)
        self.input_card.setLayout(input_row)

        self.recorder = self._build_recorder()

        header_layout.addWidget(self.avatar, 0, Qt.AlignTop)
        header_layout.addLayout(title_stack, 1)
        layout.addWidget(header)
        layout.addWidget(self.chat, 1)
        layout.addWidget(self.input_card)
        if self.recorder is not None:
            layout.addWidget(self.recorder)

        self.setCentralWidget(root)
        self._root_layout = layout
        self._header_layout = header_layout
        self._title_stack = title_stack
        self._initialize_runtime_state()
        self._apply_depth_effects()
        self._apply_styles()
        self._sync_ssml_lite_button()
        self._refresh_profile_ui()
        self._connect_runtime_signals()
        self._finalize_startup_ui()

    # Startup and object wiring
    def _build_conversation(self, conversation):
        if conversation is not None:
            return conversation
        return ConversationService(
            persona=self.persona,
            ollama=self.ollama,
            memory=self.memory,
            gallery_dir=self.conf.get("paths", {}).get("gallery_dir"),
        )

    def _build_recorder(self):
        if self.stt is None:
            return None
        recorder = RecorderWidget(
            stt=self.stt,
            on_transcript=self.on_user_utterance,
            on_error=self.on_stt_error,
        )
        recorder.set_ready_state(False, "Voice input warming up...")
        return recorder

    def _initialize_runtime_state(self):
        self._startup_complete = False
        self._startup_status_text = "Launching Nellie"
        self._startup_steps = {
            "boot": True,
            "voice": False,
            "stt": self.stt is None,
            "finalize": False,
        }
        self._active_user_text = ""
        self._active_ai_mood = "thoughtful"
        self._latest_agent_debug = "No agent activity yet."
        self._stream_buffer = []
        self._pending_stream_chunks = []
        self._tts_queue = queue.Queue()
        self._stream_tts = self._should_stream_tts()
        self._stream_flush_timer = QTimer(self)
        self._stream_flush_timer.setInterval(35)
        self._stream_flush_timer.timeout.connect(self._flush_pending_stream_chunks)
        threading.Thread(target=self._tts_worker, daemon=True).start()
        self._voice_choice_locked = False
        self._intro_animation = None
        self._resting_voice_status = "Voice ready"
        self._resting_listening_status = "Listening ready"
        self._new_gallery_unlocks = 0
        self._last_affection_progress_value = 0
        self._last_affection_level = "Anonymous"
        self._affection_glow_grow = None
        self._affection_glow_fade = None

    def _connect_runtime_signals(self):
        self.ai_stream_start.connect(self._on_ai_stream_start)
        self.ai_stream_chunk.connect(self._on_ai_stream_chunk)
        self.ai_stream_done.connect(self._on_ai_stream_done)
        self.ai_stream_error.connect(self._on_ai_stream_error)
        self.voice_status_update.connect(self._on_voice_status_update)
        self.listening_status_update.connect(self._on_listening_status_update)
        self.voice_catalog_update.connect(self._on_voice_catalog_update)
        self.input.textChanged.connect(self._sync_input_state)

    def _finalize_startup_ui(self):
        self._sync_language_combo()
        self._set_voice_combo_loading()
        self._set_interaction_enabled(False)
        self._refresh_startup_progress("Launching Nellie")
        self._sync_input_state(self.input.text())
        self._refresh_affection_progress()
        self._apply_viewport_mode()
        self._start_voice_warmup()
        self._start_stt_warmup()

    def showEvent(self, event):
        super().showEvent(event)
        if self._intro_animation is not None:
            return
        self.setWindowOpacity(0.0)
        animation = QPropertyAnimation(self, b"windowOpacity", self)
        animation.setDuration(260)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.start()
        self._intro_animation = animation

    # Chat and streaming delegation
    def _submit_text(self):
        self.chat_controller.submit_text()

    def on_user_utterance(self, text: str):
        self.chat_controller.on_user_utterance(text)

    def _run_chat(self, text: str):
        self.chat_controller.run_chat(text)

    def _on_ai_stream_start(self):
        self.chat_controller.on_ai_stream_start()

    def _on_ai_stream_chunk(self, chunk: str):
        self.chat_controller.on_ai_stream_chunk(chunk)

    def _on_ai_stream_done(self, reply: str, meta):
        self.chat_controller.on_ai_stream_done(reply, meta)

    def _on_ai_stream_error(self, err: str):
        self.chat_controller.on_ai_stream_error(err)

    def _flush_pending_stream_chunks(self):
        self.chat_controller.flush_pending_stream_chunks()

    def _format_agent_trace(self, agent_trace: list[dict]) -> dict[str, str] | None:
        return self.chat_controller.format_agent_trace(agent_trace)

    def _set_agent_debug_payload(self, mode: str, agent_trace: list[dict], tool_events: list[dict]):
        self.settings_controller.set_agent_debug_payload(mode=mode, agent_trace=agent_trace, tool_events=tool_events)

    def _format_agent_debug_chips(self, mode: str, agent_trace: list[dict], tool_events: list[dict]) -> str:
        return self.settings_controller.format_agent_debug_chips(mode=mode, agent_trace=agent_trace, tool_events=tool_events)

    def _chip_html(self, text: str, tone: str) -> str:
        return self.settings_controller.chip_html(text, tone)

    def _format_agent_debug(self, mode: str, agent_trace: list[dict], tool_events: list[dict]) -> str:
        return self.settings_controller.format_agent_debug(mode=mode, agent_trace=agent_trace, tool_events=tool_events)

    def on_stt_error(self, err: str):
        self.chat_controller.on_stt_error(err)

    def _enqueue_tts(self, text: str, mood: str | None = None):
        self.chat_controller.enqueue_tts(text, mood=mood)

    def _interrupt_current_output(self):
        self.chat_controller.interrupt_current_output()

    def _clear_tts_queue(self):
        self.chat_controller.clear_tts_queue()

    def _tts_worker(self):
        self.chat_controller.tts_worker()

    def _should_stream_tts(self) -> bool:
        return self.chat_controller.should_stream_tts()

    def _prepare_tts_text(self, text: str) -> str:
        return self.chat_controller.prepare_tts_text(text)

    def _prepare_tts_payload(self, text: str, mood: str | None = None) -> str:
        return self.chat_controller.prepare_tts_payload(text, mood=mood)

    def _inject_spoken_mood_texture(self, spoken: str, mood: str, ssml_lite_active: bool) -> str:
        return self.chat_controller.inject_spoken_mood_texture(spoken, mood, ssml_lite_active)

    def _start_voice_warmup(self):
        self.startup_controller.start_voice_warmup()

    def _start_stt_warmup(self):
        self.startup_controller.start_stt_warmup()

    def _warmup_voice(self):
        self.startup_controller.warmup_voice()

    def _warmup_stt(self):
        self.startup_controller.warmup_stt()

    def _on_voice_status_update(self, text: str):
        self.startup_controller.on_voice_status_update(text)

    def _on_listening_status_update(self, text: str, ready: bool):
        self.startup_controller.on_listening_status_update(text, ready)

    def _on_voice_catalog_update(self, voices_obj, selected_voice: str):
        voices = [str(item) for item in (voices_obj or []) if str(item).strip()]
        self._voice_choice_locked = True
        self.voice_combo.clear()
        if not voices:
            self.voice_combo.addItem("No voices found", "")
            self.voice_combo.setEnabled(False)
            self._voice_choice_locked = False
            return
        for voice in voices:
            self.voice_combo.addItem(voice, voice)
        target_voice = selected_voice or voices[0]
        index = self.voice_combo.findData(target_voice)
        self.voice_combo.setCurrentIndex(index if index >= 0 else 0)
        self.voice_combo.setEnabled(len(voices) > 1)
        self._voice_choice_locked = False

    def _sync_language_combo(self):
        preferred = (
            self.conf.get("stt", {}).get("language")
            or self.conf.get("tts", {}).get("language")
            or "auto"
        )
        preferred = str(preferred).strip().lower()
        index = self.language_combo.findData(preferred)
        self.language_combo.blockSignals(True)
        self.language_combo.setCurrentIndex(index if index >= 0 else 0)
        self.language_combo.blockSignals(False)

    def _set_voice_combo_loading(self):
        self.startup_controller.set_voice_combo_loading()

    def _on_language_changed(self, index: int):
        language = str(self.language_combo.itemData(index) or "").strip().lower()
        if not language:
            return
        stt_language = "" if language == "auto" else language
        self.conf.setdefault("stt", {})["language"] = stt_language
        self.conf.setdefault("stt", {}).setdefault("server", {})["language"] = stt_language
        if language != "auto":
            self.conf.setdefault("tts", {})["language"] = language
        if self.stt is not None and hasattr(self.stt, "set_language"):
            try:
                self.stt.set_language(stt_language or "auto")
                if hasattr(self.stt, "get_status_text"):
                    self.listening_status.setText(self.stt.get_status_text())
            except Exception as exc:
                print(f"[stt language] {exc}")
        if language != "auto" and self.tts is not None and hasattr(self.tts, "set_language"):
            try:
                self.tts.set_language(language)
                voices = []
                selected_voice = ""
                if hasattr(self.tts, "get_available_voices"):
                    voices = list(self.tts.get_available_voices() or [])
                if hasattr(self.tts, "get_selected_voice"):
                    selected_voice = str(self.tts.get_selected_voice() or "")
                self.voice_catalog_update.emit(voices, selected_voice)
            except Exception as exc:
                print(f"[tts language] {exc}")

    def _on_voice_changed(self, index: int):
        if self._voice_choice_locked:
            return
        voice_key = str(self.voice_combo.itemData(index) or "").strip()
        if not voice_key:
            return
        self.conf.setdefault("tts", {}).setdefault("vibevoice", {})["speaker_name"] = voice_key
        if self.tts is not None and hasattr(self.tts, "set_voice"):
            try:
                self.tts.set_voice(voice_key)
                self.voice_status_update.emit(f"Voice ready ({voice_key})")
            except Exception as exc:
                print(f"[tts voice] {exc}")

    def _sync_input_state(self, text: str):
        self.chat_controller.sync_input_state(text)

    def _set_interaction_enabled(self, enabled: bool):
        self.startup_controller.set_interaction_enabled(enabled)

    def _refresh_startup_progress(self, detail: str):
        self.startup_controller.refresh_startup_progress(detail)

    # Styling and visual helpers
    def _apply_styles(self):
        palette = self.THEME_PRESETS[self.current_theme]
        self._render_title_label(palette)
        self.setStyleSheet(self._build_stylesheet(palette))

        for name, button in self.theme_buttons.items():
            button.setChecked(name == self.current_theme)
        self._refresh_depth_colors()

    def _build_stylesheet(self, palette: dict[str, str]) -> str:
        return f"""
            #appRoot {{
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 {palette["bg_start"]},
                    stop: 0.55 {palette["bg_mid"]},
                    stop: 1 {palette["bg_end"]}
                );
            }}
            #headerCard {{
                background: {palette["card_bg"]};
                border: 1px solid {palette["card_border"]};
                border-radius: 28px;
            }}
            #statusStrip {{
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid {palette["divider"]};
                border-radius: 18px;
                margin-top: 2px;
            }}
            #utilityStrip {{
                background: rgba(255, 255, 255, 0.028);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 16px;
                margin-top: 2px;
            }}
            #moodAvatar {{
                border: 5px solid {palette["avatar_ring"]};
                border-radius: 66px;
                background: {palette["avatar_bg"]};
                padding: 6px;
            }}
            #eyebrowLabel {{
                color: {palette["eyebrow"]};
                background: {palette["eyebrow_bg"]};
                border: 1px solid {palette["card_border"]};
                border-radius: 11px;
                padding: 4px 12px;
                font-size: 10px;
                font-weight: 800;
                letter-spacing: 1.8px;
            }}
            #titleLabel {{
                color: {palette["title"]};
                background: transparent;
            }}
            #subtitleLabel {{
                color: {palette["subtitle"]};
                font-size: 13px;
                line-height: 1.35em;
            }}
            #profileLabel {{
                color: {palette["status"]};
                font-size: 11px;
                letter-spacing: 0.2px;
                padding: 0 0 2px 0;
            }}
            #loadingLabel {{
                color: {palette["eyebrow"]};
                font-size: 12px;
                font-weight: 800;
                letter-spacing: 0.9px;
                padding: 3px 0 1px 0;
            }}
            #affectionCard {{
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 rgba(255, 255, 255, 0.07),
                    stop: 0.45 rgba(255, 255, 255, 0.035),
                    stop: 1 rgba(255, 255, 255, 0.055)
                );
                border: 1px solid {palette["divider"]};
                border-radius: 18px;
                margin-top: 2px;
            }}
            #affectionCard[affectionTone="strangers"] {{
                border: 1px solid rgba(255,255,255,0.08);
            }}
            #affectionCard[affectionTone="curious"] {{
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 rgba(214, 189, 153, 0.10),
                    stop: 1 rgba(255, 255, 255, 0.04)
                );
                border: 1px solid rgba(214, 189, 153, 0.16);
            }}
            #affectionCard[affectionTone="warm"] {{
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 rgba(224, 156, 112, 0.13),
                    stop: 1 rgba(255, 255, 255, 0.04)
                );
                border: 1px solid rgba(224, 156, 112, 0.18);
            }}
            #affectionCard[affectionTone="close"] {{
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 rgba(209, 132, 118, 0.15),
                    stop: 1 rgba(255, 255, 255, 0.04)
                );
                border: 1px solid rgba(209, 132, 118, 0.20);
            }}
            #affectionCard[affectionTone="magnetic"] {{
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 1,
                    stop: 0 rgba(223, 181, 107, 0.18),
                    stop: 1 rgba(255, 255, 255, 0.05)
                );
                border: 1px solid rgba(223, 181, 107, 0.24);
            }}
            #affectionHeader {{
                color: {palette["eyebrow"]};
                font-size: 10px;
                font-weight: 800;
                letter-spacing: 1.4px;
                text-transform: uppercase;
            }}
            #affectionLevelLabel {{
                color: {palette["title"]};
                font-size: 13px;
                font-weight: 800;
                letter-spacing: 0.2px;
            }}
            #affectionHint {{
                color: {palette["subtitle"]};
                font-size: 11px;
                line-height: 1.35em;
            }}
            #affectionScale {{
                color: {palette["status"]};
                font-size: 10px;
                font-weight: 700;
                line-height: 1.35em;
            }}
            #affectionProgress {{
                background: rgba(255, 255, 255, 0.07);
                border: 1px solid {palette["divider"]};
                border-radius: 10px;
                min-height: 14px;
                max-height: 14px;
                padding: 1px;
            }}
            #affectionProgress::chunk {{
                border-radius: 8px;
                background: qlineargradient(
                    x1: 0, y1: 0, x2: 1, y2: 0,
                    stop: 0 rgba(255,255,255,0.92),
                    stop: 0.06 {palette["eyebrow"]},
                    stop: 0.52 {palette["send_bg"]},
                    stop: 1 {palette["theme_chip_active"]}
                );
            }}
            #affectionProgress[affectionTone="curious"]::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(255,255,255,0.92), stop:0.08 #d6bd99, stop:1 #caa278);
            }}
            #affectionProgress[affectionTone="warm"]::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(255,255,255,0.92), stop:0.08 #e09c70, stop:1 #c57b57);
            }}
            #affectionProgress[affectionTone="close"]::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(255,255,255,0.92), stop:0.08 #d18476, stop:1 #b6606d);
            }}
            #affectionProgress[affectionTone="magnetic"]::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 rgba(255,255,255,0.96), stop:0.08 #dfb56b, stop:1 #c99543);
            }}
            #voiceStatus {{
                color: {palette["status"]};
                font-size: 11px;
                font-weight: 800;
                letter-spacing: 0.4px;
                text-transform: uppercase;
                padding-top: 0;
                padding-right: 6px;
                padding-bottom: 0;
            }}
            #headerDivider {{
                background: {palette["divider"]};
                min-height: 1px;
                max-height: 1px;
                border: none;
                margin: 4px 0 2px 0;
            }}
            #controlStrip {{
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid {palette["divider"]};
                border-radius: 20px;
                margin-top: 2px;
            }}
            #agentDebugPanel {{
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid {palette["divider"]};
                border-radius: 18px;
                margin-top: 4px;
            }}
            #galleryCard {{
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid {palette["divider"]};
                border-radius: 20px;
            }}
            #galleryCardTitle {{
                color: {palette["title"]};
                font-size: 12px;
                font-weight: 800;
            }}
            #galleryCardMeta {{
                color: {palette["status"]};
                font-size: 11px;
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 1px;
            }}
            #galleryCardCaption {{
                color: {palette["subtitle"]};
                font-size: 12px;
                line-height: 1.35em;
            }}
            #agentDebugTitle {{
                color: {palette["status"]};
                font-size: 11px;
                font-weight: 800;
                letter-spacing: 1.2px;
                text-transform: uppercase;
            }}
            #agentDebugChips {{
                color: {palette["title"]};
                background: transparent;
                min-height: 28px;
            }}
            #agentDebugText {{
                background: transparent;
                color: {palette["title"]};
                border: none;
                font-family: "Consolas";
                font-size: 11px;
                selection-background-color: {palette["theme_chip_active"]};
                padding: 0;
            }}
            #themeButton {{
                background: {palette["theme_chip_bg"]};
                color: {palette["theme_chip_text"]};
                border: 1px solid rgba(255, 255, 255, 0.04);
                border-radius: 16px;
                min-height: 34px;
                padding: 0 12px;
                font-size: 12px;
                font-weight: 700;
            }}
            #themeButton:hover {{
                background: {palette["theme_chip_hover"]};
                border: 1px solid {palette["card_border"]};
            }}
            #themeButton:checked {{
                background: {palette["theme_chip_active"]};
                color: {palette["theme_chip_active_text"]};
            }}
            QComboBox#themeButton {{
                min-height: 36px;
                padding: 0 30px 0 12px;
            }}
            QComboBox#themeButton::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: 28px;
                border: none;
                background: transparent;
            }}
            QComboBox#themeButton::down-arrow {{
                width: 0px;
                height: 0px;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid {palette["theme_chip_text"]};
                margin-right: 10px;
            }}
            QComboBox#themeButton QAbstractItemView {{
                background: {palette["input_bg"]};
                color: {palette["input_text"]};
                border: 1px solid {palette["card_border"]};
                selection-background-color: {palette["theme_chip_active"]};
                selection-color: {palette["theme_chip_active_text"]};
                border-radius: 14px;
                padding: 6px;
                outline: none;
            }}
            #fxToggleButton {{
                background: {palette["clear_chip_bg"]};
                color: {palette["clear_chip_text"]};
                border: 1px solid rgba(255, 255, 255, 0.04);
                border-radius: 16px;
                min-height: 34px;
                padding: 0 12px;
                font-size: 12px;
                font-weight: 700;
            }}
            #fxToggleButton:hover {{
                background: {palette["clear_chip_hover"]};
                border: 1px solid {palette["card_border"]};
            }}
            #fxToggleButton:checked {{
                background: {palette["theme_chip_active"]};
                color: {palette["theme_chip_active_text"]};
                border: 1px solid transparent;
            }}
            #fxToggleButton:disabled {{
                color: {palette["status"]};
                background: {palette["chat_scroll_track"]};
            }}
            #fxIconButton {{
                background: rgba(255, 255, 255, 0.06);
                color: {palette["clear_chip_text"]};
                border: 1px solid rgba(255, 255, 255, 0.06);
                border-radius: 15px;
                min-width: 30px;
                max-width: 30px;
                min-height: 30px;
                max-height: 30px;
                padding: 0;
                font-size: 16px;
                font-weight: 700;
                text-align: center;
            }}
            #fxIconButton:hover {{
                background: rgba(255, 255, 255, 0.12);
                border: 1px solid {palette["card_border"]};
            }}
            #fxIconButton:pressed {{
                background: {palette["clear_chip_pressed"]};
            }}
            #clearMemoryButton {{
                background: {palette["clear_chip_bg"]};
                color: {palette["clear_chip_text"]};
                border: 1px solid rgba(255, 255, 255, 0.04);
                border-radius: 16px;
                min-height: 34px;
                padding: 0 12px;
                font-size: 12px;
                font-weight: 700;
            }}
            #clearMemoryButton:hover {{
                background: {palette["clear_chip_hover"]};
                border: 1px solid {palette["card_border"]};
            }}
            #clearMemoryButton:pressed {{
                background: {palette["clear_chip_pressed"]};
            }}
            #chatList {{
                background: {palette["chat_bg"]};
                border: 1px solid {palette["chat_border"]};
                border-radius: 28px;
                padding: 20px 16px 20px 14px;
                outline: none;
            }}
            #chatList::item {{
                background: transparent;
                border: none;
            }}
            #chatList QScrollBar:vertical {{
                background: {palette["chat_scroll_track"]};
                width: 12px;
                margin: 12px 8px 12px 0;
                border-radius: 6px;
            }}
            #chatList QScrollBar::handle:vertical {{
                background: {palette["chat_scroll_thumb"]};
                min-height: 36px;
                border-radius: 6px;
            }}
            #chatList QScrollBar::handle:vertical:hover {{
                background: {palette["chat_scroll_thumb_hover"]};
            }}
            #chatList QScrollBar::add-line:vertical,
            #chatList QScrollBar::sub-line:vertical,
            #chatList QScrollBar::add-page:vertical,
            #chatList QScrollBar::sub-page:vertical {{
                background: transparent;
                border: none;
                height: 0px;
            }}
            #chatEmptyState {{
                color: {palette["status"]};
                font-size: 13px;
                font-weight: 600;
                line-height: 1.45em;
                padding: 0 52px;
            }}
            #chatBubble[role="assistant"] {{
                background: {palette["assistant_bg"]};
                border: 1px solid {palette["assistant_border"]};
                border-radius: 28px;
            }}
            #chatBubble[role="system"] {{
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid {palette["divider"]};
                border-radius: 16px;
            }}
            #chatBubble[role="system-plan"] {{
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid {palette["divider"]};
                border-radius: 16px;
            }}
            #chatBubble[role="system-ok"] {{
                background: rgba(126, 184, 125, 0.12);
                border: 1px solid rgba(126, 184, 125, 0.26);
                border-radius: 16px;
            }}
            #chatBubble[role="system-warning"] {{
                background: rgba(212, 160, 99, 0.12);
                border: 1px solid rgba(212, 160, 99, 0.26);
                border-radius: 16px;
            }}
            #chatBubble[role="system-danger"] {{
                background: rgba(207, 124, 102, 0.12);
                border: 1px solid rgba(207, 124, 102, 0.30);
                border-radius: 16px;
            }}
            #chatBubble[role="user"] {{
                background: {palette["user_bg"]};
                border: 1px solid {palette["user_border"]};
                border-radius: 28px;
            }}
            #chatBubble[streaming="true"] {{
                background: rgba(255, 255, 255, 0.08);
                border: 1px solid {palette["input_focus"]};
                border-style: solid;
            }}
            #chatBubble {{
                padding-top: 0;
            }}
            #chatBubble[role="assistant"] #speakerLabel {{
                color: {palette["assistant_speaker"]};
            }}
            #chatBubble[role="system"] #speakerLabel {{
                color: {palette["status"]};
                font-size: 9px;
                letter-spacing: 1.8px;
                padding-bottom: 0;
            }}
            #chatBubble[role="system-plan"] #speakerLabel {{
                color: {palette["status"]};
                font-size: 9px;
                letter-spacing: 1.8px;
                padding-bottom: 0;
            }}
            #chatBubble[role="system-ok"] #speakerLabel {{
                color: #d8f0d0;
                font-size: 9px;
                letter-spacing: 1.8px;
                padding-bottom: 0;
            }}
            #chatBubble[role="system-warning"] #speakerLabel {{
                color: #f5dfbf;
                font-size: 9px;
                letter-spacing: 1.8px;
                padding-bottom: 0;
            }}
            #chatBubble[role="system-danger"] #speakerLabel {{
                color: #ffd9d0;
                font-size: 9px;
                letter-spacing: 1.8px;
                padding-bottom: 0;
            }}
            #chatBubble[role="user"] #speakerLabel {{
                color: {palette["user_speaker"]};
            }}
            #chatBubble[role="assistant"] #bubbleText {{
                color: {palette["assistant_text"]};
            }}
            #chatBubble[role="system"] #bubbleText {{
                color: {palette["status"]};
                font-size: 12px;
                font-weight: 700;
                line-height: 1.28em;
                padding-bottom: 0;
            }}
            #chatBubble[role="system-plan"] #bubbleText {{
                color: {palette["status"]};
                font-size: 12px;
                font-weight: 700;
                line-height: 1.28em;
                padding-bottom: 0;
            }}
            #chatBubble[role="system-ok"] #bubbleText {{
                color: #e6f6df;
                font-size: 12px;
                font-weight: 700;
                line-height: 1.28em;
                padding-bottom: 0;
            }}
            #chatBubble[role="system-warning"] #bubbleText {{
                color: #f8e5c8;
                font-size: 12px;
                font-weight: 700;
                line-height: 1.28em;
                padding-bottom: 0;
            }}
            #chatBubble[role="system-danger"] #bubbleText {{
                color: #ffe3dc;
                font-size: 12px;
                font-weight: 700;
                line-height: 1.28em;
                padding-bottom: 0;
            }}
            #chatBubble[role="user"] #bubbleText {{
                color: {palette["user_text"]};
            }}
            #speakerLabel {{
                font-size: 10px;
                font-weight: 800;
                text-transform: uppercase;
                letter-spacing: 1.5px;
                padding-bottom: 4px;
            }}
            #bubbleText {{
                font-family: "Georgia";
                font-size: 16px;
                font-weight: 500;
                line-height: 1.34em;
                padding-bottom: 0;
            }}
            #bubbleImage {{
                background: rgba(255, 255, 255, 0.04);
                border: 1px solid {palette["divider"]};
                border-radius: 18px;
                padding: 6px;
                margin-bottom: 6px;
            }}
            #inputCard {{
                background: {palette["input_shell"]};
                border: 1px solid {palette["card_border"]};
                border-radius: 24px;
            }}
            #inputCard[state="active"] {{
                background: rgba(255, 255, 255, 0.10);
                border: 1px solid {palette["input_focus"]};
            }}
            #messageInput {{
                background: {palette["input_bg"]};
                color: {palette["input_text"]};
                border: 1px solid {palette["input_border"]};
                border-radius: 20px;
                padding: 16px 18px;
                font-size: 15px;
                font-family: "Georgia";
            }}
            #messageInput:focus {{
                border: 1px solid {palette["input_focus"]};
            }}
            #sendButton {{
                background: {palette["send_bg"]};
                color: {palette["send_text"]};
                border: none;
                border-radius: 20px;
                padding: 0 22px;
                min-width: 96px;
                min-height: 50px;
                font-size: 14px;
                font-weight: 800;
            }}
            #sendButton:hover {{
                background: {palette["send_hover"]};
            }}
            #sendButton:pressed {{
                background: {palette["send_pressed"]};
            }}
            #sendButton:disabled {{
                background: {palette["chat_scroll_track"]};
                color: {palette["status"]};
            }}
            #recorderCard {{
                background: {palette["record_bg"]};
                border: 1px solid {palette["record_border"]};
                border-radius: 24px;
            }}
            #recorderCard[state="recording"] {{
                background: {palette["record_rec_bg"]};
                border: 1px solid {palette["record_rec_border"]};
            }}
            #recorderCard[state="busy"] {{
                background: {palette["record_busy_bg"]};
                border: 1px solid {palette["record_busy_border"]};
            }}
            #recordButton {{
                background: {palette["record_btn_bg"]};
                color: {palette["record_btn_text"]};
                border: none;
                border-radius: 20px;
                min-width: 132px;
                min-height: 46px;
                padding: 0 18px;
                font-size: 13px;
                font-weight: 800;
            }}
            #recordButton:hover {{
                background: {palette["record_btn_hover"]};
            }}
            #recordButton:pressed {{
                background: {palette["record_btn_pressed"]};
            }}
            #recordButton:disabled {{
                background: {palette["chat_scroll_track"]};
                color: {palette["status"]};
            }}
            #recordStatus {{
                color: {palette["record_status"]};
                font-size: 13px;
                font-weight: 700;
                line-height: 1.3em;
            }}
            """

    def _render_title_label(self, palette):
        self.title_label.setText(
            (
                f"<span style=\"font-family:'Bodoni MT'; font-size:12px; "
                f"font-weight:700; letter-spacing:4px; color:{palette['eyebrow']};\">THE </span>"
                f"<span style=\"font-family:'Bodoni MT'; font-size:48px; "
                f"font-weight:700; color:{palette['title']};\">N</span>"
                f"<span style=\"font-family:'Georgia'; font-size:37px; "
                f"font-style:italic; letter-spacing:1px; color:{palette['title']};\">ellie</span>"
            )
        )

    def _apply_depth_effects(self):
        self._depth_targets = {
            "header": self._build_shadow(0, 28, 60, "rgba(20, 16, 12, 0.14)"),
            "chat": self._build_shadow(0, 24, 48, "rgba(20, 16, 12, 0.10)"),
            "input": self._build_shadow(0, 18, 34, "rgba(20, 16, 12, 0.10)"),
            "avatar": self._build_shadow(0, 18, 34, "rgba(20, 16, 12, 0.14)"),
            "affection": self._build_shadow(0, 18, 30, "rgba(20, 16, 12, 0.12)"),
            "loading": self._build_shadow(0, 0, 22, "rgba(239, 199, 142, 0.45)"),
        }
        self.findChild(QFrame, "headerCard").setGraphicsEffect(self._depth_targets["header"])
        self.chat.list.setGraphicsEffect(self._depth_targets["chat"])
        self.input_card.setGraphicsEffect(self._depth_targets["input"])
        self.avatar.setGraphicsEffect(self._depth_targets["avatar"])
        self.affection_card.setGraphicsEffect(self._depth_targets["affection"])
        self.loading_label.setGraphicsEffect(self._depth_targets["loading"])
        if self.recorder is not None:
            self._depth_targets["recorder"] = self._build_shadow(0, 18, 34, "rgba(20, 16, 12, 0.10)")
            self.recorder.setGraphicsEffect(self._depth_targets["recorder"])

    def _build_shadow(self, x_offset: int, y_offset: int, blur: int, color: str):
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setOffset(x_offset, y_offset)
        shadow.setBlurRadius(blur)
        shadow.setColor(QColor(color))
        return shadow

    def _refresh_depth_colors(self):
        palette = self.THEME_PRESETS[self.current_theme]
        for shadow in getattr(self, "_depth_targets", {}).values():
            shadow.setColor(QColor(palette["card_glow"]))

    def _build_theme_switcher(self):
        return self.settings_controller.build_theme_switcher()

    def _build_viewport_switcher(self):
        return self.settings_controller.build_viewport_switcher()

    def _build_control_row(self):
        return self.settings_controller.build_control_row()

    def _open_conversation_log(self):
        self.settings_controller.open_conversation_log()


    # Profile handling now lives in ui.profile_controller.DesktopProfileController.
    # These delegating methods intentionally override the older in-class implementations
    # above so the behavior can be extracted without a risky one-shot rewrite.
    def _profile_path(self) -> Path:
        return self.profile_controller.profile_path()

    def _profile_registry_path(self) -> Path:
        return self.profile_controller.profile_registry_path()

    def _load_profile_registry(self) -> dict:
        return self.profile_controller.load_profile_registry()

    def _save_profile_registry(self, registry: dict):
        self.profile_controller.save_profile_registry(registry)

    def _active_profile(self) -> dict:
        return self.profile_controller.active_profile()

    def _refresh_profile_ui(self):
        self.profile_controller.refresh_profile_ui()

    def _profile_db_path(self, user_id: str) -> Path:
        return self.profile_controller.profile_db_path(user_id)

    def _profile_snapshot(self, user_id: str) -> dict:
        return self.profile_controller.profile_snapshot(user_id)

    def _level_from_xp_local(self, xp: int) -> int:
        return self.profile_controller.level_from_xp_local(xp)

    def _relationship_stage_local(self, level: int) -> str:
        return self.profile_controller.relationship_stage_local(level)

    def _apply_profile(self, profile: dict):
        self.profile_controller.apply_profile(profile)

    def _switch_profile_dialog(self):
        self.profile_controller.switch_profile_dialog()

    def _create_profile_dialog(self):
        self.profile_controller.create_profile_dialog()

    def _fallback_profile_badge(self, user_id: str) -> str:
        return self.profile_controller.fallback_profile_badge(user_id)

    def _assign_profile_badge_color(self, profile: dict, profiles: list[dict]) -> str:
        return self.profile_controller.assign_profile_badge_color(profile, profiles)

    def _rename_profile_dialog(self):
        self.profile_controller.rename_profile_dialog()

    def _delete_profile_dialog(self):
        self.profile_controller.delete_profile_dialog()

    def _open_settings_dialog(self):
        self.settings_controller.open_settings_dialog()

    def _open_unlocked_gallery(self):
        self.gallery_controller.open_unlocked_gallery()

    # Logs, export, and diagnostics
    def _build_combined_log(self) -> str:
        return build_combined_log(self)

    def _save_conversation_log(self, text: str):
        suggested = Path(self.conf["paths"]["db_path"]).with_name("conversation_log.txt")
        target, _ = QFileDialog.getSaveFileName(
            self,
            "Save conversation log",
            str(suggested),
            "Text files (*.txt);;All files (*.*)",
        )
        if not target:
            return

        try:
            Path(target).write_text(text, encoding="utf-8")
        except Exception as exc:
            QMessageBox.warning(self, "Save failed", f"Could not save the conversation log.\n\n{exc}")

    def _set_theme(self, theme_name: str):
        normalized = self._normalize_theme(theme_name)
        if normalized == self.current_theme:
            return
        self.current_theme = normalized
        self.conf.setdefault("ui", {})["theme"] = normalized
        self._apply_styles()

    def _toggle_ssml_lite(self, checked: bool):
        self.conf.setdefault("tts", {}).setdefault("vibevoice", {})["ssml_lite_enabled"] = bool(checked)
        if hasattr(self.tts, "set_ssml_lite_enabled"):
            try:
                self.tts.set_ssml_lite_enabled(checked)
            except Exception as exc:
                print(f"[tts ssml-lite] {exc}")
        self._sync_ssml_lite_button()

    def _sync_ssml_lite_button(self):
        enabled = False
        if hasattr(self.tts, "is_ssml_lite_enabled"):
            try:
                enabled = bool(self.tts.is_ssml_lite_enabled())
            except Exception:
                enabled = False
        else:
            enabled = bool(self.conf.get("tts", {}).get("vibevoice", {}).get("ssml_lite_enabled", False))

        self.ssml_lite_btn.blockSignals(True)
        self.ssml_lite_btn.setChecked(enabled)
        self.ssml_lite_btn.blockSignals(False)
        self.ssml_lite_btn.setEnabled(hasattr(self.tts, "set_ssml_lite_enabled"))
        startup_ready = bool(getattr(self, "_startup_complete", False))
        self.voice_demo_btn.setEnabled(startup_ready and hasattr(self.tts, "speak"))
        if not hasattr(self.tts, "get_available_voices"):
            self._voice_choice_locked = True
            self.voice_combo.clear()
            self.voice_combo.addItem("Voice fixed", "")
            self.voice_combo.setEnabled(False)
            self._voice_choice_locked = False

    def _toggle_agent_debug_panel(self, checked: bool):
        self.settings_controller.toggle_agent_debug_panel(checked)

    # Voice and memory actions
    def _play_voice_demo(self):
        self._interrupt_current_output()
        language = str(self.conf.get("tts", {}).get("language", "en") or "en").strip().lower()
        if hasattr(self.tts, "is_ssml_lite_enabled"):
            try:
                ssml_lite_active = bool(self.tts.is_ssml_lite_enabled())
            except Exception:
                ssml_lite_active = False
        else:
            ssml_lite_active = False

        if language == "sv":
            if ssml_lite_active:
                sample = (
                    '<speak>'
                    '<filler kind="mm"/> nu hör du det nog tydligare.'
                    '<break time="140ms"/>'
                    'Rösten saktar ner lite,'
                    '<break time="120ms"/>'
                    'andas lite naturligare,'
                    '<break time="160ms"/>'
                    'och landar mjukare i slutet.'
                    '</speak>'
                )
            else:
                sample = "Nu hör du det nog tydligare. Rösten känns renare och rakare, men lite mindre formad."
        elif ssml_lite_active:
            sample = (
                '<speak>'
                '<filler kind="mm"/> you can probably hear it now.'
                '<break time="140ms"/>'
                'The voice slows down a touch,'
                '<break time="120ms"/>'
                'breathes a little more naturally,'
                '<break time="160ms"/>'
                'and lands more softly at the end.'
                '</speak>'
            )
        else:
            sample = "You can probably hear it now. The voice is cleaner and more direct, but less shaped."

        self.voice_status_update.emit("Playing voice demo...")
        self._enqueue_tts(sample)

    def _clear_conversation_memory(self):
        answer = QMessageBox.question(
            self,
            "Clear Nellie's memory",
            "Clear Nellie's saved chat history and remembered user details?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        if hasattr(self.conversation, "clear_all"):
            self.conversation.clear_all()
        elif self.memory is not None:
            self.memory.clear_all()
        self.chat.clear_messages()
        self._active_user_text = ""
        self._stream_buffer.clear()
        self.avatar.set_mood("neutral")
        self._new_gallery_unlocks = 0
        self._refresh_gallery_button()
        self._refresh_affection_progress()
        self.chat.add_ai("Memory cleared. We can start fresh.")

    def _normalize_viewport_mode(self, mode_name: str) -> str:
        mode = (mode_name or "mobile").strip().lower()
        return "max" if mode in {"max", "desktop", "wide", "fullscreen"} else "mobile"

    # Layout and gallery helpers
    def _set_viewport_mode(self, mode_name: str):
        normalized = self._normalize_viewport_mode(mode_name)
        if normalized == self.current_viewport_mode:
            return
        self.current_viewport_mode = normalized
        self.conf.setdefault("ui", {})["viewport_mode"] = normalized
        self._apply_viewport_mode()

    def _apply_viewport_mode(self):
        mode = self._normalize_viewport_mode(self.current_viewport_mode)
        preset = self.VIEWPORT_PRESETS.get(mode, self.VIEWPORT_PRESETS["mobile"])
        is_mobile = mode == "mobile"

        self.mobile_mode_btn.blockSignals(True)
        self.max_mode_btn.blockSignals(True)
        self.mobile_mode_btn.setChecked(is_mobile)
        self.max_mode_btn.setChecked(not is_mobile)
        self.mobile_mode_btn.blockSignals(False)
        self.max_mode_btn.blockSignals(False)

        self.subtitle_label.setMaximumWidth(preset["subtitle_width"])
        self.avatar.setFixedSize(preset["avatar"], preset["avatar"])
        self._root_layout.setContentsMargins(22 if is_mobile else 28, 18 if is_mobile else 22, 22 if is_mobile else 28, 18 if is_mobile else 22)
        self._root_layout.setSpacing(14 if is_mobile else 18)
        self._header_layout.setDirection(QBoxLayout.TopToBottom if is_mobile else QBoxLayout.LeftToRight)
        self._header_layout.setSpacing(12 if is_mobile else 18)
        self._title_stack.setSpacing(8 if is_mobile else 10)
        self._header_layout.setAlignment(self.avatar, Qt.AlignHCenter if is_mobile else Qt.AlignTop)
        self._header_layout.setAlignment(self._title_stack, Qt.AlignTop)
        self.utility_strip.setMaximumWidth(148 if is_mobile else 164)

        if is_mobile:
            self.showNormal()
            self.setMinimumSize(*preset["min_size"])
            self.resize(*preset["size"])
        else:
            self.showNormal()
            self.setMinimumSize(*preset["min_size"])
            self.resize(*preset["size"])
            self.showMaximized()

        self._sync_input_state(self.input.text())

    def _mark_gallery_unlock(self):
        self.gallery_controller.mark_gallery_unlock()

    def _clear_gallery_unlock_marker(self):
        self.gallery_controller.clear_gallery_unlock_marker()

    def _refresh_gallery_button(self):
        self.gallery_controller.refresh_gallery_button()

    def _relationship_ui_copy(self, stage: str) -> dict:
        return self.gallery_controller.relationship_ui_copy(stage)

    def _format_gallery_unlock_title(self, filename: str) -> str:
        return self.gallery_controller.format_gallery_unlock_title(filename)

    def _set_affection_tone(self, level: str):
        self.gallery_controller.set_affection_tone(level)

    def _animate_affection_glow(self):
        self.gallery_controller.animate_affection_glow()

    def _refresh_affection_progress_legacy(self):
        self.gallery_controller.refresh_affection_progress_legacy()

    def _refresh_affection_progress(self):
        self.gallery_controller.refresh_affection_progress()

    def _build_affection_scale_html(self, level_thresholds: list[tuple[int, str]], score: int, current_level: str) -> str:
        return self.gallery_controller.build_affection_scale_html(level_thresholds, score, current_level)

    def _normalize_theme(self, theme_name: str) -> str:
        theme = (theme_name or "light").strip().lower()
        aliases = {
            "darkmode": "dark",
            "dakmode": "dark",
            "dark": "dark",
            "red": "red",
            "light": "light",
        }
        return aliases.get(theme, "light")

