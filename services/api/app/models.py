"""SQLAlchemy models for the AgriFlow platform.

All datetimes are stored in UTC. `demo=True` marks seeded synthetic records.
Field-level validation (ranges) happens in Pydantic schemas AND engine guards,
never trusting client-side calculations (master spec rule 6/16).
"""
from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    JSON, Boolean, DateTime, Enum, Float, ForeignKey, Index, Integer,
    String, Text, TypeDecorator, UniqueConstraint
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UTCDateTime(TypeDecorator):
    """Always tz-aware UTC in Python, regardless of backend (SQLite drops tzinfo)."""
    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Role(str, enum.Enum):
    farmer = "farmer"
    agronomist = "agronomist"
    admin = "admin"


class GrowthStage(str, enum.Enum):
    GERMINATION = "GERMINATION"
    VEGETATIVE = "VEGETATIVE"
    FLOWERING = "FLOWERING"
    FRUITING = "FRUITING"
    MATURITY = "MATURITY"
    HARVEST = "HARVEST"


class IrrigationMethod(str, enum.Enum):
    drip = "drip"
    sprinkler = "sprinkler"
    flood = "flood"
    furrow = "furrow"
    manual = "manual"
    other = "other"


class ReadingSource(str, enum.Enum):
    manual = "manual"
    sensor = "sensor"


class Urgency(str, enum.Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SensorStatus(str, enum.Enum):
    online = "online"
    offline = "offline"


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(160))
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    role: Mapped[Role] = mapped_column(Enum(Role), default=Role.farmer)
    language: Mapped[str] = mapped_column(String(8), default="en")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # notification prefs
    alert_level: Mapped[str] = mapped_column(String(16), default="medium")  # critical|high|medium|low
    channel_push: Mapped[bool] = mapped_column(Boolean, default=True)
    channel_email: Mapped[bool] = mapped_column(Boolean, default=False)
    demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    farms: Mapped[list[Farm]] = relationship(
        primaryjoin="User.id == Farm.farmer_id", back_populates="farmer",
        foreign_keys="Farm.farmer_id")


class Farm(Base):
    __tablename__ = "farms"
    id: Mapped[int] = mapped_column(primary_key=True)
    farmer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    location_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_area: Mapped[float | None] = mapped_column(Float, nullable=True)
    area_unit: Mapped[str] = mapped_column(String(8), default="ha")
    assigned_agronomist_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)  # soft delete
    demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    farmer: Mapped[User] = relationship(
        primaryjoin="Farm.farmer_id == User.id", back_populates="farms",
        foreign_keys="Farm.farmer_id")
    fields: Mapped[list[Field]] = relationship(back_populates="farm", cascade="all, delete-orphan")


class Field(Base):
    __tablename__ = "fields"
    id: Mapped[int] = mapped_column(primary_key=True)
    farm_id: Mapped[int] = mapped_column(ForeignKey("farms.id"), index=True)
    name: Mapped[str] = mapped_column(String(160))
    area: Mapped[float] = mapped_column(Float)  # in area_unit
    area_unit: Mapped[str] = mapped_column(String(8), default="ha")
    soil_type_id: Mapped[int] = mapped_column(ForeignKey("soil_types.id"))
    crop_id: Mapped[int] = mapped_column(ForeignKey("crops.id"))
    growth_stage: Mapped[GrowthStage] = mapped_column(Enum(GrowthStage), default=GrowthStage.VEGETATIVE)
    sow_date: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    irrigation_method: Mapped[IrrigationMethod] = mapped_column(Enum(IrrigationMethod), default=IrrigationMethod.flood)
    water_source: Mapped[str | None] = mapped_column(String(80), nullable=True)
    boundary_geojson: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, onupdate=utcnow)

    farm: Mapped[Farm] = relationship(back_populates="fields")
    crop: Mapped[Crop] = relationship()
    soil_type: Mapped[SoilType] = relationship()
    sensors: Mapped[list[Sensor]] = relationship(back_populates="field")


class Crop(Base):
    """Configurable crop database (spec section 7 — never hard-code crop assumptions)."""
    __tablename__ = "crops"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    scientific_name: Mapped[str | None] = mapped_column(String(160), nullable=True)
    root_depth_mm: Mapped[float] = mapped_column(Float, default=500.0)
    maturity_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # per-stage: {stage_code: {kc, critical, duration_days}}
    stage_params: Mapped[dict] = mapped_column(JSON, default=dict)
    advisory_key: Mapped[str | None] = mapped_column(String(120), nullable=True)
    demo: Mapped[bool] = mapped_column(Boolean, default=False)


class SoilType(Base):
    __tablename__ = "soil_types"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    field_capacity_pct: Mapped[float] = mapped_column(Float)
    wilting_point_pct: Mapped[float] = mapped_column(Float)
    bulk_density: Mapped[float | None] = mapped_column(Float, nullable=True)
    water_holding_capacity_mm_per_m: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_estimate: Mapped[bool] = mapped_column(Boolean, default=True)  # spec 9: label estimates
    label_key: Mapped[str | None] = mapped_column(String(80), nullable=True)


class Sensor(Base):
    __tablename__ = "sensors"
    id: Mapped[int] = mapped_column(primary_key=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id"), index=True)
    type: Mapped[str] = mapped_column(String(40), default="soil_moisture")
    manufacturer: Mapped[str | None] = mapped_column(String(120), nullable=True)
    device_identifier: Mapped[str] = mapped_column(String(120), unique=True)
    device_key_hash: Mapped[str] = mapped_column(String(255))
    status: Mapped[SensorStatus] = mapped_column(Enum(SensorStatus), default=SensorStatus.online)
    installed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    last_seen_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    demo: Mapped[bool] = mapped_column(Boolean, default=False)

    field: Mapped[Field] = relationship(back_populates="sensors")
    readings: Mapped[list[SensorReading]] = relationship(back_populates="sensor")


class SensorReading(Base):
    __tablename__ = "sensor_readings"
    __table_args__ = (
        Index("ix_sensor_readings_sensor_ts", "sensor_id", "timestamp"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    sensor_id: Mapped[int] = mapped_column(ForeignKey("sensors.id"), index=True)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    soil_moisture: Mapped[float | None] = mapped_column(Float, nullable=True)  # % VWC, 0..100
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)
    humidity: Mapped[float | None] = mapped_column(Float, nullable=True)
    battery_level: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality_flag: Mapped[str | None] = mapped_column(String(24), nullable=True)  # None|spike|duplicate
    demo: Mapped[bool] = mapped_column(Boolean, default=False)

    sensor: Mapped[Sensor] = relationship(back_populates="readings")


class SoilMoistureReading(Base):
    """Unified manual + sensor-derived moisture record used by the engine."""
    __tablename__ = "soil_moisture_readings"
    __table_args__ = (
        Index("ix_smr_field_taken", "field_id", "taken_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id"), index=True)
    value_pct: Mapped[float] = mapped_column(Float)  # validated 0..100
    source: Mapped[ReadingSource] = mapped_column(Enum(ReadingSource))
    taken_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    demo: Mapped[bool] = mapped_column(Boolean, default=False)


class WeatherObservation(Base):
    __tablename__ = "weather_observations"
    __table_args__ = (
        UniqueConstraint("lat_key", "observed_at", name="uq_weather_obs"),
        Index("ix_weather_obs_latkey_ts", "lat_key", "observed_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    lat_key: Mapped[str] = mapped_column(String(16), index=True)  # rounded to 2dp to protect exact farm coords
    observed_at: Mapped[datetime] = mapped_column(UTCDateTime)
    temp_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    humidity_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_kmh: Mapped[float | None] = mapped_column(Float, nullable=True)
    rain_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    et0_mm: Mapped[float | None] = mapped_column(Float, nullable=True)  # Hargreaves estimate
    tmax_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    tmin_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    provider: Mapped[str] = mapped_column(String(40))
    demo: Mapped[bool] = mapped_column(Boolean, default=False)


class WeatherForecast(Base):
    __tablename__ = "weather_forecasts"
    __table_args__ = (
        UniqueConstraint("lat_key", "day", "generated_at", name="uq_weather_fc"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    lat_key: Mapped[str] = mapped_column(String(16), index=True)
    generated_at: Mapped[datetime] = mapped_column(UTCDateTime)
    day: Mapped[str] = mapped_column(String(10))  # YYYY-MM-DD
    min_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    max_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    rain_prob_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    rain_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    et0_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    condition_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    provider: Mapped[str] = mapped_column(String(40))
    demo: Mapped[bool] = mapped_column(Boolean, default=False)


class IrrigationEvent(Base):
    __tablename__ = "irrigation_events"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_irrigation_idempotency"),
        Index("ix_ie_field_time", "field_id", "irrigated_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id"), index=True)
    recommendation_id: Mapped[int | None] = mapped_column(ForeignKey("irrigation_recommendations.id"), nullable=True)
    farmer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    irrigated_at: Mapped[datetime] = mapped_column(UTCDateTime)
    duration_minutes: Mapped[float | None] = mapped_column(Float, nullable=True)
    amount_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    liters: Mapped[float | None] = mapped_column(Float, nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source: Mapped[str] = mapped_column(String(10), default="manual")  # manual | sync
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    demo: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class IrrigationRecommendation(Base):
    __tablename__ = "irrigation_recommendations"
    __table_args__ = (
        Index("ix_rec_field_computed", "field_id", "computed_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id"), index=True)
    computed_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)
    irrigation_needed: Mapped[bool] = mapped_column(Boolean)
    urgency: Mapped[Urgency] = mapped_column(Enum(Urgency))
    recommended_time_key: Mapped[str] = mapped_column(String(60))
    window_start: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    window_end: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    water_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    liters: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float] = mapped_column(Float)
    reasons_json: Mapped[list] = mapped_column(JSON, default=list)
    warnings_json: Mapped[list] = mapped_column(JSON, default=list)
    confidence_factors_json: Mapped[list] = mapped_column(JSON, default=list)
    inputs_digest_json: Mapped[dict] = mapped_column(JSON, default=dict)
    engine_version: Mapped[str] = mapped_column(String(40), default="rules-1.0")
    # agronomist override
    override_action: Mapped[str | None] = mapped_column(String(16), nullable=True)  # defer|approve|cancel
    override_reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    override_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    override_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    demo: Mapped[bool] = mapped_column(Boolean, default=False)


class FarmerFeedback(Base):
    __tablename__ = "farmer_feedback"
    id: Mapped[int] = mapped_column(primary_key=True)
    recommendation_id: Mapped[int] = mapped_column(ForeignKey("irrigation_recommendations.id"), index=True)
    farmer_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    useful: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    did_irrigate: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    comment: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("user_id", "dedupe_key", name="uq_notification_dedupe"),
        Index("ix_notif_user_unread", "user_id", "read_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(String(32))
    severity: Mapped[str] = mapped_column(String(10), default="medium")
    title_key: Mapped[str] = mapped_column(String(120))
    params_json: Mapped[dict] = mapped_column(JSON, default=dict)
    dedupe_key: Mapped[str] = mapped_column(String(160))
    channel_delivered: Mapped[str | None] = mapped_column(String(40), nullable=True)  # "inapp,email" etc (real only)
    read_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Advisory(Base):
    __tablename__ = "advisories"
    id: Mapped[int] = mapped_column(primary_key=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("fields.id"), index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_user_ts", "user_id", "created_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(64))  # e.g. recommendation.override
    resource_type: Mapped[str] = mapped_column(String(32))
    resource_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    previous_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)


class Job(Base):
    """DB-backed background job queue (worker long-polls this). Portable: no Redis needed."""
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_status_due", "status", "due_at"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(40))  # weather_sync | recommendation | notify | cleanup
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(12), default="pending", index=True)  # pending|running|done|failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    due_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    dedupe_key: Mapped[str | None] = mapped_column(String(160), nullable=True, unique=True)
