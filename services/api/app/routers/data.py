"""Weather, readings, sensors (device-key ingestion), recommendations, dashboard summary."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import (
    Field, IrrigationRecommendation, ReadingSource, Role, Sensor,
    SensorReading, SoilMoistureReading, User,
)
from app.schemas import (
    ForecastDayOut, OverrideIn, ReadingIn, ReadingOut, RecommendationOut, SensorCreated,
    SensorIn, SensorOut, SensorReadingIn, WeatherOut,
)
from app.services import (
    audit, check_device_key, get_field_403, http_err, recommendation_to_dict, sensor_key_pair, store_recommendation,
)
from app.weather import weather_provider

router = APIRouter()


# ---------------------------------------------------------------- weather

def _weather_payload(field: Field) -> WeatherOut:
    farm = field.farm
    if farm.latitude is None or farm.longitude is None:
        return WeatherOut(available=False, provider="none",
                          fetched_at=datetime.now(timezone.utc),
                          latitude=0, longitude=0, reason="farm.no_location")
    snap = weather_provider().get_weather(farm.latitude, farm.longitude, days=6)
    if not snap.available:
        return WeatherOut(available=False, provider=snap.provider,
                          fetched_at=snap.fetched_at, latitude=snap.lat, longitude=snap.lon,
                          reason=snap.reason or "weather.unavailable")
    days = snap.forecast
    def _sum(n): return round(sum((d.rain_mm or 0.0) for d in days[:n]), 1)
    alert = None
    if days and days[0].max_c is not None and days[0].max_c >= 40:
        alert = {"key": "alerts.extreme_heat", "params": {"temp_c": days[0].max_c}}
    if _sum(2) >= 8 and days[0].rain_prob_pct and days[0].rain_prob_pct >= 50:
        alert = {"key": "alerts.rain_incoming", "params": {"mm": _sum(2)}}
    return WeatherOut(
        available=True, provider=snap.provider, fetched_at=snap.fetched_at,
        latitude=snap.lat, longitude=snap.lon,
        current={"temp_c": snap.temp_c, "humidity_pct": snap.humidity_pct,
                 "wind_kmh": snap.wind_kmh, "rain_prob_pct": snap.rain_prob_pct,
                 "condition_code": snap.condition_code,
                 "observed_at": snap.fetched_at.isoformat()},
        forecast=[ForecastDayOut(**vars(d)) for d in days],
        recent_rainfall_mm={"last_24h": _sum(1), "last_72h": _sum(3),
                            "last_7d": _sum(7)},
        alert=alert)


@router.get("/weather/field/{field_id}", response_model=WeatherOut)
def field_weather(field_id: int, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    field, _ = get_field_403(db, user, field_id)
    return _weather_payload(field)


# ---------------------------------------------------------------- readings

@router.post("/fields/{field_id}/readings", response_model=ReadingOut, status_code=201)
def add_reading(field_id: int, body: ReadingIn, request: Request,
                db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    field, _ = get_field_403(db, user, field_id, write=True)
    taken = body.taken_at or datetime.now(timezone.utc)
    if taken > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise http_err("validation.future_timestamp", "Reading timestamp is in the future", 422)
    row = SoilMoistureReading(field_id=field.id, value_pct=body.soil_moisture_pct,
                              source=ReadingSource.manual, taken_at=taken)
    db.add(row)
    db.flush()
    audit(db, request, user.id, "reading.create", "soil_moisture_reading", str(row.id),
          None, {"field_id": field.id, "value_pct": row.value_pct})
    db.commit()
    return row


@router.get("/fields/{field_id}/readings", response_model=list[ReadingOut])
def list_readings(field_id: int, limit: int = 50, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)):
    field, _ = get_field_403(db, user, field_id)
    return db.scalars(select(SoilMoistureReading)
                      .where(SoilMoistureReading.field_id == field.id)
                      .order_by(SoilMoistureReading.taken_at.desc())
                      .limit(min(limit, 200))).all()


# ---------------------------------------------------------------- sensors

@router.post("/fields/{field_id}/sensors", response_model=SensorCreated, status_code=201)
def create_sensor(field_id: int, body: SensorIn, request: Request,
                  db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    field, _ = get_field_403(db, user, field_id, write=True)
    if db.scalar(select(Sensor.id).where(Sensor.device_identifier == body.device_identifier)):
        raise http_err("sensor.duplicate_id", "Device identifier already registered", 409)
    key, key_hash = sensor_key_pair()
    s = Sensor(field_id=field.id, type=body.type, manufacturer=body.manufacturer,
               device_identifier=body.device_identifier, device_key_hash=key_hash)
    db.add(s)
    db.flush()
    audit(db, request, user.id, "sensor.create", "sensor", str(s.id),
          None, {"field_id": field.id, "device": s.device_identifier})
    db.commit()
    out = SensorCreated.model_validate(s)
    out.device_key = key  # shown exactly once; only its hash is stored
    return out


@router.get("/fields/{field_id}/sensors", response_model=list[SensorOut])
def list_sensors(field_id: int, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    field, _ = get_field_403(db, user, field_id)
    return db.scalars(select(Sensor).where(Sensor.field_id == field.id)).all()


def _resolve_sensor(db: Session, sensor_id: int,
                    x_device_key: str | None) -> Sensor:
    s = db.get(Sensor, sensor_id)
    if s is None:
        raise http_err("sensor.not_found", "Sensor not found", 404)
    if not x_device_key or not check_device_key(x_device_key, s.device_key_hash):
        raise http_err("sensor.auth_failed", "Invalid device key", 401)
    return s


@router.post("/sensors/{sensor_id}/readings", status_code=201)
def sensor_reading_in(
        sensor_id: int, body: SensorReadingIn,
        x_device_key: str | None = Header(default=None),
        db: Session = Depends(get_db)):
    """Device ingestion — MQTT gateway's HTTP sibling (docs/sensor-integration.md).
    Data-quality checks (spec 40): impossible values rejected by schema; spikes flagged."""
    s = _resolve_sensor(db, sensor_id, x_device_key)
    ts = body.timestamp or datetime.now(timezone.utc)
    if ts > datetime.now(timezone.utc) + timedelta(minutes=5):
        raise http_err("validation.future_timestamp", "Reading timestamp is in the future", 422)
    last = db.scalars(select(SensorReading)
                      .where(SensorReading.sensor_id == s.id)
                      .order_by(SensorReading.timestamp.desc()).limit(1)).first()
    flag = None
    if last and last.timestamp == ts and last.soil_moisture == body.soil_moisture_pct:
        flag = "duplicate"
    elif (last and body.soil_moisture_pct is not None and last.soil_moisture is not None
          and abs(body.soil_moisture_pct - last.soil_moisture) > 40):
        flag = "spike"
    row = SensorReading(sensor_id=s.id, timestamp=ts,
                        soil_moisture=body.soil_moisture_pct, temperature=body.temperature_c,
                        humidity=body.humidity_pct, battery_level=body.battery_level,
                        quality_flag=flag)
    db.add(row)
    s.last_seen_at = datetime.now(timezone.utc)
    s.status = "online"
    if body.soil_moisture_pct is not None and flag is None:
        db.add(SoilMoistureReading(field_id=s.field_id, value_pct=body.soil_moisture_pct,
                                   source=ReadingSource.sensor, taken_at=ts))
    db.commit()
    return {"id": row.id, "status": "ok", "quality_flag": flag}


@router.get("/sensors/{sensor_id}/readings")
def sensor_readings(sensor_id: int, limit: int = 100,
                    db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    field = None
    s = db.get(Sensor, sensor_id)
    if s is None:
        raise http_err("sensor.not_found", "Sensor not found", 404)
    field, _ = get_field_403(db, user, s.field_id)
    return db.scalars(select(SensorReading).where(SensorReading.sensor_id == s.id)
                      .order_by(SensorReading.timestamp.desc())
                      .limit(min(limit, 500))).all()


# ---------------------------------------------------------------- recommendations

@router.get("/recommendations/field/{field_id}", response_model=RecommendationOut)
def latest_recommendation(field_id: int, db: Session = Depends(get_db),
                          user: User = Depends(get_current_user)):
    field, _ = get_field_403(db, user, field_id)
    row = db.scalars(select(IrrigationRecommendation)
                     .where(IrrigationRecommendation.field_id == field.id)
                     .order_by(IrrigationRecommendation.computed_at.desc()).limit(1)).first()
    if row is None or row.expires_at < datetime.now(timezone.utc):
        row = store_recommendation(db, field)
    return RecommendationOut.model_validate(recommendation_to_dict(row))


@router.post("/recommendations/field/{field_id}/refresh", response_model=RecommendationOut)
def refresh_recommendation(field_id: int, request: Request,
                           db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    field, _ = get_field_403(db, user, field_id)
    row = store_recommendation(db, field)
    audit(db, request, user.id, "recommendation.refresh", "field", str(field.id))
    db.commit()
    return RecommendationOut.model_validate(recommendation_to_dict(row))


@router.get("/recommendations/field/{field_id}/history")
def recommendation_history(field_id: int, limit: int = 20,
                           db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    field, _ = get_field_403(db, user, field_id)
    rows = db.scalars(select(IrrigationRecommendation)
                      .where(IrrigationRecommendation.field_id == field.id)
                      .order_by(IrrigationRecommendation.computed_at.desc())
                      .limit(min(limit, 100))).all()
    return [recommendation_to_dict(r) for r in rows]


@router.post("/recommendations/{rec_id}/override", response_model=RecommendationOut)
def override_recommendation(rec_id: int, body: OverrideIn, request: Request,
                            db: Session = Depends(get_db),
                            user: User = Depends(get_current_user)):
    if user.role not in (Role.agronomist, Role.admin):
        raise http_err("rec.override_forbidden", "Only agronomists or admins can override", 403)
    row = db.get(IrrigationRecommendation, rec_id)
    if row is None:
        raise http_err("rec.not_found", "Recommendation not found", 404)
    field = db.get(Field, row.field_id)
    get_field_403(db, user, field.id)  # permission check (assigned farms)
    previous = {"override_action": row.override_action}
    row.override_action = body.action
    row.override_reason = body.reason  # required — every override records who/when/what/why (spec 46)
    row.override_by = user.id
    row.override_at = datetime.now(timezone.utc)
    if body.action == "cancel":
        row.irrigation_needed = False
    audit(db, request, user.id, "recommendation.override", "recommendation", str(row.id),
          previous, {"action": body.action, "reason": body.reason,
                     "field_id": row.field_id})
    db.commit()
    return RecommendationOut.model_validate(recommendation_to_dict(row))
