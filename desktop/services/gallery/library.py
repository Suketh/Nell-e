import json
import random
from pathlib import Path
from typing import Any


class GalleryLibrary:
    def __init__(self, gallery_dir: str):
        self.gallery_dir = Path(gallery_dir)
        self.gallery_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.gallery_dir / "manifest.json"
        self.items = self._load_manifest()

    def _load_manifest(self) -> list[dict[str, Any]]:
        if not self.manifest_path.exists():
            self.manifest_path.write_text("[]\n", encoding="utf-8")
            return []
        try:
            data = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]

    def choose_image(self, mood: str, text: str = "") -> dict[str, Any] | None:
        if not self.items:
            return None

        text_l = text.lower()
        eligible: list[tuple[int, dict[str, Any], Path, bool, list[str]]] = []
        for item in self.items:
            file_name = item.get("file")
            if not file_name:
                continue
            image_path = self.gallery_dir / file_name
            if not image_path.exists():
                continue

            score = 0
            moods = [m.lower() for m in item.get("moods", []) if isinstance(m, str)]
            triggers = [t.lower() for t in item.get("triggers", []) if isinstance(t, str)]

            mood_match = mood.lower() in moods if moods else False
            trigger_matches = [trigger for trigger in triggers if trigger in text_l]
            trigger_match = bool(trigger_matches)

            if mood_match:
                score += 3
            if trigger_match:
                score += 4
            if mood_match and trigger_match:
                score += 2

            # Reject loose matches so images appear only when the topic really fits.
            if not mood_match and not trigger_match:
                continue

            eligible.append((score, item, image_path, mood_match, trigger_matches))

        if not eligible:
            return None

        eligible.sort(key=lambda row: row[0], reverse=True)
        top_score = eligible[0][0]
        top = [row for row in eligible if row[0] == top_score]
        _, item, image_path, mood_match, trigger_matches = random.choice(top)
        return {
            "path": str(image_path),
            "caption": item.get("caption", ""),
            "name": item.get("name", image_path.name),
            "mood_match": mood_match,
            "trigger_matches": trigger_matches,
        }
