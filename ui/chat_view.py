from pathlib import Path

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QColor, QMouseEvent, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


class ClickableLabel(QLabel):
    clicked = Signal()

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._source_pixmap = QPixmap()

    def set_source_pixmap(self, pixmap: QPixmap) -> None:
        self._source_pixmap = QPixmap(pixmap)

    def source_pixmap(self) -> QPixmap:
        return QPixmap(self._source_pixmap)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


class PreviewDialog(QDialog):
    def __init__(self, title: str, content: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setObjectName("previewDialog")
        self.resize(760, 760)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        header = QLabel(title)
        header.setObjectName("previewTitle")
        layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setWidget(content)
        layout.addWidget(scroll)


class ChatView(QWidget):
    feedback_requested = Signal(str, str, int)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        header = QWidget()
        header.setObjectName("chatHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(6, 0, 6, 0)
        header_layout.setSpacing(10)

        title_wrap = QWidget()
        title_layout = QVBoxLayout(title_wrap)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(2)

        eyebrow = QLabel("Conversation")
        eyebrow.setObjectName("chatEyebrow")
        title = QLabel("Private Exchange")
        title.setObjectName("chatTitle")
        subtitle = QLabel("A calmer, closer thread between you and Nellie.")
        subtitle.setObjectName("chatSubtitle")
        subtitle.setWordWrap(True)

        title_layout.addWidget(eyebrow)
        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)
        header_layout.addWidget(title_wrap, 1)
        layout.addWidget(header)

        surface = QFrame()
        surface.setObjectName("chatSurface")
        shadow = QGraphicsDropShadowEffect(surface)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 7)
        shadow.setColor(QColor(43, 30, 20, 24))
        surface.setGraphicsEffect(shadow)
        surface_layout = QVBoxLayout(surface)
        surface_layout.setContentsMargins(7, 9, 7, 9)

        self.list = QListWidget()
        self.list.setObjectName("chatList")
        self.list.setSpacing(12)
        self.list.setWordWrap(True)
        self.list.setAlternatingRowColors(False)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        surface_layout.addWidget(self.list)
        layout.addWidget(surface, 1)
        self._stream_label: ClickableLabel | None = None
        self._preview_dialogs: list[QDialog] = []

    def add_user(self, text: str) -> None:
        self._add_bubble("You", text, "user")

    def add_ai(self, text: str, user_text: str = "", allow_feedback: bool = False) -> None:
        self._add_bubble(
            "Nellie",
            text,
            "ai",
            feedback_user_text=user_text if allow_feedback else "",
        )

    def add_ai_image(self, image_path: str, caption: str = "") -> None:
        stick_to_bottom = self._should_stick_to_bottom()
        container = QWidget()
        outer = QVBoxLayout(container)
        outer.setContentsMargins(44, 0, 18, 0)

        card = QWidget()
        card.setObjectName("imageCard")
        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel("Nellie shared a moment")
        title.setObjectName("imageCardTitle")
        layout.addWidget(title)

        img_label = ClickableLabel()
        img_label.setObjectName("imageCardImage")
        img_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        img_label.setCursor(Qt.CursorShape.PointingHandCursor)
        img_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        pixmap = QPixmap(str(Path(image_path)))
        if not pixmap.isNull():
            img_label.set_source_pixmap(pixmap)
            self._resize_image_label(img_label)
            img_label.clicked.connect(lambda p=QPixmap(pixmap), c=caption: self._open_image_preview(p, c))
        else:
            img_label.setText(f"[Image unavailable] {image_path}")
        layout.addWidget(img_label)

        if caption:
            caption_label = QLabel(caption)
            caption_label.setObjectName("imageCardCaption")
            caption_label.setWordWrap(True)
            layout.addWidget(caption_label)

        footer = QLabel("from her private album")
        footer.setObjectName("imageCardFooter")
        layout.addWidget(footer)

        outer.addWidget(card)
        container.setProperty("messageRole", "image")

        item = QListWidgetItem()
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        item.setSizeHint(container.sizeHint())
        self.list.addItem(item)
        self.list.setItemWidget(item, container)
        self._schedule_item_refresh(item)
        self._maybe_scroll_to_bottom(stick_to_bottom)

    def add_ai_stream_start(self) -> None:
        stick_to_bottom = self._should_stick_to_bottom()
        container, self._stream_label = self._make_bubble_widget("Nellie", "", "ai", streaming=True)
        item = QListWidgetItem()
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        item.setSizeHint(container.sizeHint())
        self.list.addItem(item)
        self.list.setItemWidget(item, container)
        self._schedule_item_refresh(item)
        self._maybe_scroll_to_bottom(stick_to_bottom)

    def add_ai_stream_chunk(self, chunk: str) -> None:
        if self._stream_label is not None:
            self._stream_label.setText(self._stream_label.text() + chunk)
            self._refresh_stream_item()

    def add_ai_stream_end(self, final_text: str = "") -> None:
        if self._stream_label is None:
            if final_text:
                self.add_ai(final_text)
            return
        if not self._stream_label.text().strip() and final_text:
            self._stream_label.setText(final_text)
        self._refresh_stream_item()
        self._stream_label = None

    def _add_bubble(
        self,
        sender: str,
        text: str,
        role: str,
        feedback_user_text: str = "",
    ) -> None:
        stick_to_bottom = self._should_stick_to_bottom()
        container, _ = self._make_bubble_widget(
            sender,
            text,
            role,
            feedback_user_text=feedback_user_text,
        )
        item = QListWidgetItem()
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
        item.setSizeHint(container.sizeHint())
        self.list.addItem(item)
        self.list.setItemWidget(item, container)
        self._schedule_item_refresh(item)
        self._maybe_scroll_to_bottom(stick_to_bottom)

    def _make_bubble_widget(
        self,
        sender: str,
        text: str,
        role: str,
        streaming: bool = False,
        feedback_user_text: str = "",
    ) -> tuple[QWidget, ClickableLabel]:
        container = QWidget()
        container.setProperty("messageRole", role)
        outer = QVBoxLayout(container)
        align = Qt.AlignmentFlag.AlignRight if role == "user" else Qt.AlignmentFlag.AlignLeft
        self._set_message_margins(outer, role)

        card = QWidget()
        card.setObjectName(f"{role}Bubble")
        card.setMaximumWidth(480)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(17, 14, 17, 15)
        layout.setSpacing(6)

        sender_label = QLabel(sender)
        sender_label.setObjectName(f"{role}BubbleSender")
        layout.addWidget(sender_label, alignment=align)

        body = ClickableLabel(text)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body.setObjectName(f"{role}BubbleBody")
        body.setCursor(Qt.CursorShape.IBeamCursor)
        if streaming:
            body.setObjectName("streamBubbleBody")
        layout.addWidget(body)

        if not streaming and text.strip():
            body.clicked.connect(lambda s=sender, t=text: self._open_text_preview(s, t))

        if role == "ai" and feedback_user_text and text.strip():
            feedback_row = QHBoxLayout()
            feedback_row.setContentsMargins(0, 2, 0, 0)
            feedback_row.setSpacing(6)

            useful_btn = QPushButton("Useful")
            useful_btn.setObjectName("feedbackButton")
            improve_btn = QPushButton("Improve")
            improve_btn.setObjectName("feedbackButton")

            def submit(rating: int) -> None:
                useful_btn.setEnabled(False)
                improve_btn.setEnabled(False)
                self.feedback_requested.emit(feedback_user_text, text, rating)

            useful_btn.clicked.connect(lambda: submit(1))
            improve_btn.clicked.connect(lambda: submit(-1))
            feedback_row.addWidget(useful_btn)
            feedback_row.addWidget(improve_btn)
            feedback_row.addStretch(1)
            layout.addLayout(feedback_row)

        outer.addWidget(card, alignment=align)
        return container, body

    def _refresh_stream_item(self) -> None:
        if self._stream_label is None:
            return
        item = self.list.item(self.list.count() - 1)
        if item is not None:
            self._refresh_item_size(item)
        self._maybe_scroll_to_bottom(True)

    def _schedule_item_refresh(self, item: QListWidgetItem) -> None:
        QTimer.singleShot(0, lambda current=item: self._refresh_item_size(current))

    def _refresh_item_size(self, item: QListWidgetItem) -> None:
        widget = self.list.itemWidget(item)
        if widget is None:
            return
        layout = widget.layout()
        if layout is not None:
            layout.invalidate()
            layout.activate()
        widget.adjustSize()
        item.setSizeHint(widget.sizeHint())

    def _refresh_all_item_sizes(self) -> None:
        for index in range(self.list.count()):
            item = self.list.item(index)
            if item is not None:
                widget = self.list.itemWidget(item)
                if widget is not None:
                    role = str(widget.property("messageRole") or "")
                    outer = widget.layout()
                    if isinstance(outer, QVBoxLayout):
                        self._set_message_margins(outer, role)
                    image = widget.findChild(ClickableLabel, "imageCardImage")
                    if image is not None:
                        self._resize_image_label(image)
                self._refresh_item_size(item)

    def _message_side_margin(self) -> int:
        width = max(1, self.list.viewport().width())
        return max(10, min(72, int(width * 0.16)))

    def _set_message_margins(self, layout: QVBoxLayout, role: str) -> None:
        side = self._message_side_margin()
        edge = 8 if self.list.viewport().width() < 420 else 12
        if role == "user":
            layout.setContentsMargins(side, 0, edge, 0)
        elif role == "ai":
            layout.setContentsMargins(edge, 0, side, 0)
        elif role == "image":
            layout.setContentsMargins(edge, 0, edge, 0)

    def _resize_image_label(self, label: ClickableLabel) -> None:
        source = label.source_pixmap()
        if source.isNull():
            return
        available = max(120, self.list.viewport().width() - 72)
        target_width = min(320, available)
        label.setPixmap(
            source.scaledToWidth(
                target_width,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        QTimer.singleShot(0, self._refresh_all_item_sizes)

    def _should_stick_to_bottom(self) -> bool:
        bar = self.list.verticalScrollBar()
        if bar.maximum() <= 0:
            return True
        return bar.value() >= bar.maximum() - 48

    def _maybe_scroll_to_bottom(self, should_scroll: bool) -> None:
        if should_scroll:
            self.list.scrollToBottom()

    def _open_text_preview(self, sender: str, text: str) -> None:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        body = QLabel(text)
        body.setWordWrap(True)
        body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        body.setObjectName("previewBody")
        layout.addWidget(body)

        self._show_preview(f"{sender} message", content)

    def _open_image_preview(self, pixmap: QPixmap, caption: str) -> None:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        image = QLabel()
        image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        image.setObjectName("previewImage")
        image.setPixmap(
            pixmap.scaled(
                960,
                960,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        layout.addWidget(image)

        if caption:
            label = QLabel(caption)
            label.setWordWrap(True)
            label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            label.setObjectName("previewCaption")
            layout.addWidget(label)

        self._show_preview("Shared image", content)

    def _show_preview(self, title: str, content: QWidget) -> None:
        dialog = PreviewDialog(title, content, self)
        self._preview_dialogs.append(dialog)
        dialog.finished.connect(lambda _result: self._preview_dialogs.remove(dialog) if dialog in self._preview_dialogs else None)
        dialog.exec()

    def clear_messages(self) -> None:
        self.list.clear()
        self._stream_label = None
