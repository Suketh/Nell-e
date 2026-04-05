from __future__ import annotations

import threading


class DesktopStartupController:
    def __init__(self, window):
        self.window = window

    @property
    def tts(self):
        return self.window.tts

    @property
    def stt(self):
        return self.window.stt

    def start_voice_warmup(self):
        if not hasattr(self.tts, "warmup"):
            self.window._startup_steps["voice"] = True
            self.window.voice_status_update.emit("Voice ready")
            return
        self.window.voice_status_update.emit("Voice warming up...")
        threading.Thread(target=self.warmup_voice, daemon=True).start()

    def start_stt_warmup(self):
        if self.stt is None:
            self.window._startup_steps["stt"] = True
            self.window.listening_status_update.emit("Listening unavailable", False)
            return
        if not hasattr(self.stt, "warmup"):
            self.window._startup_steps["stt"] = True
            self.window.listening_status_update.emit("Listening ready", True)
            return
        initial_text = "Listening warming up..."
        if hasattr(self.stt, "get_status_text"):
            try:
                initial_text = self.stt.get_status_text()
            except Exception:
                initial_text = "Listening warming up..."
        self.window.listening_status_update.emit(initial_text, False)
        threading.Thread(target=self.warmup_stt, daemon=True).start()

    def warmup_voice(self):
        try:
            self.tts.warmup()
            voices = []
            selected_voice = ""
            if hasattr(self.tts, "get_available_voices"):
                try:
                    voices = list(self.tts.get_available_voices() or [])
                except Exception:
                    voices = []
            if hasattr(self.tts, "get_selected_voice"):
                try:
                    selected_voice = str(self.tts.get_selected_voice() or "")
                except Exception:
                    selected_voice = ""
            self.window._startup_steps["voice"] = True
            self.window.voice_catalog_update.emit(voices, selected_voice)
            self.window.voice_status_update.emit(f"Voice ready{f' ({selected_voice})' if selected_voice else ''}")
        except Exception as exc:
            print(f"[voice warmup] {exc}")
            self.window._startup_steps["voice"] = True
            self.window.voice_status_update.emit("Voice unavailable")

    def warmup_stt(self):
        try:
            self.stt.warmup()
            status_text = "Listening ready"
            if hasattr(self.stt, "get_status_text"):
                try:
                    status_text = self.stt.get_status_text()
                except Exception:
                    status_text = "Listening ready"
            self.window._startup_steps["stt"] = True
            self.window.listening_status_update.emit(status_text, True)
        except Exception as exc:
            print(f"[stt warmup] {exc}")
            detail = str(exc).strip() or "startup failed"
            self.window._startup_steps["stt"] = True
            self.window.listening_status_update.emit(f"Listening unavailable: {detail}", False)

    def set_voice_combo_loading(self):
        self.window._voice_choice_locked = True
        self.window.voice_combo.clear()
        self.window.voice_combo.addItem("Loading voices...", "")
        self.window.voice_combo.setEnabled(False)
        self.window._voice_choice_locked = False

    def on_voice_status_update(self, text: str):
        if text and not any(marker in text.lower() for marker in ["thinking", "playing voice demo", "retrying"]):
            self.window._resting_voice_status = text
        self.refresh_startup_progress(text or self.window._startup_status_text)

    def on_listening_status_update(self, text: str, ready: bool):
        if text and "warming" not in text.lower():
            self.window._resting_listening_status = text
        self.refresh_startup_progress(text or self.window._startup_status_text)
        if self.window.recorder is not None:
            self.window.recorder.set_ready_state(ready and self.window._startup_complete, text)

    def set_interaction_enabled(self, enabled: bool):
        self.window.input.setEnabled(bool(enabled))
        self.window.send_btn.setEnabled(bool(enabled) and bool((self.window.input.text() or "").strip()))
        self.window.voice_demo_btn.setEnabled(bool(enabled) and hasattr(self.tts, "speak"))
        if self.window.recorder is not None:
            self.window.recorder.set_ready_state(
                bool(enabled),
                "Press and hold to speak" if enabled else "Nellie is still loading...",
            )

    def refresh_startup_progress(self, detail: str):
        detail_text = str(detail or "").strip() or "Launching Nellie"
        self.window._startup_status_text = detail_text

        percent = 15
        if self.window._startup_steps.get("voice"):
            percent += 35
        if self.window._startup_steps.get("stt"):
            percent += 35

        fully_ready = bool(self.window._startup_steps.get("voice")) and bool(self.window._startup_steps.get("stt"))
        if fully_ready:
            self.window._startup_steps["finalize"] = True
            percent = 100
            self.window._startup_complete = True
            self.set_interaction_enabled(True)
            self.window._sync_ssml_lite_button()
            self.window.loading_label.setText(
                '<span style="font-weight:800; letter-spacing:1.3px;">Nellie is ready. 100%</span>'
                '<br><span style="font-size:11px; opacity:0.88;">You can start typing now.</span>'
            )
            return

        percent = max(1, min(99, percent))
        self.window.loading_label.setText(
            f'<span style="font-weight:800; letter-spacing:1.3px;">{detail_text} {percent}%</span>'
        )
