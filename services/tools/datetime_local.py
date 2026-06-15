from datetime import datetime
from typing import Any


def _time_of_day(hour: int) -> str:
    if 5 <= hour < 9:
        return "early morning"
    if 9 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 22:
        return "evening"
    return "late night"


def lookup_local_datetime(now: datetime | None = None) -> dict[str, Any]:
    now = (now or datetime.now().astimezone()).astimezone()
    iso_year, iso_week, iso_weekday = now.isocalendar()
    return {
        "iso": now.isoformat(timespec="seconds"),
        "time": now.strftime("%H:%M"),
        "date": now.strftime("%Y-%m-%d"),
        "day": now.strftime("%A"),
        "month": now.strftime("%B"),
        "year": str(now.year),
        "week": str(iso_week),
        "iso_year": str(iso_year),
        "weekday_number": str(iso_weekday),
        "timezone": str(now.tzinfo or ""),
        "time_of_day": _time_of_day(now.hour),
        "hour": now.hour,
    }
