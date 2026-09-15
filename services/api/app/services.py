"""Service layer: permission helpers, recommendation orchestration, notifications,
analytics aggregation, audit. Business logic stays out of routers/UI (spec rule 7)."""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import engine as eng
from app.auth import hash_password, verify_password
from app.config import get_settings
from app.models import (
    AuditLog, Crop, Farm, Field, IrrigationEvent,
    IrrigationRecommendation, Notification, Role, Sensor,
    SoilMoistureReading, User, Urgency,
)
from app.weather import lat_key, weather_provider

log = logging.getLogger("agriflow.services")
settings = get_settings()

ERR = lambda code, msg, d=None: HTTPException(  # noqa: E731
    status.HTTP_400_BAD_REQUEST, detail={"error": {"code": code, "message": msg, "details": d}})


def http_err(code: str, msg: str, status_code: int = 400, details=None) -> HTTPException:
    return HTTPException(status_code, detail={"error": {"code": code, "message": msg, "details": details}})


def audit(db: Session, request: Request | None, user_id: int | None, action: str,
          resource_type: str, resource_id: str | None = None,
          previous: dict | None = None, new: dict | None = None) -> None:
    db.add(AuditLog(user_id=user_id, action=action, resource_type=resource_type,
                    resource_id=resource_id, previous_json=previous, new_json=new,
                    ip=request.client.host if request and request.client else None))


# ------------------------------------------------------------- permissions

def visible_farms(db: Session, user: User) -> list[Farm]:
    if user.role == Role.admin:
        return list(db.scalars(select(Farm).where(Farm.is_active)).all())
    if user.role == Role.agronomist:
        return list(db.scalars(select(Farm).where(Farm.assigned_agronomist_id == user.id,
                                                  Farm.is_active)).all())
    return list(db.scalars(select(Farm).where(Farm.farmer_id == user.id, Farm.is_active)).all())


def get_farm_403(db: Session, user: User, farm_id: int) -> Farm:
    farm = db.get(Farm, farm_id)
    if farm is None or not farm.is_active:
        raise http_err("farm.not_found", "Farm not found", 404)
    if user.role == Role.admin or farm.farmer_id == user.id:
        return farm
    if user.role == Role.agronomist and farm.assigned_agronomist_id == user.id:
        return farm
    raise http_err("farm.forbidden", "You do not have access to this farm", 403)


def get_field_403(db: Session, user: User, field_id: int, write: bool = False) -> tuple[Field, Farm]:
    field = db.get(Field, field_id)
    if field is None or not field.is_active:
        raise http_err("field.not_found", "Field not found", 404)
    farm = get_farm_403(db, user, field.farm_id)
    if write and user.role == Role.agronomist:
        raise http_err("field.readonly_agronomist", "Agronomists have read access to field data", 403)
    return field, farm


def field_area_ha(field: Field) -> float:
    return field.area * (0.404686 if field.area_unit == "acre" else 1.0)


# ------------------------------------------------------------- engine glue

def latest_moisture(db: Session, field_id: int) -> SoilMoistureReading | None:
    return db.scalars(select(SoilMoistureReading)
                      .where(SoilMoistureReading.field_id == field_id)
                      .order_by(SoilMoistureReading.taken_at.desc()).limit(1)).first()


def build_engine_input(db: Session, field: Field) -> eng.EngineInput:
    crop: Crop = field.crop
    stage_code = field.growth_stage.value
    sp = (crop.stage_params or {}).get(stage_code, {})
    kc = float(sp.get("kc", 1.0))
    critical = bool(sp.get("critical", False))
    fc = field.soil_type.field_capacity_pct
    pwp = field.soil_type.wilting_point_pct
    m = latest_moisture(db, field.id)
    moisture = eng.MoistureInput(
        value_pct=m.value_pct if m else None,
        source=m.source.value if m else None,
        taken_at=m.taken_at if m else None)

    last_event = db.scalars(select(IrrigationEvent)
                            .where(IrrigationEvent.field_id == field.id)
                            .order_by(IrrigationEvent.irrigated_at.desc()).limit(1)).first()
    days_since = None
    if last_event:
        days_since = (datetime.now(timezone.utc) - last_event.irrigated_at).total_seconds() / 86400.0

    farm = field.farm
    snap = None
    if farm.latitude is not None and farm.longitude is not None:
        snap = weather_provider().get_weather(farm.latitude, farm.longitude, days=6)

    available = bool(snap and snap.available)
    inp = eng.EngineInput(
        crop_name=crop.name, crop_id=crop.id, growth_stage=stage_code,
        kc=kc, critical_stage=critical, root_depth_mm=crop.root_depth_mm,
        field_capacity_pct=fc, wilting_point_pct=pwp,
        bulk_density=field.soil_type.bulk_density,
        area_ha=field_area_ha(field),
        irrigation_method=field.irrigation_method.value,
        moisture=moisture, days_since_irrigation=days_since,
        weather_available=available)

    if available and snap:
        inp.temp_c = snap.temp_c
        inp.humidity_pct = snap.humidity_pct
        inp.wind_kmh = snap.wind_kmh
        inp.rain_prob_next24_pct = snap.rain_prob_pct
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        days = [f for f in snap.forecast if f.day >= today][:3]
        inp.forecast_rain_mm_48h = sum((f.rain_mm or 0.0) for f in days[:2])
        # ET0: prefer provider value for today; else Hargreaves if temps known
        if days and days[0].et0_mm is not None:
            inp.et0_mm = days[0].et0_mm
            inp.temp_max_c = days[0].max_c
        elif snap.forecast:
            tmax = days[0].max_c if days else None
            tmin = days[0].min_c if days else None
            inp.temp_max_c = tmax
            if tmax is not None and tmin is not None:
                inp.et0_mm = hargreaves_et0(tmax, tmin, snap.temp_c)
        # recent rainfall from stored live observations (observed, not forecast;
        # demo rows excluded so demo history never leaks into live recommendations)
        from app.models import WeatherObservation
        obs_window = datetime.now(timezone.utc) - timedelta(hours=72)
        total = db.scalar(select(func.coalesce(func.sum(WeatherObservation.rain_mm), 0.0))
                          .where(WeatherObservation.lat_key == lat_key(farm.latitude, farm.longitude),
                                 WeatherObservation.observed_at >= obs_window,
                                 WeatherObservation.demo == False))  # noqa: E712
        inp.recent_rain_mm_72h = float(total or 0.0)
    return inp


def hargreaves_et0(tmax: float, tmin: float, tmean: float | None = None) -> float:
    """FAO-56 Hargreaves ET0 estimate (°C -> mm/day). Documented as an ESTIMATE
    requiring only temperature; extra-terrestrial radiation approximated by
    latitude-independent mid-latitude value (see docs/irrigation-engine.md)."""
    tmean = tmean if tmean is not None else (tmax + tmin) / 2.0
    if tmax - tmin <= 0:
        return max(0.0, 0.0023 * (tmean + 17.8) * 0.5)
    ra = 12.0  # equivalent mm/day radiation term, mid-latitude annual mean (documented assumption)
    return max(0.0, 0.0023 * (tmean + 17.8) * ((tmax - tmin) ** 0.5) * ra)


def store_recommendation(db: Session, field: Field) -> IrrigationRecommendation:
    inp = build_engine_input(db, field)
    rec = eng.compute_recommendation(inp)
    row = IrrigationRecommendation(
        field_id=field.id, irrigation_needed=rec.irrigation_needed,
        urgency=Urgency(rec.urgency.value),
        recommended_time_key=rec.recommended_time_key,
        window_start=rec.window_start, window_end=rec.window_end,
        water_mm=rec.water_mm, liters=rec.liters,
        confidence=rec.confidence,
        reasons_json=[r.to_json() for r in rec.reasons],
        warnings_json=[w.to_json() for w in rec.warnings],
        confidence_factors_json=[f.to_json() for f in rec.confidence_factors],
        inputs_digest_json=rec.inputs_digest,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.recommendation_ttl_hours),
        demo=bool(field.demo))
    db.add(row)
    maybe_create_alert(db, field, row, rec)
    db.commit()
    db.refresh(row)
    return row


# ------------------------------------------------------------- notifications

SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}


def user_wants(user: User, severity: str) -> bool:
    return SEVERITY_RANK.get(severity, 3) <= SEVERITY_RANK.get(user.alert_level, 2)


def notify(db: Session, user: User, ntype: str, severity: str, title_key: str,
           params: dict, dedupe_key: str) -> Notification | None:
    """In-app notification always stored; email ONLY if SMTP configured (no fake sends, spec 72)."""
    if not user_wants(user, severity):
        return None
    db.flush()  # session uses autoflush=False: surface pending inserts before dedupe check
    exists = db.scalar(select(Notification.id).where(Notification.dedupe_key == dedupe_key))
    if exists:
        return None
    ch = "inapp"
    if user.channel_email and settings.smtp_host:
        ch += ",email"
        try:
            from app import notify_email
            notify_email.send_async(user.email, title_key, params, user.language)
        except Exception as exc:  # pragma: no cover
            log.warning("email delivery failed: %s", exc)
    n = Notification(user_id=user.id, type=ntype, severity=severity, title_key=title_key,
                     params_json=params, dedupe_key=dedupe_key, channel_delivered=ch)
    db.add(n)
    return n


def maybe_create_alert(db: Session, field: Field, row: IrrigationRecommendation,
                       rec: eng.Recommendation) -> None:
    farm = field.farm
    farmer = db.get(User, farm.farmer_id)
    if farmer is None:
        return
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if row.irrigation_needed and row.urgency in (Urgency.HIGH, Urgency.CRITICAL):
        notify(db, farmer, "irrigation_needed",
               "critical" if row.urgency == Urgency.CRITICAL else "high",
               "alerts.irrigation_needed", {"field": field.name},
               f"irr:{field.id}:{today}:{row.urgency.value}")
    if row.irrigation_needed and row.urgency == Urgency.MEDIUM:
        notify(db, farmer, "irrigation_needed", "medium", "alerts.irrigation_review",
               {"field": field.name}, f"irr:{field.id}:{today}:MEDIUM")
    if row.warnings_json:
        for w in row.warnings_json:
            if w["key"] in ("warnings.sensor_offline_stale", "warnings.no_recent_moisture"):
                notify(db, farmer, "low_confidence", "medium", "alerts.low_confidence",
                       {"field": field.name}, f"conf:{field.id}:{today}")
            elif w["key"] == "warnings.weather_unavailable":
                notify(db, farmer, "weather_unavailable", "low", "alerts.weather_unavailable",
                       {"field": field.name}, f"wun:{field.id}:{today}")
    # rain incoming alert (from digest)
    if (rec.inputs_digest.get("rain_next_48h_mm") or 0) >= settings.rain_defer_mm:
        notify(db, farmer, "rain_incoming", "medium", "alerts.rain_incoming",
               {"mm": rec.inputs_digest["rain_next_48h_mm"]}, f"rain:{field.id}:{today}")
    if (rec.inputs_digest.get("temp_max_c") or 0) >= 40:
        notify(db, farmer, "extreme_heat", "high", "alerts.extreme_heat",
               {"temp_c": rec.inputs_digest.get("temp_max_c")}, f"heat:{field.id}:{today}")


def check_sensor_offline(db: Session) -> int:
    """Worker job: mark sensors silent > 24h offline + notify (spec 24/39)."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    count = 0
    sensors = db.scalars(select(Sensor)).all()
    for s in sensors:
        if s.last_seen_at and s.last_seen_at < cutoff and s.status == "online":
            s.status = "offline"
            count += 1
            field = db.get(Field, s.field_id)
            if field:
                farmer = db.get(User, field.farm.farmer_id)
                if farmer:
                    notify(db, farmer, "sensor_offline", "medium", "alerts.sensor_offline",
                           {"field": field.name}, f"sensor:{s.id}:{datetime.now(timezone.utc).strftime('%Y-%m-%d')}")
    db.commit()
    return count


# ------------------------------------------------------------- shaping

def recommendation_to_dict(row: IrrigationRecommendation) -> dict:
    water = {"value": row.water_mm, "unit": "mm"} if row.water_mm is not None else None
    conf_factors = row.confidence_factors_json or []
    level = "HIGH" if row.confidence >= 0.75 else ("MEDIUM" if row.confidence >= 0.5 else "LOW")
    return {
        "id": row.id, "field_id": row.field_id,
        "computed_at": row.computed_at, "expires_at": row.expires_at,
        "irrigation_needed": row.irrigation_needed, "urgency": row.urgency.value,
        "recommended_time": {"key": row.recommended_time_key, "params": {}},
        "window_start": row.window_start, "window_end": row.window_end,
        "estimated_water_requirement": water,
        "estimated_liters": row.liters,
        "confidence": {"score": row.confidence, "level": level, "factors": conf_factors},
        "reasons": row.reasons_json or [], "warnings": row.warnings_json or [],
        "inputs_digest": row.inputs_digest_json or {},
        "engine_version": row.engine_version,
        "override": ({"by_user_id": row.override_by, "action": row.override_action,
                      "reason": row.override_reason, "at": row.override_at}
                     if row.override_action else None),
        "disclaimer_key": "rec.disclaimer",
        "demo": row.demo,
    }


def sensor_key_pair() -> tuple[str, str]:
    key = secrets.token_urlsafe(24)
    return key, hash_password(key)


def check_device_key(raw: str, stored_hash: str) -> bool:
    return verify_password(raw, stored_hash)
