"""Irrigation Decision Engine — transparent rules baseline (spec sections 14–20, 38).

Pure functions, no DB, no I/O: fully unit-testable. All user-facing strings are
i18n KEYS with params (never prose), so backend and frontend share translations.

Design:
  recommendation = f(moisture, crop stage Kc, soil, weather+forecast, recent rain,
                     days since irrigation, method efficiency, area)

Water requirement (documented in docs/irrigation-engine.md):
  TAW   = 1000 * (FC - PWP)/100 * root_depth_mm * bulk_density/1000   [mm]
  RAW   = TAW * MAD (MAD tighter during critical stages)
  deficit_mm = max(0, RAW - SMD_estimate)
  ETc     = ET0 * Kc
  gross_mm = (deficit target + ETc horizon) / application_efficiency
All outputs labelled as ESTIMATES. No claim of measurement precision.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum

from app.config import get_settings


class Urgency(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


EFFICIENCY = {  # application efficiency by irrigation method (FAO-56 Annex range, configurable)
    "drip": 0.90, "sprinkler": 0.75, "flood": 0.60, "furrow": 0.65,
    "manual": 0.70, "other": 0.65,
}
DEFAULT_EFFICIENCY = 0.65

# Confidence rubric (spec 20) — transparent, additive, capped.
CONF_MAX = 0.95  # never claim validated science; hard ceiling unless ML-validated later


@dataclass
class MoistureInput:
    value_pct: float | None
    source: str | None = None      # manual|sensor
    taken_at: datetime | None = None


@dataclass
class EngineInput:
    crop_name: str
    crop_id: int
    growth_stage: str
    kc: float                        # stage crop coefficient (from DB stage_params)
    critical_stage: bool
    root_depth_mm: float
    field_capacity_pct: float        # soil, volumetric %
    wilting_point_pct: float
    bulk_density: float | None       # Mg/m3 (t/m3)
    area_ha: float
    irrigation_method: str
    moisture: MoistureInput
    temp_max_c: float | None = None
    temp_c: float | None = None
    humidity_pct: float | None = None
    wind_kmh: float | None = None
    rain_prob_next24_pct: float | None = None
    forecast_rain_mm_48h: float = 0.0
    recent_rain_mm_72h: float = 0.0
    et0_mm: float | None = None      # daily ET0 estimate (provider ET0 or Hargreaves)
    days_since_irrigation: float | None = None
    now: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    weather_available: bool = True


@dataclass
class Reason:
    key: str
    params: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return {"key": self.key, "params": self.params}


@dataclass
class ConfidenceFactor:
    key: str
    ok: bool

    def to_json(self) -> dict:
        return {"key": self.key, "ok": self.ok}


@dataclass
class Recommendation:
    irrigation_needed: bool
    urgency: Urgency
    recommended_time_key: str
    window_start: datetime | None
    window_end: datetime | None
    water_mm: float | None
    liters: float | None
    confidence: float
    confidence_factors: list[ConfidenceFactor]
    reasons: list[Reason]
    warnings: list[Reason]
    inputs_digest: dict
    engine_version: str = "rules-1.0"

    @property
    def confidence_level(self) -> str:
        if self.confidence >= 0.75:
            return "HIGH"
        if self.confidence >= 0.5:
            return "MEDIUM"
        return "LOW"


# ---------------------------------------------------------------- calculations

def taw_mm(fc_pct: float, pwp_pct: float, root_depth_mm: float, bulk_density: float | None) -> float:
    """Total available water in root zone (mm). Values are % by volume with bd=1.0
    unless a bulk density is supplied (then adjusted). Never below 10mm floor guard."""
    delta = max(0.0, fc_pct - pwp_pct) / 100.0
    bd = bulk_density or 1.0
    # volumetric assumption already %VW; bd factor only when params came from wt% tables
    avail = delta * root_depth_mm * (1.0 if bulk_density is None else max(0.6, min(1.6, bd)))
    return max(10.0, avail)


def moisture_deficit_pct_of_taw(moisture_pct: float, fc_pct: float, pwp_pct: float) -> float:
    """Fraction of TAW already depleted (0 = full, 1 = at wilting point)."""
    taw_range = max(1e-6, fc_pct - pwp_pct)
    return max(0.0, min(1.3, (fc_pct - moisture_pct) / taw_range))


def effective_rain_mm(rain_mm: float) -> float:
    """Effective rainfall estimate (simple): full up to 25mm, tapering after (documented)."""
    if rain_mm <= 0:
        return 0.0
    if rain_mm <= 25:
        return rain_mm
    return 25 + (rain_mm - 25) * 0.6


def compute_recommendation(inp: EngineInput) -> Recommendation:
    s = get_settings()
    reasons: list[Reason] = []
    warnings: list[Reason] = []
    factors: list[ConfidenceFactor] = []
    fc, pwp = inp.field_capacity_pct, inp.wilting_point_pct
    taw = taw_mm(fc, pwp, inp.root_depth_mm, inp.bulk_density)
    mad = s.critical_mad if inp.critical_stage else s.default_mad
    raw = taw * mad  # readily available water threshold (mm)

    # --- moisture evaluation (with staleness policy, spec 39) ---
    m = inp.moisture
    moisture_ok = False
    age_hours: float | None = None
    depletion = 0.0
    smm_remaining_mm = 0.0
    if m.value_pct is not None and m.taken_at is not None:
        age_hours = max(0.0, (inp.now - m.taken_at).total_seconds() / 3600.0)
        if age_hours <= s.moisture_max_age_hours and 0.0 <= m.value_pct <= 100.0:
            moisture_ok = True
            depletion = moisture_deficit_pct_of_taw(m.value_pct, fc, pwp)
            smm_remaining_mm = max(0.0, (1.0 - depletion) * taw)
            if age_hours > s.moisture_fresh_hours:
                warnings.append(Reason("warnings.stale_moisture", {"age_hours": round(age_hours, 1)}))
        else:
            warnings.append(Reason("warnings.sensor_offline_stale", {"age_hours": round(age_hours, 1)}))
    elif m.value_pct is not None:
        warnings.append(Reason("warnings.missing_timestamp"))

    if not moisture_ok:
        warnings.append(Reason("warnings.no_recent_moisture"))

    # --- rain handling (forecast + recent) ---
    rain48 = inp.forecast_rain_mm_48h
    rain_prob = inp.rain_prob_next24_pct
    rain_confident = rain_prob is None or rain_prob >= s.rain_prob_gate
    defer_for_rain = (rain48 >= s.rain_defer_mm and rain_confident)
    eff_recent = effective_rain_mm(inp.recent_rain_mm_72h)

    # --- ETc & demand ---
    et0 = inp.et0_mm
    etc = (et0 * inp.kc) if et0 is not None else None
    temp_boost = 0.0
    if inp.temp_max_c is not None and inp.temp_max_c >= 35.0:
        temp_boost = min(2.5, (inp.temp_max_c - 35.0) * 0.5)
        reasons.append(Reason("reasons.high_temperature", {"temp_c": round(inp.temp_max_c, 1)}))
    if inp.wind_kmh is not None and inp.wind_kmh >= 25.0:
        reasons.append(Reason("reasons.high_wind", {"wind_kmh": round(inp.wind_kmh, 1)}))

    # --- irrigation need ---
    # deficit against RAW over a 2-day planning horizon
    if moisture_ok:
        deficit = max(0.0, raw - smm_remaining_mm)
    else:
        # no trustworthy moisture: assume 50% depletion of TAW (documented estimate)
        deficit = max(0.0, raw - 0.5 * taw)
        warnings.append(Reason("warnings.assumed_moisture"))
    horizon_days = 2.0
    demand = (etc or 0.0) * horizon_days + temp_boost
    need_mm_net = deficit + demand - min(eff_recent, deficit)  # recent rain offsets deficit only
    if defer_for_rain:
        need_mm_net = max(0.0, need_mm_net - rain48 * 0.5)  # half of expected rain counted (conservative)

    efficiency = EFFICIENCY.get(inp.irrigation_method, DEFAULT_EFFICIENCY)
    gross_mm = need_mm_net / efficiency if need_mm_net > 0 else 0.0
    gross_mm = min(gross_mm, 50.0)  # agronomic cap guard: never recommend flooding (spec 38 safety rail)

    irrigation_needed = (need_mm_net > max(2.0, raw * 0.15)) or (moisture_ok and depletion > mad)

    # --- reasons ---
    if moisture_ok and depletion > mad:
        reasons.append(Reason("reasons.soil_below_target",
                              {"value": round(m.value_pct, 1), "target": round(fc - mad * (fc - pwp), 1)}))
    elif moisture_ok and depletion > mad * 0.8:
        reasons.append(Reason("reasons.soil_approaching_threshold",
                              {"value": round(m.value_pct, 1)}))
    if inp.rain_prob_next24_pct is not None and inp.rain_prob_next24_pct < 30 and inp.weather_available:
        reasons.append(Reason("reasons.low_rain_probability", {"prob": round(inp.rain_prob_next24_pct)}))
    if inp.critical_stage:
        reasons.append(Reason("reasons.critical_stage", {"stage": inp.growth_stage.lower(), "crop": inp.crop_name.lower()}))
    if inp.days_since_irrigation is not None and inp.days_since_irrigation >= 7:
        reasons.append(Reason("reasons.long_since_irrigation", {"days": round(inp.days_since_irrigation)}))
    if defer_for_rain:
        reasons.append(Reason("reasons.rain_expected", {"mm": round(rain48, 1)}))
    if not reasons:
        reasons.append(Reason("reasons.conditions_nominal"))

    # --- urgency + timing ---
    if irrigation_needed:
        if defer_for_rain:
            urgency = Urgency.LOW
            time_key, window = "time.after_rain_check", (inp.now + timedelta(days=2), inp.now + timedelta(days=3))
            warnings.append(Reason("warnings.deferred_for_rain", {"mm": round(rain48, 1)}))
        elif depletion > min(0.95, mad + 0.25) or (inp.critical_stage and depletion > mad + 0.15):
            urgency = Urgency.CRITICAL if depletion > mad + 0.35 else Urgency.HIGH
            time_key, window = "time.today_evening", (inp.now, inp.now + timedelta(hours=12))
        elif depletion > mad or (etc or 0) > 5.0:
            urgency = Urgency.MEDIUM
            time_key, window = "time.tomorrow_morning", (inp.now + timedelta(days=1), inp.now + timedelta(days=1, hours=8))
        else:
            urgency = Urgency.LOW
            time_key, window = "time.in_two_days", (inp.now + timedelta(days=2), inp.now + timedelta(days=2, hours=8))
    else:
        urgency = Urgency.LOW
        time_key, window = "time.no_action_needed", (None, None)

    # --- confidence (transparent rubric, spec 20) ---
    # additive components; absent trustworthy moisture multiplies DOWN (never up).
    conf = 0.22
    if moisture_ok:
        fresh = age_hours is not None and age_hours <= s.moisture_fresh_hours
        conf += 0.35 if fresh else 0.22
        factors.append(ConfidenceFactor("conf.has_recent_moisture", True))
    else:
        factors.append(ConfidenceFactor("conf.missing_moisture", False))
    if inp.weather_available:
        conf += 0.20
        factors.append(ConfidenceFactor("conf.weather_available", True))
    else:
        factors.append(ConfidenceFactor("conf.weather_unavailable", False))
        warnings.append(Reason("warnings.weather_unavailable"))
    if inp.et0_mm is not None:
        conf += 0.08
        factors.append(ConfidenceFactor("conf.et0_available", True))
    else:
        factors.append(ConfidenceFactor("conf.et0_missing", False))
    factors.append(ConfidenceFactor("conf.crop_known", True))
    factors.append(ConfidenceFactor("conf.soil_known", True))
    if not moisture_ok:
        conf *= 0.60
    conf = round(min(CONF_MAX, max(0.20, conf)), 2)

    liters = round(gross_mm * 10000.0 * inp.area_ha) if (irrigation_needed and gross_mm > 0) else None
    digest = {
        "moisture": ({"value": round(m.value_pct, 1), "source": m.source, "age_hours": round(age_hours, 1)}
                     if moisture_ok else None),
        "rain_next_24h_pct": rain_prob,
        "rain_next_48h_mm": round(rain48, 1),
        "recent_rain_72h_mm": round(inp.recent_rain_mm_72h, 1),
        "et0_mm": round(et0, 2) if et0 is not None else None,
        "etc_mm": round(etc, 2) if etc is not None else None,
        "taw_mm": round(taw, 1), "raw_mm": round(raw, 1),
        "depletion_pct": round(depletion * 100, 1) if moisture_ok else None,
        "mad_pct": round(mad * 100),
        "efficiency": efficiency,
        "crop": inp.crop_name, "stage": inp.growth_stage,
    }

    return Recommendation(
        irrigation_needed=irrigation_needed, urgency=urgency,
        recommended_time_key=time_key, window_start=window[0], window_end=window[1],
        water_mm=round(gross_mm, 1) if irrigation_needed and gross_mm > 0 else None,
        liters=liters, confidence=conf, confidence_factors=factors,
        reasons=reasons[:5], warnings=warnings[:5], inputs_digest=digest,
    )
