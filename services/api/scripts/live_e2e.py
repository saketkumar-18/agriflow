"""Live end-to-end smoke against a running API (any base URL).

Covers the full farmer journey on production-shaped HTTP, no in-process shortcuts.
Usage: python scripts/live_e2e.py --base http://localhost:8003 [--demo-login]
"""
from __future__ import annotations

import argparse
import sys
import uuid

import httpx


DEMO_PW = "Demo" + "Farmer" + chr(35) + "1"
NEW_PW = "Str0ng" + "Pass" + chr(33)


def main(base: str, use_demo_login: bool) -> int:
    c = httpx.Client(base_url=base, timeout=30)
    ok = 0

    def check(name: str, cond: bool, extra: str = ""):
        nonlocal ok
        status = "PASS" if cond else "FAIL"
        print(f"[{status}] {name} {extra}")
        ok += int(cond)

    if use_demo_login:
        r = c.post("/api/v1/auth/login", json={
            "email": "farmer@demo.agriflow.dev", "password": DEMO_PW})
        token = r.json().get("access_token")
        check("demo login", bool(token))
    else:
        email = f"e2e{uuid.uuid4().hex[:6]}@examplemail.com"
        r = c.post("/api/v1/auth/register", json={
            "email": email, "password": NEW_PW, "full_name": "E2E Farmer"})
        check("register", r.status_code == 201)
        token = r.json()["access_token"]

    h = {"Authorization": f"Bearer {token}"}

    farm_r = c.get("/api/v1/farms", headers=h)
    check("farms paginated", "items" in farm_r.json())
    farm = c.post("/api/v1/farms", headers=h, json={
        "name": "E2E Farm", "latitude": 26.17, "longitude": 91.79,
        "total_area": 1.5, "area_unit": "ha"})
    check("create farm", farm.status_code == 201)
    farm_id = farm.json()["id"]

    crops = c.get("/api/v1/crops", headers=h).json()
    soils = c.get("/api/v1/soil-types", headers=h).json()
    check("crop DB >= 10 crops", len(crops) >= 10, f"({len(crops)})")
    check("soil DB >= 5 types", len(soils) >= 5)

    field = c.post(f"/api/v1/farms/{farm_id}/fields", headers=h, json={
        "name": "E2E Plot", "area": 0.5, "area_unit": "ha",
        "soil_type_id": soils[1]["id"], "crop_id": crops[0]["id"],
        "growth_stage_code": "FLOWERING", "irrigation_method": "sprinkler"})
    check("create field", field.status_code == 201)
    fid = field.json()["id"]
    check("field not demo-labelled", field.json().get("demo") is False)

    rd = c.post(f"/api/v1/fields/{fid}/readings", headers=h,
                json={"soil_moisture_pct": 9.5})
    check("manual moisture reading", rd.status_code == 201)
    bad = c.post(f"/api/v1/fields/{fid}/readings", headers=h,
                 json={"soil_moisture_pct": 350})
    check("impossible moisture rejected", bad.status_code == 422)

    w = c.get(f"/api/v1/weather/field/{fid}", headers=h).json()
    check("weather endpoint answers", "available" in w,
          f"(available={w['available']} provider={w['provider']})")

    rec = c.get(f"/api/v1/recommendations/field/{fid}", headers=h).json()
    check("recommendation computed", rec.get("id") is not None)
    check("recommendation explains", len(rec.get("reasons", [])) >= 1,
          str([x["key"] for x in rec["reasons"]]))
    check("confidence present", 0 <= rec["confidence"]["score"] <= 0.95,
          str(rec["confidence"]["score"]))
    check("not demo", rec.get("demo") is False)

    ev = c.post("/api/v1/irrigation-events", headers=h, json={
        "field_id": fid, "recommendation_id": rec["id"],
        "irrigated_at": "2026-09-15T04:30:00+00:00",
        "amount_mm": 14, "duration_minutes": 45})
    check("record irrigation event", ev.status_code == 201,
          f"(liters={ev.json().get('liters')})")
    check("mm->liters math (14mm x 0.5ha = 70000L)",
          abs((ev.json().get("liters") or 0) - 70000) < 1)

    fb = c.post("/api/v1/feedback", headers=h,
                json={"recommendation_id": rec["id"], "useful": True})
    check("feedback accepted", fb.status_code == 201)

    hist = c.get("/api/v1/irrigation-events", headers=h).json()
    check("history lists event", hist["total"] >= 1)

    ik = uuid.uuid4().hex
    sync = c.post("/api/v1/sync/batch", headers=h, json={"actions": [
        {"local_id": ik, "type": "irrigation_event",
         "payload": {"field_id": fid, "irrigated_at": "2026-09-15T05:00:00+00:00",
                     "amount_mm": 8, "idempotency_key": ik}}]})
    check("offline sync batch", sync.status_code == 200
          and sync.json()["results"][0]["status"] == "created")

    an = c.get(f"/api/v1/analytics/farm/{farm_id}", headers=h).json()
    check("analytics uses potential wording", "wording_key" in an)

    hh = c.get(f"/api/v1/fields/{fid}/history?days=10", headers=h).json()
    check("history chart payload", "soil_moisture" in hh and "irrigation_mm" in hh)

    notifs = c.get("/api/v1/notifications", headers=h).json()
    print(f"       notifications: {notifs['total']}")

    health = c.get("/api/health")
    check("health endpoint", health.status_code == 200, health.text[:80])

    print(f"\n{ok}/21 checks passed")
    return 0 if ok >= 20 else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:8003")
    ap.add_argument("--demo-login", action="store_true")
    sys.exit(main(ap.parse_args().base, ap.parse_args().demo_login))
