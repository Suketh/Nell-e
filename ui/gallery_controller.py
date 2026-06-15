from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QLabel,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class DesktopGalleryController:
    def __init__(self, window):
        self.window = window

    @property
    def conversation(self):
        return self.window.conversation

    def open_unlocked_gallery(self):
        entries = []
        catalog = []
        progress = {"xp": 0, "level": 1, "stage": "Anonymous"}
        if hasattr(self.conversation, "get_unlocked_gallery"):
            try:
                entries = list(self.conversation.get_unlocked_gallery() or [])
            except Exception as exc:
                QMessageBox.warning(
                    self.window,
                    "Gallery unavailable",
                    f"Could not load the unlocked gallery.\n\n{exc}",
                )
                return
        if hasattr(self.conversation, "get_gallery_catalog"):
            try:
                catalog = list(self.conversation.get_gallery_catalog() or [])
            except Exception:
                catalog = []
        if hasattr(self.conversation, "get_progress_state"):
            try:
                progress = dict(self.conversation.get_progress_state() or progress)
            except Exception:
                progress = {"xp": 0, "level": 1, "stage": "Anonymous"}

        dialog = QDialog(self.window)
        dialog.setWindowTitle("Unlocked gallery")
        dialog.resize(860, 640)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        progress_label = QLabel(
            f"Level: <b>{int(progress.get('level', 1) or 1)}</b> • "
            f"XP: <b>{int(progress.get('xp', 0) or 0)}</b> • "
            f"Stage: <b>{progress.get('stage', 'Anonymous')}</b>"
        )
        progress_label.setTextFormat(Qt.RichText)
        layout.addWidget(progress_label)

        gallery_items = catalog or entries
        if not gallery_items:
            empty = QLabel("No images unlocked yet. Let Nellie send you a few status shots first.")
            empty.setWordWrap(True)
            empty.setAlignment(Qt.AlignCenter)
            layout.addWidget(empty, 1)
        else:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.NoFrame)
            container = QWidget()
            grid = QGridLayout(container)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(12)
            grid.setVerticalSpacing(12)

            for idx, entry in enumerate(gallery_items):
                card = QFrame()
                card.setObjectName("galleryCard")
                card_layout = QVBoxLayout(card)
                card_layout.setContentsMargins(10, 10, 10, 10)
                card_layout.setSpacing(8)

                image_label = QLabel()
                image_label.setAlignment(Qt.AlignCenter)
                if entry.get("unlocked", True):
                    pixmap = QPixmap(entry["image_path"])
                    if not pixmap.isNull():
                        image_label.setPixmap(
                            pixmap.scaled(220, 220, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        )
                else:
                    image_label.setText("Locked")
                    image_label.setMinimumHeight(180)
                title = QLabel(str(entry.get("title", "") or entry.get("filename", "image")))
                title.setObjectName("galleryCardTitle")
                title.setWordWrap(True)
                rarity = str(entry.get("rarity", "common") or "common").title()
                level_min = int(entry.get("level_min", 1) or 1)
                unlocked = bool(entry.get("unlocked", True))
                if unlocked:
                    caption_text = entry.get("caption", "") or "Unlocked."
                    reason_text = str(entry.get("reason_text", "") or "").strip()
                    if reason_text:
                        caption_text = f"{caption_text}\n{reason_text}"
                    meta_text = f"{rarity} • unlocked"
                else:
                    caption_text = f"Unlocks at level {level_min}."
                    meta_text = f"{rarity} • locked"
                meta = QLabel(meta_text)
                meta.setObjectName("galleryCardMeta")
                caption = QLabel(caption_text)
                caption.setObjectName("galleryCardCaption")
                caption.setWordWrap(True)

                card_layout.addWidget(image_label, 0, Qt.AlignCenter)
                card_layout.addWidget(title)
                card_layout.addWidget(meta)
                card_layout.addWidget(caption)

                row = idx // 3
                col = idx % 3
                grid.addWidget(card, row, col)

            scroll.setWidget(container)
            layout.addWidget(scroll, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)
        dialog.exec()
        self.clear_gallery_unlock_marker()

    def mark_gallery_unlock(self):
        self.window._new_gallery_unlocks += 1
        self.refresh_gallery_button()

    def clear_gallery_unlock_marker(self):
        if self.window._new_gallery_unlocks <= 0:
            return
        self.window._new_gallery_unlocks = 0
        self.refresh_gallery_button()

    def refresh_gallery_button(self):
        progress = {"stage": "Anonymous"}
        try:
            if hasattr(self.conversation, "get_progress_state"):
                progress = dict(self.conversation.get_progress_state() or progress)
        except Exception:
            progress = {"stage": "Anonymous"}
        stage = str(progress.get("stage", "Anonymous") or "Anonymous")
        stage_label = {
            "Anonymous": "private",
            "Curious": "opening",
            "Warm": "warmer",
            "Flirted": "closer",
            "Close": "intimate",
            "Magnetic": "magnetic",
        }.get(stage, "private")
        if self.window._new_gallery_unlocks > 0:
            suffix = "1 new" if self.window._new_gallery_unlocks == 1 else f"{self.window._new_gallery_unlocks} new"
            self.window.gallery_btn.setText(f"Gallery • {suffix}")
            self.window.gallery_icon_btn.setToolTip(
                f"Open Nellie's gallery. {self.window._new_gallery_unlocks} new unlock and a {stage_label} overall tone."
            )
        else:
            self.window.gallery_btn.setText(f"Gallery • {stage_label}")
            self.window.gallery_icon_btn.setToolTip(
                f"Open Nellie's gallery. Current relationship tone: {stage_label}."
            )

    def relationship_ui_copy(self, stage: str) -> dict:
        stage_name = str(stage or "Anonymous").strip()
        mapping = {
            "Anonymous": {
                "eyebrow": "QUIET HOURS",
                "subtitle": "Private, observant, and still deciding how much of herself to show.",
                "header": "Relationship",
                "hint_prefix": "Nellie is still guarded. Consistency, warmth, and shared interests matter most here.",
            },
            "Curious": {
                "eyebrow": "CURIOUS STATIC",
                "subtitle": "She is noticing patterns now, and starting to lean in instead of only listening.",
                "header": "Relationship",
                "hint_prefix": "Nellie is opening up a little. She notices continuity and starts following your threads more closely.",
            },
            "Warm": {
                "eyebrow": "WARM SIGNAL",
                "subtitle": "Less guarded, more present, and starting to feel genuinely familiar with you.",
                "header": "Relationship",
                "hint_prefix": "Nellie is warmer now. Shared details and thoughtful conversation begin to stick harder.",
            },
            "Flirted": {
                "eyebrow": "AFTER HOURS",
                "subtitle": "She is clearly more playful now, and not pretending she does not feel the chemistry.",
                "header": "Connection",
                "hint_prefix": "Nellie is openly more playful here. She can take a little more initiative and let more personality through.",
            },
            "Close": {
                "eyebrow": "CLOSER THAN BEFORE",
                "subtitle": "She sounds like someone who remembers you on purpose, not just by chance.",
                "header": "Connection",
                "hint_prefix": "Nellie trusts the bond more here. Expect more continuity, more tailored replies, and more personal unlocks.",
            },
            "Magnetic": {
                "eyebrow": "MIDNIGHT CURRENT",
                "subtitle": "Confident, invested, and very aware of the effect you have on each other.",
                "header": "Connection",
                "hint_prefix": "Nellie is fully in her stride here. The tone can get intimate, confident, and much more tailored.",
            },
        }
        return mapping.get(stage_name, mapping["Anonymous"])

    def format_gallery_unlock_title(self, filename: str) -> str:
        stem = Path(str(filename or "")).stem.replace("_", " ").strip()
        return stem.title() if stem else "New image"

    def set_affection_tone(self, level: str):
        tone_map = {
            "anonymous": "strangers",
            "curious": "curious",
            "warm": "warm",
            "flirted": "close",
            "close": "close",
            "magnetic": "magnetic",
        }
        tone = tone_map.get(str(level or "").strip().lower(), "strangers")
        for widget in (self.window.affection_card, self.window.affection_progress):
            widget.setProperty("affectionTone", tone)
            widget.style().unpolish(widget)
            widget.style().polish(widget)

    def animate_affection_glow(self):
        effect = getattr(self.window, "_depth_targets", {}).get("affection")
        if effect is None:
            return
        if self.window._affection_glow_grow is not None and self.window._affection_glow_grow.state():
            self.window._affection_glow_grow.stop()
        if self.window._affection_glow_fade is not None and self.window._affection_glow_fade.state():
            self.window._affection_glow_fade.stop()

        base_blur = 30.0
        peak_blur = 48.0
        self.window._affection_glow_grow = QPropertyAnimation(effect, b"blurRadius", self.window)
        self.window._affection_glow_grow.setDuration(230)
        self.window._affection_glow_grow.setStartValue(base_blur)
        self.window._affection_glow_grow.setEndValue(peak_blur)
        self.window._affection_glow_grow.setEasingCurve(QEasingCurve.OutCubic)

        self.window._affection_glow_fade = QPropertyAnimation(effect, b"blurRadius", self.window)
        self.window._affection_glow_fade.setDuration(360)
        self.window._affection_glow_fade.setStartValue(peak_blur)
        self.window._affection_glow_fade.setEndValue(base_blur)
        self.window._affection_glow_fade.setEasingCurve(QEasingCurve.OutCubic)
        self.window._affection_glow_grow.finished.connect(self.window._affection_glow_fade.start)
        self.window._affection_glow_grow.start()

    def refresh_affection_progress(self):
        progress = {"xp": 0, "level": 1, "stage": "Anonymous", "xp_to_next_level": 0, "next_tool_unlock": None}
        catalog = []
        try:
            if hasattr(self.conversation, "get_progress_state"):
                progress = dict(self.conversation.get_progress_state() or progress)
            if hasattr(self.conversation, "get_gallery_catalog"):
                catalog = list(self.conversation.get_gallery_catalog() or [])
        except Exception:
            progress = {"xp": 0, "level": 1, "stage": "Anonymous", "xp_to_next_level": 0, "next_tool_unlock": None}
            catalog = []

        xp = int(progress.get("xp", 0) or 0)
        level = int(progress.get("level", 1) or 1)
        stage = str(progress.get("stage", "Anonymous") or "Anonymous")
        xp_into_level = int(progress.get("xp_into_level", 0) or 0)
        xp_for_next_level = int(progress.get("xp_for_next_level", 0) or 0)
        xp_to_next_level = int(progress.get("xp_to_next_level", 0) or 0)
        next_tool = progress.get("next_tool_unlock") or None
        ui_copy = self.relationship_ui_copy(stage)
        self.window.eyebrow_label.setText(ui_copy["eyebrow"])
        self.window.subtitle_label.setText(ui_copy["subtitle"])
        self.window.affection_header.setText(ui_copy["header"])
        level_thresholds = list(
            getattr(
                self.conversation,
                "RELATIONSHIP_STAGES",
                [(1, "Anonymous"), (6, "Curious"), (16, "Warm"), (32, "Flirted"), (54, "Close"), (80, "Magnetic")],
            )
        )
        next_locked = next((item for item in catalog if not bool(item.get("unlocked", False))), None)
        if next_locked is not None:
            next_requirement = int(next_locked.get("level_min", 1) or 1)
            progress_value = 100 if xp_for_next_level <= 0 else int(
                max(0, min(100, (xp_into_level / max(1, xp_for_next_level)) * 100))
            )
            title = self.format_gallery_unlock_title(str(next_locked.get("filename", "") or ""))
            rarity = str(next_locked.get("rarity", "common") or "common").title()
            self.window.affection_level_label.setText(f"Level {level} • {stage} • {xp} XP")
            next_tool_text = ""
            if isinstance(next_tool, dict) and next_tool.get("label"):
                next_tool_text = (
                    f" Next function: <b>{next_tool['label']}</b> at level "
                    f"{int(next_tool.get('level', level) or level)}."
                )
            self.window.affection_hint.setText(
                f"{ui_copy['hint_prefix']} Next gallery reward: <b>{title}</b> at level {next_requirement}. "
                f"You need {max(0, next_requirement - level)} more levels and {xp_to_next_level} XP to level up. "
                f"{rarity} unlock.{next_tool_text}"
            )
            self.window.affection_hint.setTextFormat(Qt.RichText)
        else:
            progress_value = 100 if xp_for_next_level <= 0 else int(
                max(0, min(100, (xp_into_level / max(1, xp_for_next_level)) * 100))
            )
            self.window.affection_level_label.setText(f"Level {level} • {stage} • {xp} XP")
            self.window.affection_hint.setText(
                f"{ui_copy['hint_prefix']} The gallery is fully open. Further levels mainly deepen Nellie's persona "
                "and unlock more capable agent behavior."
            )
            self.window.affection_hint.setTextFormat(Qt.PlainText)

        previous_value = self.window._last_affection_progress_value
        previous_level = self.window._last_affection_level
        self.set_affection_tone(stage)
        self.window.affection_progress.setValue(progress_value)
        self.window.affection_scale.setText(self.build_affection_scale_html(level_thresholds, level, stage))
        self.refresh_gallery_button()
        if progress_value > previous_value or str(stage or "") != str(previous_level or ""):
            self.animate_affection_glow()
        self.window._last_affection_progress_value = progress_value
        self.window._last_affection_level = stage

    def build_affection_scale_html(self, level_thresholds: list[tuple[int, str]], score: int, current_level: str) -> str:
        safe_current = str(current_level or "").strip().lower()
        chips = []
        for threshold, name in level_thresholds:
            is_active = score >= int(threshold)
            is_current = str(name or "").strip().lower() == safe_current
            background = (
                "rgba(255,255,255,0.14)"
                if is_current
                else ("rgba(255,255,255,0.09)" if is_active else "rgba(255,255,255,0.03)")
            )
            border = "rgba(255,255,255,0.16)" if is_current else "rgba(255,255,255,0.07)"
            color = "#ffffff" if is_current else ("#f0debf" if is_active else "#b8a78d")
            chips.append(
                f"<span style=\"background:{background}; color:{color}; border:1px solid {border}; "
                "border-radius:9px; padding:2px 7px; margin-right:4px; font-size:10px; font-weight:800;\">"
                f"{name} <span style=\"opacity:0.75;\">{threshold}</span></span>"
            )
        if len(chips) <= 3:
            return " ".join(chips)
        first_row = " ".join(chips[:3])
        second_row = " ".join(chips[3:])
        return f"{first_row}<br>{second_row}"
