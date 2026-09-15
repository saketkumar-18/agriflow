# AgriFlow — Architecture

Master spec references are to section numbers (§n) of the master build prompt. The API surface is
frozen in `docs/api-contract.md`; this document explains how the system is arranged around it.

## 1. System context

```
                         ┌──────────────────────────────────────────────────────┐
                         │                    AGRIFLOW PLATFORM                  │
                         │                                                      │
  ┌───────────┐  HTTPS   │  ┌────────────────┐         ┌─────────────────────┐  │
  │  FARMER   │────────────────▶  apps/web   │────────▶   services/api      │  │
  │  PWA      │          │  │ Next.js 14 TS  │  REST   │ FastAPI + SQLAlchemy│  │
  │ (mobile-  │◀─────────────│ Tailwind PWA   │◀────────│ 2 + Pydantic v2     │  │
  │  first,   │  JSON    │  │ i18n en/hi     │ /api/v1 │ JWT auth, RBAC      │  │
  │  offline  │          │  └────────────────┘         └──────────┬──────────┘  │
  │  queue)   │                                                  │              │
  └───────────┘                                     ┌────────────┼───────────┐  │
                         ┌───────────┐              │            │           │  │
  ┌───────────┐  HTTPS   │ services/ │   reads/     ▼            ▼           ▼  │
  │ AGRONOMIST│──────────────  admin │◀── writes ──────────┐  ┌────────┐ ┌─────┐ │
  │ / ADMIN   │          │ (views on│                     │  │Postgres│ │Redis│ │
  └───────────┘          │  same    │  ┌───────────────┐  │  │  :16   │ │ :7  │ │
                         │  API)    │  │services/worker│──┘  │(SQLite │└──┬──┘ │
  ┌───────────┐  HTTP    │          │  │ python -m     │     │ dev)   │   │    │
  │  SENSOR   │──────────────────────▶ │ app.worker    │──▶──┤ shared │◀──┘    │
  │  DEVICE   │ POST /sensors/{id}     │ long-poll job │     │ model  │ cache/ │
  │  (ESP32   │ /readings +X-Device-Key│ loop          │     └────────│ rate-  │
  │  future)  │  (device endpoints live│ arq/RQ opt.   │              │ limits │
  └───────────│   inside the API)      └───────┬───────┘              └────────┘
                         │                     │ enqueue/consume jobs:
                         │                     ▼
                         │      weather_sync · recommendation_generate ·
                         │      notification_deliver · data_cleanup ·
                         │      analytics_aggregate · ml_predict (later)   (§50)
                         │
                         │        ┌──────────────────────────┐
                         └────────▶  WeatherProvider iface   │
                          fetch    │  open_meteo (default)   │──▶ Open-Meteo API
                                   │  none (stub: available  │     (free, no key)
                                   │  :false)                │
                                   └──────────────────────────┘
```

§77's product structure maps directly: Farmer/Agronomist/Admin → Farms → Fields → {Weather,
Sensors} → Irrigation Engine {Rules | ML | Safety} → Recommendation → Farmer → Irrigation Event →
Historical Data → Model Evaluation. Today the ML box is dormant (docs/ml.md); rules + safety are live.

## 2. Component responsibilities

### apps/web (Next.js 14, TypeScript strict, Tailwind, PWA) (§53)
- Farmer-facing screens: dashboard (§26), field detail + charts (§27), farm map with open
  mapping (§28), weather view (§11), recommendation view with reasons/warnings/confidence (§15,
  §19, §20), history & analytics (§22, §23), feedback (§21), notifications (§24, §25).
- i18n: renders every string from `i18n/en.json` / `hi.json` shared key namespaces; no hard-coded
  UI text (§30, §67). Recommendation reasons arrive as `{key, params}` and are translated client-side.
- Offline: service-worker app shell + cached last recommendation/weather/farm data; local queue of
  actions flushed through `POST /sync/batch` with idempotency keys (§29, §64).
- Business logic stays out of components (§76.7): the web app never computes irrigation math;
  it renders engine output and labels each value measured vs estimated.
- Admin/agronomist screens are views on the same API (kept in the app rather than a separate
  `apps/admin` initially — see ADR-005).

### services/api (Python 3.11, FastAPI, SQLAlchemy 2, Pydantic v2, Alembic) (§54)
- AuthN/AuthZ: JWT bearer (python-jose, HS256), bcrypt password hashing, RBAC dependency guards
  (docs/security.md).
- CRUD + scoping for farms/fields/crops/soil-types/readings/sensors/events/feedback/notifications/
  advisories; soft deletes; audit trail writes (§47).
- **Sensor ingestion lives here**: `POST /api/v1/sensors/{id}/readings` with `X-Device-Key` is the
  HTTP sibling of the future MQTT gateway (docs/sensor-integration.md, ADR-003).
- Weather fetching behind the `WeatherProvider` interface with per-(lat,lon) ≥30-min cache (§10, §51).
- Runs the **IrrigationDecisionEngine** as a pure, importable service (docs/irrigation-engine.md):
  compute-on-demand endpoints plus worker-triggered generation; versioned `engine_version:
  "rules-1.0"`.
- Request validation via Pydantic (0–100 moisture, lat/lon ranges, impossible-value rejection)
  (§40, §76.4–6); rate limiting per contract (10/min auth per IP, 120/min reads, 30/min writes).
- Health: `GET /api/health` and `/api/v1/health` report db/weather/version (§49).

### services/worker (§50, §54)
- Same codebase, started with `python -m app.worker` — a long-poll job loop over the jobs table
  (Postgres/SQLite backed), so no broker is required for MVP. arq/RQ sit behind `WORKER_MODE`
  (redis broker) when deployed with Redis (ADR-004).
- Jobs: weather synchronization, recommendation generation (pre-compute for active fields),
  notification delivery (in-app persisted; email only if SMTP configured — otherwise logged as
  not configured, never faked), expired-data cleanup, analytics aggregation, sensor
  offline-detection sweeps, ML prediction (Phase 2, gated).
- Nothing long-running blocks HTTP requests (§50); the API only enqueues.

### Data stores
- **PostgreSQL 16 in docker-compose; SQLite file default for dev/demo** (ADR-001). Same
  SQLAlchemy models + Alembic migrations for both; schema in docs/database.md.
- **Redis 7 optional** (compose includes it): weather/reference-data cache, cross-process rate
  limits, and broker when `WORKER_MODE=arq`. Without it the app falls back to in-process caches —
  documented behavior, not silent failure. Sensitive user data is never cached indiscriminately (§51).

### External providers (§70, §71)
- `WeatherProvider` interface: `get_current_weather(location)`, `get_forecast(location, days)`,
  `get_historical_weather(location, range)` (§10). Implementations: `open_meteo` (default; free
  personal-use API, no key — documented as an external dependency without a "free forever" claim)
  and `none` (stub returning `available:false, reason:"weather.not_configured"`).
- `MapProvider` (OpenStreetMap tiles — open mapping per §28, §71), `NotificationProvider`
  (email via SMTP when configured; push/WhatsApp later), `SensorProvider` (device-key HTTP now,
  MQTT gateway later). Provider keys come from environment only (§10, §69).

## 3. Data flows worth calling out

**Recommendation read path** (§14): UI → `GET /recommendations/field/{id}` → cache/store lookup →
if absent/stale (`expires_at`, 12 h default TTL) engine runs synchronously once (bounded work) →
inputs gathered from DB (latest reading with age, weather snapshot, crop/stage, soil, area, method)
→ rules engine → Recommendation row persisted with `inputs_digest` + `engine_version` → response.

**Sensor write path**: device → `POST /sensors/{id}/readings` (X-Device-Key) → validate ranges
(§40) → store SensorReading, bump `sensor.last_seen_at` → enqueue recommendation recompute +
offline-alert sweep.

**Offline sync path** (§29): PWA queue → `POST /sync/batch` → per-action results
`created|duplicate|error` → idempotency_key dedupe protects against replays.

## 4. Monorepo layout (§52, adapted per its own instruction)

§52 says to adapt the structure to the chosen framework rather than create empty directories. The
adaptation actually shipped:

```
agriflow/
├── apps/
│   └── web/                 # Next.js PWA. Absorbs mobile (PWA IS the mobile app, §53) and
│                            # admin (role-gated routes; split out only if it diverges).
├── services/
│   ├── api/                 # FastAPI app; includes sensor-ingestion endpoints (ADR-003),
│   │   └── app/             #   config.py, models, routers, engine, providers, worker entry
│   └── worker/              # thin entrypoint reusing services/api code: python -m app.worker
├── ml/                      # datasets/ notebooks/ src/ models/ evaluation/ — separate from
│                            #   application code (§76.9); Phase 2 per docs/ml.md
├── packages/                # i18n/ (en.json, hi.json shared namespaces) — database/types/
│                            #  /validation/config live in-code instead (single Python + TS app)
├── infrastructure/
│   ├── docker/              # Dockerfiles
│   └── migrations/          # Alembic (in services/api; documented here for §52 traceability)
├── docs/                    # this set + api-contract.md (§68, §74 Step 1)
├── tests/                   # unit/ integration/ e2e/ (§57)
├── .env.example             # §69
└── docker-compose.yml       # api + web + postgres:16 + redis:7 (§56)
```

Deviations from §52 and why: `apps/mobile` omitted (PWA-first decision, §53);
`services/sensor-ingestion` folded into the API (ADR-003); `packages/database|types|validation|config`
not spun up as separate packages until a second consumer exists (§76.19–20 — simplest thing that works).

## 5. Architecture decision records

### ADR-001 — SQLite default for dev/demo, PostgreSQL for docker-compose/production
**Decision.** SQLAlchemy models + Alembic target both. `DATABASE_URL` defaults to
`sqlite:///./agriflow.db`; compose sets `postgresql+psycopg://…@postgres:5432/agriflow`.
**Rationale.** §41 mandates PostgreSQL, but §58 demands an evaluator can launch and see data
immediately — a zero-setup SQLite file makes `uvicorn app.main:app` work with no infrastructure,
and single-container demos stay honest (same code, same migrations). Postgres in compose satisfies
the production requirement (concurrency, types, JSONB boundary_geojson). All models avoid
engine-specific SQL; timestamps stored UTC (§41).
**Consequences.** Two CI legs (pytest on SQLite; smoke on Postgres) so drift is caught. SQLite's
single-writer limit is fine for demo scale, documented as not production.

### ADR-002 — Hargreaves (temperature-based) ET₀
**Decision.** ET₀ from daily min/max temperature (plus extraterrestrial radiation by latitude/day
of year) per FAO-56 Hargreaves; labeled `kind:"estimated"` in every API payload and chart (§15,
§17, §18).
**Rationale.** §17: "Where appropriate data exists, implement ET-based estimation… Do not
fabricate scientific values." Full Penman-Monteith needs solar radiation, humidity, and wind —
Open-Meteo provides them but not all deployments do, and historic station data is patchy.
Hargreaves is the documented FAO fallback where only temperatures are reliable; accuracy is
lower, so results are always estimates feeding Kc/ETc (`ETc = ET0 × Kc`), never presented as
measurements.
**Consequences.** If radiation data is available later, a Penman-Monteith provider can be added
behind the same internal ET interface without touching the engine contract; `engine_version` bumps.

### ADR-003 — Device-key HTTP ingestion now; MQTT gateway later
**Decision.** Sensors POST to `POST /api/v1/sensors/{id}/readings` with `X-Device-Key`
(server-stored hash of a key shown once at registration). No MQTT broker in MVP.
**Rationale.** §12/§65 sketch MQTT as the future IoT path but forbid requiring hardware (§12) and
complexity (§76.19). ESP32s do HTTPS on rural networks; an HTTP endpoint is the MQTT gateway's
sibling — the same validation, storage, and recompute pipeline runs regardless of transport. A
gateway can later subscribe to a broker and replay into this exact endpoint (§65 flow:
Sensor→MQTT→Gateway→Sensor Service→DB→Engine→Farmer is preserved; the "Sensor Service" box is
these API routes).
**Consequences.** Per-device keys rotate/revoke in DB; device endpoints get their own rate limit;
offline detection compares `last_seen_at` to expected cadence (docs/sensor-integration.md, §39).

### ADR-004 — Own long-poll job loop; arq/RQ behind WORKER_MODE
**Decision.** Default worker = `python -m app.worker`: claims jobs from a DB `jobs` table with
`UPDATE … WHERE status='ready'` lease semantics and polls. `WORKER_MODE=arq` (or `rq`) switches
the same job handlers to a Redis broker queue.
**Rationale.** §54 says "Celery/RQ/appropriate worker" — whichever fits. Fitting MVP means: works
on SQLite (no broker), survives restarts (jobs are rows), and keeps §50's rule that HTTP never
blocks on long jobs. Redis is already in compose for caching, so the broker upgrade costs one env var.
**Consequences.** Job handlers are transport-agnostic functions registered in one table; retries
and dead-letter status are explicit columns, visible to admin health views (§45, §49).

### ADR-005 — Single web app, role-gated, instead of apps/admin
**Decision.** Admin and agronomist screens are routes in apps/web guarded by role.
**Rationale.** §52 lists apps/admin but also says adapt, don't blindly scaffold. Admin UI is small
(§45 list + stats); separate Next.js apps would double build/deploy cost for shared design system
(§73). Revisit when admin grows a distinct release cadence.

### ADR-006 — Rules-first, ML-later, with a gate
**Decision.** MVP ships `rules-1.0` only (§16). ML (RandomForest baselines in scikit-learn) trains
off collected data and may only influence recommendations after beating rules on farm-safety-aware
metrics and passing the safety-rails composition of §38. See docs/ml.md.
**Rationale.** §34 explicitly forbids starting with complex ML and mandates the
baseline→data→evaluate→compare→deploy-only-if-better sequence. §38/§76.18: rules must be able to
override unsafe model outputs; recommendation (never actuation) is the ceiling of automation.

### ADR-007 — Open-Meteo behind WeatherProvider; `none` stub is first-class
**Decision.** Default provider open_meteo (free, keyless personal API); `WEATHER_PROVIDER=none`
returns `available:false` and the engine degrades confidence instead of fabricating values.
**Rationale.** §10 (no provider coupling), §70 (abstraction), §71 (prefer free/open but don't
claim "free forever" — Open-Meteo's terms are documented as an external dependency), §72 (no fake
integrations: a missing provider shows as missing). Keys via env only (§69).

## 6. Caching strategy (§51)
Redis (or in-process fallback): weather snapshots per (lat,lon, 30 min), crop/soil reference data,
recent recommendations. Never: auth tokens' claims beyond request scope, farm coordinates in logs,
readings. Cache keys carry no PII.

## 7. Environment surface
See `.env.example` and the env-var table in docs/deployment.md — DATABASE_URL, REDIS_URL,
WEATHER_PROVIDER/WEATHER_API-adjacent settings, AUTH_SECRET, CORS_ORIGINS, SMTP_*, WORKER_MODE,
rate-limit and engine tunables (§69). Real secrets never in the repo (§43, §76.14).
