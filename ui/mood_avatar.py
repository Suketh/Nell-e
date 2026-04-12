import math
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import (
    QColor,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QRadialGradient,
)
from PySide6.QtWidgets import QLabel


class MoodAvatar(QLabel):
    MOOD_ALIASES = {
        "curious": "thoughtful",
        "calm": "neutral",
        "content": "happy",
        "confused": "thoughtful",
        "upset": "sad",
        "frustrated": "annoyed",
        "sleepy": "tired",
    }
    MOOD_GLOWS = {
        "happy": QColor(255, 204, 146, 92),
        "neutral": QColor(245, 219, 181, 76),
        "thoughtful": QColor(212, 182, 255, 82),
        "sad": QColor(161, 186, 230, 78),
        "annoyed": QColor(255, 171, 120, 78),
        "angry": QColor(255, 122, 102, 92),
        "tired": QColor(184, 164, 224, 72),
    }

    def __init__(self, moods_dir):
        super().__init__()
        self.moods_dir = Path(moods_dir)
        self.setFixedSize(132, 132)
        self.setAlignment(Qt.AlignCenter)
        self._current_mood = "neutral"
        self._source_pixmap = QPixmap()
        self._activity_state = "idle"
        self._animation_phase = 0.0
        self._animation_timer = QTimer(self)
        self._animation_timer.setInterval(48)
        self._animation_timer.timeout.connect(self._advance_animation)
        self.set_mood("neutral")

    def normalize_mood(self, mood: str) -> str:
        mood = (mood or "neutral").strip().lower()
        return self.MOOD_ALIASES.get(mood, mood)

    def set_mood(self, mood: str):
        mood = self.normalize_mood(mood)
        self._current_mood = mood
        img = self.moods_dir / f"{mood}.png"
        if not img.exists():
            img = self.moods_dir / "neutral.png"
        pixmap = QPixmap(str(img))
        if pixmap.isNull():
            return
        self._source_pixmap = pixmap
        self._refresh_pixmap()

    def set_activity_state(self, state: str):
        normalized = (state or "idle").strip().lower()
        if normalized not in {"idle", "listening", "thinking", "speaking"}:
            normalized = "idle"
        if normalized == self._activity_state:
            return
        self._activity_state = normalized
        if normalized == "idle":
            self._animation_timer.stop()
            self._animation_phase = 0.0
        else:
            if not self._animation_timer.isActive():
                self._animation_timer.start()
        self._refresh_pixmap()

    def _advance_animation(self):
        self._animation_phase = (self._animation_phase + 0.16) % (math.pi * 2)
        self._refresh_pixmap()

    def _refresh_pixmap(self):
        if self._source_pixmap.isNull():
            return
        self.setPixmap(self._styled_pixmap(self._source_pixmap))

    def _styled_pixmap(self, pixmap: QPixmap) -> QPixmap:
        scaled = pixmap.scaled(
            self.width(),
            self.height(),
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation,
        )
        styled = QPixmap(self.size())
        styled.fill(Qt.transparent)

        painter = QPainter(styled)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)

        clip_path = QPainterPath()
        inset = 4
        clip_path.addEllipse(inset, inset, self.width() - inset * 2, self.height() - inset * 2)
        painter.setClipPath(clip_path)
        painter.drawPixmap(0, 0, scaled)

        # Glam highlight for a warmer, more luminous portrait finish.
        highlight = QLinearGradient(12, 6, self.width() * 0.72, self.height() * 0.82)
        highlight.setColorAt(0.0, QColor(255, 243, 227, 78))
        highlight.setColorAt(0.22, QColor(255, 228, 205, 42))
        highlight.setColorAt(0.48, QColor(255, 244, 230, 18))
        highlight.setColorAt(1.0, QColor(255, 244, 230, 0))
        painter.fillPath(clip_path, highlight)

        # A second soft bloom on the cheek line keeps the portrait feeling glossy.
        bloom = QRadialGradient(
            self.width() * 0.34,
            self.height() * 0.28,
            self.width() * 0.38,
        )
        bloom.setColorAt(0.0, QColor(255, 226, 196, 34))
        bloom.setColorAt(0.55, QColor(255, 226, 196, 12))
        bloom.setColorAt(1.0, QColor(255, 226, 196, 0))
        painter.fillPath(clip_path, bloom)

        # Subtle vignette to make the portrait feel more art directed.
        vignette = QRadialGradient(
            self.width() * 0.5,
            self.height() * 0.52,
            self.width() * 0.58,
        )
        vignette.setColorAt(0.58, QColor(0, 0, 0, 0))
        vignette.setColorAt(1.0, QColor(12, 7, 9, 88))
        painter.fillPath(clip_path, vignette)

        painter.setClipping(False)

        halo_color = self.MOOD_GLOWS.get(self._current_mood, QColor(245, 219, 181, 76))
        halo_strength = self._activity_multiplier()
        halo = QRadialGradient(
            self.width() * 0.5,
            self.height() * 0.5,
            self.width() * 0.62,
        )
        halo.setColorAt(0.74, QColor(0, 0, 0, 0))
        halo.setColorAt(1.0, QColor(halo_color.red(), halo_color.green(), halo_color.blue(), min(255, int(halo_color.alpha() * halo_strength))))
        painter.setPen(Qt.NoPen)
        painter.setBrush(halo)
        painter.drawEllipse(1, 1, self.width() - 2, self.height() - 2)

        glow_pen = QPen(QColor(255, 232, 199, min(255, int(26 * halo_strength))), 4.5)
        painter.setPen(glow_pen)
        painter.drawEllipse(5, 5, self.width() - 10, self.height() - 10)

        outer_pen = QPen(QColor(255, 244, 230, min(255, int(92 * halo_strength))), 1.5)
        painter.setPen(outer_pen)
        painter.drawEllipse(3, 3, self.width() - 6, self.height() - 6)

        inner_pen = QPen(QColor(255, 224, 190, min(255, int(44 * halo_strength))), 1.0)
        painter.setPen(inner_pen)
        painter.drawEllipse(8, 8, self.width() - 16, self.height() - 16)

        painter.end()
        return styled

    def _activity_multiplier(self) -> float:
        if self._activity_state == "listening":
            return 1.15 + 0.55 * ((math.sin(self._animation_phase * 1.7) + 1.0) / 2.0)
        if self._activity_state == "thinking":
            return 1.05 + 0.28 * ((math.sin(self._animation_phase) + 1.0) / 2.0)
        if self._activity_state == "speaking":
            return 1.2 + 0.7 * ((math.sin(self._animation_phase * 2.4) + 1.0) / 2.0)
        return 1.0
