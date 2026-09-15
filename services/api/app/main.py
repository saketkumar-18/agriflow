"""AgriFlow FastAPI app entrypoint.

Security (spec 43): JWT auth, RBAC per-router, rate limiting (in-process token
bucket; Redis-backed is a drop-in when REDIS_URL set), strict CORS, secure
headers, request-id + structured logs, unified error envelope.
"""
from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict, deque

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.routers import common, data, events, farms
from app.seed import seed_demo, seed_reference, seed_users

settings = get_settings()
logging.basicConfig(level=logging.INFO,
                    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":"%(message)s"}')
log = logging.getLogger("agriflow.api")

app = FastAPI(title=settings.app_name, version=settings.version,
              docs_url="/api/docs" if settings.environment != "production" else None,
              openapi_url="/api/openapi.json")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Device-Key"],
)


@app.middleware("http")
async def security_and_observability(request: Request, call_next):
    request_id = uuid.uuid4().hex[:12]
    start = time.perf_counter()
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(self)"
    if settings.environment == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    log.info('{"req":"%s","path":"%s","status":%s,"ms":%.1f}', request_id,
             request.url.path, response.status_code, (time.perf_counter() - start) * 1000)
    return response


# ----------------------------------------------------------- rate limiting
_buckets: dict[str, deque] = defaultdict(deque)


@app.middleware("http")
async def rate_limit(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/v1"):
        key = None
        limit = None
        if path in ("/api/v1/auth/login", "/api/v1/auth/register"):
            key, limit = f"auth:{request.client.host if request.client else '?'}", settings.rate_limit_auth_per_min
        elif request.method in ("GET", "HEAD"):
            auth = request.headers.get("authorization", "")
            key, limit = f"read:{auth[-16:] or request.client.host}", settings.rate_limit_read_per_min
        else:
            auth = request.headers.get("authorization", "")
            key, limit = f"write:{auth[-16:] or request.client.host}", settings.rate_limit_write_per_min
        if key:
            now = time.monotonic()
            dq = _buckets[key]
            while dq and now - dq[0] > 60:
                dq.popleft()
            if len(dq) >= limit:
                return JSONResponse(status_code=429, content={
                    "error": {"code": "rate_limited", "message": "Too many requests, slow down", "details": None}},
                    headers={"Retry-After": "30"})
            dq.append(now)
    return await call_next(request)


# ----------------------------------------------------------- error envelope
def _err(code: str, msg: str, details=None, status_code: int = 400) -> JSONResponse:
    return JSONResponse(status_code=status_code,
                        content={"error": {"code": code, "message": msg, "details": details}})


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    loc = ".".join(str(x) for x in first.get("loc", [])[1:])
    return _err("validation.failed", "Invalid request data",
                {"field": loc, "type": first.get("type")}, 422)


@app.exception_handler(IntegrityError)
async def integrity_handler(request: Request, exc: IntegrityError):
    return _err("conflict", "Resource already exists or violates constraints", None, 409)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("unhandled error")
    return _err("internal", "Internal server error", None, 500)


# ----------------------------------------------------------- routers
API_PREFIX = "/api/v1"
for r in (common.router, farms.router, data.router, events.router):
    app.include_router(r, prefix=API_PREFIX)


# ----------------------------------------------------------- health (no auth, spec 49)
def _health_payload():
    db_ok = True
    try:
        with SessionLocal() as s:
            s.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    from app.weather import weather_provider
    if settings.weather_provider.lower().startswith("open"):
        prov = weather_provider()
        # peek = cache-state only; health polling must never become provider load
        peek = getattr(prov, "peek", None)
        if peek is not None:
            snap = peek(26.14, 91.72, days=1)
            wx = "not_probed" if snap is None else ("ok" if snap.available else "error")
        else:
            snap = prov.get_weather(26.14, 91.72, days=1)
            wx = "ok" if snap.available else "error"
    else:
        wx = "not_configured"
    state = "ok" if db_ok and wx in ("ok", "not_configured", "not_probed") else "degraded"
    return {"status": state, "db": "ok" if db_ok else "error", "weather": wx,
            "version": settings.version}


@app.get("/api/health")
def health_endpoint():
    return _health_payload()


@app.get(f"{API_PREFIX}/health")
def health_endpoint_v1():
    return _health_payload()


# ----------------------------------------------------------- lifespan
def _bootstrap():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        seed_reference(db)
        if settings.demo_seed_enabled:
            seed_users(db)
            seed_demo(db)
    finally:
        db.close()
    log.info("AgriFlow API %s ready (db=%s, weather=%s)", settings.version,
             settings.database_url.split("://")[0], settings.weather_provider)


@app.on_event("startup")
def on_startup():  # FastAPI TestClient triggers this; uvicorn too
    _bootstrap()
