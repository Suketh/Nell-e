import time
from pathlib import Path


def build_combined_log(window) -> str:
    sections = ["=== Conversation Log ===", _conversation_log_text(window)]
    _append_stt_status(window, sections)
    _append_voice_status(window, sections)
    _append_stt_server_log(window, sections)
    return "\n".join(sections).strip()


def _conversation_log_text(window) -> str:
    if hasattr(window.conversation, "get_turn_log"):
        return window.conversation.get_turn_log(limit=250)
    if window.memory is not None:
        return window.memory.get_turn_log(limit=250)
    return "Conversation log unavailable."


def _append_stt_status(window, sections: list[str]) -> None:
    if window.stt is None or not hasattr(window.stt, "get_debug_status"):
        return

    sections.extend(["", "=== STT Status ==="])
    try:
        if hasattr(window.stt, "get_status_text"):
            sections.append(f"status_text: {window.stt.get_status_text()}")
        sections.append(f"ready: {bool(getattr(window.stt, 'is_ready', lambda: False)())}")
        status = window.stt.get_debug_status() or {}
        if not status:
            sections.append("(No STT status recorded yet)")
            return

        stamp = status.get("timestamp") or 0.0
        if stamp:
            sections.append(f"last_event: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(stamp))}")
        sections.append(f"ok: {bool(status.get('ok', False))}")
        sections.append(f"provider: {status.get('provider', '') or '(unknown)'}")
        sections.append(f"text_length: {status.get('text_length', 0)}")
        detail = str(status.get("detail", "") or "").strip()
        if detail:
            sections.append(f"detail: {detail}")
    except Exception as exc:
        sections.append(f"(Could not read STT status: {exc})")


def _append_voice_status(window, sections: list[str]) -> None:
    sections.extend(["", "=== Voice Status ==="])
    try:
        sections.append(f"speech_language: {window.conf.get('tts', {}).get('language', '') or '(unknown)'}")
        if hasattr(window.tts, "get_selected_voice"):
            sections.append(f"selected_voice: {window.tts.get_selected_voice() or '(unknown)'}")
        else:
            sections.append(
                f"selected_voice: {window.conf.get('tts', {}).get('vibevoice', {}).get('speaker_name', '') or '(unknown)'}"
            )
        if hasattr(window.tts, "get_available_voices"):
            voices = list(window.tts.get_available_voices() or [])
            sections.append(f"available_voices: {len(voices)}")
            if voices:
                sections.append("voices: " + ", ".join(voices[:20]))
        else:
            sections.append("(Voice list unavailable for current TTS engine)")
    except Exception as exc:
        sections.append(f"(Could not read voice status: {exc})")


def _append_stt_server_log(window, sections: list[str]) -> None:
    stt_log_path = window.conf.get("stt", {}).get("server", {}).get("log_path", "")
    if not stt_log_path:
        return

    sections.extend(["", "=== Voxtral STT Server Log ==="])
    try:
        log_path = Path(stt_log_path)
        if not log_path.exists():
            sections.append(f"(No STT server log found at {log_path})")
            return

        raw = log_path.read_text(encoding="utf-8", errors="replace").strip()
        if not raw:
            sections.append("(STT server log is empty)")
            return

        sections.extend(raw.splitlines()[-250:])
    except Exception as exc:
        sections.append(f"(Could not read STT server log: {exc})")
