# AgriFlow — Database Design

Tables follow §41 of the master spec, extended where the frozen API contract (`docs/api-contract.md`)
requires it. SQLAlchemy 2 models, Alembic migrations, PostgreSQL 16 in production / SQLite in dev
(ADR-001 in architecture.md). Types below are Postgres; SQLite maps UUIDs→TEXT ids not needed (ids
are INTEGER everywhere per contract), `JSONB`→`JSON`, `TIMESTAMPTZ`→UTC-normalized `DATETIME`.

## 1. Global conventions

- **IDs**: `INTEGER PRIMARY KEY` autoincrement (contract: "IDs: integers").
- **Timestamps**: `created_at`/`updated_at` `TIMESTAMPTZ NOT NULL DEFAULT now()`. **All storage and
  transport is UTC** (§41, contract "UTC ISO-8601 with Z"); conversion to local time happens only
  in the UI. No naive datetimes: the app writes tz-aware UTC (`datetime.now(timezone.utc)`);
  Postgres session `SET timezone = 'UTC'`; SQLite stores ISO-strings with `Z`.
- **Soft deletes**: `deleted_at TIMESTAMPTZ NULL` on user-owned entities (farms, fields, sensors,
  users-deactivation via `is_active`). All read paths filter `deleted_at IS NULL`; history/analytics
  keep rows (§contract `DELETE /farms/{id}` "(soft delete)"). Hard purge only by the expired-data
  cleanup job after retention windows (§50).
- **Audit**: mutations of sensitive tables go through a repository layer that writes `audit_logs`
  (§47); not a DB trigger, so `user_id`/IP context is available.
- **Demo flag**: `demo BOOLEAN DEFAULT false` on seeded rows; set only by the seeder (§58, §72).
- **Naming**: snake_case; FK `<table>_id`; index `ix_<table>_<cols>`; unique `uq_<table>_<cols>`.
- **Currency-free platform**: no money columns (contract header).

## 2. Tables

### users (§3, §41)
| column | type | notes |
|---|---|---|
| id | INTEGER PK | |
| email | CITEXT UNIQUE NOT NULL | login identity |
| password_hash | VARCHAR(72) NOT NULL | bcrypt output; never selected into responses (§43) |
| full_name | VARCHAR(200) NOT NULL | |
| phone | VARCHAR(20) NULL | optional (contract register) |
| role | VARCHAR(20) NOT NULL CHECK in (farmer, agronomist, admin) | default farmer on self-register (§3) |
| language | VARCHAR(10) NOT NULL DEFAULT 'en' | en/hi (§30) |
| is_active | BOOLEAN NOT NULL DEFAULT true | admin deactivates (§45) |
| alert_level | VARCHAR(10) DEFAULT 'high' | notification preference (§25) |
| channel_push / channel_email | BOOLEAN | preference (contract `channels`) |
| created_at, updated_at, deleted_at | TIMESTAMPTZ | |

Indexes: `uq_users_email`; `ix_users_role` (admin filters).

### farms (§5)
| column | type | notes |
|---|---|---|
| id | INTEGER PK | |
| farmer_id | INTEGER FK users.id NOT NULL ON DELETE CASCADE | owner |
| name | VARCHAR(200) NOT NULL | |
| location_text | VARCHAR(300) NULL | village/district label |
| latitude | NUMERIC(9,6) NULL | CHECK −90..90; sensitive (§44) |
| longitude | NUMERIC(9,6) NULL | CHECK −180..180 |
| total_area | NUMERIC(10,2) NULL | |
| area_unit | VARCHAR(5) CHECK in (ha, acre) | |
| demo | BOOLEAN DEFAULT false | |
| created_at / updated_at / deleted_at | TIMESTAMPTZ | soft delete |

Indexes: `ix_farms_farmer_id (farmer_id, deleted_at)` — every farmer-scoped query; `ix_farms_created_at` for admin paging.

### fields (§6)
| column | type | notes |
|---|---|---|
| id | INTEGER PK | |
| farm_id | INTEGER FK farms.id NOT NULL ON DELETE CASCADE | |
| name | VARCHAR(200) NOT NULL | |
| area | NUMERIC(10,3) NOT NULL | in area_unit; CHECK > 0 |
| area_unit | VARCHAR(5) CHECK (ha, acre) | |
| soil_type_id | INTEGER FK soil_types.id NULL | |
| crop_id | INTEGER FK crops.id NULL | |
| growth_stage_code | VARCHAR(20) NULL | GERMINATION…HARVEST (§8) |
| planting_date | DATE NULL | stage progression aid |
| irrigation_method | VARCHAR(20) CHECK (drip,sprinkler,flood,furrow,manual,other) | §6 |
| water_source | VARCHAR(100) NULL | |
| boundary_geojson | JSONB NULL | optional polygon (§6, §28) |
| demo, created_at, updated_at, deleted_at | | |

Indexes: `ix_fields_farm_id`; `ix_fields_crop_id`, `ix_fields_soil_type_id` (engine joins);
`ck_fields_area_positive` check constraint.

### crops (§7)
| column | type | notes |
|---|---|---|
| id | INTEGER PK | |
| name | VARCHAR(100) UNIQUE NOT NULL | |
| scientific_name | VARCHAR(150) NULL | |
| root_depth_mm | INTEGER NOT NULL | mature depth |
| maturity_days | INTEGER NULL | |
| advisory_text_key | VARCHAR(100) NULL | i18n key, never prose (§67) |
| is_active | BOOLEAN DEFAULT true | admin retires, never deletes reference rows |
| demo | BOOLEAN | |

10 starters seeded (§7): wheat, rice, maize, tomato, potato, cotton, sugarcane, groundnut, mustard, onion.

### crop_growth_stages (§8, §17)
| column | type | notes |
|---|---|---|
| id | INTEGER PK | |
| crop_id | INTEGER FK crops.id NOT NULL ON DELETE CASCADE | |
| code | VARCHAR(20) NOT NULL | GERMINATION/VEGETATIVE/FLOWERING/FRUITING/MATURITY/HARVEST |
| name_key | VARCHAR(100) NOT NULL | i18n |
| kc | NUMERIC(4,2) NOT NULL | crop coefficient, configurable (§17) |
| critical | BOOLEAN NOT NULL DEFAULT false | drives MAD tightening (§16) |
| start_day_offset / end_day_offset | INTEGER NULL | rough calendar windows |
| target_mad | NUMERIC(3,2) NULL | per-crop override of engine default |

Indexes: `uq_crop_stage (crop_id, code)`; engine lookup is (crop_id, code) — this is the hot join.

### soil_types (§9)
| column | type | notes |
|---|---|---|
| id | INTEGER PK | |
| name | VARCHAR(100) UNIQUE NOT NULL | Sandy…Custom |
| name_key | VARCHAR(100) | i18n label |
| field_capacity_pct | NUMERIC(5,2) NULL | |
| wilting_point_pct | NUMERIC(5,2) NULL | CHECK < field_capacity when both set |
| bulk_density | NUMERIC(5,3) NULL | g/cm³ |
| water_holding_capacity_mm_per_m | NUMERIC(6,2) NULL | |
| is_estimate | BOOLEAN NOT NULL DEFAULT true | §9: reference values must be labeled estimates |

No per-farm overrides in MVP; custom soil = new row. Cached in Redis/in-process (§51).

### sensors (§13)
| column | type | notes |
|---|---|---|
| id | INTEGER PK | |
| field_id | INTEGER FK fields.id NOT NULL ON DELETE CASCADE | |
| type | VARCHAR(30) NOT NULL | soil_moisture (+future types without engine change, §13) |
| manufacturer | VARCHAR(100) NULL | |
| device_identifier | VARCHAR(100) NOT NULL | serial/IMEI-ish |
| device_key_hash | VARCHAR(72) NOT NULL | bcrypt/hash of X-Device-Key; plaintext shown once at registration (contract) |
| status | VARCHAR(10) CHECK (online, offline) DEFAULT offline | worker sweeps last_seen_at (§39) |
| expected_interval_min | INTEGER DEFAULT 60 | staleness threshold per device |
| installed_at / last_seen_at | TIMESTAMPTZ NULL | |

Indexes: `uq_sensors_field_device (field_id, device_identifier)`; `ix_sensors_status` (offline sweep).

### sensor_readings (§13, §40)
| column | type | notes |
|---|---|---|
| id | INTEGER PK | |
| sensor_id | INTEGER FK sensors.id NOT NULL ON DELETE CASCADE | |
| timestamp | TIMESTAMPTZ NOT NULL | device-reported, normalized UTC |
| soil_moisture | NUMERIC(5,2) NULL | CHECK 0–100 — impossible values rejected at API (422) AND constraint |
| temperature_c | NUMERIC(5,2) NULL | CHECK −30..60 |
| humidity_pct | NUMERIC(5,2) NULL | CHECK 0–100 |
| battery_level | NUMERIC(5,2) NULL | CHECK 0–100 |
| quality_flag | VARCHAR(10) DEFAULT 'ok' | spike-suspect/duplicate-dropped marked, never silently deleted (§40) |

Indexes: `ix_readings_sensor_time (sensor_id, timestamp DESC)` — latest-reading queries; retention
job aggregates to daily after 180 d (§50). High-volume table: partition by month when Postgres scale
requires (documented, not premature).

### manual_readings / readings view
Manual farmer entries land in the same conceptual "Reading" the contract exposes
(`source: "manual"|"sensor"`): implemented as a `soil_moisture`-typed pseudo-sensor per field, or a
parallel `field_readings(field_id, value_pct, source, taken_at)` table. Chosen: single
`field_readings` table to avoid fake sensor rows:

| column | type | notes |
|---|---|---|
| id, field_id FK, value_pct NUMERIC(5,2) CHECK 0–100, source VARCHAR(10) CHECK (manual,sensor), taken_at TIMESTAMPTZ, demo, created_at | | |

Index `ix_field_readings (field_id, taken_at DESC)`. Engine reads a UNION view so source/age is explicit.

### weather_observations / weather_forecasts (§41)
Cached provider data (also in Redis; DB copy powers history charts and offline regen).

weather_observations: `id, farm_id/lat/lon bucket, day DATE, min_c, max_c, rain_mm, source
(observed|provider), created_at`.
weather_forecasts: `id, lat_bucket, lon_bucket, fetched_at, day, min_c, max_c, rain_prob_pct
CHECK 0–100, rain_mm, condition_code SMALLINT (WMO), provider VARCHAR(30)`.
Indexes: `ix_forecast_bucket_day (lat_bucket, lon_bucket, day)`; rows older than 7 d pruned (§50).

### irrigation_events (§21, §22)
| column | type | notes |
|---|---|---|
| id | INTEGER PK | |
| field_id | INTEGER FK fields.id NOT NULL | |
| recommendation_id | INTEGER FK irrigation_recommendations.id NULL | links decision→action |
| irrigated_at | TIMESTAMPTZ NOT NULL | |
| duration_minutes | INTEGER NULL | |
| amount_mm | NUMERIC(6,2) NULL | one of mm/liters required (contract), CHECK ≥0 |
| liters | NUMERIC(12,2) NULL | server converts via area — never trust client conversion (§76.6) |
| note | TEXT NULL | |
| source | VARCHAR(10) CHECK (manual, sync) | offline replays arrive as sync |
| idempotency_key | VARCHAR(100) NULL UNIQUE | duplicate POST returns existing row (contract) |
| demo | BOOLEAN | |

Indexes: `ix_events_field_time (field_id, irrigated_at DESC)`; `ix_events_recommendation_id`;
`uq_events_idem` where key not null.

### irrigation_recommendations (§14)
| column | type | notes |
|---|---|---|
| id | INTEGER PK | |
| field_id | INTEGER FK fields.id NOT NULL | |
| computed_at | TIMESTAMPTZ NOT NULL | |
| expires_at | TIMESTAMPTZ NOT NULL | default computed_at + 12 h (engine TTL) |
| irrigation_needed | BOOLEAN NOT NULL | |
| urgency | VARCHAR(10) CHECK (LOW,MEDIUM,HIGH,CRITICAL) NULL | |
| recommended_time_key | VARCHAR(100) NULL | + window_start/window_end TIMESTAMPTZ NULL |
| estimated_water_mm | NUMERIC(6,2) NULL | labeled estimate (§18) |
| estimated_liters | NUMERIC(14,2) NULL | |
| confidence_score | NUMERIC(4,3) NOT NULL | 0–1 rubric (irrigation-engine.md §7) |
| confidence_level | VARCHAR(6) CHECK (LOW,MEDIUM,HIGH) | |
| confidence_factors | JSONB NOT NULL | [{key, ok}] |
| reasons | JSONB NOT NULL DEFAULT '[]' | [{key, params}] (§19) |
| warnings | JSONB NOT NULL DEFAULT '[]' | |
| inputs_digest | JSONB NOT NULL | exact inputs; reproducibility |
| engine_version | VARCHAR(20) NOT NULL | "rules-1.0"; future "ml-x.y" |
| override_by_user_id | INTEGER FK users.id NULL | |
| override_action | VARCHAR(10) CHECK (defer,approve,cancel) NULL | |
| override_reason | TEXT NULL | required with override (§46) |
| override_at | TIMESTAMPTZ NULL | |
| demo | BOOLEAN | |

Indexes: `ix_recos_field_computed (field_id, computed_at DESC)`; `ix_recos_expires` (recompute job).
Rows are immutable except the override columns (append-only history, §22/§19).

### farmer_feedback (§21)
`id, recommendation_id FK NOT NULL, user_id FK, useful BOOLEAN NULL, comment TEXT NULL,
created_at`. Index `ix_feedback_recommendation_id`. Training fuel for ML Phase 2 (§21 "store for
future model evaluation").

### notifications (§24, §25)
`id, user_id FK NOT NULL, type CHECK (irrigation_needed, rain_incoming, extreme_heat,
sensor_offline, low_confidence, advisory), severity SMALLINT, title_key VARCHAR(100), params JSONB,
created_at, read_at NULL`. Index `ix_notif_user_unread (user_id, read_at) WHERE read_at IS NULL`.

### advisories (§46)
`id, field_id FK, author_id FK users, note TEXT NOT NULL, created_at`. Index `ix_advisories_field`.

### farm_agronomists (assignment, §46)
`farm_id FK, agronomist_id FK, assigned_by FK, assigned_at`. PK (farm_id, agronomist_id).

### audit_logs (§47)
| column | type | notes |
|---|---|---|
| id | BIGINT PK | |
| user_id | INTEGER NULL | NULL for system/worker actions |
| action | VARCHAR(50) NOT NULL | e.g. `field.update`, `recommendation.override`, `farm.delete` |
| resource_type | VARCHAR(50) NOT NULL | |
| resource_id | INTEGER NULL | |
| previous | JSONB NULL | value before (§47) |
| new | JSONB NULL | value after |
| ip | INET NULL | device metadata (§47) |
| user_agent | TEXT NULL | |
| created_at | TIMESTAMPTZ NOT NULL | |

Append-only: no UPDATE/DELETE grants to the app role (role separation documented). Index
`ix_audit_time (created_at DESC)`, `ix_audit_user (user_id, created_at DESC)`, `ix_audit_resource
(resource_type, resource_id)`. Location-access reads are themselves audited (§44).

### jobs (worker queue, ADR-004)
`id, kind VARCHAR(50), status CHECK (ready,running,done,failed,dead), payload JSONB, run_at,
locked_until, attempts SMALLINT, last_error TEXT, created_at`. Index `ix_jobs_ready (status, run_at)`.

### weather_provider_health / system tables
Provider health is computed at request time (`/api/health`) plus `provider_checks(id, provider,
ok, latency_ms, checked_at)` for admin graphs (§45).

## 3. Entity relationships

```
users ──< farms ──< fields ──< field_readings (manual|sensor union)
  │        │          │  ╲────< sensors ──< sensor_readings
  │        │          │   ╲───< irrigation_recommendations ──< farmer_feedback
  │        │          │    ╲──< irrigation_events (→ recommendation_id nullable)
  │        │          ╲─────< advisories
  │        ╲──< farm_agronomists >── users(agronomist)
  ╲──< notifications          ╲──< weather_observations / forecasts (geo-bucketed)
  ╲──< audit_logs (any resource)     jobs · provider_checks (platform)
crops ──< crop_growth_stages        soil_types (reference)
```

## 4. Migrations & integrity

Alembic, one revision per logical change, always reversible down to base (§76.11). FK enforcement
on for both engines (`PRAGMA foreign_keys=ON` on SQLite connect). CHECK constraints mirror API
validation (defense in depth, §76.5). Demo seed runs after `upgrade head` when `DEMO_SEED_ENABLED`
(§58); seeder is idempotent and only touches `demo=true` rows on reset.
