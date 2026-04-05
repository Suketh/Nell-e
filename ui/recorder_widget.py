import queue
import threading

import sounddevice as sd
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget


class RecorderWidget(QFrame):
    transcript_ready = Signal(str)
    transcription_failed = Signal(str)

    def __init__(self, stt, on_transcript, on_error=None):
        super().__init__()
        self.setObjectName("recorderCard")
        self.stt = stt
        self.on_transcript = on_transcript
        self.on_error = on_error

        self.btn = QPushButton("Hold to talk")
        self.btn.setObjectName("recordButton")
        self.btn.pressed.connect(self.start)
        self.btn.released.connect(self.stop)
        self.btn.setCursor(Qt.PointingHandCursor)

        self.status = QLabel("Press and hold to speak")
        self.status.setObjectName("recordStatus")
        self.status.setWordWrap(True)
        self.status.setMinimumHeight(self.status.fontMetrics().height() + 8)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(12)
        layout.addWidget(self.btn, 0)
        layout.addWidget(self.status, 1)

        self._q = queue.Queue()
        self._rec = None
        self._ready = True

        self.transcript_ready.connect(self._handle_transcript_ready)
        if self.on_error:
            self.transcription_failed.connect(self._handle_transcription_failed)

    def _callback(self, indata, frames, time, status):
        self._q.put(bytes(indata))

    def start(self):
        if not self._ready:
            if self.on_error:
                self.on_error("Lyssningen värmer fortfarande upp. Vänta ett ögonblick.")
            return
        self._clear_queue()
        self.status.setText("Listening...")
        self._set_state("recording")
        self.btn.setText("Listening...")
        try:
            self._rec = sd.RawInputStream(
                channels=1,
                samplerate=16000,
                dtype="int16",
                callback=self._callback,
            )
            self._rec.start()
        except Exception as exc:
            self._rec = None
            self._set_idle_state("Press and hold to speak")
            if self.on_error:
                self.on_error(f"Mikrofonen kunde inte startas: {exc}")

    def stop(self):
        if self._rec:
            self._rec.stop()
            self._rec.close()
            self._rec = None

        audio_bytes = b"".join(list(self._q.queue))
        if len(audio_bytes) < 3200:
            self._set_idle_state("Too short, try again")
            return

        self.status.setText("Transcribing...")
        self._set_state("busy")
        self.btn.setText("Transcribing...")

        def run_stt():
            try:
                text = self.stt.transcribe(audio_bytes).strip()
                if text:
                    self.transcript_ready.emit(text)
                else:
                    self.transcription_failed.emit("Ingen text kunde tolkas från ljudet.")
            except Exception as exc:
                self.transcription_failed.emit(f"STT-fel: {exc}")

        threading.Thread(target=run_stt, daemon=True).start()

    def _handle_transcript_ready(self, text: str):
        self._set_idle_state("Press and hold to speak")
        self.on_transcript(text)

    def _handle_transcription_failed(self, err: str):
        self._set_idle_state("Press and hold to speak")
        if self.on_error:
            self.on_error(err)

    def _set_idle_state(self, status_text: str):
        self.status.setText(status_text)
        self.btn.setText("Hold to talk" if self._ready else "Voice loading")
        self._set_state("idle")

    def set_ready_state(self, ready: bool, status_text: str | None = None):
        self._ready = bool(ready)
        self.btn.setEnabled(self._ready)
        if status_text:
            self.status.setText(status_text)
        elif self._ready:
            self.status.setText("Press and hold to speak")
        else:
            self.status.setText("Voice input warming up...")
        self.btn.setText("Hold to talk" if self._ready else "Voice loading")
        self._set_state("idle" if self._ready else "busy")

    def _set_state(self, state: str):
        self.setProperty("state", state)
        self.style().unpolish(self)
        self.style().polish(self)

    def _clear_queue(self):
        while not self._q.empty():
            try:
                self._q.get_nowait()
            except queue.Empty:
                break
