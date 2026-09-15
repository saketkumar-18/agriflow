# AgriFlow — Local Setup

Works on Windows (git-bash), macOS, Linux. Two paths: **Docker (recommended, one command)** or
**manual local dev**. Environment variables are documented in `.env.example` and
docs/deployment.md; never commit real secrets (§69).

## 1. Prerequisites

| Tool | Version | Why |
|---|---|---|
| Docker + Docker Compose v2 | current stable | full-stack path |
| Python | 3.11.x | API + worker (§54) |
| Node.js + npm | 20 LTS | web app (§53) |
| git-bash (Windows) | any | commands below assume POSIX shell |

Check: `python --version` → 3.11.x · `node --version` → v20.x · `docker compose version`.

## 2. Fastest start — Docker Compose

```bash
cd agriflow
cp .env.example .env          # defaults work locally; keep AUTH_SECRET dev value ONLY for dev
docker compose up --build
```

Services (compose): `postgres:16`, `redis:7`, `api` (FastAPI on :8000, runs `alembic upgrade head`
+ demo seed on boot), `web` (Next.js on :3000), `worker` (`python -m app.worker`).

- App: http://localhost:3000 · API docs: http://localhost:8000/docs · Health:
  `curl http://localhost:8000/api/health` → `{"status":"ok","db":"ok","weather":"ok",...}`
- Demo login (seeded, all records flagged `demo:true`, §58):
  `demo@agriflow.local / demo1234` (farmer) and admin/agronomist accounts listed in README.
- First boot takes ~1–2 min (image build). Later: `docker compose up`. Stop: Ctrl-C or
  `docker compose down` (add `-v` only if you deliberately want to wipe DB data).

Windows note: keep the repo under a short path (e.g. `C:\dev\agriflow`), and if the API sees stale
files, ensure the volume isn't hit by antivirus locking; `docker compose logs -f api` shows boot.

## 3. Manual local dev (no Docker required)

The API defaults to a **SQLite file** (`DATABASE_URL` unset ⇒ `sqlite:///./agriflow.db`) and
**in-process caches** (Redis optional — ADR-001/004). Zero infrastructure.

### 3.1 API

```bash
cd services/api
python -m venv .venv
source .venv/Scripts/activate        # Windows git-bash; use `source .venv/bin/activate` on mac/linux
pip install -r requirements.txt -r requirements-dev.txt
cp ../../.env.example .env           # defaults fine
alembic upgrade head                 # migrations (AC-02)
uvicorn app.main:app --reload --port 8000
```

Smoke: `curl http://localhost:8000/api/health` then open http://localhost:8000/docs.
Demo seed runs automatically on first boot when `DEMO_SEED_ENABLED=true` and DB is empty.

### 3.2 Worker (separate terminal, same venv)

```bash
cd services/api
source .venv/Scripts/activate
python -m app.worker                 # long-poll job loop: weather sync, recs, notifications, cleanup
```

With Redis running (`docker compose up -d redis`) you can set `REDIS_URL=redis://localhost:6379/0`
and `WORKER_MODE=arq` for the broker queue path; default mode needs neither.

### 3.3 Web

```bash
cd apps/web
npm install
cp .env.local.example .env.local     # NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
npm run dev                          # http://localhost:3000
```

### 3.4 PostgreSQL variant (optional local)

```bash
docker compose up -d postgres
# in services/api/.env:
# DATABASE_URL=postgresql+psycopg://agriflow:agriflow@localhost:5432/agriflow
alembic upgrade head
```

The test suite also runs against SQLite by default; CI additionally verifies Postgres so the two
dialects don't drift.

## 4. Running tests & checks

```bash
# Backend (from services/api)
pytest                                  # unit + integration (in-memory/tmp SQLite)
pytest tests/integration -m slow        # dockerized postgres leg where marked
ruff check . && ruff format --check .   # lint
mypy app                                # type checks

# Frontend (from apps/web)
npm run lint
npx tsc --noEmit                        # strict TS (§76.1)
npm run test                            # unit/component (vitest/jest per package.json)
npm run test:e2e                        # Playwright farmer journey (needs API+web running:
                                        #   `docker compose up` or the two local servers)
npm run build                           # production build
```

All of these run in CI (§56); a PR that fails any is not mergeable (docs/contributing.md).

## 5. Demo & seed data (§58, §59)

On first boot the seeder creates: reference crops (10, §7) with stage Kc rows; soil types (labeled
`is_estimate:true`, §9); `Demo Farmer` → *Green Valley Farm* → *Field A* (wheat, loamy, 1 ha) with
30 days of synthetic weather + soil-moisture history + irrigation events, so charts and
recommendations are populated immediately. **Every seeded row carries `demo: true`** and the UI
badges demo content — synthetic data is never presented as real (§72). Reset anytime:
`POST /admin/demo/reset` (admin) or delete `agriflow.db` / `docker compose down -v postgres`.

Switch the weather stub to prove honest degradation: `WEATHER_PROVIDER=none` ⇒ endpoints return
`{"available": false, "provider": "none", "reason": "weather.not_configured"}` and confidence drops
— nothing is fabricated (§72).

## 6. Common issues

| Symptom | Fix |
|---|---|
| `sqlite3.OperationalError: database is locked` | one writer at a time: stop duplicate uvicorn `--reload` workers; use compose/Postgres for concurrency |
| Port 3000/8000 busy | `netstat -ano | grep :8000` (git-bash), kill PID or change `--port` + `NEXT_PUBLIC_API_URL` |
| Web shows "Weather provider not configured" | expected with `WEATHER_PROVIDER=none`/no network; set `open_meteo` + internet (§72 — this is honest, not broken) |
| 401 after DB reset | tokens reference old user rows — log in again |
| Alembic "target database is not at head" | `alembic upgrade head` again; check you're pointing at the DB you think (SQLite file lives in `services/api/`) |
| Windows path/venv confusion | always activate the venv per-terminal; git-bash paths (`/c/Users/...`) and `C:\...` both work for our tools |

## 7. Next steps

Read docs/architecture.md (layout + ADRs), docs/irrigation-engine.md (the rules), then
docs/deployment.md to run it for real.
