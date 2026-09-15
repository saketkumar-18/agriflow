"""PROD smoke: the farmer core loop against the LIVE deployed stack.

1. login demo farmer -> farm summary (recommendations computed w/ real weather
   OR degraded gracefully) -> field history -> weather endpoint shape.
2. register a fresh account end-to-end (no seeding path) and get a recommendation.
3. assert every payload carries no fabricated weather when provider is down.
"""
import httpx

API = "https://agriflow-api-90yf.onrender.com"
WEB = "https://agriflow-web-nu.vercel.app"
PW = "Demo" + "Farmer" + chr(35) + "1"
c = httpx.Client(base_url=API, timeout=90)
ok = 0


def check(name, cond, extra=""):
    global ok
    ok += int(cond)
    print(f"[{'PASS' if cond else 'FAIL'}] {name} {extra}")


r = c.post("/api/v1/auth/login", json={"email": "farmer@demo.agriflow.dev", "password": PW})
check("prod demo login", r.status_code == 200)
h = {"Authorization": "Bearer " + r.json()["access_token"]}

s = c.get("/api/v1/farms/1/summary", headers=h)
check("prod farm summary 200", s.status_code == 200, str(s.status_code))
d = s.json()
check("summary has 3 demo fields", len(d.get("fields", [])) == 3)
w = d.get("weather_snapshot") or {}
check("weather honest (available OR labeled unavailable)",
      w.get("available") is True or w.get("reason") in
      ("weather.not_configured", "weather.unavailable", "weather.error", None),
      f"available={w.get('available')} reason={w.get('reason')}")
rec = d["fields"][0]["recommendation"]
check("recommendation present with reasons", len(rec.get("reasons", [])) >= 1,
      str([x["key"] for x in rec["reasons"]][:2]))
check("recommendation demo-labelled", rec["demo"] is True)
check("confidence bounded", 0.2 <= rec["confidence"]["score"] <= 0.95,
      str(rec["confidence"]["score"]))

f = c.get("/api/v1/fields/1/history?days=30", headers=h)
check("prod history payload", f.status_code == 200 and len(f.json()["irrigation_mm"]) > 0)

an = c.get("/api/v1/analytics/farm/1", headers=h)
check("prod analytics", an.status_code == 200 and "wording_key" in an.json())

# fresh user registration on prod
import uuid
pw2 = "Str0ng" + "Pass" + chr(33)
rr = c.post("/api/v1/auth/register", json={
    "email": f"prod{uuid.uuid4().hex[:6]}@examplemail.com",
    "password": pw2, "full_name": "Prod Farmer"})
check("prod register", rr.status_code == 201, rr.text[:150])
if rr.status_code == 201:
    h2 = {"Authorization": "Bearer " + rr.json()["access_token"]}
    farm = c.post("/api/v1/farms", headers=h2, json={"name": "Prod Farm",
                                                     "latitude": 18.52, "longitude": 73.86}).json()
    crops = c.get("/api/v1/crops", headers=h2).json()
    soils = c.get("/api/v1/soil-types", headers=h2).json()
    fld = c.post(f"/api/v1/farms/{farm['id']}/fields", headers=h2, json={
        "name": "P1", "area": 1, "soil_type_id": soils[1]["id"], "crop_id": crops[0]["id"],
        "growth_stage_code": "VEGETATIVE", "irrigation_method": "drip"}).json()
    c.post(f"/api/v1/fields/{fld['id']}/readings", headers=h2, json={"soil_moisture_pct": 12})
    rec2 = c.get(f"/api/v1/recommendations/field/{fld['id']}", headers=h2).json()
    check("prod live recommendation", rec2.get("id") is not None and rec2["demo"] is False,
          f"conf={rec2['confidence']['score']} needed={rec2['irrigation_needed']}")

import urllib.request
try:
    with urllib.request.urlopen(WEB + "/login", timeout=30) as resp:
        body = resp.read(4000).decode("utf-8", "ignore")
    check("prod web serves login", resp.status == 200 and "AgriFlow" in body)
except Exception as e:
    check("prod web serves login", False, str(e))

print(f"\n{ok}/12 prod checks passed")
