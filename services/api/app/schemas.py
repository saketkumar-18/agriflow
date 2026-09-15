"""Pydantic v2 schemas — all API input validated server-side (spec rule 4/6)."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.engine import Urgency
from app.models import GrowthStage, IrrigationMethod, ReadingSource, Role


class Msg(BaseModel):
    error: str
    message: str


# ---------- auth ----------
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=2, max_length=160)
    phone: str | None = Field(default=None, max_length=32)
    language: Literal["en", "hi"] = "en"


class LoginIn(BaseModel):
    # login accepts any address shape (incl. reserved TLDs); registration validates strictly
    email: str = Field(min_length=5, max_length=254, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    password: str = Field(max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    full_name: str
    role: Role
    phone: str | None = None
    language: str
    is_active: bool
    alert_level: str = "medium"
    channel_push: bool = True
    channel_email: bool = False
    demo: bool = False
    created_at: datetime | None = None


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class PreferencesIn(BaseModel):
    alert_level: Literal["critical", "high", "medium", "low"] = "medium"
    channels: dict[Literal["push", "email"], bool] | None = None
    language: Literal["en", "hi"] | None = None


# ---------- farms / fields ----------
class FarmIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    location_text: str | None = Field(default=None, max_length=255)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    total_area: float | None = Field(default=None, gt=0, le=100000)
    area_unit: Literal["ha", "acre"] = "ha"


class FarmOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    location_text: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    total_area: float | None = None
    area_unit: str = "ha"
    field_count: int = 0
    demo: bool = False
    created_at: datetime
    updated_at: datetime


class FieldIn(BaseModel):
    name: str = Field(min_length=1, max_length=160)
    area: float = Field(gt=0, le=10000)
    area_unit: Literal["ha", "acre"] = "ha"
    soil_type_id: int
    crop_id: int
    growth_stage_code: GrowthStage = GrowthStage.VEGETATIVE
    irrigation_method: IrrigationMethod = IrrigationMethod.flood
    water_source: str | None = Field(default=None, max_length=80)
    boundary_geojson: dict | None = None


class FieldPatchIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    area: float | None = Field(default=None, gt=0, le=10000)
    soil_type_id: int | None = None
    crop_id: int | None = None
    growth_stage_code: GrowthStage | None = None
    irrigation_method: IrrigationMethod | None = None
    water_source: str | None = Field(default=None, max_length=80)


class SoilTypeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    field_capacity_pct: float
    wilting_point_pct: float
    bulk_density: float | None = None
    water_holding_capacity_mm_per_m: float | None = None
    is_estimate: bool = True
    label_key: str | None = None


class CropBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    scientific_name: str | None = None


class CropOut(CropBrief):
    root_depth_mm: float
    maturity_days: int | None = None
    stage_params: dict = {}
    advisory_key: str | None = None
    demo: bool = False


class FieldOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    farm_id: int
    name: str
    area: float
    area_unit: str
    soil_type: SoilTypeOut | None = None
    crop: CropBrief | None = None
    growth_stage_code: str = Field(validation_alias="growth_stage", serialization_alias="growth_stage_code")
    irrigation_method: IrrigationMethod
    water_source: str | None = None
    boundary_geojson: dict | None = None
    sensor_present: bool = False
    demo: bool = False
    created_at: datetime
    updated_at: datetime


# ---------- readings ----------
class ReadingIn(BaseModel):
    soil_moisture_pct: float = Field(ge=0, le=100)
    taken_at: datetime | None = None

    @field_validator("soil_moisture_pct")
    @classmethod
    def _impossible(cls, v: float) -> float:
        if v > 100 or v < 0:
            raise ValueError("validation.impossible_value")
        return v


class ReadingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    field_id: int
    value_pct: float = Field(validation_alias="value_pct", serialization_alias="value_pct")
    source: ReadingSource
    taken_at: datetime
    demo: bool = False


# ---------- weather (response shaping done in router from dataclass) ----------
class ForecastDayOut(BaseModel):
    day: str
    min_c: float | None = None
    max_c: float | None = None
    rain_prob_pct: float | None = None
    rain_mm: float | None = None
    et0_mm: float | None = None
    condition_code: int | None = None


class WeatherOut(BaseModel):
    available: bool
    provider: str
    fetched_at: datetime
    latitude: float
    longitude: float
    current: dict | None = None
    forecast: list[ForecastDayOut] = []
    recent_rainfall_mm: dict | None = None
    alert: dict | None = None
    reason: str | None = None


# ---------- recommendations ----------
class RecommendationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    field_id: int
    computed_at: datetime
    expires_at: datetime
    irrigation_needed: bool
    urgency: Urgency
    recommended_time: dict
    window_start: datetime | None = None
    window_end: datetime | None = None
    estimated_water_requirement: dict | None = None
    estimated_liters: float | None = None
    confidence: dict
    reasons: list
    warnings: list
    inputs_digest: dict
    engine_version: str
    override: dict | None = None
    disclaimer_key: str = "rec.disclaimer"
    demo: bool = False


class OverrideIn(BaseModel):
    action: Literal["defer", "approve", "cancel"]
    reason: str = Field(min_length=10, max_length=1000)


# ---------- irrigation events / feedback ----------
class IrrigationEventIn(BaseModel):
    field_id: int
    recommendation_id: int | None = None
    irrigated_at: datetime
    duration_minutes: float | None = Field(default=None, ge=0, le=24 * 60)
    amount_mm: float | None = Field(default=None, gt=0, le=200)
    liters: float | None = Field(default=None, gt=0, le=10_000_000)
    note: str | None = Field(default=None, max_length=500)
    idempotency_key: str | None = Field(default=None, max_length=64)

    @model_validator(mode="after")
    def _one_amount(self):
        if self.amount_mm is None and self.liters is None:
            raise ValueError("irrigation.amount_required")
        return self


class IrrigationEventOut(IrrigationEventIn):
    model_config = ConfigDict(from_attributes=True)
    id: int
    source: str
    demo: bool = False


class FeedbackIn(BaseModel):
    recommendation_id: int
    useful: bool | None = None
    did_irrigate: bool | None = None
    comment: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def _some_answer(self):
        if self.useful is None and self.did_irrigate is None and not self.comment:
            raise ValueError("feedback.empty")
        return self


# ---------- notifications ----------
class NotificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    type: str
    severity: str
    title_key: str
    params: dict = Field(validation_alias="params_json", serialization_alias="params")
    created_at: datetime
    read_at: datetime | None = None


# ---------- sensors ----------
class SensorIn(BaseModel):
    type: Literal["soil_moisture", "temperature", "humidity", "weather_station"] = "soil_moisture"
    manufacturer: str | None = Field(default=None, max_length=120)
    device_identifier: str = Field(min_length=3, max_length=120)


class SensorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    field_id: int
    type: str
    manufacturer: str | None = None
    device_identifier: str
    status: str
    installed_at: datetime
    last_seen_at: datetime | None = None


class SensorCreated(SensorOut):
    device_key: str | None = None  # populated by router; shown exactly once


class SensorReadingIn(BaseModel):
    soil_moisture_pct: float | None = Field(default=None, ge=0, le=100)
    temperature_c: float | None = Field(default=None, ge=-30, le=60)
    humidity_pct: float | None = Field(default=None, ge=0, le=100)
    battery_level: float | None = Field(default=None, ge=0, le=100)
    timestamp: datetime | None = None


# ---------- advisory / sync / admin ----------
class AdvisoryIn(BaseModel):
    field_id: int
    note: str = Field(min_length=3, max_length=2000)


class AdvisoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    field_id: int
    author_id: int
    note: str
    created_at: datetime


class SyncAction(BaseModel):
    local_id: str = Field(min_length=1, max_length=64)
    type: Literal["irrigation_event", "reading", "feedback"]
    payload: dict


class SyncBatchIn(BaseModel):
    actions: list[SyncAction] = Field(max_length=50)


class UserPatchIn(BaseModel):
    role: Role | None = None
    is_active: bool | None = None


class AssignAgronomistIn(BaseModel):
    user_id: int
