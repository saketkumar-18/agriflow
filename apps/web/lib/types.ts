// Typed interfaces mirroring docs/api-contract.md (v1, frozen) exactly.

export type Role = "farmer" | "agronomist" | "admin";
export type AreaUnit = "ha" | "acre";
export type IrrigationMethod =
  | "drip"
  | "sprinkler"
  | "flood"
  | "furrow"
  | "manual"
  | "other";

/** Error envelope: {"error": {"code", "message", "details"}} */
export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details: Record<string, unknown> | null;
  };
}

export interface Paginated<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
}

/** i18n key + params, shared by reasons/warnings/time/alerts/notifications. */
export interface I18nText {
  key: string;
  params?: Record<string, string | number | boolean> | null;
  window_start?: string | null;
  window_end?: string | null;
}

export interface User {
  id: number;
  email: string;
  full_name: string;
  role: Role;
  phone: string | null;
  language: string;
  created_at: string;
  is_active: boolean;
  demo?: boolean;
}

export interface LoginResponse {
  access_token: string;
  expires_in?: number;
  token_type?: string;
  user: User;
}

export type AlertLevel = "critical" | "high" | "medium" | "low";

export interface NotificationPreferences {
  alert_level: AlertLevel;
  channels: { push: boolean; email: boolean };
}

export interface Farm {
  id: number;
  name: string;
  location_text: string | null;
  latitude: number | null;
  longitude: number | null;
  total_area: number | null;
  area_unit: AreaUnit | null;
  field_count: number;
  created_at: string;
  updated_at: string;
  demo?: boolean;
}

export interface FarmSummaryField {
  id: number;
  name: string;
  crop_name: string;
  growth_stage: string;
  soil_moisture: {
    value: number;
    source: "manual" | "sensor" | "none";
    measured_at: string | null;
    age_hours: number | null;
  } | null;
  recommendation: Recommendation | null;
  status: "needs_irrigation" | "review" | "ok" | "unknown";
}

export interface FarmSummary {
  farm: Farm;
  fields: FarmSummaryField[];
  weather_snapshot: WeatherResponse;
  generated_at: string;
}

export interface SoilType {
  id: number;
  name: string;
  field_capacity_pct: number;
  wilting_point_pct: number;
  bulk_density: number;
  water_holding_capacity_mm_per_m: number;
  is_estimate: boolean;
  label_key: string;
}

export interface CropStage {
  code: string;
  kc: number;
  critical: boolean;
  label_key: string;
}

export interface Crop {
  id: number;
  name: string;
  scientific_name: string | null;
  root_depth_mm: number;
  maturity_days: number;
  stages: CropStage[];
  advisory_text_key: string;
  demo?: boolean;
}

export interface CropBrief {
  id: number;
  name: string;
  scientific_name?: string | null;
  stages?: CropStage[];
  advisory_text_key?: string;
}

export interface Field {
  id: number;
  farm_id: number;
  name: string;
  area: number;
  area_unit: AreaUnit;
  soil_type: SoilType;
  crop: CropBrief;
  growth_stage_code: string;
  irrigation_method: IrrigationMethod;
  water_source: string | null;
  boundary_geojson: Record<string, unknown> | null;
  sensor_present: boolean;
  created_at: string;
  updated_at: string;
  demo?: boolean;
}

export interface FieldDetail {
  field: Field;
  latest_reading: Reading | null;
  recommendation: Recommendation | null;
  weather: WeatherResponse;
}

// ---------- Weather ----------

export interface WeatherCurrent {
  temp_c: number;
  humidity_pct: number;
  wind_kmh: number;
  rain_prob_pct: number;
  condition_code: number;
  observed_at: string;
}

export interface WeatherForecastDay {
  day: string;
  min_c: number;
  max_c: number;
  rain_prob_pct: number;
  rain_mm: number;
  condition_code: number;
}

export interface RecentRainfall {
  last_24h: number;
  last_72h: number;
  last_7d: number;
}

export interface WeatherAvailable {
  available: true;
  provider: string;
  fetched_at: string;
  latitude: number;
  longitude: number;
  current: WeatherCurrent;
  forecast: WeatherForecastDay[];
  recent_rainfall_mm: RecentRainfall;
  alert: I18nText | null;
}

export interface WeatherUnavailable {
  available: false;
  provider: "none";
  reason: string; // "weather.not_configured" | "weather.unavailable"
}

export type WeatherResponse = WeatherAvailable | WeatherUnavailable;

// ---------- Readings / sensors ----------

export interface Reading {
  id: number;
  field_id: number;
  value_pct: number;
  source: "manual" | "sensor";
  taken_at: string;
  demo?: boolean;
}

export interface Sensor {
  id: number;
  field_id: number;
  type: string;
  manufacturer: string | null;
  device_identifier: string;
  status: "online" | "offline";
  installed_at: string;
  last_seen_at: string | null;
}

// ---------- Recommendations ----------

export type Urgency = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type ConfidenceLevel = "LOW" | "MEDIUM" | "HIGH";

export interface ConfidenceFactor {
  key: string;
  ok: boolean;
}

export interface Confidence {
  score: number;
  level: ConfidenceLevel;
  factors: ConfidenceFactor[];
}

export interface RecommendationOverride {
  by_user_id: number;
  action: "defer" | "approve" | "cancel";
  reason: string;
  at: string;
}

export interface InputsDigest {
  moisture?: { value: number; source: string; age_hours: number | null } | null;
  rain_next_24h_mm?: number | null;
  et0_mm?: number | null;
  crop?: string | null;
  stage?: string | null;
  soil?: string | null;
}

export interface Recommendation {
  id: number;
  field_id: number;
  computed_at: string;
  expires_at: string;
  irrigation_needed: boolean;
  urgency: Urgency;
  recommended_time: I18nText | null;
  estimated_water_requirement: { value: number; unit: string } | null;
  estimated_liters: number | null;
  confidence: Confidence;
  reasons: I18nText[];
  warnings: I18nText[];
  inputs_digest: InputsDigest;
  engine_version: string;
  override: RecommendationOverride | null;
  disclaimer_key: string;
  demo?: boolean;
}

// ---------- Events / feedback ----------

export interface IrrigationEvent {
  id: number;
  field_id: number;
  recommendation_id: number | null;
  irrigated_at: string;
  duration_minutes: number | null;
  amount_mm: number | null;
  liters: number | null;
  note: string | null;
  source: "manual" | "sync";
  demo?: boolean;
}

export interface IrrigationEventCreate {
  field_id: number;
  recommendation_id?: number | null;
  irrigated_at: string;
  duration_minutes?: number | null;
  amount_mm?: number | null;
  liters?: number | null;
  note?: string | null;
  idempotency_key: string;
}

// ---------- Notifications ----------

export type NotificationType =
  | "irrigation_needed"
  | "rain_incoming"
  | "extreme_heat"
  | "sensor_offline"
  | "low_confidence"
  | "advisory";

export interface AppNotification {
  id: number;
  type: NotificationType;
  severity: string;
  title_key: string;
  params: Record<string, string | number | boolean> | null;
  created_at: string;
  read_at: string | null;
}

// ---------- Analytics ----------

export interface AnalyticsWeekly {
  week: string;
  irrigated_liters: number;
  recommended_liters: number;
}

export interface FarmAnalytics {
  month: string;
  total_irrigation_liters: number;
  recommended_liters: number;
  potential_difference_liters: number;
  wording_key: string;
  events_count: number;
  fields: unknown[];
  weekly: AnalyticsWeekly[];
}

export interface WaterOverTimePoint {
  day: string;
  liters: number;
  mm: number;
}

// ---------- History chart series ----------

export interface HistoryResponse {
  field_id: number;
  from: string;
  to: string;
  soil_moisture: { t: string; value: number; source: string }[];
  rainfall_mm: { day: string; value: number; kind: "observed" | "forecast" }[];
  temperature_c: { day: string; min: number; max: number }[];
  irrigation_mm: { day: string; value: number }[];
  et0_mm: { day: string; value: number; kind?: string }[];
  etc_mm: { day: string; value: number; kind?: string }[];
}

// ---------- Agronomist / admin ----------

export interface Advisory {
  id: number;
  author: string | User;
  note: string;
  created_at: string;
}

export interface AgronomistFarm extends Farm {
  needs_review_count: number;
}

export interface AuditLog {
  id: number;
  user_id: number | null;
  action: string;
  resource_type: string;
  resource_id: number | null;
  previous: Record<string, unknown> | null;
  new: Record<string, unknown> | null;
  ip: string | null;
  created_at: string;
}

export interface AdminStats {
  total_users: number;
  total_farms: number;
  active_farms: number;
  total_fields: number;
  recommendations_today: number;
  irrigation_events_30d: number;
  sensor_uptime_pct: number | null;
  weather_provider_health: string;
}

// ---------- Sync ----------

export type SyncActionType = "irrigation_event" | "reading" | "feedback";

export interface SyncAction {
  local_id: string;
  type: SyncActionType;
  payload: Record<string, unknown>;
}

export interface SyncResult {
  local_id: string;
  status: "created" | "duplicate" | "error";
  error?: string | null;
}

export interface SyncBatchResponse {
  results: SyncResult[];
}

// ---------- Misc ----------

export interface HealthResponse {
  status: "ok" | "degraded";
  db: string;
  weather: string;
  version: string;
}
