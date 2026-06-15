from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QGraphicsOpacityEffect, QLabel, QSizePolicy, QVBoxLayout, QWidget


class MoodAvatar(QWidget):
    MOOD_IMAGE_ALIASES = {
        "neutral": ["neutral", "listening"],
        "happy": ["warm_smile", "smile", "aww"],
        "excited": ["fun_reaction", "lol", "crazy", "surprized"],
        "sensual": ["medium_flirt", "small_flirt", "your_sweet"],
        "thinking": ["intrigued", "wait", "listening"],
        "sceptical": ["what", "no_way", "annoyed"],
        "sad": ["crying", "im_sorry", "bad"],
        "tired": ["bored", "bad", "anxious"],
        "bored": ["bored", "wait"],
        "angry": ["annoyed", "chocked", "what"],
        "anxious": ["anxious", "wait"],
        "sorry": ["im_sorry", "sad"],
        "cute": ["aww", "your_sweet"],
    }
    EXPRESSION_IMAGE_ALIASES = {
        "neutral": ["neutral", "listening"],
        "listening": ["listening", "neutral"],
        "intrigued": ["intrigued", "wait", "listening"],
        "wait": ["wait", "intrigued"],
        "aww": ["aww", "warm_smile", "your_sweet"],
        "warm_smile": ["warm_smile", "smile", "neutral"],
        "smile": ["smile", "warm_smile", "neutral"],
        "your_sweet": ["your_sweet", "small_flirt", "medium_flirt"],
        "small_flirt": ["small_flirt", "your_sweet", "medium_flirt"],
        "medium_flirt": ["medium_flirt", "small_flirt", "your_sweet"],
        "fun_reaction": ["fun_reaction", "lol", "crazy", "surprized"],
        "lol": ["lol", "fun_reaction", "smile"],
        "crazy": ["crazy", "fun_reaction", "surprized"],
        "surprized": ["surprized", "chocked", "what"],
        "chocked": ["chocked", "surprized", "what"],
        "what": ["what", "no_way", "annoyed"],
        "no_way": ["no_way", "what", "surprized"],
        "annoyed": ["annoyed", "what", "no_way"],
        "anxious": ["anxious", "wait", "bad"],
        "crying": ["crying", "im_sorry", "bad"],
        "im_sorry": ["im_sorry", "crying", "bad"],
        "bad": ["bad", "bored", "neutral"],
        "bored": ["bored", "wait", "neutral"],
    }

    def __init__(self, moods_dir: str | Path) -> None:
        super().__init__()
        self.moods_dir = Path(moods_dir)
        self._source_pixmap = QPixmap()
        self.setObjectName("avatarCard")
        self.setProperty("compact", True)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        compact = bool(self.property("compact"))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10 if compact else 16, 10 if compact else 16, 10 if compact else 16, 12 if compact else 16)
        layout.setSpacing(8 if compact else 10)

        top_row = QWidget()
        top_layout = QVBoxLayout(top_row)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(5)

        self.eyebrow_label = QLabel("Current presence")
        self.eyebrow_label.setObjectName("avatarEyebrow")
        self.presence_chip = QLabel("Live portrait")
        self.presence_chip.setObjectName("avatarChip")
        self.presence_chip.setAlignment(Qt.AlignmentFlag.AlignCenter)

        top_layout.addWidget(self.eyebrow_label, alignment=Qt.AlignmentFlag.AlignCenter)
        top_layout.addWidget(self.presence_chip, alignment=Qt.AlignmentFlag.AlignCenter)

        self.image_frame = QWidget()
        self.image_frame.setObjectName("avatarFrame")
        frame_layout = QVBoxLayout(self.image_frame)
        frame_layout.setContentsMargins(6 if compact else 10, 6 if compact else 10, 6 if compact else 10, 6 if compact else 10)
        frame_layout.setSpacing(0)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_label.setMinimumSize(112, 112)
        self.image_label.resize(184 if compact else 208, 184 if compact else 208)
        self.image_label.setObjectName("avatarImage")
        self.image_opacity = QGraphicsOpacityEffect(self.image_label)
        self.image_opacity.setOpacity(1.0)
        self.image_label.setGraphicsEffect(self.image_opacity)
        self.image_anim = QPropertyAnimation(self.image_opacity, b"opacity", self)
        self.image_anim.setDuration(280)
        self.image_anim.setStartValue(0.72)
        self.image_anim.setEndValue(1.0)
        self.image_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        frame_layout.addWidget(self.image_label, alignment=Qt.AlignmentFlag.AlignCenter)

        self.mood_label = QLabel("Neutral")
        self.mood_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.mood_label.setObjectName("avatarMood")

        self.note_label = QLabel("Soft, attentive, and here with you.")
        self.note_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.note_label.setWordWrap(True)
        self.note_label.setObjectName("avatarNote")
        self.note_label.setMaximumWidth(180 if compact else 220)
        self.note_label.setVisible(not compact)

        layout.addWidget(top_row)
        layout.addWidget(self.image_frame, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.mood_label)
        layout.addWidget(self.note_label)
        self.current_mood = "neutral"
        self.current_expression = "neutral"
        self.set_mood("neutral")

    def set_mood(self, mood: str) -> None:
        self.set_state(mood)

    def set_expression(self, expression: str) -> None:
        self.set_state(self.current_mood, expression)

    def set_state(self, mood: str, expression: str | None = None) -> None:
        mood = str(mood or "neutral")
        expression = str(expression or mood or "neutral")
        aliases = list(self.EXPRESSION_IMAGE_ALIASES.get(expression, [expression]))
        aliases.extend(self.MOOD_IMAGE_ALIASES.get(mood, [mood, "neutral"]))
        candidates = []
        for alias in aliases:
            candidates.extend(
                [
                    self.moods_dir / f"{alias}.png",
                    self.moods_dir / f"{alias}.jpg",
                ]
            )
        candidates.extend([self.moods_dir / "neutral.png", self.moods_dir / "neutral.jpg"])
        img = next((path for path in candidates if path.exists()), candidates[-1])
        pixmap = QPixmap(str(img))
        if pixmap.isNull():
            self.image_label.clear()
            self.mood_label.setText(mood.title())
            return
        self.current_mood = mood
        self.current_expression = expression
        self._source_pixmap = pixmap
        self._render_portrait()
        self.presence_chip.setText(expression.replace("_", " ").title())
        if expression and expression != mood:
            self.mood_label.setText(f"{mood.replace('_', ' ').title()} · {expression.replace('_', ' ').title()}")
        else:
            self.mood_label.setText(mood.replace("_", " ").title())
        note = self._mood_note(mood, expression)
        self.note_label.setText(note)
        self.image_frame.setProperty("moodState", mood)
        self.mood_label.setProperty("moodState", mood)
        self.note_label.setProperty("moodState", mood)
        self._refresh_styles()
        self.image_anim.stop()
        self.image_anim.start()
        self.setToolTip(f"Mood: {mood}\nExpression: {expression}\n{note}")

    def set_portrait_size(self, size: int) -> None:
        resolved = max(112, min(224, int(size)))
        if self.image_label.width() == resolved and self.image_label.height() == resolved:
            return
        self.image_label.setFixedSize(resolved, resolved)
        self.note_label.setMaximumWidth(max(160, resolved))
        self._render_portrait()
        self.updateGeometry()

    def _render_portrait(self) -> None:
        if self._source_pixmap.isNull():
            return
        self.image_label.setPixmap(
            self._portrait_avatar(
                self._source_pixmap,
                self.image_label.width(),
                self.image_label.height(),
            )
        )

    def _refresh_styles(self) -> None:
        for widget in (self.image_frame, self.mood_label, self.note_label):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()

    def _mood_note(self, mood: str, expression: str | None = None) -> str:
        expression_notes = {
            "listening": "Locked in, attentive, and following every word.",
            "intrigued": "Curious, alert, and leaning into the moment.",
            "wait": "Holding the beat, expecting what comes next.",
            "aww": "Softened, touched, and openly affectionate.",
            "warm_smile": "Warm, calm, and easy to settle into.",
            "smile": "Relaxed, bright, and easygoing.",
            "your_sweet": "Tender, close, and clearly charmed.",
            "small_flirt": "Lightly teasing, warm, and a little playful.",
            "medium_flirt": "More forward, affectionate, and openly drawn in.",
            "fun_reaction": "Animated, reactive, and enjoying the exchange.",
            "lol": "Amused and openly entertained.",
            "crazy": "Unfiltered, lively, and a little chaotic.",
            "surprized": "Caught off guard and visibly reactive.",
            "chocked": "Sharply startled and trying to catch up.",
            "what": "Questioning, tilted, and not fully buying it yet.",
            "no_way": "Disbelieving and pushing back on what she heard.",
            "annoyed": "Sharpened at the edges and clearly irritated.",
            "anxious": "A little tense and looking for reassurance.",
            "crying": "Hurting, delicate, and emotionally exposed.",
            "im_sorry": "Trying to soften the moment and make it right.",
            "bad": "Low, unsettled, and not doing great.",
            "bored": "Restless and waiting for something with spark.",
        }
        if expression and expression in expression_notes:
            return expression_notes[expression]
        notes = {
            "neutral": "Soft, attentive, and here with you.",
            "happy": "Bright, warm, and easy to melt into.",
            "excited": "More animated, reactive, and hard to miss.",
            "sensual": "Warm, close, and openly affectionate.",
            "thinking": "Curious, reflective, and clearly following along.",
            "sceptical": "Questioning, unconvinced, and watching your angle.",
            "sad": "Quieter, softer, and a little fragile.",
            "tired": "Gentle, worn down, and slower around the edges.",
            "bored": "Restless and waiting for something interesting.",
            "angry": "Sharper than usual, holding some heat.",
            "anxious": "A touch tense, uncertain, and looking for reassurance.",
            "sorry": "Trying to soften things and make them right again.",
        }
        return notes.get(mood, "Soft, attentive, and here with you.")

    def _portrait_avatar(self, pixmap: QPixmap, width: int, height: int) -> QPixmap:
        inset = 5
        available_width = max(1, width - (inset * 2))
        available_height = max(1, height - (inset * 2))
        scaled = pixmap.scaled(
            available_width,
            available_height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        result = QPixmap(width, height)
        result.fill(Qt.GlobalColor.transparent)

        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

        clip_path = QPainterPath()
        clip_path.addRoundedRect(inset, inset, available_width, available_height, 22, 22)
        painter.setClipPath(clip_path)
        painter.fillPath(clip_path, QColor(255, 255, 255, 12))
        x = (width - scaled.width()) // 2
        y = (height - scaled.height()) // 2
        painter.drawPixmap(x, y, scaled)
        painter.setClipping(False)

        pen = QPen(QColor(255, 255, 255, 62), 1.25)
        painter.setPen(pen)
        painter.drawRoundedRect(inset, inset, available_width, available_height, 22, 22)
        painter.end()
        return result
