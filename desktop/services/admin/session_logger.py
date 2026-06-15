import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any


class SessionLogger:
    def __init__(self, log_dir: Path) -> None:
        self.log_dir = log_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = self.log_dir / f"session_{stamp}.jsonl"
        self._lock = threading.Lock()
        self._lines: list[str] = []

    def record(self, event: str, **payload: Any) -> str:
        entry = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "event": event,
            **payload,
        }
        line = self._format_line(entry)
        encoded = json.dumps(entry, ensure_ascii=False)
        with self._lock:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(encoded + "\n")
            self._lines.append(line)
        return line

    def lines(self) -> list[str]:
        with self._lock:
            return list(self._lines)

    def clear_view(self) -> None:
        with self._lock:
            self._lines.clear()

    def _format_line(self, entry: dict[str, Any]) -> str:
        ts = entry.get("ts", "")
        event = str(entry.get("event", "event"))
        turn_id = entry.get("turn_id")
        prefix = f"[{ts}]"
        if turn_id is not None:
            prefix += f" [turn {turn_id}]"
        details = []
        for key in ("source", "duration_ms", "text", "reply", "mood", "status", "error", "log_path"):
            value = entry.get(key)
            if value in (None, ""):
                continue
            if key in {"text", "reply", "error"}:
                text = str(value).replace("\n", " ").strip()
                if len(text) > 180:
                    text = text[:177].rstrip() + "..."
                details.append(f"{key}={text}")
            else:
                details.append(f"{key}={value}")
        suffix = " | ".join(details)
        return f"{prefix} {event}" + (f" | {suffix}" if suffix else "")
