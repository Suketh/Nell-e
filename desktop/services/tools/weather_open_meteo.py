import re
import time
from importlib import import_module
from typing import Any


GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
FORECAST_FALLBACK_URL = "https://customer-api.open-meteo.com/v1/forecast"

WEATHER_CODES = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "freezing fog",
    51: "light drizzle",
    53: "drizzle",
    55: "heavy drizzle",
    56: "light freezing drizzle",
    57: "freezing drizzle",
    61: "light rain",
    63: "rain",
    65: "heavy rain",
    66: "light freezing rain",
    67: "freezing rain",
    71: "light snow",
    73: "snow",
    75: "heavy snow",
    77: "snow grains",
    80: "light rain showers",
    81: "rain showers",
    82: "heavy rain showers",
    85: "light snow showers",
    86: "heavy snow showers",
    95: "thunderstorms",
    96: "thunderstorms with light hail",
    99: "thunderstorms with hail",
}


def is_weather_query(text: str) -> bool:
    lower = str(text or "").casefold()
    return any(
        cue in lower
        for cue in (
            "weather",
            "forecast",
            "temperature",
            "väder",
            "vädret",
            "prognos",
            "temperatur",
        )
    )


def extract_location(text: str) -> str:
    value = re.sub(r"\s+", " ", str(text or "")).strip(" ?!.")
    patterns = (
        r"\b(?:weather|forecast|temperature)\s+(?:is\s+it\s+)?(?:like\s+)?(?:in|for|at)\s+(.+)$",
        r"\b(?:what(?:'s| is)\s+the\s+weather\s+(?:like\s+)?(?:in|for|at))\s+(.+)$",
        r"\b(?:väder(?:et)?|prognos(?:en)?|temperatur(?:en)?)\s+(?:i|för|pa|på)\s+(.+)$",
        r"\b(?:hur\s+är\s+vädret\s+i)\s+(.+)$",
    )
    location = ""
    for pattern in patterns:
        match = re.search(pattern, value, flags=re.IGNORECASE)
        if match:
            location = match.group(1)
            break
    if not location:
        match = re.search(r"\b(?:in|at|i)\s+([\wÀ-ÿ' -]{2,80})", value, flags=re.IGNORECASE)
        if match:
            location = match.group(1)
    location = re.sub(
        r"\b(?:right now|currently|today|tomorrow|now|just nu|idag|imorgon)\b.*$",
        "",
        location,
        flags=re.IGNORECASE,
    )
    return location.strip(" ,?!.")


def current_weather(location: str) -> dict[str, Any]:
    location = str(location or "").strip()
    if not location:
        raise ValueError("I need a city or place name to check the weather.")
    requests = import_module("requests")
    geocoding = requests.get(
        GEOCODING_URL,
        params={"name": location, "count": 1, "language": "en", "format": "json"},
        timeout=20,
    )
    geocoding.raise_for_status()
    candidates = geocoding.json().get("results") or []
    if not candidates:
        raise ValueError(f"I could not find a weather location matching {location}.")
    place = candidates[0]
    forecast_params = {
        "latitude": place["latitude"],
        "longitude": place["longitude"],
        "current": (
            "temperature_2m,apparent_temperature,relative_humidity_2m,"
            "precipitation,weather_code,wind_speed_10m,wind_gusts_10m"
        ),
        "daily": (
            "weather_code,temperature_2m_max,temperature_2m_min,"
            "precipitation_probability_max"
        ),
        "timezone": "auto",
        "forecast_days": 2,
    }
    forecast = _get_with_retry(
        requests,
        (FORECAST_URL, FORECAST_FALLBACK_URL),
        forecast_params,
    )
    payload = forecast.json()
    current = payload.get("current") or {}
    daily = payload.get("daily") or {}
    return {
        "name": str(place.get("name", location)),
        "admin1": str(place.get("admin1", "")),
        "country": str(place.get("country", "")),
        "timezone": str(payload.get("timezone", "")),
        "time": str(current.get("time", "")),
        "temperature": current.get("temperature_2m"),
        "feels_like": current.get("apparent_temperature"),
        "humidity": current.get("relative_humidity_2m"),
        "precipitation": current.get("precipitation"),
        "weather_code": current.get("weather_code"),
        "wind_speed": current.get("wind_speed_10m"),
        "wind_gusts": current.get("wind_gusts_10m"),
        "today_max": _first(daily.get("temperature_2m_max")),
        "today_min": _first(daily.get("temperature_2m_min")),
        "precipitation_probability": _first(daily.get("precipitation_probability_max")),
    }


def format_weather(data: dict[str, Any]) -> str:
    place_parts = [data.get("name"), data.get("admin1"), data.get("country")]
    place = ", ".join(str(part) for part in place_parts if part)
    description = WEATHER_CODES.get(_as_int(data.get("weather_code")), "mixed conditions")
    temperature = _number(data.get("temperature"))
    feels_like = _number(data.get("feels_like"))
    wind = _number(data.get("wind_speed"))
    low = _number(data.get("today_min"))
    high = _number(data.get("today_max"))
    rain_chance = _number(data.get("precipitation_probability"))
    humidity = _number(data.get("humidity"))

    reply = f"In {place}, it is currently {temperature}°C with {description}."
    details = []
    if feels_like:
        details.append(f"It feels like {feels_like}°C")
    if wind:
        details.append(f"wind is around {wind} km/h")
    if humidity:
        details.append(f"humidity is {humidity}%")
    if details:
        reply += " " + ", ".join(details) + "."
    if low and high:
        reply += f" Today's forecast is roughly {low} to {high}°C"
        if rain_chance:
            reply += f", with up to a {rain_chance}% chance of precipitation"
        reply += "."
    return reply


def _first(value: Any) -> Any:
    return value[0] if isinstance(value, list) and value else None


def _get_with_retry(requests: Any, urls: tuple[str, ...], params: dict[str, Any]) -> Any:
    last_error: Exception | None = None
    for url in urls:
        for attempt in range(3):
            try:
                response = requests.get(url, params=params, timeout=20)
                response.raise_for_status()
                return response
            except Exception as exc:
                last_error = exc
                if attempt < 2:
                    time.sleep(0.4 * (attempt + 1))
    if last_error is not None:
        raise last_error
    raise RuntimeError("Weather service did not return a response.")


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def _number(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    return str(int(number)) if number.is_integer() else f"{number:.1f}"
