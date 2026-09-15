"""Shared fixtures: isolated temp SQLite DB per test session, TestClient app factory.

WEATHER_PROVIDER=static makes the engine deterministic in tests without touching
the network; the static provider is clearly named 'static-demo' in every payload.
"""
from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator

import pytest

# Set env at CONFTES import time (before any app.* import during collection) —
# settings are lru-cached at first import, so fixture-time env would be too late.
_FD, _DB_PATH = tempfile.mkstemp(suffix=".db", prefix="agriflow_test_")
os.close(_FD)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{_DB_PATH}")
os.environ.setdefault("WEATHER_PROVIDER", "static")
os.environ.setdefault("AUTH_SECRET", "test-secret")
os.environ.setdefault("DEMO_SEED_ENABLED", "false")
os.environ.setdefault("ENVIRONMENT", "test")
# suite makes far more than 10 auth calls/min from one "IP" — lift limiter in tests
os.environ.setdefault("RATE_LIMIT_AUTH_PER_MIN", "100000")
os.environ.setdefault("RATE_LIMIT_READ_PER_MIN", "100000")
os.environ.setdefault("RATE_LIMIT_WRITE_PER_MIN", "100000")


@pytest.fixture(scope="session", autouse=True)
def _env() -> None:
    return None




@pytest.fixture()
def client() -> Iterator:
    # reimport per test module usage keeps settings singleton consistent with env
    from fastapi.testclient import TestClient
    from app.database import Base, engine
    from app.main import app
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c


def register(client, email, password="Passw0rd!23", name="Test Farmer", role=None):
    r = client.post("/api/v1/auth/register",
                    json={"email": email, "password": password, "full_name": name})
    assert r.status_code == 201, r.text
    tok = r.json()["access_token"]
    if role:  # elevate via admin bootstrap (tests seed admin directly)
        _set_role(email, role)
        r = client.post("/api/v1/auth/login", json={"email": email, "password": password})
        tok = r.json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}, r.json()["user"]


def _set_role(email: str, role: str) -> None:
    from app.database import SessionLocal
    from app.models import Role, User
    db = SessionLocal()
    u = db.query(User).filter(User.email == email).first()
    u.role = Role(role)
    db.commit()
    db.close()


def full_farm_setup(client) -> tuple[dict, int, int]:
    """Register farmer -> crop/soil refs -> farm -> field. Returns (hdrs, farm_id, field_id)."""
    hdrs, _ = register(client, "f1@examplemail.com")
    crops = client.get("/api/v1/crops", headers=hdrs).json()
    soils = client.get("/api/v1/soil-types", headers=hdrs).json()
    wheat = next(c for c in crops if c["name"] == "Wheat")
    loam = next(s for s in soils if s["name"] == "Loamy")
    farm = client.post("/api/v1/farms", headers=hdrs, json={
        "name": "Test Farm", "latitude": 26.14, "longitude": 91.72,
        "total_area": 2.0, "area_unit": "ha"}).json()
    field = client.post(f"/api/v1/farms/{farm['id']}/fields", headers=hdrs, json={
        "name": "Field A", "area": 1.0, "area_unit": "ha",
        "soil_type_id": loam["id"], "crop_id": wheat["id"],
        "growth_stage_code": "VEGETATIVE", "irrigation_method": "drip"}).json()
    return hdrs, farm["id"], field["id"]
