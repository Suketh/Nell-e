import queue
import re
import threading


class DesktopChatController:
    def __init__(self, window):
        self.window = window

    def submit_text(self):
        if not self.window._startup_complete:
            return
        text = self.window.input.text().strip()
        if not text:
            return
        self.window.input.clear()
        self.on_user_utterance(text)

    def on_user_utterance(self, text: str):
        if not self.window._startup_complete:
            return
        text = (text or "").strip()
        if not text:
            return

        self.interrupt_current_output()
        self.window.chat.add_user(text)
        self.window._active_user_text = text
        self.window.ai_stream_start.emit()

        worker = threading.Thread(target=self.run_chat, args=(text,), daemon=True)
        worker.start()

    def run_chat(self, text: str):
        try:
            result = self.window.conversation.reply(
                text,
                stream_callback=lambda chunk: self.window.ai_stream_chunk.emit(chunk),
            )
            self.window.ai_stream_done.emit(
                result.reply,
                {
                    "mood": result.mood,
                    "mode": result.mode,
                    "tool_events": result.tool_events or [],
                    "agent_trace": result.agent_trace or [],
                    "gallery_image_path": result.gallery_image_path or "",
                    "gallery_image_caption": result.gallery_image_caption or "",
                    "new_unlock": result.new_unlock or {},
                },
            )
        except Exception as exc:
            self.window.ai_stream_error.emit(str(exc))

    def on_ai_stream_start(self):
        self.window._stream_buffer.clear()
        self.window._pending_stream_chunks.clear()
        self.window._stream_flush_timer.stop()
        self.window.input_card.setProperty("state", "active")
        self.window.input_card.style().unpolish(self.window.input_card)
        self.window.input_card.style().polish(self.window.input_card)
        self.window.voice_status_update.emit("Nellie is thinking...")
        self.window.chat.add_ai_stream_start()

    def on_ai_stream_chunk(self, chunk: str):
        self.window._pending_stream_chunks.append(chunk)
        if not self.window._stream_flush_timer.isActive():
            self.window._stream_flush_timer.start()
        self.window._stream_buffer.append(chunk)
        if not self.window._stream_tts:
            return
        joined = "".join(self.window._stream_buffer)
        match = re.search(r"([^.?!]{20,}[.?!])", joined)
        if match:
            sentence = match.group(1)
            rest = joined[len(sentence) :]
            self.window._stream_buffer.clear()
            self.window._stream_buffer.append(rest)
            self.enqueue_tts(sentence, mood=self.window._active_ai_mood)

    def on_ai_stream_done(self, reply: str, meta):
        self.flush_pending_stream_chunks()
        self.window._stream_flush_timer.stop()
        self.window.chat.set_ai_stream_text(reply)
        self.window.chat.add_ai_stream_end()
        mood = self.window.avatar.normalize_mood((meta or {}).get("mood", "thoughtful"))
        self.window._active_ai_mood = mood
        self.window.avatar.set_mood(mood)
        mode = (meta or {}).get("mode", "direct_reply")
        agent_trace = (meta or {}).get("agent_trace", [])
        trace_note = self.format_agent_trace(agent_trace)
        if trace_note:
            self.window.chat.add_system(trace_note["text"], role=trace_note["role"])
        tool_events = (meta or {}).get("tool_events", [])
        if tool_events:
            parts = []
            system_role = "system-ok"
            for event in tool_events:
                tool_name = event.get("tool", "tool")
                status = event.get("status", "ok")
                parts.append(tool_name if status == "ok" else f"{tool_name} failed")
                if status != "ok":
                    system_role = "system-warning"
            self.window.chat.add_system("Tool activity: " + ", ".join(parts), role=system_role)
        self.window._set_agent_debug_payload(mode=mode, agent_trace=agent_trace, tool_events=tool_events)
        self.sync_input_state(self.window.input.text())
        self.window.voice_status_update.emit(self.window._resting_voice_status)
        gallery_image_path = str((meta or {}).get("gallery_image_path", "") or "").strip()
        gallery_image_caption = str((meta or {}).get("gallery_image_caption", "") or "").strip()
        new_unlock = (meta or {}).get("new_unlock") or {}
        if gallery_image_path:
            self.window.chat.add_ai_image(gallery_image_caption or "Thought you'd like this one.", gallery_image_path)
        if new_unlock:
            unlock_title = str(
                new_unlock.get("title", "") or self.window._format_gallery_unlock_title(new_unlock.get("filename", ""))
            ).strip()
            unlock_rarity = str(new_unlock.get("rarity", "common") or "common").strip().title()
            unlock_text = f"New unlock: {unlock_title} added to your gallery."
            if unlock_rarity and unlock_rarity != "Common":
                unlock_text += f" {unlock_rarity} pull."
            self.window.chat.add_system(unlock_text, role="system-ok")
            self.window._mark_gallery_unlock()
        self.window._refresh_affection_progress()
        if self.window._stream_tts:
            tail = "".join(self.window._stream_buffer).strip()
            if tail:
                self.enqueue_tts(tail, mood=mood)
        else:
            self.enqueue_tts(reply, mood=mood)

    def on_ai_stream_error(self, err: str):
        self.flush_pending_stream_chunks()
        self.window._stream_flush_timer.stop()
        fallback = "Couldn't answer just now. Try that one more time."
        self.window.chat.set_ai_stream_text(fallback)
        self.window.chat.add_ai_stream_end()
        self.window._stream_buffer.clear()
        self.window._pending_stream_chunks.clear()
        self.window.avatar.set_mood("thoughtful")
        self.sync_input_state(self.window.input.text())
        self.window.voice_status_update.emit(self.window._resting_voice_status)
        self.window._set_agent_debug_payload(
            mode="error",
            agent_trace=[{"step": "reply_error", "status": "error", "error": err}],
            tool_events=[],
        )

    def flush_pending_stream_chunks(self):
        if not self.window._pending_stream_chunks:
            return
        combined = "".join(self.window._pending_stream_chunks)
        self.window._pending_stream_chunks.clear()
        self.window.chat.add_ai_stream_chunk(combined)

    def format_agent_trace(self, agent_trace: list[dict]) -> dict[str, str] | None:
        if not agent_trace:
            return None

        plan = next((item for item in agent_trace if item.get("step") == "plan"), None)
        if not plan:
            return None

        mode = plan.get("mode", "direct_reply")
        tool_name = plan.get("tool_name")
        execute = next((item for item in agent_trace if item.get("step") == "tool_execute"), None)
        lookup = next((item for item in agent_trace if item.get("step") == "tool_lookup"), None)

        if mode == "direct_reply":
            return None
        if lookup and lookup.get("status") == "missing":
            return {
                "role": "system-warning",
                "text": f"Tool missing: planned {tool_name or 'tool use'}, but nothing was available.",
            }
        if execute and execute.get("status") == "error":
            return {
                "role": "system-danger",
                "text": f"Fallback: planned {tool_name or 'tool use'}, then recovered after a tool error.",
            }
        if execute and execute.get("status") == "ok":
            return {
                "role": "system-ok",
                "text": f"Tool ok: planned {tool_name or 'tool use'} and executed it.",
            }
        return {
            "role": "system-plan",
            "text": f"Plan: {tool_name or mode}.",
        }

    def on_stt_error(self, err: str):
        self.window.chat.add_ai(f"Mikrofonen hördes otydligt. {err}")

    def enqueue_tts(self, text: str, mood: str | None = None):
        display_text = (text or "").strip()
        if not display_text:
            return

        spoken_text = self.prepare_tts_payload(display_text, mood=mood)
        if spoken_text:
            self.window._tts_queue.put(
                {
                    "payload": spoken_text,
                    "plain": self.prepare_tts_text(display_text),
                }
            )

    def interrupt_current_output(self):
        self.window._stream_buffer.clear()
        self.window._pending_stream_chunks.clear()
        self.window._stream_flush_timer.stop()
        self.clear_tts_queue()
        if hasattr(self.window.tts, "stop"):
            try:
                self.window.tts.stop()
            except Exception as exc:
                print(f"[tts stop] {exc}")

    def clear_tts_queue(self):
        while True:
            try:
                self.window._tts_queue.get_nowait()
            except queue.Empty:
                break
            else:
                self.window._tts_queue.task_done()

    def tts_worker(self):
        while True:
            item = self.window._tts_queue.get()
            if isinstance(item, dict):
                text = item.get("payload", "")
                plain = item.get("plain", "")
            else:
                text = item
                plain = re.sub(r"<[^>]+>", " ", text or "")
                plain = re.sub(r"\s+", " ", plain).strip()
            status_text = "Voice ready"
            try:
                self.window.tts.speak(text)
            except Exception as exc:
                print(f"[tts] {exc}")
                self.window.voice_status_update.emit("Voice retrying...")
                if plain and plain != text:
                    try:
                        self.window.tts.speak(plain)
                    except Exception as fallback_exc:
                        print(f"[tts fallback] {fallback_exc}")
                        status_text = "Voice unavailable"
                else:
                    status_text = "Voice unavailable"
            finally:
                self.window.voice_status_update.emit(status_text)
                self.window._tts_queue.task_done()

    def should_stream_tts(self) -> bool:
        tts_conf = self.window.conf.get("tts", {})
        if "stream_while_generating" in tts_conf:
            return bool(tts_conf["stream_while_generating"])
        return tts_conf.get("engine") != "vibevoice_realtime"

    def prepare_tts_text(self, text: str) -> str:
        spoken = re.sub(r"\s+", " ", (text or "").strip())
        if not spoken:
            return ""

        ssml_lite_active = False
        if hasattr(self.window.tts, "is_ssml_lite_enabled"):
            try:
                ssml_lite_active = bool(self.window.tts.is_ssml_lite_enabled())
            except Exception:
                ssml_lite_active = False

        spoken = spoken.replace("“", '"').replace("”", '"')
        spoken = spoken.replace("‘", "'").replace("’", "'")
        spoken = re.sub(r"\(([^()]{1,80})\)", r", \1,", spoken)

        if not ssml_lite_active:
            spoken = re.sub(r"\s*[;:]\s*", ", ", spoken)
            spoken = re.sub(r"\s*-\s*", ", ", spoken)
            spoken = re.sub(r"\.\.\.+", ". ", spoken)
            spoken = re.sub(r"\s+", " ", spoken).strip()
            return spoken

        spoken = re.sub(r"\s*-\s*", ' <break time="110ms"/> ', spoken)
        spoken = re.sub(r"\s*[;:]\s*", ' <break time="120ms"/> ', spoken)
        spoken = re.sub(r"\.\.\.+", ' <break time="180ms"/> ', spoken)
        spoken = re.sub(r",\s*(and|but|so)\s+", r', <break time="70ms"/> \1 ', spoken, flags=re.IGNORECASE)
        spoken = re.sub(r"\s+", " ", spoken).strip()
        return spoken

    def prepare_tts_payload(self, text: str, mood: str | None = None) -> str:
        spoken = self.prepare_tts_text(text)
        if not spoken:
            return ""

        mood = self.window.avatar.normalize_mood(mood or self.window._active_ai_mood)
        ssml_lite_active = False
        if hasattr(self.window.tts, "is_ssml_lite_enabled"):
            try:
                ssml_lite_active = bool(self.window.tts.is_ssml_lite_enabled())
            except Exception:
                ssml_lite_active = False

        spoken = self.inject_spoken_mood_texture(spoken, mood, ssml_lite_active)
        if not ssml_lite_active:
            return re.sub(r"\s+", " ", spoken).strip()

        spoken = re.sub(r"(?<=[.!?])\s+(?=[A-Z])", ' <break time="110ms"/> ', spoken)
        spoken = re.sub(r",\s+", ' <break time="70ms"/> ', spoken)
        spoken = re.sub(r"\s+", " ", spoken).strip()
        return spoken

    def inject_spoken_mood_texture(self, spoken: str, mood: str, ssml_lite_active: bool) -> str:
        text = (spoken or "").strip()
        if not text:
            return ""
        if re.match(r"(?i)^(mm|hm|heh|mmh|well|ehh)\b", text):
            return text

        lower = text.lower()
        prefix = ""
        if mood in {"thoughtful", "sad", "tired"} and len(text) <= 120:
            thoughtful_markers = ["think", "maybe", "perhaps", "gently", "honestly", "quietly", "i suppose", "i think"]
            if any(token in lower for token in thoughtful_markers):
                prefix = '<filler kind="hm"/> ' if ssml_lite_active else "Hm, "
        elif mood == "happy" and len(text) <= 120 and any(
            token in lower for token in ["glad", "love", "like", "charming", "sweet", "fun", "!"]
        ):
            prefix = '<laugh>heh</laugh> ' if ssml_lite_active else "Heh, "
        elif mood == "annoyed" and len(text) <= 100 and any(
            token in lower for token in ["awkward", "mess", "seriously", "annoying"]
        ):
            prefix = '<filler kind="hm"/> ' if ssml_lite_active else "Hm, "

        if not prefix:
            return text
        return f"{prefix}{text}".strip()

    def sync_input_state(self, text: str):
        state = "active" if (text or "").strip() else "idle"
        self.window.input_card.setProperty("state", state)
        self.window.input_card.style().unpolish(self.window.input_card)
        self.window.input_card.style().polish(self.window.input_card)
        self.window.send_btn.setEnabled(self.window._startup_complete and bool((text or "").strip()))
