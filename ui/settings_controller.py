from __future__ import annotations

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)


class DesktopSettingsController:
    def __init__(self, window):
        self.window = window

    def build_theme_switcher(self):
        row = QHBoxLayout()
        row.setContentsMargins(0, 6, 0, 0)
        row.setSpacing(8)
        for theme_name, label in [("light", "Light"), ("red", "Red"), ("dark", "Dark")]:
            btn = QPushButton(label)
            btn.setObjectName("themeButton")
            btn.setCheckable(True)
            btn.setAutoExclusive(True)
            btn.clicked.connect(lambda checked, name=theme_name: self.window._set_theme(name))
            self.window.theme_buttons[theme_name] = btn
            row.addWidget(btn, 0)
        row.addStretch(1)
        return row

    def build_viewport_switcher(self):
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        row.addWidget(self.window.mobile_mode_btn, 0)
        row.addWidget(self.window.max_mode_btn, 0)
        row.addStretch(1)
        return row

    def build_control_row(self):
        stack = QVBoxLayout()
        stack.setContentsMargins(0, 2, 0, 0)
        stack.setSpacing(8)

        utility_row = QHBoxLayout()
        utility_row.setContentsMargins(0, 0, 0, 0)
        utility_row.setSpacing(8)
        utility_row.addWidget(self.window.clear_memory_btn, 0)
        utility_row.addWidget(self.window.view_log_btn, 0)
        utility_row.addWidget(self.window.gallery_btn, 0)
        utility_row.addStretch(1)

        mode_row = QHBoxLayout()
        mode_row.setContentsMargins(0, 0, 0, 0)
        mode_row.setSpacing(8)
        mode_row.addWidget(self.window.language_combo, 0)
        mode_row.addWidget(self.window.model_combo, 0)
        mode_row.addStretch(1)

        voice_row = QHBoxLayout()
        voice_row.setContentsMargins(0, 0, 0, 0)
        voice_row.setSpacing(8)
        voice_row.addWidget(self.window.voice_combo, 0)
        voice_row.addWidget(self.window.voice_demo_btn, 0)
        voice_row.addStretch(1)

        toggles_row = QHBoxLayout()
        toggles_row.setContentsMargins(0, 0, 0, 0)
        toggles_row.setSpacing(8)
        toggles_row.addWidget(self.window.ssml_lite_btn, 0)
        toggles_row.addWidget(self.window.agent_debug_btn, 0)
        toggles_row.addStretch(1)

        stack.addLayout(utility_row)
        stack.addLayout(mode_row)
        stack.addLayout(voice_row)
        stack.addLayout(toggles_row)
        return stack

    def open_settings_dialog(self):
        dialog = QDialog(self.window)
        dialog.setWindowTitle("Nellie settings")
        dialog.resize(540, 620)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        intro = QLabel("Theme, viewport, voice and debug controls live here so the main window stays clean.")
        intro.setObjectName("galleryCardCaption")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self.window._settings_host_layout.removeWidget(self.window.profile_panel)
        self.window._settings_host_layout.removeWidget(self.window.control_strip)
        self.window._settings_host_layout.removeWidget(self.window.agent_debug_panel)
        layout.addWidget(self.window.profile_panel)
        layout.addWidget(self.window.control_strip)
        layout.addWidget(self.window.agent_debug_panel)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)

        try:
            dialog.exec()
        finally:
            layout.removeWidget(self.window.profile_panel)
            layout.removeWidget(self.window.control_strip)
            layout.removeWidget(self.window.agent_debug_panel)
            self.window._settings_host_layout.addWidget(self.window.profile_panel)
            self.window._settings_host_layout.addWidget(self.window.control_strip)
            self.window._settings_host_layout.addWidget(self.window.agent_debug_panel)

    def toggle_agent_debug_panel(self, checked: bool):
        self.window.agent_debug_panel.setVisible(bool(checked))
        self.window.agent_debug_text.setPlainText(self.window._latest_agent_debug)

    def set_agent_debug_payload(self, mode: str, agent_trace: list[dict], tool_events: list[dict]):
        self.window._latest_agent_debug = self.format_agent_debug(
            mode=mode,
            agent_trace=agent_trace,
            tool_events=tool_events,
        )
        self.window.agent_debug_chips.setText(
            self.format_agent_debug_chips(mode=mode, agent_trace=agent_trace, tool_events=tool_events)
        )
        self.window.agent_debug_text.setPlainText(self.window._latest_agent_debug)

    def format_agent_debug_chips(self, mode: str, agent_trace: list[dict], tool_events: list[dict]) -> str:
        plan = next((item for item in agent_trace if item.get("step") == "plan"), None)
        execute = next((item for item in agent_trace if item.get("step") == "tool_execute"), None)
        lookup = next((item for item in agent_trace if item.get("step") == "tool_lookup"), None)

        chips = []
        if mode and mode != "direct_reply":
            tool_name = (plan or {}).get("tool_name") or "tool"
            chips.append(self.chip_html(f"plan: {tool_name}", "neutral"))

        if execute and execute.get("status") == "ok":
            tool_name = execute.get("tool_name") or (plan or {}).get("tool_name") or "tool"
            chips.append(self.chip_html(f"tool ok: {tool_name}", "ok"))
        elif lookup and lookup.get("status") == "missing":
            chips.append(self.chip_html("tool missing", "warning"))
        elif execute and execute.get("status") == "error":
            chips.append(self.chip_html("fallback", "warning"))
            chips.append(self.chip_html("tool error", "danger"))
        elif mode == "direct_reply":
            chips.append(self.chip_html("direct reply", "neutral"))

        if tool_events and not any(event.get("status") != "ok" for event in tool_events):
            chips.append(self.chip_html("tool activity", "ok"))

        return " ".join(chips) if chips else self.chip_html("no activity", "neutral")

    def chip_html(self, text: str, tone: str) -> str:
        tone_map = {
            "neutral": ("rgba(255,255,255,0.06)", "#d9c7ae"),
            "ok": ("rgba(126,184,125,0.18)", "#d8f0d0"),
            "warning": ("rgba(212,160,99,0.20)", "#f5dfbf"),
            "danger": ("rgba(207,124,102,0.20)", "#ffd9d0"),
        }
        background, foreground = tone_map.get(tone, tone_map["neutral"])
        safe_text = (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        return (
            f"<span style=\"background:{background}; color:{foreground}; "
            "border:1px solid rgba(255,255,255,0.06); border-radius:10px; "
            "padding:3px 8px; font-size:10px; font-weight:700; letter-spacing:0.5px;\">"
            f"{safe_text}</span>"
        )

    def format_agent_debug(self, mode: str, agent_trace: list[dict], tool_events: list[dict]) -> str:
        lines = [f"Mode: {mode or 'direct_reply'}"]

        if tool_events:
            lines.extend(["", "Tools:"])
            for event in tool_events:
                tool_name = event.get("tool", "tool")
                status = event.get("status", "ok")
                detail = event.get("error") or event.get("detail") or ""
                line = f"- {tool_name}: {status}"
                if detail:
                    line += f" ({detail})"
                lines.append(line)

        if agent_trace:
            lines.extend(["", "Trace:"])
            for item in agent_trace:
                parts = [item.get("step", "step")]
                if item.get("status"):
                    parts.append(str(item["status"]))
                if item.get("tool_name"):
                    parts.append(f"tool={item['tool_name']}")
                if item.get("reason"):
                    parts.append(item["reason"])
                if item.get("error"):
                    parts.append(f"error={item['error']}")
                lines.append("- " + " | ".join(parts))
        else:
            lines.extend(["", "Trace:", "- direct reply with no tool activity"])

        return "\n".join(lines)

    def open_conversation_log(self):
        log_text = self.window._build_combined_log()

        dialog = QDialog(self.window)
        dialog.setWindowTitle("Conversation and debug log")
        dialog.resize(760, 620)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        editor = QPlainTextEdit()
        editor.setReadOnly(True)
        editor.setPlainText(log_text)
        layout.addWidget(editor, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        copy_btn = buttons.addButton("Copy", QDialogButtonBox.ActionRole)
        save_btn = buttons.addButton("Save as...", QDialogButtonBox.ActionRole)
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(editor.toPlainText()))
        save_btn.clicked.connect(lambda: self.window._save_conversation_log(editor.toPlainText()))
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)

        dialog.exec()
