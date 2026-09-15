# AgriFlow — Sensor Integration

Two states of the world, both honest (§72): **today** the platform supports manual readings plus a
device-key HTTP ingestion API; **later** an ESP32/MQTT fleet plugs in without touching the engine.
No hardware is required for any release (§12, §65).

## 1. Where sensors sit in the architecture (§12, §65)

Master spec §65's future flow and what exists today:

```
FUTURE (Phase 2, §65)                 TODAY (MVP)
─────────────────────                 ─────────────────────────────────
ESP32 + soil/cap sensor      HTTP/TLS
Temp/DHT humidity   ──▶ MQTT ──▶ IoT ──▶ Sensor ──▶ Postgres ──▶ Irrigation ──▶ Farmer
RTC                 │  broker  Gateway │ Service │      │       Engine
                    │                  │         │      │
                    └── (not shipped)  │         │      │
                                       ▼         ▼      ▼
Device (ESP32 w/ SIM/WiFi) ── POST /api/v1/sensors/{id}/readings ──▶ same validation ──▶ same
    X-Device-Key: ***                       (inside services/api)     storage & recompute
```

The "Sensor Service" box of §65 is implemented as the device-authenticated routes inside the API
(ADR-003 in architecture.md). When an MQTT gateway arrives, it becomes **another client of this
exact HTTP contract** (or an in-cluster consumer writing through the same repository layer) —
schema, validation, and the engine are unchanged. That is the whole point of building the
abstraction now (§12).

## 2. Data model (§13)

`Sensor` — id, field_id, type (`soil_moisture` today; weather-station/EC/leaf-temp later without
engine rewrites, §13), manufacturer, device_identifier (unique per field), status
(online|offline), device_key_hash (plaintext key shown once at provisioning), installed_at,
last_seen_at, expected_interval_min.

`SensorReading` — id, sensor_id, timestamp (UTC), soil_moisture, temperature, humidity,
battery_level (+ quality_flag). See docs/database.md for columns/types/indexes.

Registering a sensor is a farmer action through the normal API:

```
POST /api/v1/fields/{field_id}/sensors
  { "type": "soil_moisture", "manufacturer": "Acme", "device_identifier": "ESP32-A7F3" }
→ 201 { "id": 5, ..., "device_key": "<shown exactly once — store on device>" }
```

## 3. Current ingestion contract (device auth, NOT user auth)

Per the frozen contract:

```
POST /api/v1/sensors/{id}/readings
Headers:  X-Device-Key: ***
Body:     { "soil_moisture_pct": 31.5,
            "temperature_c": 27.8,        # optional
            "humidity_pct": 60.2,         # optional
            "battery_level": 87,          # optional
            "timestamp": "2026-09-15T04:12:00Z" }   # optional; server UTC-normalizes if absent
→ 201 Reading stored
→ 401 {"error":{"code":"sensor.invalid_key"}}   on wrong/missing/revoked key
→ 422 {"error":{"code":"validation.impossible_value", ...}} on out-of-range data (§40)
→ 404 unknown sensor
→ 429 device rate limit
```

Server behavior on success: validate ranges → reject or flag quality → upsert
`sensor.last_seen_at = now()`, flip status online → enqueue recommendation-recompute job (§50) →
201. Readings are never echoed back into user endpoints as "current" unless fresh (§4).

Reference device flow (pseudocode, transport-agnostic):

```python
# ESP32 loop sketch (illustrative — not shipped firmware)
read_sensor()                      # capacitive probe, DHT, battery ADC
POST https://agriflow.example/api/v1/sensors/5/readings
  headers: X-Device-Key: ***
  body: readings + device timestamp
on 401: halt + blink error (key revoked)     # never retry-spam
on 5xx/timeout: keep in flash queue, retry with backoff ≤ every 15 min
```

Manual farmer entry uses the user-auth sibling `POST /fields/{id}/readings` (source `manual`) —
same validation, same downstream path, different auth (contract §Soil moisture readings).

## 4. Validation & data quality (§40)

Applied at the API edge (Pydantic) and again as DB CHECKs:

| Rule | Behavior |
|---|---|
| soil moisture outside 0–100% | 422 `validation.impossible_value` — rejected (spec's `350%` example) |
| temperature outside −30…60 °C | 422 rejected |
| humidity/battery outside 0–100 | 422 rejected |
| missing timestamp | server assigns received-at UTC; flag `quality_flag='no_ts'` |
| duplicate reading (same sensor, same ts ±2 s) | idempotent 200/201 no double-row |
| spike (Δ vs prior > 25 pts within one interval) | stored but `quality_flag='spike'`; engine ignores flagged values for band decision, confidence notes it (§40 "rejected or flagged") |
| future-dated beyond clock-skew tolerance | rejected |

## 5. Offline / stale handling (§39)

The §39 ladder, exactly:

```
Sensor offline
      ↓
Do not pretend data is current
      ↓
Use last known reading
      ↓
Lower confidence
      ↓
Notify farmer
```

Implementation:

1. **Detection** — worker sweep: `now() − last_seen_at > 2 × expected_interval_min` (default
   cadence 60 min ⇒ offline at > 2 h) ⇒ status `offline`, generate `sensor_offline` notification
   (§24) — rate-limited to one open alert per sensor, resolved on next reading.
2. **Aging policy** (engine constants in config.py):
   - ≤ 12 h: fresh — full confidence credit.
   - 12–48 h: stale — partial credit, warning `warnings.stale_moisture` with `age_hours` param;
     UI wording: *"Soil moisture data is 18 hours old. Recommendation confidence is reduced."*
     (§39 example, verbatim in spirit; text via i18n key).
   - > 48 h: treated as **absent** — no moisture factor in confidence, status can degrade to
     `unknown`, engine answers from weather/ET only and says so (§72: "No sensor connected."
     when none exists at all).
3. **Never interpolate** between old readings to fake currency; `source`/`measured_at`/`age_hours`
   ride with every moisture value in API payloads (contract farms/summary).
4. **Recovery** — first new reading clears the offline alert and restores confidence; the
   recompute job refreshes recommendations immediately.

## 6. Security notes (details in docs/security.md)

- Device keys: ≥ 128-bit random, stored **hashed** (bcrypt/sha256), shown once, revocable per
  sensor without touching others; rotation = re-provision (§43 "never expose private sensor
  credentials").
- HTTPS-only in production; device endpoints rate-limited per sensor; no PII or farm coordinates
  returned to device-auth calls — ingestion responses contain status only (§44).
- A device may write only to its own sensor id (key ⇔ sensor binding checked server-side).

## 7. MQTT path, when it comes (§65)

Planned shape (no commitment until hardware partners exist — §71 "clearly document external
dependencies"):

- Broker (Mosquitto/Eclipse) at the farm or regional gateway; topics
  `agriflow/v1/{org}/{device_id}/readings` and `/status` (retained + LWT for instant offline
  signal).
- Gateway service verifies device tokens, then calls the **same ingestion contract** this doc
  defines — meaning everything in §3–§5 stays valid.
- Device registry grows a `transport` column (http|mqtt); OTA/config topics come later.
- The engine continues to require nothing: sensor data is optional-by-design (§12).

## 8. Testing (§57)

Contract tests pin: key auth matrix (401 cases), range rejects incl. 350%, spike flagging,
duplicate idempotency, last_seen/status transitions, staleness thresholds at 11 h 59 m vs 12 h vs
48 h boundaries, and that a recommendation computed from stale data emits the exact warning +
reduced confidence factors (§39 + §20 together).
