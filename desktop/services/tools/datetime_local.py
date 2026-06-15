from datetime import datetime


def lookup_local_datetime() -> dict[str, str]:
    now = datetime.now().astimezone()
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
    }
