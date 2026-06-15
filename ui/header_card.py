from pathlib import Path

from PySide6.QtCore import QSize, QTimer, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QBoxLayout,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.mood_avatar import MoodAvatar


class HeaderCard(QFrame):
    settings_clicked = Signal()

    def __init__(self, moods_dir: str | Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("headerCard")
        self._flash_timer = QTimer(self)
        self._flash_timer.setSingleShot(True)
        self._flash_timer.timeout.connect(self._clear_progression_flash)
        self._stacked_layout: bool | None = None
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(36)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(43, 30, 20, 24))
        self.setGraphicsEffect(shadow)

        self.card_layout = QVBoxLayout(self)
        self.card_layout.setContentsMargins(24, 20, 22, 20)
        self.card_layout.setSpacing(11)

        eyebrow = QLabel("Companion Interface")
        eyebrow.setObjectName("headerEyebrow")
        self.settings_btn = QPushButton("⚙  Settings")
        self.settings_btn.setObjectName("headerSettingsButton")
        self.settings_btn.setMinimumWidth(108)
        self.settings_btn.clicked.connect(self.settings_clicked.emit)

        top_bar = QWidget()
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(0, 0, 0, 0)
        top_bar_layout.setSpacing(10)
        top_bar_layout.addWidget(eyebrow)
        top_bar_layout.addStretch(1)
        top_bar_layout.addWidget(self.settings_btn)
        self.card_layout.addWidget(top_bar)

        title = QLabel("Nellie")
        title.setObjectName("headerTitle")
        subtitle = QLabel("Soft voice, visual moods, and a calmer conversational flow.")
        subtitle.setObjectName("headerSubtitle")
        subtitle.setWordWrap(True)
        self.status_label = QLabel("Voice ready.")
        self.status_label.setObjectName("headerStatus")
        self.status_label.setWordWrap(True)

        self.avatar = MoodAvatar(moods_dir)
        self.avatar.setObjectName("headerPortrait")
        self.avatar.setMinimumWidth(164)
        self.avatar.setMaximumWidth(248)

        intro = QWidget()
        self.intro_layout = QHBoxLayout(intro)
        self.intro_layout.setContentsMargins(0, 0, 0, 0)
        self.intro_layout.setSpacing(20)

        copy = QWidget()
        copy_layout = QVBoxLayout(copy)
        copy_layout.setContentsMargins(0, 0, 0, 0)
        copy_layout.setSpacing(3)
        copy_layout.addWidget(title)
        copy_layout.addWidget(subtitle)
        copy_layout.addWidget(self.status_label)
        copy_layout.addStretch(1)

        self.intro_layout.addWidget(copy, 1)
        self.intro_layout.addWidget(self.avatar, 0, Qt.AlignmentFlag.AlignTop)
        self.card_layout.addWidget(intro)

        meta_row = QWidget()
        meta_row.setObjectName("headerMetaRow")
        meta_layout = QVBoxLayout(meta_row)
        meta_layout.setContentsMargins(0, 5, 0, 0)
        meta_layout.setSpacing(5)
        self.engine_badge = QLabel()
        self.engine_badge.setObjectName("metaBadge")
        self.language_badge = QLabel()
        self.language_badge.setObjectName("metaBadge")
        self.memory_badge = QLabel()
        self.memory_badge.setObjectName("metaBadge")
        self.speech_badge = QLabel()
        self.speech_badge.setObjectName("metaBadge")
        self.mood_badge = QLabel()
        self.mood_badge.setObjectName("metaBadgeAccent")

        for badge in (
            self.engine_badge,
            self.language_badge,
            self.memory_badge,
            self.speech_badge,
            self.mood_badge,
        ):
            badge.setWordWrap(True)

        meta_row_top = QWidget()
        self.meta_row_top_layout = QHBoxLayout(meta_row_top)
        self.meta_row_top_layout.setContentsMargins(0, 0, 0, 0)
        self.meta_row_top_layout.setSpacing(6)
        self.meta_row_top_layout.addWidget(self.engine_badge)
        self.meta_row_top_layout.addWidget(self.language_badge)
        self.meta_row_top_layout.addWidget(self.memory_badge)
        self.meta_row_top_layout.addStretch(1)

        meta_row_bottom = QWidget()
        self.meta_row_bottom_layout = QHBoxLayout(meta_row_bottom)
        self.meta_row_bottom_layout.setContentsMargins(0, 0, 0, 0)
        self.meta_row_bottom_layout.setSpacing(6)
        self.meta_row_bottom_layout.addWidget(self.speech_badge)
        self.meta_row_bottom_layout.addWidget(self.mood_badge)
        self.meta_row_bottom_layout.addStretch(1)

        meta_layout.addWidget(meta_row_top)
        meta_layout.addWidget(meta_row_bottom)
        self.card_layout.addWidget(meta_row)

        self.progress_wrap = QWidget()
        self.progress_wrap.setObjectName("bondProgressWrap")
        progress_layout = QVBoxLayout(self.progress_wrap)
        progress_layout.setContentsMargins(0, 4, 0, 0)
        progress_layout.setSpacing(5)

        top_row = QWidget()
        top_row_layout = QHBoxLayout(top_row)
        top_row_layout.setContentsMargins(0, 0, 0, 0)
        top_row_layout.setSpacing(8)
        self.progress_title = QLabel("Bond Level")
        self.progress_title.setObjectName("bondProgressTitle")
        self.level_badge = QLabel("Lv.1")
        self.level_badge.setObjectName("bondLevelBadge")
        top_row_layout.addWidget(self.progress_title)
        top_row_layout.addStretch(1)
        top_row_layout.addWidget(self.level_badge)
        progress_layout.addWidget(top_row)

        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("bondProgressBar")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        progress_layout.addWidget(self.progress_bar)

        bottom_row = QWidget()
        bottom_row_layout = QHBoxLayout(bottom_row)
        bottom_row_layout.setContentsMargins(0, 0, 0, 0)
        bottom_row_layout.setSpacing(8)
        self.progress_hint = QLabel("Still getting to know each other.")
        self.progress_hint.setObjectName("bondProgressHint")
        self.progress_hint.setWordWrap(True)
        self.progress_next = QLabel("")
        self.progress_next.setObjectName("bondProgressNext")
        self.progress_next.setWordWrap(True)
        bottom_row_layout.addWidget(self.progress_hint, 1)
        bottom_row_layout.addWidget(self.progress_next, 0, Qt.AlignmentFlag.AlignTop)
        progress_layout.addWidget(bottom_row)

        self.xp_burst = QLabel("")
        self.xp_burst.setObjectName("bondXpBurst")
        self.xp_burst.setWordWrap(True)
        self.xp_burst.hide()
        progress_layout.addWidget(self.xp_burst, 0, Qt.AlignmentFlag.AlignLeft)

        self.card_layout.addWidget(self.progress_wrap)
        self._apply_responsive_layout(self.width())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_responsive_layout(event.size().width())

    def minimumSizeHint(self) -> QSize:
        hint = super().minimumSizeHint()
        return QSize(280, hint.height())

    def _apply_responsive_layout(self, width: int) -> None:
        stacked = width < 500
        if stacked != self._stacked_layout:
            direction = (
                QBoxLayout.Direction.TopToBottom
                if stacked
                else QBoxLayout.Direction.LeftToRight
            )
            self.intro_layout.setDirection(direction)
            self.intro_layout.setSpacing(14 if stacked else 20)
            self.intro_layout.setAlignment(
                self.avatar,
                Qt.AlignmentFlag.AlignHCenter if stacked else Qt.AlignmentFlag.AlignTop,
            )
            meta_direction = (
                QBoxLayout.Direction.TopToBottom
                if stacked
                else QBoxLayout.Direction.LeftToRight
            )
            self.meta_row_top_layout.setDirection(meta_direction)
            self.meta_row_bottom_layout.setDirection(meta_direction)
            self.meta_row_top_layout.setSpacing(4 if stacked else 6)
            self.meta_row_bottom_layout.setSpacing(4 if stacked else 6)
            margin = 14 if stacked else 22
            self.card_layout.setContentsMargins(margin, 16 if stacked else 20, margin, 16 if stacked else 20)
            self._stacked_layout = stacked

        portrait_size = max(112, min(224, int(width * (0.42 if stacked else 0.34))))
        avatar_width = max(144, min(248, portrait_size + 28))

        self.avatar.setFixedWidth(avatar_width)
        self.avatar.set_portrait_size(portrait_size)

    def set_status(self, text: str) -> None:
        self.status_label.setText(str(text or "").strip())

    def set_badges(self, engine: str, language: str, memory: str, speech: str, mood: str) -> None:
        self.engine_badge.setText(engine)
        self.language_badge.setText(language)
        self.memory_badge.setText(memory)
        self.speech_badge.setText(speech)
        self.mood_badge.setText(mood)

    def set_avatar_state(self, mood: str, expression: str) -> None:
        self.avatar.set_state(mood, expression)

    def set_progression(
        self,
        title: str,
        level: int,
        progress_percent: int,
        hint: str,
        next_unlock: str = "",
    ) -> None:
        self.progress_title.setText(str(title or "Bond Level"))
        self.level_badge.setText(f"Lv.{max(1, int(level))}")
        self.progress_bar.setValue(max(0, min(100, int(progress_percent))))
        self.progress_hint.setText(str(hint or "").strip())
        self.progress_next.setText(str(next_unlock or "").strip())

    def flash_progression_gain(self) -> None:
        self.progress_wrap.setProperty("xpFlash", True)
        self.level_badge.setProperty("xpFlash", True)
        self.progress_bar.setProperty("xpFlash", True)
        self._repolish_progression()
        self._flash_timer.start(1800)

    def show_xp_burst(self, text: str) -> None:
        burst = str(text or "").strip()
        if not burst:
            self.xp_burst.hide()
            return
        self.xp_burst.setText(burst)
        self.xp_burst.show()
        self.flash_progression_gain()

    def _clear_progression_flash(self) -> None:
        self.progress_wrap.setProperty("xpFlash", False)
        self.level_badge.setProperty("xpFlash", False)
        self.progress_bar.setProperty("xpFlash", False)
        self.xp_burst.hide()
        self._repolish_progression()

    def _repolish_progression(self) -> None:
        for widget in (self.progress_wrap, self.level_badge, self.progress_bar):
            style = widget.style()
            style.unpolish(widget)
            style.polish(widget)
            widget.update()
