# AgriFlow API Contract (v1) — FROZEN for all build tracks

Base URL: `/api/v1`. Auth: `Authorization: Bearer <JWT>` unless marked public.
Errors: `{"error": {"code": string, "message": string, "details": object|null}}` with proper HTTP status.
Pagination: `?page=1&page_size=20` → `{"items": [...], "page": int, "page_size": int, "total": int}`.
Timestamps: UTC ISO-8601 with `Z` in all payloads. UI converts to local.
IDs: integers.
Money-free platform; units: mm (depth), liters (volume), ha (area, float), °C, %, km/h.

## Conventions
- Every recommendation `reason`/`warning` is an i18n key + params, e.g. `{"key": "reasons.soil_below_target", "params": {"value": 31, "target": 45}}`. The UI translates via i18n/en.json + hi.json.
- `demo: true` appears on any record created by the demo seed. Demo data is always labeled.
- Never fake provider data: if weather provider is not configured/failed, weather endpoints return HTTP 200 with `{"available": false, "provider": "none", "reason": "weather.not_configured"}` — the engine degrades confidence instead of fabricating values.

## Auth
- `POST /auth/register` (public) `{email, password, full_name, phone?, language?}` → `201 {access_token, token_type:"bearer", user}`. Public registration only creates role `farmer`. Password ≥ 8 chars, server-validated.
- `POST /auth/login` (public) `{email, password}` → `{access_token, expires_in, user}`. 401 generic message on bad creds (no user enumeration).
- `GET /auth/me` → `User`
- `User`: `{id, email, full_name, role: "farmer"|"agronomist"|"admin", phone, language, created_at, is_active, demo?}`
- `PUT /auth/me/preferences` `{alert_level: "critical"|"high"|"medium"|"low", channels: {push: bool, email: bool}}` → `NotificationPreferences`

## Farms (farmer scope; agronomist sees assigned; admin all)
- `GET /farms?page=` → paginated `Farm`
- `POST /farms` `{name, location_text?, latitude?, longitude?, total_area?, area_unit: "ha"|"acre"}` → `201 Farm` (validates lat/lon range)
- `GET /farms/{id}` → `Farm` (404/403)
- `PATCH /farms/{id}`, `DELETE /farms/{id}` (soft delete)
- `Farm`: `{id, name, location_text, latitude, longitude, total_area, area_unit, field_count, created_at, updated_at, demo?}`
- `GET /farms/{id}/summary` → dashboard payload:
```json
{
  "farm": Farm,
  "fields": [ {
     "id": 1, "name": "Field A", "crop_name": "Wheat", "growth_stage": "VEGETATIVE",
     "soil_moisture": {"value": 31.0, "source": "manual|sensor|none", "measured_at": "...", "age_hours": 5},
     "recommendation": Recommendation|null,
     "status": "needs_irrigation"|"review"|"ok"|"unknown"
  } ],
  "weather_snapshot": WeatherResponse,
  "generated_at": "..."
}
```

## Fields
- `POST /farms/{farm_id}/fields` `{name, area, area_unit, soil_type_id, crop_id, growth_stage_code, irrigation_method: "drip"|"sprinkler"|"flood"|"furrow"|"manual"|"other", water_source?, boundary_geojson?: object}` → `201 Field`
- `GET /fields/{id}` → `Field`
- `PATCH /fields/{id}` (growth stage changes here; every change audit-logged)
- `DELETE /fields/{id}`
- `Field`: `{id, farm_id, name, area, area_unit, soil_type: SoilType, crop: CropBrief, growth_stage_code, irrigation_method, water_source, boundary_geojson, sensor_present, created_at, updated_at, demo?}`
- `GET /fields/{id}/detail` → `{field: Field, latest_reading, recommendation, weather: WeatherResponse}`
- `GET /fields/{id}/history?days=30` → chart series (all labeled measured vs estimated):
```json
{
 "field_id": 1, "from": "...", "to": "...",
 "soil_moisture": [{"t": "...", "value": 31.2, "source": "manual"}],
 "rainfall_mm":   [{"day": "2026-09-10", "value": 4.0, "kind": "observed|forecast"}],
 "temperature_c": [{"day": "...", "min": 22.1, "max": 31.4}],
 "irrigation_mm": [{"day": "...", "value": 18.0}],
 "et0_mm":        [{"day": "...", "value": 4.8, "kind": "estimated"}],
 "etc_mm":        [{"day": "...", "value": 3.8, "kind": "estimated"}]
}
```

## Reference data
- `GET /crops` → `[Crop]`; `GET /crops/{id}`
- `Crop`: `{id, name, scientific_name, root_depth_mm, maturity_days, stages: [{code: "GERMINATION|VEGETATIVE|FLOWERING|FRUITING|Maturity...", kc: float, critical: bool, label_key}], advisory_text_key, demo?}`
- `GET /soil-types` → `[SoilType]`
- `SoilType`: `{id, name, field_capacity_pct, wilting_point_pct, bulk_density, water_holding_capacity_mm_per_m, is_estimate: true, label_key}`

## Weather
- `GET /weather/field/{field_id}` → `WeatherResponse`:
```json
{
  "available": true, "provider": "open-meteo", "fetched_at": "...",
  "latitude": 26.14, "longitude": 91.72,
  "current": {"temp_c": 28.1, "humidity_pct": 61, "wind_kmh": 11, "rain_prob_pct": 20, "condition_code": 1, "observed_at": "..."},
  "forecast": [{"day":"2026-09-16","min_c":22,"max_c":31,"rain_prob_pct":20,"rain_mm":2.0,"condition_code":3}],
  "recent_rainfall_mm": {"last_24h": 0.0, "last_72h": 4.5, "last_7d": 12.0},
  "alert": null | {"key": "alerts.extreme_heat", "params": {}}
}
```
If unavailable: `{"available": false, "provider": "none", "reason": "weather.not_configured"|"weather.unavailable"}` (HTTP 200).
`condition_code` is WMO; UI maps to icon. Server caches weather per (lat,lon) ≥30 min.

## Soil moisture readings
- `POST /fields/{id}/readings` `{soil_moisture_pct, temperature_c?, humidity_c?..., taken_at?}` (farmer manual entry; validated 0–100) → `201 Reading`. Rejects impossible values with 422 `code:"validation.impossible_value"`.
- `GET /fields/{id}/readings?limit=50` → `[Reading]`
- `Reading`: `{id, field_id, value_pct, source: "manual"|"sensor", taken_at, demo?}`

## Sensors (abstraction; ingestion API)
- `POST /fields/{id}/sensors` `{type: "soil_moisture", manufacturer?, device_identifier}` → `201 Sensor` (returns `device_key` once)
- `GET /fields/{id}/sensors`, `GET /sensors/{id}`
- `Sensor`: `{id, field_id, type, manufacturer, device_identifier, status: "online"|"offline", installed_at, last_seen_at}`
- `POST /sensors/{id}/readings` + header `X-Device-Key` `{soil_moisture_pct, temperature_c?, humidity_pct?, battery_level?, timestamp?}` → `201` (device auth, not user auth)
- `GET /sensors/{id}/readings?limit=100`

## Recommendations
- `GET /recommendations/field/{field_id}` → latest stored recommendation (computes one if none exists)
- `POST /recommendations/field/{field_id}/refresh` → recompute now → `Recommendation`
- `GET /recommendations/field/{id}/history?limit=20` → `[Recommendation]`
- `Recommendation`:
```json
{
  "id": 12, "field_id": 3, "computed_at": "...", "expires_at": "...",
  "irrigation_needed": true,
  "urgency": "LOW"|"MEDIUM"|"HIGH"|"CRITICAL",
  "recommended_time": {"key": "time.tomorrow_morning", "params": {}, "window_start": "...", "window_end": "..."} ,
  "estimated_water_requirement": {"value": 18, "unit": "mm"},
  "estimated_liters": 180000,
  "confidence": {"score": 0.82, "level": "HIGH", "factors": [{"key":"conf.has_recent_moisture","ok":true},{"key":"conf.missing_moisture","ok":false}]},
  "reasons": [{"key":"reasons.soil_below_target","params":{"value":31,"target":45}}],
  "warnings": [{"key":"warnings.stale_moisture","params":{"age_hours":18}}],
  "inputs_digest": {"moisture": {"value":31,"source":"manual","age_hours":5}, "rain_next_24h_mm":0, "et0_mm":4.8, "crop":"Wheat","stage":"VEGETATIVE","soil":"Loamy"},
  "engine_version": "rules-1.0",
  "override": null | {"by_user_id": 7, "action": "defer"|"approve"|"cancel", "reason": "...", "at": "..."},
  "disclaimer_key": "rec.disclaimer",
  "demo": false
}
```
- `POST /recommendations/{id}/override` (agronomist/admin) `{action, reason}` → updated Recommendation. reason REQUIRED, audit-logged with who/when/what/why.

## Feedback
- `POST /feedback` `{recommendation_id, useful: bool|null, comment?}` → `201`
- `POST /irrigation-events` `{field_id, recommendation_id?, irrigated_at, duration_minutes?, amount_mm?, liters?, note?, idempotency_key}` → `201 IrrigationEvent`. amount_mm or liters (one required; server converts via field area). idempotency_key makes offline replays safe (409-safe: returns existing).
- `GET /irrigation-events?field_id=&farm_id=&from=&to=&page=` → paginated
- `IrrigationEvent`: `{id, field_id, recommendation_id, irrigated_at, duration_minutes, amount_mm, liters, note, source:"manual"|"sync", demo?}`

## Notifications
- `GET /notifications?unread=true&page=` → paginated `Notification`: `{id, type: "irrigation_needed"|"rain_incoming"|"extreme_heat"|"sensor_offline"|"low_confidence"|"advisory", severity, title_key, params, created_at, read_at}`
- `POST /notifications/{id}/read`, `POST /notifications/read-all`

## Analytics
- `GET /analytics/farm/{farm_id}?month=2026-09` →
```json
{"month":"2026-09","total_irrigation_liters":42000,"recommended_liters":38500,
 "potential_difference_liters":3500, "wording_key":"analytics.potential_reduction_note",
 "events_count":6,"fields":[...], "weekly":[{"week":"...","irrigated_liters":...,"recommended_liters":...}]}
```
- `GET /analytics/farm/{id}/water-over-time?days=90` → `[{"day","liters","mm"}]`

## Agronomist
- `GET /agronomist/farms` → assigned farms with `needs_review_count`
- `POST /agronomist/assign` is admin-only (`POST /admin/farms/{farm_id}/assign-agronomist {user_id}`)
- `GET /fields/{id}/advisories`, `POST /advisories` `{field_id, note}` → `{id, author, note, created_at}`

## Admin
- `GET /admin/users?role=&page=`, `PATCH /admin/users/{id}` `{role?, is_active?}`
- `GET /admin/stats` → `{total_users, total_farms, active_farms, total_fields, recommendations_today, irrigation_events_30d, sensor_uptime_pct, weather_provider_health}`
- `GET /admin/audit?page=&user_id=&action=` → paginated `AuditLog`: `{id, user_id, action, resource_type, resource_id, previous, new, ip, created_at}`
- `POST /admin/demo/reset` (seeds/resets demo data)

## Sync (offline queue)
- `POST /sync/batch` `{actions: [{"local_id": "...", "type": "irrigation_event"|"reading"|"feedback", "payload": {...}}]}` → `{"results":[{"local_id","status":"created"|"duplicate"|"error","error"?}]}`

## Health (no auth)
- `GET /api/health` → `{"status":"ok"|"degraded","db":"ok","weather":"ok"|"not_configured"|"error","version":"..."}`
  and `GET /api/v1/health` same.

## Rate limits
Login/register: 10/min/IP. Reads 120/min/user, writes 30/min/user (429 with `code:"rate_limited"`).

## i18n keys namespace (frontend + backend share)
`nav.*, farm.*, field.*, crop.*, soil.*, weather.*, rec.*, reasons.*, warnings.*, conf.*, time.*, urgency.*, alerts.*, analytics.*, feedback.*, errors.*, common.*`
