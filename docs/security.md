# AgriFlow — Security Design

Covers master spec §43 (security), §44 (location privacy), §47 (audit), and the API contract's
rate-limit conventions. Threat posture: a public-facing agricultural SaaS where farm location is
sensitive personal data and sensor devices are untrusted HTTP clients.

## 1. Authentication (§43)

- **Users**: JWT bearer tokens, HS256 (`python-jose`), secret from `AUTH_SECRET` env (never in
  code; dev default string is loudly insecure and rejected in production mode). 7-day expiry
  chosen deliberately for low-connectivity farmers (config.py) — the compensating controls are
  server-side revocation on deactivate + short write-scope where possible.
- **Passwords**: bcrypt hashing (cost ≥ 12), min 8 chars validated server-side on register
  (contract). Login failures return a generic 401 message — **no user enumeration** (contract
  Auth). No password hash or reset token ever serialized in responses (§43 "never expose").
- **Devices**: separate credential class. `X-Device-Key` matched against a stored **hash**, bound
  to exactly one sensor id, revocable/rotatable per sensor without user involvement
  (docs/sensor-integration.md §6). Device keys are not JWTs and cannot call user endpoints; user
  JWTs cannot call device endpoints. Auth surfaces are disjoint.

## 2. RBAC matrix — role → endpoints (§3, §43)

Legend: ✅ allowed · 🔒 allowed only on owned/assigned resources · ❌ 403.

| Endpoint group | farmer | agronomist | admin | device key |
|---|---|---|---|---|
| POST /auth/register, /auth/login | public | public | public | — |
| GET /auth/me, PUT preferences | ✅ | ✅ | ✅ | ❌ |
| GET/POST/PATCH/DELETE /farms, /fields | 🔒 own farms | 🔒 assigned (read) + advisories/overrides | ✅ all | ❌ |
| GET /crops, /soil-types | ✅ | ✅ | ✅ + write | ❌ |
| GET /weather/field/{id} | 🔒 own | 🔒 assigned | ✅ | ❌ |
| POST /fields/{id}/readings (manual) | 🔒 own | ❌ | ✅ | ❌ |
| POST /fields/{id}/sensors | 🔒 own | ❌ | ✅ | ❌ |
| GET /sensors…, /fields/{id}/sensors | 🔒 own | 🔒 assigned | ✅ | ❌ |
| POST /sensors/{id}/readings | ❌ (user auth path differs) | ❌ | ❌ | ✅ own sensor |
| GET /sensors/{id}/readings | 🔒 own | 🔒 assigned | ✅ | ❌ |
| GET/POST /recommendations…, /refresh | 🔒 own | 🔒 assigned; override ✅ | ✅ override | ❌ |
| POST /recommendations/{id}/override | ❌ | ✅ (reason required) | ✅ | ❌ |
| POST /irrigation-events, /feedback | 🔒 own | ❌ | ✅ | ❌ |
| GET /analytics/… | 🔒 own farm | 🔒 assigned | ✅ aggregate | ❌ |
| GET /notifications + read | ✅ self | ✅ self | ✅ self | ❌ |
| GET /agronomist/farms | ❌ | ✅ | ✅ | ❌ |
| POST /advisories | ❌ | ✅ | ✅ | ❌ |
| /admin/** (users, stats, audit, assign-agronomist, demo/reset) | ❌ | ❌ | ✅ | ❌ |
| /api/health | public (no PII) | | | |

Enforcement is declarative: FastAPI dependencies (`require_role`, `get_owned_farm`,
`get_assigned_field`) so object-level authorization (IDOR) cannot be forgotten route-by-route —
ownership check runs on the path id, not on client-claimed bodies (§76.6 "never trust client-side").

## 3. Input validation (§40, §43, §76.4–5)

- Every request body is a Pydantic v2 model; strict types, bounds, enums. Out-of-range readings
  (moisture 350%) fail with 422 `validation.impossible_value`; lat/lon ranges checked on farms
  (contract). No `extra` keys silently accepted on writes (`extra="forbid"` on ingest models).
- SQL: SQLAlchemy 2 ORM/Core only — parameterized everywhere; no f-string SQL (SQL-injection
  protection §43). Migrations via Alembic.
- GeoJSON boundaries: size-capped, parsed against a schema, stored as JSONB (never executed).
- XSS: frontend renders translated strings, never `dangerouslySetInnerHTML`; API returns JSON with
  `Content-Type` discipline; notes/advisory text escaped at render (XSS §43).
- i18n keys from the server are whitelisted (`reasons.*` etc.) — the UI refuses to render unknown
  keys, so a compromised/buggy engine can't inject prose (§67).
- Upload surface is zero in MVP (no files), minimizing that class.

## 4. Rate limiting & abuse (contract §Rate limits)

| Scope | Limit | Mechanism |
|---|---|---|
| Login/register | 10/min/IP | fixed-window, Redis-backed cross-process or in-process fallback |
| Reads | 120/min/user | per token subject |
| Writes | 30/min/user | per token subject |
| Device ingestion | per-sensor (expected interval × slack) | per device key |
| Bulk endpoints (/sync/batch) | ≤ 200 actions/request | payload-size cap too |

429 carries `code:"rate_limited"` (§contract). Auth endpoints also get exponential backoff hints
via `Retry-After`. Health endpoints are exempt but return no sensitive data.

## 5. Secrets management (§10, §43, §69, §76.14)

- All provider keys (`WEATHER_API_KEY`/Open-Meteo optional key, SMTP creds, `AUTH_SECRET`,
  `MAP_PROVIDER_KEY`) come from environment / `.env` (gitignored) — never committed, never logged,
  never returned by any endpoint (§43). `config.py` dev defaults are explicitly insecure; boot in
  `ENVIRONMENT=production` **refuses to start** with the default `AUTH_SECRET`.
- `.env.example` holds placeholders only (§69). Device keys shown once at provisioning, stored
  hashed (sensor doc). CI has a secret-scan step; DoD AC-24 checks "no secrets committed" (§75).
- Passwords for seed/demo accounts are documented demo credentials (README) and the demo reset
  endpoint is admin-only.

## 6. Transport, CORS, headers (§43)

- HTTPS enforced at the edge (reverse proxy HSTS). docker-compose internal network only for
  postgres/redis; ports not published to the LAN by default in prod overrides.
- CORS allowlist from `CORS_ORIGINS` env (exact origins, no wildcard with credentials).
- Secure headers: `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`,
  `Cache-Control: no-store` on authenticated/PII payloads, CSP on the web app.
- CSRF: bearer tokens in `Authorization` header + PWA storage (not ambient cookies) ⇒ classic
  CSRF surface is minimal; if cookie sessions are ever added, SameSite=strict + CSRF tokens
  (§43 "where applicable").

## 7. Location privacy (§44, §5)

Farm coordinates reveal where a person works and what they grow. Controls:

- **Consent-aware collection**: browser geolocation requested with explicit permission; user may
  always choose manual/approximate location instead (§5 "Avoid exposing precise coordinates
  unnecessarily"). Map picker snaps to configurable precision (default ~4-decimal ≈ 11 m; village
  level is enough for weather).
- **Minimal necessity**: precise lat/lon used only for weather fetch and (opt-in) map display;
  list/summary payloads expose `location_text` and never raw coordinates unless the requester owns
  the farm or is admin. Public endpoints contain zero coordinates.
- **Access control**: coordinates are farmer-owned data; agronomists see them only for assigned
  farms (§3).
- **Audit of access**: reads of precise location by non-owners and any admin bulk export are
  written to `audit_logs` (§44 "audit access to sensitive location data", §47).
- **Storage hygiene**: weather cache keyed by rounded lat/lon buckets, not user id — no PII in
  cache keys (§51 "don't cache sensitive user data indiscriminately"); logs redact coordinates by
  default (structured logger masks `lat`/`lon` fields).
- Sensor/device endpoints never return farm coordinates (§44 + sensor doc).

## 8. Audit logging (§47)

Events written to `audit_logs` (schema in docs/database.md §2):

- AuthN: login success/failure (user id where known, IP, user-agent).
- AuthZ denials on sensitive resources (403s) — attempted access is itself signal.
- All writes: create/update/soft-delete on farms, fields, sensors, users (role/active changes);
  **every field change** including growth stage (contract Fields note); recommendation overrides
  with who/when/what/why + mandatory reason (§46); advisory posts; admin actions including
  `/admin/demo/reset` and agronomist assignments.
- Previous/new values recorded as JSON diffs for updates (§47).
- Read-audit: access to precise location data and bulk exports (§44).
- Append-only table; admin query via `GET /admin/audit?page=&user_id=&action=` (§45, §47).
- Retention: ≥ 12 months online, then archived per deployment policy (no silent purges).

## 9. OWASP Top 10 mapping (§43)

| OWASP (2021) | AgriFlow control |
|---|---|
| A01 Broken access control | RBAC dependencies + object-ownership checks (§2); IDOR tests per endpoint; soft-delete scoping |
| A02 Cryptographic failures | bcrypt passwords; hashed device keys; TLS everywhere; HS256 with strong env secret, refuse-defaults in prod (§5) |
| A03 Injection | ORM-only SQL; Pydantic strict schemas; JSONB never eval'd; XSS-safe rendering (§3) |
| A04 Insecure design | Rules-first, recommend-only (§66/§38); no fake data path (§72); demo flag on synthetic rows |
| A05 Security misconfiguration | Prod boot validation (no dev secrets, https, CORS list); least-privilege DB roles; compose defaults publish no DB ports (§6) |
| A06 Vulnerable components | Pinned deps, Dependabot/`pip-audit`/`npm audit` in CI, minimal deps (§55 "no libraries without a reason", §76.20) |
| A07 Auth failures | Generic 401s, rate-limit on auth (10/min/IP), account deactivate path, documented token expiry tradeoff (§1) |
| A08 Software/integrity | Image pinning, CI builds, migrations versioned (Alembic) (§56) |
| A09 Logging/monitoring gaps | Structured logs + audit_logs + health endpoints + worker job states (§49, §8) |
| A10 SSRF | Weather provider base URL is env-controlled (ops input, not user input); user-supplied locations never used as fetch targets beyond coordinate whitelisting against the fixed provider endpoint (§10) |

## 10. Security review checklist (§74 Step 19)

Before release: dependency audit clean; secret scan (git history) clean; authz fuzz pass on
resource ids (expect 403/404, never another user's data); rate-limit proof at contract numbers;
headers scan; audit-log completeness for overrides + role changes; location-redaction test;
production boot refuses dev defaults; pentest notes for any external exposure of postgres/redis.
