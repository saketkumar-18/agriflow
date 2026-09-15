"""Unit tests for the pure irrigation engine (spec 57: rules, water calc, thresholds)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.engine import (
    EngineInput, MoistureInput, Urgency, compute_recommendation,
    effective_rain_mm, moisture_deficit_pct_of_taw, taw_mm,
)

NOW = datetime(2026, 9, 15, 6, 0, tzinfo=timezone.utc)


def make_input(**kw) -> EngineInput:
    base = dict(
        crop_name="Wheat", crop_id=1, growth_stage="VEGETATIVE", kc=0.8,
        critical_stage=False, root_depth_mm=700, field_capacity_pct=22.0,
        wilting_point_pct=8.0, bulk_density=None, area_ha=1.0,
        irrigation_method="drip",
        moisture=MoistureInput(40.0, "manual", NOW - timedelta(hours=2)),
        temp_max_c=30.0, temp_c=28.0, humidity_pct=60.0, wind_kmh=10.0,
        rain_prob_next24_pct=20.0, forecast_rain_mm_48h=0.5,
        recent_rain_mm_72h=0.0, et0_mm=4.5, days_since_irrigation=6.0,
        now=NOW, weather_available=True)
    base.update(kw)
    return EngineInput(**base)


class TestWaterMath:
    def test_taw_positive_and_bounded(self):
        t = taw_mm(22.0, 8.0, 700, None)
        assert t == pytest.approx(98.0)

    def test_depletion_zero_at_field_capacity(self):
        assert moisture_deficit_pct_of_taw(22.0, 22.0, 8.0) == 0.0

    def test_depletion_one_at_wilting_point(self):
        assert moisture_deficit_pct_of_taw(8.0, 22.0, 8.0) == pytest.approx(1.0)

    def test_effective_rain_tapers_after_25mm(self):
        assert effective_rain_mm(10) == 10
        assert effective_rain_mm(25) == 25
        assert effective_rain_mm(45) == pytest.approx(37.0)


class TestRecommendation:
    def test_wet_soil_no_irrigation(self):
        rec = compute_recommendation(make_input(moisture=MoistureInput(21.0, "manual", NOW - timedelta(hours=2))))
        assert rec.irrigation_needed is False
        assert rec.water_mm is None or rec.water_mm == 0 or not rec.irrigation_needed
        assert rec.confidence >= 0.8

    def test_dry_soil_irrigation_needed_with_reasons(self):
        rec = compute_recommendation(make_input(moisture=MoistureInput(10.0, "manual", NOW - timedelta(hours=2))))
        assert rec.irrigation_needed is True
        keys = [r.key for r in rec.reasons]
        assert "reasons.soil_below_target" in keys
        assert rec.water_mm and rec.water_mm > 0
        assert rec.liters == pytest.approx(rec.water_mm * 10000, rel=0.01)  # 1 ha

    def test_gross_mm_respects_method_efficiency(self):
        # moderate deficit so the 50mm safety cap does not mask the difference
        drip = compute_recommendation(make_input(moisture=MoistureInput(14.0, "manual", NOW), irrigation_method="drip"))
        flood = compute_recommendation(make_input(moisture=MoistureInput(14.0, "manual", NOW), irrigation_method="flood"))
        assert drip.water_mm and flood.water_mm and flood.water_mm > drip.water_mm

    def test_water_cap_safety_rail(self):
        rec = compute_recommendation(make_input(moisture=MoistureInput(1.0, "sensor", NOW),
                                                et0_mm=20.0, temp_max_c=48.0))
        assert rec.water_mm is not None and rec.water_mm <= 50.0

    def test_rain_forecast_defers_irrigation(self):
        rec = compute_recommendation(make_input(
            moisture=MoistureInput(14.0, "manual", NOW - timedelta(hours=2)),
            forecast_rain_mm_48h=15.0, rain_prob_next24_pct=80.0))
        # either not needed, or deferred LOW urgency with rain reason
        assert (not rec.irrigation_needed) or (rec.urgency == Urgency.LOW and
               any(r.key == "reasons.rain_expected" for r in rec.reasons))

    def test_recent_rain_reduces_requirement(self):
        dry = compute_recommendation(make_input(moisture=MoistureInput(13.0, "manual", NOW)))
        rained = compute_recommendation(make_input(moisture=MoistureInput(13.0, "manual", NOW),
                                                   recent_rain_mm_72h=12.0))
        assert (rained.water_mm or 0) <= (dry.water_mm or 0)

    def test_critical_stage_tighter_threshold(self):
        normal = compute_recommendation(make_input(moisture=MoistureInput(16.0, "manual", NOW)))
        critical = compute_recommendation(make_input(moisture=MoistureInput(16.0, "manual", NOW),
                                                     growth_stage="FLOWERING", kc=1.15,
                                                     critical_stage=True))
        assert critical.irrigation_needed and (critical.water_mm or 0) >= (normal.water_mm or 0)
        assert any(r.key == "reasons.critical_stage" for r in critical.reasons)

    def test_stale_moisture_warns_and_lowers_confidence(self):
        fresh = compute_recommendation(make_input())
        stale = compute_recommendation(make_input(
            moisture=MoistureInput(10.0, "sensor", NOW - timedelta(hours=30))))
        assert any(w.key == "warnings.stale_moisture" for w in stale.warnings)
        assert stale.confidence < fresh.confidence

    def test_no_moisture_low_confidence_and_assumption_warning(self):
        rec = compute_recommendation(make_input(moisture=MoistureInput(None, None, None)))
        assert rec.confidence < 0.6
        assert any(w.key == "warnings.no_recent_moisture" for w in rec.warnings)
        assert any(w.key == "warnings.assumed_moisture" for w in rec.warnings)
        assert any(f.key == "conf.missing_moisture" and not f.ok for f in rec.confidence_factors)

    def test_weather_unavailable_degrades(self):
        rec = compute_recommendation(make_input(weather_available=False))
        assert any(w.key == "warnings.weather_unavailable" for w in rec.warnings)
        assert rec.confidence <= 0.70

    def test_confidence_never_exceeds_ceiling(self):
        rec = compute_recommendation(make_input())
        assert rec.confidence <= 0.95

    def test_every_recommendation_has_reasons_and_version(self):
        rec = compute_recommendation(make_input())
        assert rec.reasons and all(r.key.startswith("reasons.") for r in rec.reasons)
        assert rec.engine_version == "rules-1.0"

    def test_hot_temp_adds_reason(self):
        rec = compute_recommendation(make_input(temp_max_c=41.0))
        assert any(r.key == "reasons.high_temperature" for r in rec.reasons)

    def test_high_wind_adds_reason(self):
        rec = compute_recommendation(make_input(wind_kmh=30.0))
        assert any(r.key == "reasons.high_wind" for r in rec.reasons)
