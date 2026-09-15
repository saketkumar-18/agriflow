# AgriFlow — Deployment

Target: a small single-host or VM deployment of docker-compose (api + web + worker + postgres:16 +
redis:7), TLS-terminated at a reverse proxy. §56 DevOps, §69 env vars, §49 observability.

## 1. Production compose

`docker-compose.yml` (repo root) runs everything locally; production uses
`docker-compose.prod.yml` overrides:

```yaml
# infrastructure/docker/docker-compose.prod.yml (shape)
services:
  postgres:
    image: postgres:16
    volumes: [pgdata:/var/lib/postgresql/data]
    # NO ports: published — reachable only on the compose network
    healthcheck: {test: ["CMD-SHELL", "pg_isready -U agriflow"], interval: 10s, retries: 5}
  redis:
    image: redis:7
    command: redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy allkeys-lru
    # internal only
  api:
    build: services/api
    env_file: .env
    depends_on: {postgres: {condition: service_healthy}, redis: {condition: service_started}}
    healthcheck: {test: ["CMD", "curl", "-fsS", "http://localhost:8000/api/health"], interval: 30s, timeout: 5s, retries: 3}
    command: sh -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2"
  worker:
    build: services/api
    env_file: .env
    command: python -m app.worker
    depends_on: {api: {condition: service_started}}
    healthcheck: {test: ["CMD", "python", "-m", "app.worker", "--ping"], interval: 60s}
  web:
    build: apps/web
    env_file: .env
    depends_on: [api]
    # next start (production build via `next build` in image)
  caddy:               # or nginx/traefik — TLS, HSTS, rate-limit at edge
    ports: ["80:80", "443:443"]
volumes: {pgdata: {}}
```

Rules: Postgres/Redis never exposed publicly; only :443 through the proxy. Images pinned by tag
(postgres:16, redis:7) and built from committed Dockerfiles (§76). Release = pull/checkout a tag →
`docker compose -f docker-compose.yml -f .../docker-compose.prod.yml up -d --build` → **migrations
run on api boot** (`alembic upgrade head`); for zero-downtime critical systems run migrations as a
separate pre-deploy step with backward-compatible revisions.

## 2. Environment variables (mirrors `.env.example`)

| Variable | Required | Default (dev) | Prod guidance | Purpose (spec) |
|---|---|---|---|---|
| `ENVIRONMENT` | no | `development` | `production` — enables boot checks | mode gate (§56) |
| `DATABASE_URL` | prod yes | `sqlite:///./agriflow.db` | `postgresql+psycopg://user:pw@postgres:5432/agriflow` | DB (§41, ADR-001) |
| `REDIS_URL` | no | empty (in-process caches) | `redis://redis:6379/0` | cache/rate-limits/broker (§51) |
| `WORKER_MODE` | no | `db` (long-poll loop) | `db` or `arq` | job transport (ADR-004, §50) |
| `AUTH_SECRET` | **yes** | insecure dev string | ≥32 random bytes; app **refuses to boot in prod** with the dev default | JWT signing (§43, §69) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | no | `10080` (7 d) | keep 7 d (low-connectivity tradeoff, documented in security.md §1) | token life (§43) |
| `WEATHER_PROVIDER` | no | `open_meteo` | `open_meteo` \| `none` | provider choice (§10, §70) |
| `WEATHER_API_KEY` / `OPEN_METEO_API_KEY` | no | empty | set only if using a commercial Open-Meteo plan | key, never committed (§10, §69) |
| `WEATHER_BASE_URL` | no | public Open-Meteo | optional proxy/self-host | endpoint override (§10) |
| `WEATHER_CACHE_MINUTES` | no | `30` | 30+ (contract caches ≥30 min per lat/lon) | §11, §51 |
| `MAP_PROVIDER_KEY` | no | empty (OSM tiles) | only if using a commercial tile service | §69, §71 |
| `CORS_ORIGINS` | prod yes | localhost dev origins | exact public origins, comma-separated, no `*` with credentials | §43 |
| `SMTP_HOST/PORT/USER/PASSWORD/FROM` | no | empty | set to enable email alerts; unset ⇒ in-app only + logged, never faked | §25, §72 |
| `RATE_LIMIT_AUTH_PER_MIN` | no | 10 | 10 | contract limits (§43) |
| `RATE_LIMIT_READ_PER_MIN` | no | 120 | 120 | " |
| `RATE_LIMIT_WRITE_PER_MIN` | no | 30 | 30 | " |
| `DEFAULT_MAD` / `CRITICAL_MAD` | no | 0.55 / 0.40 | tune with agronomist input, document changes | engine (§16) |
| `MOISTURE_FRESH_HOURS` / `MOISTURE_MAX_AGE_HOURS` | no | 12 / 48 | keep default (§39 semantics) | staleness (§39) |
| `RAIN_DEFER_MM` / `RAIN_PROB_GATE` | no | 8.0 / 50.0 | regional tuning, DB overrides preferred | rain deferral (§16) |
| `RECOMMENDATION_TTL_HOURS` | no | 12 | 12 | recompute cadence (§14) |
| `DEMO_SEED_ENABLED` | **prod: no** | `true` | `false` in production (demo creds must not exist on public instances) | §58 |
| `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` | no | empty | push notifications later (§64) | notifications |

`.env` is gitignored; only `.env.example` (placeholders, no real values) is committed (§69, §76.14).
Rotate `AUTH_SECRET` + device keys if any leak; a rotation invalidates sessions by design.

## 3. Health checks & observability (§49)

Endpoints (no auth, no PII): `GET /api/health` and `GET /api/v1/health` →
`{"status":"ok"|"degraded","db":"ok","weather":"ok"|"not_configured"|"error","version":"..."}`.

- `status:"degraded"` (not `error`) when the weather provider is down/unconfigured but core
  functions work — an honest partial state; `weather:"not_configured"` is a valid ok-ish mode (§72).
- Container-level: compose healthchecks above drive restarts and the proxy's upstream state;
  worker liveness via `--ping` (job loop heartbeat row).
- Logs: structured JSON (level, ts, request id, user id hash — **coordinates and secrets redacted**,
  security.md §7) to stdout → container log driver; error tracking via Sentry-style DSN env when
  provided (never required, §76.20).
- Background job monitoring: `jobs` table states (ready/running/failed/dead) exposed in admin
  stats; dead-letter alert to admin notification (§45, §50).
- Sensor ingestion monitoring: per-sensor `last_seen_at` sweep ⇒ `sensor_offline` alerts (§39) +
  admin `sensor_uptime_pct` (§45, contract /admin/stats).
- Uptime probes: hit `/api/health` externally (any monitor); DB health = probe succeeds with
  `db:"ok"`; weather-provider health column in /admin/stats (§45).

## 4. Backups & restores

- **Postgres**: nightly `pg_dump -Fc agriflow` via a scheduled `docker compose run api pg_dump`-style
  sidecar (or `pg_dumpall` roles) to object storage/offsite copy; retain daily ×14 + weekly ×8 +
  monthly ×12. Test a restore **quarterly** — an untested backup is not a backup; restore drill is
  part of the ops checklist (audit_logs included, §47).
- Redis needs no backup (cache/queue; DB is the source of truth; `WORKER_MODE=db` puts jobs in
  Postgres anyway).
- App server is stateless: rebuilding from image + restore = recovery. SQLite (dev/demo only):
  file-level copy with `sqlite3 .backup` or just regenerate from seed.
- Before destructive ops (purges, migration downgrades): take a fresh dump first; destructive
  DB operations require explicit human confirmation (§79's stop-list).

## 5. Scaling notes (§48, §78 Phase 4)

Single host comfortably serves MVP scale. Growth order: uvicorn workers → dedicated Postgres +
connection pooling (PgBouncer) → more worker replicas (`WORKER_MODE=arq` for proper queue
distribution) → read replicas for analytics → partition `sensor_readings`. Do not pre-build for it
(§76.19). Rate limits (Redis-backed) already shard across processes.

## 6. Release checklist

1. Tag commit; CI green (lint, type, unit, integration, build — §56).
2. Review migration reversibility; snapshot/pre-deploy backup.
3. `docker compose … up -d --build`; watch `alembic` log line; `/api/health` green.
4. Smoke: login → dashboard → refresh recommendation → record event (then delete smoke data).
5. Confirm `DEMO_SEED_ENABLED=false`, strong `AUTH_SECRET`, real `CORS_ORIGINS`, TLS headers
   (security.md §10 checklist).
6. Announce version; version appears in `/api/health` and admin UI.
