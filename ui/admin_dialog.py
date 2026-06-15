from pathlib import Path

from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)


class AdminDialog(QDialog):
    def __init__(self, log_path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.log_path = log_path
        self.setWindowTitle("Admin Monitor")
        self.setMinimumSize(760, 520)
        self.setObjectName("settingsDialog")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        title = QLabel("Temporary diagnostics")
        title.setObjectName("settingsTitle")
        subtitle = QLabel(f"Session log: {self.log_path}")
        subtitle.setObjectName("settingsSubtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.setObjectName("previewBody")
        layout.addWidget(self.output, 1)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 4, 0, 0)
        footer.setSpacing(8)

        self.copy_btn = QPushButton("Copy Log")
        self.copy_btn.setObjectName("secondaryButton")
        self.copy_btn.clicked.connect(self.copy_log)
        footer.addWidget(self.copy_btn)

        self.clear_btn = QPushButton("Clear View")
        self.clear_btn.setObjectName("secondaryButton")
        footer.addWidget(self.clear_btn)

        footer.addStretch(1)

        self.close_btn = QPushButton("Close")
        self.close_btn.setObjectName("primaryButton")
        self.close_btn.clicked.connect(self.accept)
        footer.addWidget(self.close_btn)

        layout.addLayout(footer)

    def set_lines(self, lines: list[str]) -> None:
        self.output.setPlainText("\n".join(lines))
        cursor = self.output.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.output.setTextCursor(cursor)

    def append_line(self, line: str) -> None:
        if not line:
            return
        if self.output.toPlainText():
            self.output.appendPlainText(line)
        else:
            self.output.setPlainText(line)
        cursor = self.output.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        self.output.setTextCursor(cursor)

    def copy_log(self) -> None:
        text = self.output.toPlainText()
        if not text:
            QMessageBox.information(self, "Admin Monitor", "There is no log text to copy yet.")
            return
        self.output.selectAll()
        self.output.copy()
        self.output.moveCursor(self.output.textCursor().MoveOperation.End)
