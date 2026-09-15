# AgriFlow — Product Requirements

Master spec references are to `pasted_content_2026-09-15_15-36-10-140_37aec2.txt` (§n = section n).

## 1. Problem statement (§1)

Farmers often irrigate on fixed schedules, intuition, or incomplete information. That causes
over-irrigation, under-irrigation, wasted water, higher costs, and crop stress. AgriFlow combines
weather, rainfall forecasts, temperature, humidity, wind, soil moisture (manual or sensor), soil
type, crop type, growth stage, farm location, and irrigation history into **one explainable answer
to the question "Does my field need irrigation?"** (§61), delivered on a mobile-first, low-bandwidth,
offline-capable PWA (§2, §29).

AgriFlow is a **decision-support tool, not a replacement for an agronomist or irrigation
specialist** (§1). Every recommendation carries a disclaimer key (`rec.disclaimer`) and is never
presented as guaranteed agricultural advice (§54, non-goal below).

## 2. Primary users (§2, §58)

| User | Who | Primary need |
|---|---|---|
| Farmer (primary) | Smallholder to mid-size, mobile-first, often low connectivity and low technical literacy | See irrigation status in seconds; understand *why*; record what they did |
| Agronomist | Advisory professional assigned to farms | Review recommendations, add notes, override with justification (§46) |
| Admin | Platform operator | Manage users/reference data, monitor health, audit activity (§45) |
| Evaluator/demo visitor | Reviewer of the system | Launch and immediately see meaningful, clearly-labeled demo data (§58) |

UI constraints (§2, §31, §63): large touch targets, icons + text (never color alone), short
sentences, localized (en/hi from day one, §30/§67), accessible (keyboard, screen readers, contrast).

## 3. Roles and capabilities (§3)

| Capability | Farmer | Agronomist | Admin |
|---|---|---|---|
| Register / login | yes (self, role=farmer) | issued by admin | issued by admin |
| Create/read/update own farms & fields | yes | read assigned | read all |
| Set crop, growth stage, soil info | yes | no (advises) | no |
| Enter manual soil-moisture readings | yes | no | no |
| Register sensors (device key) | yes | no | yes |
| View weather / recommendations / history / analytics | own scope | assigned farms | aggregate |
| Receive alerts (per preference level) | yes | yes | — |
| Add advisory notes on a field | no | yes | yes |
| Override a recommendation (reason required, audited) | no | yes | yes |
| Assign agronomist to farm | no | no | yes |
| Manage users, crops, soil types, regions | no | no | yes |
| View audit logs, platform stats | no | no | yes |
| Reset demo seed | no | no | yes |

Scope rules: farmers act only on their own farms (403 otherwise); agronomists see only assigned
farms (`POST /admin/farms/{farm_id}/assign-agronomist` is admin-only); registration always creates
role `farmer` (§3, API contract Auth).

## 4. Core journey (§4)

```
Register → Create Farm → Add Field → Select Crop → Enter Soil Info
→ Weather connects (auto, via provider) → Enter/receive soil moisture
→ Irrigation Engine → Explained Recommendation → Farmer Decision
→ Irrigate → Record Actual Irrigation → History & feedback → system learns later (§21)
```

The first five steps must be completable on a phone in under a few minutes; the dashboard answer
("review tomorrow / irrigate / OK / unknown") must be readable in seconds (§26, §61, §62 — priority
order: recommendation → reason → soil moisture → rain forecast → weather → crop status → history →
analytics).

## 5. MVP scope = Master spec Phase 1 (§78)

Included:

1. **Farmer authentication** — register/login, JWT bearer tokens, bcrypt password hashing (§43;
   see docs/security.md).
2. **Farm management** — multiple farms; GPS / manual / approximate location; lat/lon validation (§5).
3. **Field management** — area, soil type, crop, growth stage, irrigation method, water source,
   optional boundary; every change audit-logged (§6, §47).
4. **Crop selection from a database** — 10 starter crops (wheat, rice, maize, tomato, potato,
   cotton, sugarcane, groundnut, mustard, onion) with configurable stages/Kc — never hard-coded in
   app logic (§7, §8).
5. **Soil information** — sandy/loamy/clay/sandy loam/clay loam/custom with FC, wilting point,
   bulk density, WHC; reference values explicitly labeled `is_estimate: true` (§9).
6. **Weather** — provider abstraction (§10, §70); Open-Meteo default (free, no key); graceful
   `available:false` degradation (§72); 5-day forecast made highly visible (§11).
7. **Rule-based irrigation engine** — transparent baseline (§14–§18); full explanation of reasons
   and warnings (§15, §19); confidence with stated factors (§20). Docs: docs/irrigation-engine.md.
8. **Irrigation recommendation UI** — never a bare "irrigate now"; reasons, estimate vs measurement
   labels, disclaimer (§15, §76.17).
9. **Irrigation history & recording** — events with mm/liters, offline-safe idempotent sync (§21,
   §22, §29; contract `/sync/batch`).
10. **Basic dashboard** — per-field status cards, weather snapshot, next-5-days (§26).
11. **Basic notifications** — in-app alert types from §24 (irrigation needed, rain incoming,
    extreme heat, sensor offline, low confidence), user alert-level preference (§25). Email/SMS/
    WhatsApp channels are later; the worker logs "channel not configured" rather than pretending.
12. **PostgreSQL (via docker-compose) with SQLite default for dev** (ADR-001, docs/architecture.md).
13. **PWA** — installable, cached last recommendation/weather, offline action queue (§29, §64).
14. **Tests** — unit (rules, water math, thresholds), integration (user→farm→field→weather→rec→
    event), E2E farmer journey (§57).
15. **Docker** — one-command start (§56, docs/setup.md).
16. **Admin (basic)** — user management, stats, audit view, demo reset (§45, §58).
17. **Agronomist (basic)** — assigned-farm view, advisories, overrides (§46, §74 Step 13).
18. **Sensor abstraction** — data model + device-key HTTP ingestion API built now; no hardware
    required (§12, §13, docs/sensor-integration.md).

## 6. Explicit non-goals

| Non-goal | Rule source |
|---|---|
| **No pump control / no automated irrigation.** Recommendation → human is the end of the loop; ML never autonomously operates equipment. | §66, §38, §76.18 |
| **No fake data.** Unconfigured providers return `available:false` / "No sensor connected"; synthetic seed data is flagged `demo: true` everywhere it appears. | §58, §72, API contract conventions |
| **No guaranteed agronomic advice.** Decision support only; every recommendation shows a disclaimer; savings wording is "estimated potential reduction" against a modeled baseline, never claimed actual savings. | §1, §23 |
| Complex ML in MVP (rules baseline only; ML is Phase 2+, gated per docs/ml.md) | §78 Phase 1 |
| IoT hardware dependency (sensors are an optional ingestion path, not required) | §12, §65 |
| Voice assistant (§32) and AI farm chat assistant (§33) — Phase 2 | §32, §33, §78 |
| Marketplace, social features | §78 Phase 1 exclusions |
| Native mobile app (responsive PWA first; React Native only if native features become necessary) | §53 |
| Advanced GIS, satellite/remote sensing, multi-field optimization — Phase 3 | §78 |

## 7. Key functional requirements (traceable)

- FR-1 Auth: register (password ≥8 chars, server-validated), login, `/auth/me`, preferences. 401s
  give a generic message — no user enumeration. (§43; contract Auth)
- FR-2 Farms/fields CRUD with soft deletes; lat/lon range validated; precise coordinates never
  exposed unnecessarily. (§5, §44)
- FR-3 Crop/soil-type reference endpoints; engine reads coefficients from DB, not code. (§7, §9)
- FR-4 Weather per field with server-side caching ≥30 min per (lat,lon); forecast list includes
  per-day min/max °C, rain probability, rain mm. (§10, §11; contract Weather)
- FR-5 Recommendations: latest (compute-if-missing), refresh, history; full Recommendation schema
  with `inputs_digest`, `engine_version: "rules-1.0"`, i18n-keyed reasons/warnings/confidence
  factors. (§14, §15, §19; contract Recommendations)
- FR-6 Readings: manual entry validated 0–100 with 422 `validation.impossible_value`; sensor
  ingestion via device key. (§12, §40)
- FR-7 Irrigation events: amount_mm or liters (server converts via area), `idempotency_key` makes
  offline replays safe (returns existing on replay). (§21, §29)
- FR-8 Feedback: useful/not-useful per recommendation; stored for future model evaluation. (§21)
- FR-9 Analytics: monthly water used vs recommended vs potential difference, correct cautious
  wording, weekly series, water-over-time chart. (§22, §23)
- FR-10 Notifications list/mark-read + generation by worker jobs. (§24, §50)
- FR-11 Admin: users PATCH, stats, audit log pagination, demo reset. (§45)
- FR-12 Agronomist: assigned farms with needs-review counts, advisories, override with mandatory
  reason, audit who/when/what/why. (§46, §47)
- FR-13 i18n: all user-visible strings via shared key namespace (en/hi). (§30, §67, contract §i18n)
- FR-14 Offline: cache farms/recs/weather; queue irrigation records; sync safely. (§29, §64)

## 8. Non-functional requirements

- NFR-1 Performance: fast load, minimal API calls, cached weather, pagination, lazy charts,
  works on low-end phones (§48).
- NFR-2 Reliability: never a blank screen; every failure mode (§60) has an explicit user-facing
  state.
- NFR-3 Security: as docs/security.md (§43, §44).
- NFR-4 Observability: structured logs, `/api/health`, DB/weather/job/sensor-ingestion health
  (§49, docs/deployment.md).
- NFR-5 Honesty: estimates labeled, measurements labeled, nothing fabricated, no false "free
  forever" claims about third-party services (§71, §72, §76.15–17).
- NFR-6 Maintainability: TS strict, Python type hints, business logic out of UI, irrigation math
  unit-testable, ML code separate (§76).

## 9. Acceptance criteria — mapped to Definition of Done (§75)

Each AC is checked by an actual run, not by file existence ("Do not declare the project finished
merely because files were generated", §75).

| AC | Criterion (spec §75 item) | Verification |
|---|---|---|
| AC-01 | Application starts successfully | `docker compose up` brings api+web healthy; `GET /api/health` → `status:"ok"` |
| AC-02 | Database migrations work | `alembic upgrade head` on empty SQLite and on postgres:16; downgrade/upgrade round-trip |
| AC-03 | Authentication works | register → login → `/auth/me` → wrong password 401 generic |
| AC-04 | RBAC works | farmer 403 on `/admin/users`; agronomist sees only assigned farms; override blocked for farmers |
| AC-05 | Farmer can create farm | POST /farms → appears on dashboard; bad lat rejected |
| AC-06 | Farmer can create field | POST /farms/{id}/fields with method/soil/crop → GET /fields/{id} |
| AC-07 | Farmer can select crop | /crops lists DB-driven crops incl. all 10 starters; stage codes present |
| AC-08 | Weather loads | /weather/field/{id} → `available:true, provider:"open-meteo"`; with WEATHER_PROVIDER=none → `available:false, reason:"weather.not_configured"` |
| AC-09 | Recommendation engine works | refresh returns valid Recommendation matching inputs_digest |
| AC-10 | Recommendation has explanations | ≥1 reason; stale moisture → warning; confidence factors listed; disclaimer key present |
| AC-11 | Irrigation event can be recorded | POST /irrigation-events; liters⇄mm via area; idempotent replay returns existing |
| AC-12 | History works | /fields/{id}/history returns labeled series; /recommendations/.../history |
| AC-13 | Notifications work | worker generates irrigation-needed alert; preference level filters; read/unread |
| AC-14 | Offline behavior works | PWA records event offline → queued → /sync/batch dedupes (no duplicate rows) |
| AC-15 | Admin works | users PATCH role/active, stats numbers match seeded state, audit query, demo reset |
| AC-16 | Agronomist workflow works | assign → advisory → override stored with who/when/what/why in audit_logs |
| AC-17 | Tests pass | pytest unit+integration green; E2E critical journey green |
| AC-18 | Lint passes | ruff + eslint report 0 errors |
| AC-19 | Type checks pass | mypy (API) + `tsc --noEmit` strict (web) clean |
| AC-20 | Production build passes | `next build`; `uvicorn` boot of same image CI builds |
| AC-21 | Docker setup works | fresh clone → compose up → demo login works (AC-01..14 re-run) |
| AC-22 | README works | setup steps copy-paste accurate on Windows git-bash + Linux |
| AC-23 | .env.example exists | every runtime env var documented there; matches docs/deployment.md table |
| AC-24 | No secrets committed | git grep of secret patterns empty; real .env gitignored (§69) |
| AC-25 | Error states handled | each §60 state reachable in UI with friendly message (offline banner, no-farm empty, weather-not-configured, sensor-offline, invalid-location, 5xx, DB-down) |
| AC-26 | Demo data available | seeded farm/field/crop/weather/moisture/history visible immediately; every demo record `demo:true` (§58, §59, §72) |

## 10. Success metrics (post-launch, honest)

Farmer-facing: time-to-first-recommendation, % recommendations rated useful (§21 feedback),
recorded-irrigation compliance. Water: *estimated potential reduction* vs modeled scheduled-
irrigation baseline only — actual savings claims require a real baseline (§23). Engine:
missed-irrigation vs unnecessary-irrigation error rates tracked separately (§37, docs/ml.md).
