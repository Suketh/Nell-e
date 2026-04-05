from __future__ import annotations

FEATURE_CATALOG: list[dict] = [
    {
        "id": "datetime_local",
        "label": "Time and date sense",
        "description": "Let Nellie check the local time, date, weekday, and similar basics.",
        "category": "utility",
        "min_level": 8,
        "implemented": True,
        "default_enabled": True,
    },
    {
        "id": "weather_lookup",
        "label": "Weather checks",
        "description": "Let Nellie check the weather for a place you mention.",
        "category": "utility",
        "min_level": 1,
        "implemented": True,
        "default_enabled": True,
    },
    {
        "id": "calculator",
        "label": "Calculator",
        "description": "Let Nellie solve arithmetic and quick calculation questions.",
        "category": "utility",
        "min_level": 14,
        "implemented": True,
        "default_enabled": True,
    },
    {
        "id": "device_timers",
        "label": "Timer widgets",
        "description": "Let Nellie create timers on your phone when that bridge is connected.",
        "category": "device",
        "min_level": 18,
        "implemented": True,
        "default_enabled": False,
    },
    {
        "id": "wikipedia_search",
        "label": "Wikipedia lookups",
        "description": "Let Nellie look up people, topics, and summaries on Wikipedia.",
        "category": "knowledge",
        "min_level": 22,
        "implemented": True,
        "default_enabled": True,
    },
    {
        "id": "device_alarms",
        "label": "Alarm widgets",
        "description": "Let Nellie set alarms on your phone once device widgets are wired in.",
        "category": "device",
        "min_level": 26,
        "implemented": True,
        "default_enabled": False,
    },
    {
        "id": "vision_describe_image",
        "label": "Image understanding",
        "description": "Let Nellie inspect images and tell you what she sees.",
        "category": "knowledge",
        "min_level": 32,
        "implemented": True,
        "default_enabled": True,
    },
    {
        "id": "web_search",
        "label": "Web search",
        "description": "Let Nellie search the web for lightweight lookups.",
        "category": "knowledge",
        "min_level": 42,
        "implemented": True,
        "default_enabled": True,
    },
    {
        "id": "web_fetch",
        "label": "Web page reading",
        "description": "Let Nellie open a page and pull out readable text from it.",
        "category": "knowledge",
        "min_level": 50,
        "implemented": True,
        "default_enabled": True,
    },
    {
        "id": "pdf_reading",
        "label": "PDF reading",
        "description": "Let Nellie extract text and summarize PDF documents.",
        "category": "knowledge",
        "min_level": 58,
        "implemented": True,
        "default_enabled": True,
    },
    {
        "id": "spotify_control",
        "label": "Spotify connection",
        "description": "Let Nellie open Spotify or steer music requests for you.",
        "category": "services",
        "min_level": 60,
        "implemented": True,
        "default_enabled": False,
    },
    {
        "id": "youtube_control",
        "label": "YouTube connection",
        "description": "Let Nellie open YouTube and follow media requests there.",
        "category": "services",
        "min_level": 60,
        "implemented": True,
        "default_enabled": False,
    },
    {
        "id": "browser_actions",
        "label": "Browser actions",
        "description": "Let Nellie open browser targets and follow through on links.",
        "category": "services",
        "min_level": 64,
        "implemented": True,
        "default_enabled": False,
    },
]

FEATURE_BY_ID = {str(item["id"]): item for item in FEATURE_CATALOG}


def _normalize_overrides(overrides: dict | None) -> dict[str, bool]:
    if not isinstance(overrides, dict):
        return {}
    normalized: dict[str, bool] = {}
    for key, value in overrides.items():
        feature_id = str(key or "").strip()
        if not feature_id:
            continue
        normalized[feature_id] = bool(value)
    return normalized


def build_feature_items(level: int, overrides: dict | None = None) -> list[dict]:
    current_level = int(level or 1)
    user_overrides = _normalize_overrides(overrides)
    items: list[dict] = []
    for feature in FEATURE_CATALOG:
        feature_id = str(feature["id"])
        min_level = int(feature.get("min_level", 1) or 1)
        unlocked = current_level >= min_level
        enabled = False
        if unlocked:
            if feature_id in user_overrides:
                enabled = bool(user_overrides[feature_id])
            else:
                enabled = bool(feature.get("default_enabled", False))
        items.append(
            {
                **feature,
                "unlocked": unlocked,
                "enabled": enabled,
            }
        )
    return items


def build_feature_access_state(level: int, overrides: dict | None = None) -> dict:
    items = build_feature_items(level, overrides=overrides)
    enabled_ids = [str(item["id"]) for item in items if bool(item.get("enabled"))]
    return {
        "items": items,
        "enabled_ids": enabled_ids,
        "enabled_count": len(enabled_ids),
        "available_count": sum(1 for item in items if bool(item.get("unlocked"))),
    }


def get_unlocked_feature_items(level: int, overrides: dict | None = None) -> list[dict]:
    return [item for item in build_feature_items(level, overrides=overrides) if bool(item.get("unlocked"))]


def get_enabled_feature_items(level: int, overrides: dict | None = None) -> list[dict]:
    return [item for item in build_feature_items(level, overrides=overrides) if bool(item.get("enabled"))]


def get_next_feature_unlock(level: int) -> dict | None:
    current_level = int(level or 1)
    for item in FEATURE_CATALOG:
        min_level = int(item.get("min_level", 1) or 1)
        if current_level < min_level:
            return {
                "id": str(item.get("id", "") or "").strip(),
                "label": str(item.get("label", "") or "").strip(),
                "description": str(item.get("description", "") or "").strip(),
                "category": str(item.get("category", "") or "").strip(),
                "level": min_level,
                "implemented": bool(item.get("implemented", False)),
            }
    return None


def is_feature_enabled(feature_id: str, level: int, overrides: dict | None = None) -> bool:
    for item in build_feature_items(level, overrides=overrides):
        if str(item.get("id", "")) == str(feature_id):
            return bool(item.get("enabled"))
    return False


def resolve_feature(feature_id: str) -> dict | None:
    return FEATURE_BY_ID.get(str(feature_id or "").strip())


def tool_feature_id(tool_name: str, tool_input: dict | None = None) -> str | None:
    tool = str(tool_name or "").strip()
    if not tool:
        return None
    if tool == "datetime_local":
        return "datetime_local"
    if tool == "calculator":
        return "calculator"
    if tool == "weather_lookup":
        return "weather_lookup"
    if tool == "wikipedia_search":
        return "wikipedia_search"
    if tool == "web_search":
        return "web_search"
    if tool == "web_fetch":
        return "web_fetch"
    if tool == "vision_describe_image":
        return "vision_describe_image"
    if tool == "pdf_extract_text":
        return "pdf_reading"
    if tool == "browser_open":
        target = str((tool_input or {}).get("target", "") or "").strip().lower()
        if target == "spotify":
            return "spotify_control"
        if target == "youtube":
            return "youtube_control"
        return "browser_actions"
    return None
