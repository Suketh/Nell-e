import os
import queue
import tempfile
import threading
import time

import numpy as np
import sounddevice as sd
import soundfile as sf
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QPushButton, QWidget


PRE_ROLL_MS = 180
POST_ROLL_MS = 220
TARGET_PEAK = 0.82
SILENCE_THRESHOLD = 550
MIN_INPUT_PEAK = 80
KEEP_EDGE_MS = 120


def pick_combo(conf_audio: dict):
    audio = conf_audio or {}
    device = audio.get("input_device", None)
    samplerate = int(audio.get("sample_rate", 16000))
    channels = int(audio.get("channels", 1))
    dtype = str(audio.get("dtype", "int16")).lower()

    if device is None:
        default_device = sd.default.device
        device = default_device[0] if isinstance(default_device, (list, tuple)) else default_device

    sr_list = [samplerate, 48000, 44100, 32000, 16000]
    ch_list = [channels, 1, 2] if channels in (1, 2) else [1, 2]
    dt_list = [dtype, "int16", "float32"]

    def uniq(values):
        out = []
        for value in values:
            if value not in out:
                out.append(value)
        return out

    sr_list, ch_list, dt_list = uniq(sr_list), uniq(ch_list), uniq(dt_list)

    last_err = None
    for sr in sr_list:
        for ch in ch_list:
            for dt in dt_list:
                try:
                    sd.check_input_settings(device=device, channels=ch, samplerate=sr, dtype=dt)
                    return device, sr, ch, dt
                except Exception as e:
                    last_err = e
    raise RuntimeError(
        f"No working audio input combination found for device {device}. Last error: {last_err}"
    )


class RecorderWidget(QWidget):
    transcript_ready = Signal(str)
    error_raised = Signal(str)
    ui_state_changed = Signal(str, bool)

    def __init__(self, on_transcript, transcribe_func=None, conf=None, event_callback=None):
        super().__init__()
        self.conf = conf or {}
        self.on_transcript = on_transcript
        self.transcribe_func = transcribe_func
        self.event_callback = event_callback

        self.btn = QPushButton("◉")
        self.btn.setObjectName("talkButton")
        self.btn.setFixedSize(44, 44)
        self.btn.pressed.connect(self.start)
        self.btn.released.connect(self.stop)

        self.status_label = QLabel("Hold to Talk")
        self.status_label.setObjectName("voiceStatusLabel")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(self.btn)
        lay.addWidget(self.status_label, 1)

        self._q = queue.Queue()
        self._rec = None
        self._device = None
        self._overflow_detected = False
        self._samplerate = int((self.conf.get("audio") or {}).get("sample_rate", 16000))
        self._channels = int((self.conf.get("audio") or {}).get("channels", 1))
        self._dtype = (self.conf.get("audio") or {}).get("dtype", "int16")
        self._busy = False
        self._recording = False
        self._muted = False

        self.transcript_ready.connect(self.on_transcript)
        self.error_raised.connect(self._show_error)
        self.ui_state_changed.connect(self._apply_ui_state)

    def _callback(self, indata, frames, time, status):
        if status:
            self._overflow_detected = True
        self._q.put(bytes(indata))

    def start(self):
        if self._muted:
            self.ui_state_changed.emit("Microphone muted", False)
            return
        if self._busy:
            self._record_event("speech_capture_skipped", status="transcription_busy")
            self.ui_state_changed.emit("Still transcribing...", False)
            return
        if self._recording:
            return
        try:
            cfg_audio = self.conf.get("audio") or {}
            self._device, self._samplerate, self._channels, self._dtype = pick_combo(cfg_audio)
            self._overflow_detected = False

            with self._q.mutex:
                self._q.queue.clear()
            self._rec = sd.InputStream(
                device=self._device,
                channels=self._channels,
                samplerate=self._samplerate,
                dtype=self._dtype,
                callback=self._callback,
                latency=str(cfg_audio.get("latency", "low")),
                blocksize=int(cfg_audio.get("blocksize", 0) or 0),
            )
            self._rec.start()
            self._recording = True
            self._record_event(
                "speech_capture_started",
                device=str(self._device),
                sample_rate=self._samplerate,
                channels=self._channels,
                dtype=str(self._dtype),
            )
            self.ui_state_changed.emit("Listening…  release to send", True)
        except Exception as e:
            self._recording = False
            self._record_event("speech_capture_failed", error=str(e))
            self.error_raised.emit(
                "Could not open the microphone.\n\n"
                f"{e}\n\n"
                "Tip: leave audio.input_device empty to use the default microphone."
            )
            self._rec = None

    def stop(self):
        if self._busy:
            return
        if not self._recording or self._rec is None:
            return

        try:
            if POST_ROLL_MS > 0:
                time.sleep(POST_ROLL_MS / 1000.0)
            self._rec.stop()
            self._rec.close()
        except Exception as e:
            self._record_event("speech_capture_failed", error=str(e))
            self.error_raised.emit(f"Could not finish microphone capture.\n\n{e}")
            return
        finally:
            self._rec = None
            self._recording = False

        chunks = []
        while True:
            try:
                chunks.append(self._q.get_nowait())
            except queue.Empty:
                break
        audio_bytes = b"".join(chunks)
        if not audio_bytes:
            self._record_event("speech_capture_empty", status="no_audio_frames")
            self.ui_state_changed.emit("No microphone audio — try again", True)
            return

        self._busy = True
        sample_width = np.dtype(self._dtype).itemsize
        frame_count = len(audio_bytes) / max(1, sample_width * self._channels)
        duration_ms = round((frame_count / max(1, self._samplerate)) * 1000)
        self._record_event(
            "speech_capture_complete",
            duration_ms=duration_ms,
            bytes=len(audio_bytes),
            overflow=self._overflow_detected,
        )
        self.ui_state_changed.emit("Transcribing...", False)
        threading.Thread(target=self._transcribe_audio, args=(audio_bytes,), daemon=True).start()

    def _transcribe_audio(self, audio_bytes: bytes):
        keep_result_status = False
        try:
            if self.transcribe_func:
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
                    wav_path = f.name
                try:
                    np_dtype = "float32" if "float" in str(self._dtype) else "int16"
                    data = np.frombuffer(audio_bytes, dtype=np_dtype)
                    if self._channels > 1:
                        data = data.reshape(-1, self._channels)
                        data = data.mean(axis=1)
                    if np_dtype == "float32":
                        data = (np.clip(data, -1.0, 1.0) * 32767.0).astype("int16")
                    data = data.astype("int16", copy=False)
                    if data.size:
                        data = data - int(np.mean(data))
                    raw_peak = int(np.max(np.abs(data))) if data.size else 0
                    minimum_peak = int((self.conf.get("audio") or {}).get("minimum_input_peak", MIN_INPUT_PEAK))
                    if raw_peak < minimum_peak:
                        self._record_event(
                            "speech_input_too_quiet",
                            device=str(self._device),
                            peak=raw_peak,
                            minimum_peak=minimum_peak,
                        )
                        self.ui_state_changed.emit(
                            f"Microphone signal too low on input {self._device}",
                            True,
                        )
                        keep_result_status = True
                        return
                    data = self._trim_silence(data, self._samplerate)
                    peak = int(np.max(np.abs(data))) if data.size else 0
                    if peak > 0:
                        target_peak = int(32767 * TARGET_PEAK)
                        gain = min(2.8, target_peak / peak)
                        if gain > 1.02:
                            data = np.clip(data.astype("float32") * gain, -32767, 32767).astype("int16")
                    pre_roll_samples = max(1, int(self._samplerate * (PRE_ROLL_MS / 1000.0)))
                    silence = np.zeros(pre_roll_samples, dtype="int16")
                    data = np.concatenate([silence, data])
                    sf.write(wav_path, data, self._samplerate, subtype="PCM_16")
                    text = self.transcribe_func(wav_path)
                finally:
                    try:
                        os.remove(wav_path)
                    except Exception:
                        pass
            else:
                text = "(stub) Hello Nellie!"

            if text.strip():
                self._record_event("speech_transcription_complete", text=text.strip())
                self.transcript_ready.emit(text)
            elif self._overflow_detected:
                self._record_event("speech_transcription_empty", status="input_overflow")
                self.error_raised.emit("The microphone input overflowed during capture. Try speaking a little closer or lowering other audio load.")
            else:
                self._record_event("speech_transcription_empty", status="no_speech_detected")
                self.ui_state_changed.emit("No speech detected — try again", True)
                keep_result_status = True
        except Exception as e:
            self._record_event("speech_transcription_failed", error=str(e))
            self.error_raised.emit(f"Transcription failed.\n\n{e}")
        finally:
            self._busy = False
            if not keep_result_status:
                self.ui_state_changed.emit("Hold to Talk", True)

    def _trim_silence(self, data: np.ndarray, samplerate: int) -> np.ndarray:
        if data.size == 0:
            return data
        threshold = int((self.conf.get("audio") or {}).get("silence_threshold", SILENCE_THRESHOLD))
        keep_edge = max(0, int(samplerate * ((self.conf.get("audio") or {}).get("keep_edge_ms", KEEP_EDGE_MS) / 1000.0)))
        loud = np.where(np.abs(data) >= threshold)[0]
        if loud.size == 0:
            return data
        start = max(0, int(loud[0]) - keep_edge)
        end = min(data.size, int(loud[-1]) + keep_edge)
        return data[start:end]

    def _show_error(self, message: str):
        QMessageBox.critical(self, "Audio error", message)

    def _record_event(self, event: str, **payload):
        if self.event_callback is None:
            return
        try:
            self.event_callback(event, payload)
        except Exception:
            pass

    def _apply_ui_state(self, text: str, enabled: bool):
        self.status_label.setText(text)
        self.btn.setEnabled(enabled and not self._muted)

    def set_muted(self, muted: bool) -> None:
        self._muted = bool(muted)
        if self._muted and self._recording:
            self.stop()
        self.status_label.setText("Microphone muted" if self._muted else "Hold to Talk")
        self.btn.setEnabled(not self._muted and not self._busy)
