from __future__ import annotations

import json
import re
import sqlite3
import time
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QInputDialog, QMessageBox


class DesktopProfileController:
    def __init__(self, window):
        self.window = window

    @property
    def conf(self) -> dict:
        return self.window.conf

    @property
    def conversation(self):
        return self.window.conversation

    @property
    def badge_colors(self) -> list[str]:
        return list(getattr(self.window, "PROFILE_BADGE_COLORS", []))

    def profile_path(self) -> Path:
        return Path(self.conf.get("paths", {}).get("client_profile_path", "data/client_profile.json"))

    def profile_registry_path(self) -> Path:
        return Path(self.conf.get("paths", {}).get("client_profiles_path", "data/client_profiles.json"))

    def load_profile_registry(self) -> dict:
        path = self.profile_registry_path()
        if path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    profiles = payload.get("profiles", [])
                    return {
                        "current_user_id": str(payload.get("current_user_id", "") or "").strip(),
                        "profiles": [item for item in profiles if isinstance(item, dict)],
                    }
            except Exception:
                pass
        active = self.active_profile()
        return {"current_user_id": str(active.get("user_id", "") or "").strip(), "profiles": [active]}

    def save_profile_registry(self, registry: dict):
        path = self.profile_registry_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(registry, ensure_ascii=False, indent=2), encoding="utf-8")

    def active_profile(self) -> dict:
        profile = dict((self.conf.get("profile", {}) or {}))
        user_id = str(profile.get("user_id", "") or "").strip() or "local-user"
        display_name = str(profile.get("display_name", "") or "").strip() or user_id
        badge_color = str(profile.get("badge_color", "") or "").strip() or self.fallback_profile_badge(user_id)
        return {"user_id": user_id, "display_name": display_name, "badge_color": badge_color}

    def refresh_profile_ui(self):
        profile = self.active_profile()
        display_name = str(profile.get("display_name", "") or "Local User")
        user_id = str(profile.get("user_id", "") or "local-user")
        badge_color = str(profile.get("badge_color", "") or self.fallback_profile_badge(user_id))
        snapshot = self.profile_snapshot(user_id)
        stage = str(snapshot.get("stage", "Anonymous") or "Anonymous")
        level = int(snapshot.get("level", 1) or 1)
        unlocks = int(snapshot.get("unlocks", 0) or 0)
        badge_html = (
            f"<span style=\"display:inline-block; width:10px; height:10px; "
            f"background:{badge_color}; border-radius:5px; margin-right:6px;\">&nbsp;</span>"
        )
        self.window.profile_label.setText(
            f"{badge_html}<span style=\"font-weight:700;\">Profile:</span> {display_name} "
            f"<span style=\"opacity:0.72;\">({user_id})</span> "
            f"<span style=\"opacity:0.84;\">• Lv {level} • {stage}</span>"
        )
        self.window.profile_label.setTextFormat(Qt.RichText)
        self.window.profile_panel_summary.setText(
            f"{badge_html}Active profile: <b>{display_name}</b><br>"
            f"user_id: <span style=\"opacity:0.76;\">{user_id}</span><br>"
            f"Level <b>{level}</b> • Stage <b>{stage}</b> • Gallery unlocks <b>{unlocks}</b>"
        )
        self.window.profile_panel_summary.setTextFormat(Qt.RichText)
        self.window.profile_label.setToolTip(f"Current client profile: {display_name} ({user_id})")

    def profile_db_path(self, user_id: str) -> Path:
        base_db = Path(self.conf.get("paths", {}).get("db_path", "data/nellie.sqlite")).resolve()
        stem = base_db.stem or "nellie"
        suffix = base_db.suffix or ".sqlite"
        safe_user = re.sub(r"[^a-z0-9._-]+", "-", str(user_id or "local-user").strip().lower()).strip("-._") or "local-user"
        return base_db.parent / "users" / safe_user / f"{stem}{suffix}"

    def profile_snapshot(self, user_id: str) -> dict:
        snapshot = {"level": 1, "stage": "Anonymous", "unlocks": 0}
        db_path = self.profile_db_path(user_id)
        if not db_path.exists():
            return snapshot
        try:
            conn = sqlite3.connect(str(db_path))
            try:
                row = conn.execute("SELECT value FROM agent_state WHERE key = ?", ("progression_state",)).fetchone()
                if row and row[0]:
                    payload = json.loads(row[0])
                    xp = int((payload or {}).get("xp", 0) or 0)
                    level = self.level_from_xp_local(xp)
                    snapshot["level"] = level
                    snapshot["stage"] = self.relationship_stage_local(level)
                row = conn.execute("SELECT value FROM agent_state WHERE key = ?", ("unlocked_gallery",)).fetchone()
                if row and row[0]:
                    unlocked = json.loads(row[0])
                    if isinstance(unlocked, list):
                        snapshot["unlocks"] = len([item for item in unlocked if isinstance(item, dict)])
            finally:
                conn.close()
        except Exception:
            return snapshot
        return snapshot

    def level_from_xp_local(self, xp: int) -> int:
        max_level = 255
        xp_value = max(0, int(xp or 0))
        level = 1
        for candidate in range(2, max_level + 1):
            n = candidate - 1
            threshold = int((n * n * 3.0) + (n * 18))
            if xp_value < threshold:
                break
            level = candidate
        return level

    def relationship_stage_local(self, level: int) -> str:
        if level >= 80:
            return "Magnetic"
        if level >= 54:
            return "Close"
        if level >= 32:
            return "Flirted"
        if level >= 16:
            return "Warm"
        if level >= 6:
            return "Curious"
        return "Anonymous"

    def apply_profile(self, profile: dict):
        user_id = str(profile.get("user_id", "") or "").strip()
        display_name = str(profile.get("display_name", "") or "").strip() or user_id
        badge_color = str(profile.get("badge_color", "") or "").strip()
        if not user_id:
            return
        if not badge_color:
            registry = self.load_profile_registry()
            badge_color = self.assign_profile_badge_color(profile, registry.get("profiles", []))
        normalized = {"user_id": user_id, "display_name": display_name, "badge_color": badge_color}
        self.conf.setdefault("profile", {})
        self.conf["profile"]["user_id"] = user_id
        self.conf["profile"]["display_name"] = display_name
        self.conf["profile"]["badge_color"] = badge_color

        profile_path = self.profile_path()
        profile_path.parent.mkdir(parents=True, exist_ok=True)
        profile_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")

        registry = self.load_profile_registry()
        profiles = []
        found = False
        for item in registry.get("profiles", []):
            if str(item.get("user_id", "") or "").strip() == user_id:
                profiles.append(normalized)
                found = True
            else:
                profiles.append(item)
        if not found:
            profiles.append(normalized)
        registry["profiles"] = profiles
        registry["current_user_id"] = user_id
        self.save_profile_registry(registry)

        if hasattr(self.conversation, "user_id"):
            self.conversation.user_id = user_id
            if hasattr(self.conversation, "session_id"):
                self.conversation.session_id = f"desktop-switch-{int(time.time())}"
        self.refresh_profile_ui()
        self.window._clear_gallery_unlock_marker()
        self.window._refresh_affection_progress()

    def switch_profile_dialog(self):
        registry = self.load_profile_registry()
        profiles = registry.get("profiles", [])
        if not profiles:
            QMessageBox.information(self.window, "Profiles", "No saved profiles exist yet.")
            return
        labels = []
        mapping = {}
        current_user_id = str(self.active_profile().get("user_id", "") or "")
        current_index = 0
        for idx, item in enumerate(profiles):
            user_id = str(item.get("user_id", "") or "").strip()
            display_name = str(item.get("display_name", "") or user_id).strip()
            snapshot = self.profile_snapshot(user_id)
            label = (
                f"{display_name} ({user_id})"
                f" • Lv {int(snapshot.get('level', 1) or 1)}"
                f" • {snapshot.get('stage', 'Anonymous')}"
                f" • {int(snapshot.get('unlocks', 0) or 0)} unlocks"
            )
            labels.append(label)
            mapping[label] = {"user_id": user_id, "display_name": display_name}
            if user_id == current_user_id:
                current_index = idx
        selected, ok = QInputDialog.getItem(self.window, "Switch profile", "Choose active profile:", labels, current_index, False)
        if not ok or not selected:
            return
        chosen = mapping.get(selected)
        if not chosen:
            return
        self.apply_profile(chosen)
        self.window.chat.add_system(f"Active profile switched to {chosen['display_name']}.", role="system-ok")

    def create_profile_dialog(self):
        name, ok = QInputDialog.getText(self.window, "New profile", "Display name:")
        if not ok:
            return
        display_name = str(name or "").strip()
        if not display_name:
            return
        slug = re.sub(r"[^a-z0-9]+", "-", display_name.lower()).strip("-")
        if not slug:
            slug = f"profile-{int(time.time())}"
        registry = self.load_profile_registry()
        known_ids = {str(item.get("user_id", "") or "").strip() for item in registry.get("profiles", [])}
        candidate = slug
        counter = 2
        while candidate in known_ids:
            candidate = f"{slug}-{counter}"
            counter += 1
        profile = {"user_id": candidate, "display_name": display_name}
        self.apply_profile(profile)
        self.window.chat.add_system(f"Created profile {display_name}.", role="system-ok")

    def fallback_profile_badge(self, user_id: str) -> str:
        safe = str(user_id or "local-user").strip().lower()
        score = sum(ord(ch) for ch in safe)
        colors = self.badge_colors or ["#c9785a"]
        return colors[score % len(colors)]

    def assign_profile_badge_color(self, profile: dict, profiles: list[dict]) -> str:
        existing = {
            str(item.get("badge_color", "") or "").strip().lower()
            for item in profiles
            if isinstance(item, dict)
        }
        preferred = str(profile.get("badge_color", "") or "").strip()
        if preferred:
            return preferred
        for color in self.badge_colors:
            if color.lower() not in existing:
                return color
        return self.fallback_profile_badge(str(profile.get("user_id", "") or "local-user"))

    def rename_profile_dialog(self):
        active = self.active_profile()
        current_name = str(active.get("display_name", "") or active.get("user_id", ""))
        name, ok = QInputDialog.getText(self.window, "Rename profile", "Display name:", text=current_name)
        if not ok:
            return
        display_name = str(name or "").strip()
        if not display_name:
            return
        updated = {"user_id": str(active.get("user_id", "") or "").strip(), "display_name": display_name}
        self.apply_profile(updated)
        self.window.chat.add_system(f"Renamed active profile to {display_name}.", role="system-ok")

    def delete_profile_dialog(self):
        registry = self.load_profile_registry()
        profiles = [item for item in registry.get("profiles", []) if isinstance(item, dict)]
        if len(profiles) <= 1:
            QMessageBox.information(self.window, "Delete profile", "You need at least one local profile.")
            return

        labels = []
        mapping = {}
        active_user_id = str(self.active_profile().get("user_id", "") or "")
        current_index = 0
        for idx, item in enumerate(profiles):
            user_id = str(item.get("user_id", "") or "").strip()
            display_name = str(item.get("display_name", "") or user_id).strip()
            label = f"{display_name} ({user_id})"
            labels.append(label)
            mapping[label] = item
            if user_id == active_user_id:
                current_index = idx

        selected, ok = QInputDialog.getItem(self.window, "Delete profile", "Choose profile to delete:", labels, current_index, False)
        if not ok or not selected:
            return
        chosen = mapping.get(selected)
        if not chosen:
            return

        chosen_user_id = str(chosen.get("user_id", "") or "").strip()
        chosen_name = str(chosen.get("display_name", "") or chosen_user_id).strip()
        answer = QMessageBox.question(
            self.window,
            "Delete profile",
            f"Delete profile '{chosen_name}'?\n\nThis removes it from the local profile list.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if answer != QMessageBox.Yes:
            return

        remaining = [item for item in profiles if str(item.get("user_id", "") or "").strip() != chosen_user_id]
        registry["profiles"] = remaining
        fallback = remaining[0]
        if chosen_user_id == active_user_id:
            registry["current_user_id"] = str(fallback.get("user_id", "") or "").strip()
            self.save_profile_registry(registry)
            self.apply_profile(fallback)
        else:
            registry["current_user_id"] = active_user_id
            self.save_profile_registry(registry)
        self.window.chat.add_system(f"Deleted profile {chosen_name}.", role="system-ok")
