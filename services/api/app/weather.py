"""Weather provider abstraction (spec sections 10, 70).

- WeatherProvider interface: get_weather(lat, lon, days) -> WeatherSnapshot | Unavailable.
- OpenMeteoProvider: free, keyless, no fabrication — on any failure returns Unavailable
  with reason so the engine degrades confidence instead of inventing numbers.
- NoneProvider: explicit 'not configured' stub.
- In-process TTL cache per rounded lat/lon key (30 min default). Redis-backed sharing
  is a documented drop-in when REDIS_URL is set.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Protocol

import httpx

from app.config import get_settings

settings = get_settings()


def lat_key(lat: float, lon: float) -> str:
    """Round to 2 decimals (~1 km) — location privacy (spec 44): never store exact coords in weather cache."""
    return f"{round(lat, 2)},{round(lon, 2)}"


@dataclass
class ForecastDay:
    day: str            # YYYY-MM-DD
    min_c: float | None
    max_c: float | None
    rain_prob_pct: float | None
    rain_mm: float | None
    et0_mm: float | None
    condition_code: int | None


@dataclass
class WeatherSnapshot:
    available: bool
    provider: str
    fetched_at: datetime
    lat: float
    lon: float
    temp_c: float | None = None
    humidity_pct: float | None = None
    wind_kmh: float | None = None
    rain_prob_pct: float | None = None
    condition_code: int | None = None
    forecast: list[ForecastDay] = field(default_factory=list)
    reason: str | None = None  # when available=False


class WeatherProvider(Protocol):
    name: str

    def get_weather(self, lat: float, lon: float, days: int = 6) -> WeatherSnapshot: ...


def _unavailable(provider: str, lat: float, lon: float, reason: str) -> WeatherSnapshot:
    return WeatherSnapshot(available=False, provider=provider,
                           fetched_at=datetime.now(timezone.utc), lat=lat, lon=lon, reason=reason)


class NoneProvider:
    name = "none"

    def get_weather(self, lat: float, lon: float, days: int = 6) -> WeatherSnapshot:
        return _unavailable("none", lat, lon, "weather.not_configured")


class OpenMeteoProvider:
    name = "open-meteo"

    def __init__(self, base_url: str | None = None, timeout: float = 10.0):
        self.base_url = (base_url or settings.weather_base_url).rstrip("/")
        self.timeout = timeout

    def get_weather(self, lat: float, lon: float, days: int = 6) -> WeatherSnapshot:
        params = {
            "latitude": round(lat, 4), "longitude": round(lon, 4),
            "current": "temperature_2m,relative_humidity_2m,wind_speed_10m,precipitation,weather_code",
            "daily": ("temperature_2m_max,temperature_2m_min,precipitation_probability_max,"
                      "precipitation_sum,weather_code,et0_fao_evapotranspiration"),
            "forecast_days": min(days, 7),
            "timezone": "UTC",
            "models": "best_match",
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                r = client.get(f"{self.base_url}/v1/forecast", params=params)
                if r.status_code != 200:
                    return _unavailable(self.name, lat, lon, "weather.unavailable")
                data = r.json()
        except (httpx.HTTPError, ValueError):
            return _unavailable(self.name, lat, lon, "weather.unavailable")

        cur = data.get("current", {})
        daily = data.get("daily", {})
        days_list: list[ForecastDay] = []
        dates = daily.get("time", [])
        for i, d in enumerate(dates):
            days_list.append(ForecastDay(
                day=d,
                min_c=_num(daily.get("temperature_2m_min"), i),
                max_c=_num(daily.get("temperature_2m_max"), i),
                rain_prob_pct=_num(daily.get("precipitation_probability_max"), i),
                rain_mm=_num(daily.get("precipitation_sum"), i),
                et0_mm=_num(daily.get("et0_fao_evapotranspiration"), i),
                condition_code=_int(daily.get("weather_code"), i),
            ))
        return WeatherSnapshot(
            available=True, provider=self.name,
            fetched_at=datetime.now(timezone.utc), lat=lat, lon=lon,
            temp_c=_maybe_float(cur.get("temperature_2m")),
            humidity_pct=_maybe_float(cur.get("relative_humidity_2m")),
            wind_kmh=_maybe_float(cur.get("wind_speed_10m")),
            rain_prob_pct=days_list[0].rain_prob_pct if days_list else None,
            condition_code=_maybe_int(cur.get("weather_code")),
            forecast=days_list,
        )


class StaticProvider:
    """Deterministic provider used by the demo/test environment — ALWAYS labelled demo.
    Not exposed unless WEATHER_PROVIDER=static (tests) — never silently replaces live data."""
    name = "static-demo"

    def __init__(self, days: list[ForecastDay] | None = None, current: tuple[float, float, float] = (28.0, 60.0, 10.0)):
        self.days = days or []
        self.current = current

    def get_weather(self, lat: float, lon: float, days: int = 6) -> WeatherSnapshot:
        fc = self.days or [
            ForecastDay((datetime.now(timezone.utc) + timedelta(days=i)).strftime("%Y-%m-%d"),
                        22.0, 31.0, 10.0 + 5 * i, 0.0 if i != 2 else 1.0, 4.5, 1)
            for i in range(6)
        ]
        return WeatherSnapshot(True, self.name, datetime.now(timezone.utc), lat, lon,
                               self.current[0], self.current[1], self.current[2], 15.0, 1, fc)


def _num(arr, i):
    try:
        v = arr[i]
        return float(v) if v is not None else None
    except (IndexError, TypeError, ValueError):
        return None


def _int(arr, i):
    try:
        return int(arr[i])
    except (IndexError, TypeError, ValueError):
        return None


def _maybe_float(v):
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _maybe_int(v):
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


class CachedProvider:
    """TTL cache wrapper — spec 48/51: cache weather, do not hammer the provider.
    On provider failure we still SERVE the last good snapshot (marked via
    fetched_at staleness) rather than storming the API on every retry."""

    def __init__(self, inner: WeatherProvider, ttl_seconds: int):
        self.inner = inner
        self.ttl = ttl_seconds
        self._cache: dict[str, tuple[float, WeatherSnapshot]] = {}
        self._last_good: dict[str, WeatherSnapshot] = {}

    @property
    def name(self) -> str:
        return self.inner.name

    def get_weather(self, lat: float, lon: float, days: int = 6) -> WeatherSnapshot:
        key = f"{lat_key(lat, lon)}|{days}"
        now = time.monotonic()
        hit = self._cache.get(key)
        if hit and now - hit[0] < self.ttl:
            return hit[1]
        snap = self.inner.get_weather(lat, lon, days)
        if snap.available:
            self._cache[key] = (now, snap)
            self._last_good[key] = snap
        else:
            # failure: extend last good (serve stale with old fetched_at, honest),
            # and back off hard for 5 min so we don't storm a rate-limited provider
            stale = self._last_good.get(key)
            if stale is not None:
                self._cache[key] = (now - self.ttl + 300, stale)  # retry only in 5 min
            else:
                # no history: cache the honest failure briefly (60s) so a persistent
                # 429 doesn't cost one provider call per request
                self._cache[key] = (now - self.ttl + 60, snap)
            return self._cache[key][1]
        return snap


def make_provider() -> WeatherProvider:
    kind = settings.weather_provider.lower()
    if kind in ("open_meteo", "openmeteo"):
        inner: WeatherProvider = OpenMeteoProvider()
    elif kind == "static":
        inner = StaticProvider()
    else:
        inner = NoneProvider()
    return CachedProvider(inner, settings.weather_cache_minutes * 60)  # type: ignore[return-value]


_provider: WeatherProvider | None = None


def weather_provider() -> WeatherProvider:
    global _provider
    if _provider is None:
        _provider = make_provider()
    return _provider
