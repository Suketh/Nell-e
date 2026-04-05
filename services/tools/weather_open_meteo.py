from __future__ import annotations

import requests


GEOCODE_API = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_API = "https://api.open-meteo.com/v1/forecast"

WEATHER_CODES = {
    0: "clear",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "foggy",
    48: "foggy",
    51: "light drizzle",
    53: "drizzle",
    55: "dense drizzle",
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
    80: "rain showers",
    81: "rain showers",
    82: "heavy showers",
    85: "snow showers",
    86: "heavy snow showers",
    95: "thunderstorm",
    96: "thunderstorm with hail",
    99: "thunderstorm with hail",
}


def lookup_weather(location: str) -> dict[str, str | float | int]:
    query = str(location or "").strip()
    if not query:
        raise ValueError("Weather lookup requires a location.")

    geocode_response = requests.get(
        GEOCODE_API,
        params={"name": query, "count": 1, "language": "en", "format": "json"},
        headers={"User-Agent": "Nellie/1.0"},
        timeout=20,
    )
    geocode_response.raise_for_status()
    geocode_payload = geocode_response.json()
    results = list(geocode_payload.get("results", []) or [])
    if not results:
        raise ValueError(f"I couldn't find a weather match for '{query}'.")

    best = results[0]
    latitude = float(best.get("latitude"))
    longitude = float(best.get("longitude"))
    display_name = ", ".join(
        part
        for part in [
            str(best.get("name", "") or "").strip(),
            str(best.get("admin1", "") or "").strip(),
            str(best.get("country", "") or "").strip(),
        ]
        if part
    )

    forecast_response = requests.get(
        FORECAST_API,
        params={
            "latitude": latitude,
            "longitude": longitude,
            "current": ",".join(["temperature_2m", "apparent_temperature", "weather_code", "wind_speed_10m"]),
            "timezone": "auto",
        },
        headers={"User-Agent": "Nellie/1.0"},
        timeout=20,
    )
    forecast_response.raise_for_status()
    current = (forecast_response.json() or {}).get("current", {}) or {}

    weather_code = int(current.get("weather_code", -1) or -1)
    return {
        "location": display_name or query,
        "observed_at": str(current.get("time", "") or "").strip(),
        "temperature_c": float(current.get("temperature_2m", 0.0) or 0.0),
        "feels_like_c": float(current.get("apparent_temperature", 0.0) or 0.0),
        "wind_kmh": float(current.get("wind_speed_10m", 0.0) or 0.0),
        "weather_code": weather_code,
        "condition": WEATHER_CODES.get(weather_code, "unsettled"),
        "source": "Open-Meteo",
    }
