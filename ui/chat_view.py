from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class ChatBubble(QFrame):
    def __init__(self, speaker: str, text: str, is_user: bool, role: str | None = None, image_path: str | None = None):
        super().__init__()
        bubble_role = role or ("user" if is_user else "assistant")
        self._image_path = image_path or ""

        self.setObjectName("chatBubble")
        self.setProperty("role", bubble_role)
        self.setProperty("streaming", False)

        layout = QVBoxLayout(self)
        if bubble_role.startswith("system"):
            layout.setContentsMargins(14, 10, 14, 10)
            layout.setSpacing(5)
        else:
            layout.setContentsMargins(20, 16, 20, 16)
            layout.setSpacing(8)

        self.speaker_label = QLabel(speaker)
        self.speaker_label.setObjectName("speakerLabel")
        self.speaker_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.speaker_label.setWordWrap(False)
        self.speaker_label.setContentsMargins(0, 0, 0, 0)

        self.meta_label = QLabel(self._meta_text_for_role(bubble_role))
        self.meta_label.setObjectName("bubbleMeta")
        self.meta_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.meta_label.setWordWrap(False)
        self.meta_label.setContentsMargins(0, 0, 0, 0)

        self.text_label = QLabel(text)
        self.text_label.setObjectName("bubbleText")
        self.text_label.setTextFormat(Qt.PlainText)
        self.text_label.setWordWrap(True)
        self.text_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.text_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self.text_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.text_label.setContentsMargins(0, 0, 0, 0)
        self.text_label.setMinimumWidth(72)
        self.text_label.setMinimumHeight(self.text_label.fontMetrics().height() + 10)
        self.image_label = QLabel()
        self.image_label.setObjectName("bubbleImage")
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setVisible(False)
        self.image_label.setMinimumHeight(0)
        self.image_label.setMaximumHeight(280)

        layout.addWidget(self.speaker_label)
        layout.addWidget(self.meta_label)
        layout.addWidget(self.image_label)
        layout.addWidget(self.text_label)
        if self._image_path:
            self.set_image(self._image_path)

    def _meta_text_for_role(self, bubble_role: str) -> str:
        if bubble_role == "assistant":
            return "Presence reply"
        if bubble_role == "user":
            return "User signal"
        if bubble_role == "system-plan":
            return "Plan trace"
        if bubble_role == "system-ok":
            return "System ok"
        if bubble_role == "system-warning":
            return "System warning"
        if bubble_role == "system-danger":
            return "System danger"
        return "System note"

    def set_text(self, text: str):
        self.text_label.setText(text)
        self.layout().activate()
        self.text_label.adjustSize()
        self.adjustSize()

    def set_image(self, image_path: str):
        self._image_path = image_path or ""
        if not self._image_path:
            self.image_label.clear()
            self.image_label.setVisible(False)
            return
        pixmap = QPixmap(self._image_path)
        if pixmap.isNull():
            self.image_label.clear()
            self.image_label.setVisible(False)
            return
        scaled = pixmap.scaled(
            self.maximumWidth() - 24 if self.maximumWidth() > 40 else 260,
            260,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.image_label.setPixmap(scaled)
        self.image_label.setVisible(True)
        self.layout().activate()
        self.adjustSize()

    def set_streaming(self, streaming: bool):
        self.setProperty("streaming", streaming)
        self.style().unpolish(self)
        self.style().polish(self)


class ChatRow(QWidget):
    def __init__(self, speaker: str, text: str, is_user: bool, role: str | None = None, image_path: str | None = None):
        super().__init__()
        self._is_user = is_user
        self._role = role or ("user" if is_user else "assistant")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(0)

        self.bubble = ChatBubble(speaker, text, is_user, role=role, image_path=image_path)
        self.bubble.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self.set_bubble_width(480)

        if is_user:
            layout.addStretch(1)
            layout.addWidget(self.bubble, 0, Qt.AlignRight)
        else:
            layout.addWidget(self.bubble, 0, Qt.AlignLeft)
            layout.addStretch(1)

    def set_bubble_width(self, viewport_width: int):
        if self._role.startswith("system"):
            width = max(180, min(420, int(viewport_width * 0.56)))
            self.bubble.setMinimumWidth(150)
            self.bubble.setMaximumWidth(width)
            if self.bubble.image_label.isVisible():
                self.bubble.set_image(self.bubble._image_path)
            self.bubble.layout().activate()
            self.bubble.adjustSize()
            return

        width = max(220, min(620, int(viewport_width * 0.72)))
        min_width = 190 if self._is_user else 200
        self.bubble.setMinimumWidth(min_width)
        self.bubble.setMaximumWidth(width)
        if self.bubble.image_label.isVisible():
            self.bubble.set_image(self.bubble._image_path)
        self.bubble.layout().activate()
        self.bubble.adjustSize()


class ChatView(QWidget):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.list = QListWidget()
        self.list.setObjectName("chatList")
        self.list.setFrameShape(QFrame.NoFrame)
        self.list.setWordWrap(True)
        self.list.setAlternatingRowColors(False)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.list.setSpacing(12)
        layout.addWidget(self.list)

        self.empty_state = QLabel(
            "<span style=\"font-size:11px; letter-spacing:2px; font-weight:700; text-transform:uppercase;\">Private Channel</span><br>"
            "<span style=\"font-size:19px; font-weight:700;\">Nellie is listening for something worth answering.</span><br>"
            "<span style=\"font-size:13px;\">Say hello, ask something strange, or start softly. The room gets warmer once you do.</span>"
        )
        self.empty_state.setObjectName("chatEmptyState")
        self.empty_state.setAlignment(Qt.AlignCenter)
        self.empty_state.setWordWrap(True)
        self.empty_state.setTextFormat(Qt.RichText)
        self.empty_state.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(self.empty_state, 0, Qt.AlignCenter)

        self._stream_item = None
        self._stream_row = None
        self._rows = []
        self._row_animations = []
        self._sync_empty_state()

    def add_user(self, text: str):
        self._add_row("You", text, is_user=True, role="user")

    def add_ai(self, text: str):
        self._add_row("Nellie", text, is_user=False, role="assistant")

    def add_ai_image(self, text: str, image_path: str):
        self._add_row("Nellie", text, is_user=False, role="assistant", image_path=image_path)

    def add_system(self, text: str, role: str = "system"):
        self._add_row("System", text, is_user=False, role=role)

    def add_ai_stream_start(self):
        item = QListWidgetItem()
        row = ChatRow("Nellie", "", is_user=False)
        row.set_bubble_width(self.list.viewport().width())
        row.bubble.set_streaming(True)
        row.layout().activate()
        item.setSizeHint(row.sizeHint())
        self.list.addItem(item)
        self.list.setItemWidget(item, row)
        self.list.scrollToBottom()
        self._stream_item = item
        self._stream_row = row
        self._rows.append((item, row))
        self._animate_row(row)
        self._sync_empty_state()

    def add_ai_stream_chunk(self, chunk: str):
        if self._stream_row is not None:
            current = self._stream_row.bubble.text_label.text()
            self._stream_row.bubble.set_text(current + chunk)
            self._stream_item.setSizeHint(self._stream_row.sizeHint())
            self.list.scrollToBottom()

    def set_ai_stream_text(self, text: str):
        if self._stream_row is not None:
            self._stream_row.bubble.set_text(text)
            self._stream_item.setSizeHint(self._stream_row.sizeHint())
            self.list.scrollToBottom()

    def clear_messages(self):
        self.list.clear()
        self._stream_item = None
        self._stream_row = None
        self._rows.clear()
        self._row_animations.clear()
        self._sync_empty_state()

    def add_ai_stream_end(self):
        if self._stream_row is not None:
            self._stream_row.bubble.set_streaming(False)
        self._stream_item = None
        self._stream_row = None

    def _add_row(self, speaker: str, text: str, is_user: bool, role: str | None = None, image_path: str | None = None):
        item = QListWidgetItem()
        row = ChatRow(speaker, text, is_user=is_user, role=role, image_path=image_path)
        row.set_bubble_width(self.list.viewport().width())
        row.layout().activate()
        item.setSizeHint(row.sizeHint())
        self.list.addItem(item)
        self.list.setItemWidget(item, row)
        self.list.scrollToBottom()
        self._rows.append((item, row))
        self._animate_row(row)
        self._sync_empty_state()

    def _animate_row(self, row: ChatRow):
        effect = QGraphicsOpacityEffect(row)
        effect.setOpacity(0.0)
        row.setGraphicsEffect(effect)

        animation = QPropertyAnimation(effect, b"opacity", row)
        animation.setDuration(220)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.OutCubic)
        animation.finished.connect(lambda e=effect, r=row: r.setGraphicsEffect(None))
        animation.finished.connect(lambda a=animation: self._forget_animation(a))
        self._row_animations.append(animation)
        animation.start()

    def _forget_animation(self, animation):
        if animation in self._row_animations:
            self._row_animations.remove(animation)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh_row_widths()

    def _refresh_row_widths(self):
        viewport_width = self.list.viewport().width()
        for item, row in self._rows:
            row.set_bubble_width(viewport_width)
            row.layout().activate()
            item.setSizeHint(row.sizeHint())

    def _sync_empty_state(self):
        self.empty_state.setVisible(self.list.count() == 0)
