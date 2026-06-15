from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class ComposerCard(QFrame):
    def __init__(self, recorder: QWidget, placeholder: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("composerCard")
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(26)
        shadow.setOffset(0, 7)
        shadow.setColor(QColor(43, 30, 20, 28))
        self.setGraphicsEffect(shadow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 15)
        layout.setSpacing(9)

        title = QLabel("Talk to Nellie")
        title.setObjectName("composerTitle")
        hint = QLabel("Enter to send")
        hint.setObjectName("composerHint")

        heading_row = QWidget()
        heading_layout = QHBoxLayout(heading_row)
        heading_layout.setContentsMargins(2, 0, 2, 0)
        heading_layout.setSpacing(8)
        heading_layout.addWidget(title)
        heading_layout.addStretch(1)
        heading_layout.addWidget(hint)
        layout.addWidget(heading_row)

        self.text_input = QLineEdit()
        self.text_input.setObjectName("messageInput")
        self.text_input.setPlaceholderText(placeholder)

        self.send_btn = QPushButton("Send")
        self.send_btn.setObjectName("primaryButton")
        self.send_btn.setMinimumWidth(82)

        input_row = QWidget()
        input_layout = QHBoxLayout(input_row)
        input_layout.setContentsMargins(0, 0, 0, 0)
        input_layout.setSpacing(10)
        input_layout.addWidget(self.text_input, 1)
        input_layout.addWidget(self.send_btn)
        layout.addWidget(input_row)

        self.image_btn = QPushButton("Open Image")
        self.image_btn.setObjectName("secondaryButton")

        actions_row = QWidget()
        actions_layout = QHBoxLayout(actions_row)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(10)
        self.image_btn.setText("Image")
        actions_layout.addWidget(self.image_btn)
        actions_layout.addWidget(recorder, 1)
        layout.addWidget(actions_row)
