"""CachedProvider behaviour: TTL, stale-serve on failure, 5-min backoff,
honest unavailable when there is no last-good snapshot (rate-limit survival)."""
from __future__ import annotations

import datetime as dt

from app.weather import CachedProvider, ForecastDay, WeatherSnapshot, _unavailable


class ScriptedProvider:
    name = "scripted"

    def __init__(self, results):
        self.results = list(results)
        self.calls = 0

    def get_weather(self, lat, lon, days=6):
        self.calls += 1
        r = self.results.pop(0) if self.results else self.results_default()
        return r

    def results_default(self):
        raise AssertionError("provider called more times than scripted")


def _good():
    return WeatherSnapshot(True, "scripted", dt.datetime.now(dt.timezone.utc),
                           26.0, 91.0, temp_c=30.0,
                           forecast=[ForecastDay("2026-09-16", 22, 31, 10, 0, 4, 1)])


def _bad():
    return _unavailable("scripted", 26.0, 91.0, "weather.unavailable")


def test_ttl_serves_cache():
    p = ScriptedProvider([_good()])
    c = CachedProvider(p, 1800)
    a = c.get_weather(26, 91)
    b = c.get_weather(26, 91)
    assert a.available and b is a and p.calls == 1


def test_stale_served_on_failure_with_backoff():
    p = ScriptedProvider([_good(), _bad()])  # 3rd call would raise (not enough scripted)
    c = CachedProvider(p, 1800)
    c.get_weather(26, 91)
    c._cache.clear()  # simulate TTL expiry
    stale = c.get_weather(26, 91)
    assert stale.available and stale.temp_c == 30.0 and p.calls == 2
    again = c.get_weather(26, 91)  # inside backoff window: no provider call
    assert again.available and p.calls == 2


def test_honest_unavailable_without_history():
    p = ScriptedProvider([_bad()])
    c = CachedProvider(p, 1800)
    s = c.get_weather(26, 91)
    assert not s.available and s.reason == "weather.unavailable"
