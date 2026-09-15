"""Integration tests: full farmer journey + RBAC + validation + offline sync."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from tests.conftest import full_farm_setup, register


def _iso(dt=None):
    return (dt or datetime.now(timezone.utc)).isoformat()


class TestAuthRBAC:
    def test_register_login_me(self, client):
        hdrs, user = register(client, "a@examplemail.com")
        assert user["role"] == "farmer"
        r = client.get("/api/v1/auth/me", headers=hdrs)
        assert r.status_code == 200 and r.json()["email"] == "a@examplemail.com"

    def test_bad_password_401_generic(self, client):
        register(client, "a2@examplemail.com", password="Original#123")
        r = client.post("/api/v1/auth/login", json={"email": "a2@examplemail.com", "password": "wrong"})
        assert r.status_code == 401
        assert r.json()["detail"]["error"]["code"] == "auth.invalid"

    def test_short_password_rejected(self, client):
        r = client.post("/api/v1/auth/register",
                        json={"email": "x@y.com", "password": "short", "full_name": "X Y"})
        assert r.status_code == 422

    def test_duplicate_email_409(self, client):
        register(client, "dup@examplemail.com")
        r = client.post("/api/v1/auth/register",
                        json={"email": "dup@examplemail.com", "password": "Passw0rd!23", "full_name": "D U"})
        assert r.status_code == 409

    def test_no_token_401(self, client):
        assert client.get("/api/v1/farms").status_code == 401

    def test_farmer_cannot_read_other_farmer(self, client):
        h1, _ = register(client, "owner@examplemail.com")
        h2, _ = register(client, "intruder@examplemail.com")
        farm = client.post("/api/v1/farms", headers=h1,
                           json={"name": "Secret Farm"}).json()
        r = client.get(f"/api/v1/farms/{farm['id']}", headers=h2)
        assert r.status_code == 403 or (r.status_code == 200 and False)
        r2 = client.get(f"/api/v1/farms/{farm['id']}/summary", headers=h2)
        assert r2.status_code == 403

    def test_public_register_cannot_make_admin(self, client):
        # role is server-decided: register always creates farmer
        _, user = register(client, "sneaky@examplemail.com")
        assert user["role"] == "farmer"


class TestFarmerJourney:
    def test_full_journey(self, client):
        """User -> Farm -> Field -> reading -> weather -> recommendation -> event ->
        feedback -> history -> analytics. The spec-57 golden path."""
        hdrs, farm_id, field_id = full_farm_setup(client)

        # soil reading
        r = client.post(f"/api/v1/fields/{field_id}/readings", headers=hdrs,
                        json={"soil_moisture_pct": 12.0, "taken_at": _iso()})
        assert r.status_code == 201, r.text

        # weather (static provider in tests; payload labels provider)
        w = client.get(f"/api/v1/weather/field/{field_id}", headers=hdrs).json()
        assert w["available"] is True and w["provider"] == "static-demo"
        assert len(w["forecast"]) >= 5

        # recommendation
        rec = client.get(f"/api/v1/recommendations/field/{field_id}", headers=hdrs).json()
        assert rec["irrigation_needed"] is True            # dry soil -> needed
        assert rec["reasons"], "recommendation must explain itself"
        assert 0.2 <= rec["confidence"]["score"] <= 0.95
        assert rec["estimated_water_requirement"]["unit"] == "mm"
        assert rec["disclaimer_key"] == "rec.disclaimer"

        # record irrigation event
        ev = client.post("/api/v1/irrigation-events", headers=hdrs, json={
            "field_id": field_id, "recommendation_id": rec["id"],
            "irrigated_at": _iso(), "amount_mm": 18, "duration_minutes": 60})
        assert ev.status_code == 201, ev.text
        assert ev.json()["liters"] == 180000.0  # 18mm over 1 ha

        # feedback
        fb = client.post("/api/v1/feedback", headers=hdrs,
                         json={"recommendation_id": rec["id"], "useful": True})
        assert fb.status_code == 201

        # history
        hist = client.get(f"/api/v1/irrigation-events?farm_id={farm_id}", headers=hdrs).json()
        assert hist["total"] == 1
        assert hist["items"][0]["amount_mm"] == 18

        # analytics wording: potential, not claimed savings
        an = client.get(f"/api/v1/analytics/farm/{farm_id}", headers=hdrs).json()
        assert "wording_key" in an and "potential" in an["wording_key"]

    def test_impossible_moisture_rejected(self, client):
        hdrs, _, field_id = full_farm_setup(client)
        r = client.post(f"/api/v1/fields/{field_id}/readings", headers=hdrs,
                        json={"soil_moisture_pct": 350})
        assert r.status_code == 422

    def test_future_timestamp_rejected(self, client):
        hdrs, _, field_id = full_farm_setup(client)
        r = client.post(f"/api/v1/fields/{field_id}/readings", headers=hdrs,
                        json={"soil_moisture_pct": 30,
                              "taken_at": _iso(datetime.now(timezone.utc) + timedelta(days=2))})
        assert r.status_code == 422

    def test_invalid_lat_rejected(self, client):
        hdrs, _ = register(client, "geo@examplemail.com")
        r = client.post("/api/v1/farms", headers=hdrs,
                        json={"name": "Bad Farm", "latitude": 999})
        assert r.status_code == 422

    def test_irrigation_event_requires_amount(self, client):
        hdrs, _, field_id = full_farm_setup(client)
        r = client.post("/api/v1/irrigation-events", headers=hdrs,
                        json={"field_id": field_id, "irrigated_at": _iso()})
        assert r.status_code == 422

    def test_no_moisture_low_confidence_recommendation(self, client):
        hdrs, _, field_id = full_farm_setup(client)
        rec = client.get(f"/api/v1/recommendations/field/{field_id}", headers=hdrs).json()
        assert rec["confidence"]["level"] in ("LOW", "MEDIUM")
        assert any(w["key"] in ("warnings.no_recent_moisture", "warnings.assumed_moisture")
                   for w in rec["warnings"])


class TestOfflineSync:
    def test_idempotent_event_replay(self, client):
        hdrs, _, field_id = full_farm_setup(client)
        payload = {"field_id": field_id, "irrigated_at": _iso(), "amount_mm": 10,
                   "idempotency_key": "abc-123"}
        r1 = client.post("/api/v1/irrigation-events", headers=hdrs, json=payload)
        r2 = client.post("/api/v1/irrigation-events", headers=hdrs, json=payload)
        assert r1.status_code in (200, 201) and r2.status_code in (200, 201)
        assert r1.json()["id"] == r2.json()["id"]  # no duplicate

    def test_sync_batch(self, client):
        hdrs, _, field_id = full_farm_setup(client)
        r = client.post("/api/v1/sync/batch", headers=hdrs, json={"actions": [
            {"local_id": "L1", "type": "irrigation_event",
             "payload": {"field_id": field_id, "irrigated_at": _iso(), "amount_mm": 12}},
            {"local_id": "L2", "type": "reading",
             "payload": {"field_id": field_id, "soil_moisture_pct": 25}},
        ]})
        assert r.status_code == 200
        statuses = [x["status"] for x in r.json()["results"]]
        assert statuses == ["created", "created"]


class TestSensors:
    def test_sensor_registration_and_device_ingestion(self, client):
        hdrs, _, field_id = full_farm_setup(client)
        s = client.post(f"/api/v1/fields/{field_id}/sensors", headers=hdrs,
                        json={"type": "soil_moisture", "device_identifier": "dev-001"})
        assert s.status_code == 201
        key = s.json()["device_key"]

        # device auth, NOT user auth
        bad = client.post(f"/api/v1/sensors/{s.json()['id']}/readings",
                          json={"soil_moisture_pct": 30}, headers={"X-Device-Key": "wrong"})
        assert bad.status_code == 401
        ok = client.post(f"/api/v1/sensors/{s.json()['id']}/readings",
                         json={"soil_moisture_pct": 15.0, "battery_level": 88},
                         headers={"X-Device-Key": key})
        assert ok.status_code == 201
        # sensor reading now feeds the engine as latest moisture
        rec = client.get(f"/api/v1/recommendations/field/{field_id}", headers=hdrs).json()
        assert rec["inputs_digest"]["moisture"]["source"] == "sensor"

    def test_spike_flagged_not_applied(self, client):
        hdrs, _, field_id = full_farm_setup(client)
        s = client.post(f"/api/v1/fields/{field_id}/sensors", headers=hdrs,
                        json={"device_identifier": "dev-002"}).json()
        key = s["device_key"]
        sid = s["id"]
        client.post(f"/api/v1/sensors/{sid}/readings", json={"soil_moisture_pct": 30},
                    headers={"X-Device-Key": key})
        r = client.post(f"/api/v1/sensors/{sid}/readings", json={"soil_moisture_pct": 95},
                        headers={"X-Device-Key": key})
        assert r.json()["quality_flag"] == "spike"
        rec = client.get(f"/api/v1/recommendations/field/{field_id}", headers=hdrs).json()
        assert rec["inputs_digest"]["moisture"]["value"] == 30.0  # spike ignored by engine


class TestAgronomistAdmin:
    def test_agronomist_reads_assigned_and_overrides(self, client):
        h_farm, _ = register(client, "farm3@examplemail.com")
        _, farm_id, field_id = full_farm_setup(client)  # farm of f1@examplemail.com
        # admin assigns agronomist
        h_admin, _ = register(client, "boss@examplemail.com", role="admin")
        h_agro, agro = register(client, "agro@examplemail.com", role="agronomist")
        r = client.post(f"/api/v1/admin/farms/{farm_id}/assign-agronomist",
                        headers=h_admin, json={"user_id": agro["id"]})
        assert r.status_code == 200
        farms = client.get("/api/v1/agronomist/farms", headers=h_agro).json()
        assert any(f["id"] == farm_id for f in farms)

        rec = client.get(f"/api/v1/recommendations/field/{field_id}", headers=h_agro).json()
        ov = client.post(f"/api/v1/recommendations/{rec['id']}/override", headers=h_agro,
                         json={"action": "defer", "reason": "Heavy rain observed on site today"})
        assert ov.status_code == 200
        assert ov.json()["override"]["action"] == "defer"
        assert ov.json()["override"]["reason"]
        # override requires reason
        bad = client.post(f"/api/v1/recommendations/{rec['id']}/override", headers=h_agro,
                          json={"action": "defer", "reason": "x"})
        assert bad.status_code == 422

        # agronomist cannot edit farmer data
        assert client.post(f"/api/v1/fields/{field_id}/readings", headers=h_agro,
                           json={"soil_moisture_pct": 50}).status_code == 403

        # advisory
        adv = client.post("/api/v1/advisories", headers=h_agro,
                          json={"field_id": field_id, "note": "Recheck moisture tomorrow morning."})
        assert adv.status_code == 201

    def test_farmer_cannot_use_admin_routes(self, client):
        hdrs, _ = register(client, "plain@examplemail.com")
        assert client.get("/api/v1/admin/stats", headers=hdrs).status_code == 403
        assert client.get("/api/v1/admin/audit", headers=hdrs).status_code == 403

    def test_audit_logs_written(self, client):
        hdrs, farm_id, _ = full_farm_setup(client)
        h_admin, _ = register(client, "boss2@examplemail.com", role="admin")
        a = client.get("/api/v1/admin/audit", headers=h_admin).json()
        actions = {i["action"] for i in a["items"]}
        assert "farm.create" in actions and "field.create" in actions
