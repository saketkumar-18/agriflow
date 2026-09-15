"""Seeding: configurable crop/soil reference tables (spec 7/9) + demo dataset (spec 58/59).

Demo records carry demo=True everywhere and are generated with a fixed seed so
they are reproducible and clearly synthetic. Live engine inputs EXCLUDE demo
weather observations so demo history never pollutes real recommendations.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.models import (
    Crop, Farm, Field, GrowthStage, IrrigationEvent, IrrigationMethod, ReadingSource,
    Role, Sensor, SensorReading, SoilMoistureReading, SoilType, User,
    WeatherObservation,
)
from app.weather import lat_key

# FAO-56 Annex + ICIS bulks: Kc by stage, root depth, maturity. Values are advisory
# reference ranges labelled configurable estimates (docs/irrigation-engine.md).
def _stages(germ, veg, flow, fruit, mat) -> dict:
    return {
        "GERMINATION": {"kc": germ, "critical": False},
        "VEGETATIVE": {"kc": veg, "critical": False},
        "FLOWERING": {"kc": flow, "critical": True},
        "FRUITING": {"kc": fruit, "critical": True},
        "MATURITY": {"kc": mat, "critical": False},
        "HARVEST": {"kc": mat, "critical": False},
    }

CROPS = [
    ("Wheat", "Triticum aestivum", 700, 120, _stages(0.45, 0.80, 1.15, 1.05, 0.45), "crop.wheat.advisory"),
    ("Rice", "Oryza sativa", 600, 130, _stages(1.10, 1.15, 1.25, 1.20, 0.95), "crop.rice.advisory"),
    ("Maize", "Zea mays", 800, 110, _stages(0.45, 0.75, 1.15, 1.05, 0.55), "crop.maize.advisory"),
    ("Tomato", "Solanum lycopersicum", 500, 95, _stages(0.55, 0.75, 1.05, 1.15, 0.90), "crop.tomato.advisory"),
    ("Potato", "Solanum tuberosum", 500, 100, _stages(0.50, 0.70, 1.05, 1.15, 0.75), "crop.potato.advisory"),
    ("Cotton", "Gossypium hirsutum", 1000, 165, _stages(0.40, 0.55, 1.00, 1.15, 0.70), "crop.cotton.advisory"),
    ("Sugarcane", "Saccharum officinarum", 1000, 330, _stages(0.45, 0.85, 1.05, 1.00, 0.80), "crop.sugarcane.advisory"),
    ("Groundnut", "Arachis hypogaea", 500, 110, _stages(0.40, 0.50, 0.90, 1.05, 0.60), "crop.groundnut.advisory"),
    ("Mustard", "Brassica juncea", 600, 115, _stages(0.45, 0.70, 1.00, 0.95, 0.50), "crop.mustard.advisory"),
    ("Onion", "Allium cepa", 400, 100, _stages(0.70, 0.80, 1.05, 1.00, 0.75), "crop.onion.advisory"),
]

# % by volume, typical textbook ranges (estimates — is_estimate=True always).
SOILS = [
    ("Sandy", 12.0, 4.0, 1.6, 80), ("Loamy", 22.0, 8.0, 1.4, 140),
    ("Clay", 28.0, 14.0, 1.3, 120), ("Sandy loam", 17.0, 6.0, 1.5, 110),
    ("Clay loam", 25.0, 11.0, 1.4, 130), ("Custom", 20.0, 8.0, 1.4, 120),
]


def seed_reference(db: Session) -> None:
    if db.scalar(select(SoilType).limit(1)) is None:
        for name, fc, pwp, bd, whc in SOILS:
            db.add(SoilType(name=name, field_capacity_pct=fc, wilting_point_pct=pwp,
                            bulk_density=bd, water_holding_capacity_mm_per_m=whc,
                            is_estimate=True, label_key=f"soil.{name.lower().replace(' ', '_')}"))
    if db.scalar(select(Crop).limit(1)) is None:
        for name, sci, root, mat, stages, adv in CROPS:
            db.add(Crop(name=name, scientific_name=sci, root_depth_mm=root,
                        maturity_days=mat, stage_params=stages, advisory_key=adv))
    db.commit()


def seed_users(db: Session) -> None:
    if db.scalar(select(User).limit(1)) is not None:
        return
    farmer = User(email="farmer@demo.agriflow.dev", password_hash=hash_password("DemoFarmer#1"),
                  full_name="Demo Farmer", role=Role.farmer, language="en", demo=True)
    agr = User(email="agronomist@demo.agriflow.dev", password_hash=hash_password("DemoAgro#12"),
               full_name="Demo Agronomist", role=Role.agronomist, language="en", demo=True)
    adm = User(email="admin@demo.agriflow.dev", password_hash=hash_password("DemoAdmin#12"),
               full_name="Demo Admin", role=Role.admin, language="en", demo=True)
    db.add_all([farmer, agr, adm])
    db.commit()


def seed_demo(db: Session) -> None:
    """One farm with 3 fields near Guwahati (IITG area) + 45 days synthetic history."""
    seed_reference(db)
    seed_users(db)
    farmer = db.scalar(select(User).where(User.email == "farmer@demo.agriflow.dev"))
    if db.scalar(select(Farm).where(Farm.farmer_id == farmer.id).limit(1)):
        return
    rng = random.Random(42)
    now = datetime.now(timezone.utc)
    farm = Farm(farmer_id=farmer.id, name="Green Valley Farm",
                location_text="Near Guwahati, Assam", latitude=26.144, longitude=91.736,
                total_area=2.4, area_unit="ha", demo=True)
    db.add(farm)
    db.flush()

    wheat = db.scalar(select(Crop).where(Crop.name == "Wheat"))
    rice = db.scalar(select(Crop).where(Crop.name == "Rice"))
    tomato = db.scalar(select(Crop).where(Crop.name == "Tomato"))
    loamy = db.scalar(select(SoilType).where(SoilType.name == "Loamy"))
    clay = db.scalar(select(SoilType).where(SoilType.name == "Clay loam"))
    sandy = db.scalar(select(SoilType).where(SoilType.name == "Sandy loam"))

    fields = [
        Field(farm_id=farm.id, name="Field A", area=1.0, area_unit="ha",
              soil_type_id=loamy.id, crop_id=wheat.id, growth_stage=GrowthStage.VEGETATIVE,
              irrigation_method=IrrigationMethod.furrow, water_source="borewell", demo=True),
        Field(farm_id=farm.id, name="Field B", area=0.9, area_unit="ha",
              soil_type_id=clay.id, crop_id=rice.id, growth_stage=GrowthStage.FLOWERING,
              irrigation_method=IrrigationMethod.flood, water_source="canal", demo=True),
        Field(farm_id=farm.id, name="Field C", area=0.5, area_unit="ha",
              soil_type_id=sandy.id, crop_id=tomato.id, growth_stage=GrowthStage.VEGETATIVE,
              irrigation_method=IrrigationMethod.drip, water_source="borewell", demo=True),
    ]
    db.add_all(fields)
    db.flush()

    # sensor on field A
    from app.services import sensor_key_pair
    key, kh = sensor_key_pair()
    sensor = Sensor(field_id=fields[0].id, type="soil_moisture", manufacturer="DemoSense",
                    device_identifier="demo-sensor-A1", device_key_hash=kh,
                    last_seen_at=now - timedelta(hours=3), demo=True)
    db.add(sensor)

    # 45 days of weather observations + moisture + irrigation history
    base_m = {f.id: 34.0 for f in fields}
    for d in range(45, 0, -1):
        day = now - timedelta(days=d)
        rain = round(rng.choice([0, 0, 0, 0, 0.5, 1.2, 3.0, 8.5]) , 1)
        tmax = round(27 + rng.uniform(-2, 5) + (2 if d < 15 else 0), 1)
        tmin = round(tmax - 7 - rng.uniform(0, 3), 1)
        et0 = round(0.0023 * ((tmax + tmin) / 2 + 17.8) * ((tmax - tmin) ** 0.5) * 12.0, 2)
        db.add(WeatherObservation(lat_key=lat_key(farm.latitude, farm.longitude),
                                  observed_at=day, temp_c=(tmax + tmin) / 2,
                                  humidity_pct=round(rng.uniform(50, 85)),
                                  wind_kmh=round(rng.uniform(3, 18), 1), rain_mm=rain,
                                  et0_mm=et0, tmax_c=tmax, tmin_c=tmin,
                                  provider="demo-seed", demo=True))
        for f, crop in zip(fields, (wheat, rice, tomato)):
            kc = crop.stage_params[f.growth_stage.value]["kc"]
            use = et0 * kc * (1.2 if rain < 1 else 0.3)
            base_m[f.id] = max(f.soil_type.wilting_point_pct + 1,
                               min(f.soil_type.field_capacity_pct - 1,
                                   base_m[f.id] + rng.uniform(-3, 2) - use * 0.6 + rain * 1.1))
            if d % 3 == 0:
                db.add(SoilMoistureReading(field_id=f.id, value_pct=round(base_m[f.id], 1),
                                           source=ReadingSource.manual, taken_at=day, demo=True))
        if sensor.id:
            pass  # sensor id assigned after flush; handled below
    db.flush()
    for d in range(30, 0, -2):
        db.add(SensorReading(sensor_id=sensor.id, timestamp=now - timedelta(days=d),
                             soil_moisture=round(base_m[fields[0].id] + rng.uniform(-2, 2), 1),
                             temperature=round(rng.uniform(20, 32), 1),
                             humidity=round(rng.uniform(45, 85)), battery_level=round(rng.uniform(55, 99)),
                             demo=True))
    # irrigation events: ~every 6 days per field
    for f in fields:
        for d in (38, 32, 26, 20, 14, 8, 3):
            mm = round(rng.uniform(14, 24), 1)
            ha = f.area
            db.add(IrrigationEvent(field_id=f.id, farmer_id=farmer.id,
                                   irrigated_at=now - timedelta(days=d, hours=6),
                                   duration_minutes=round(mm * 3.2), amount_mm=mm,
                                   liters=round(mm * 10000 * ha), source="manual", demo=True))
    # fresh readings so the demo dashboard shows recent data + meaningful confidence
    db.add(SoilMoistureReading(field_id=fields[0].id, value_pct=17.5,
                               source=ReadingSource.manual, taken_at=now - timedelta(hours=4), demo=True))
    db.add(SensorReading(sensor_id=sensor.id, timestamp=now - timedelta(hours=3),
                         soil_moisture=18.1, temperature=27.0, humidity=82.0,
                         battery_level=91.0, demo=True))
    db.add(SoilMoistureReading(field_id=fields[1].id, value_pct=24.0,
                               source=ReadingSource.manual, taken_at=now - timedelta(hours=5), demo=True))
    # Field C: deliberately DRY (below threshold) so demo shows an active recommendation
    db.add(SoilMoistureReading(field_id=fields[2].id, value_pct=7.5,
                               source=ReadingSource.manual, taken_at=now - timedelta(hours=2), demo=True))
    db.commit()

    # Generate current recommendations and attach the 2 most recent events of each
    # field to a recommendation, so analytics has an honest recommendation-linked baseline.
    from app.services import store_recommendation
    for f in fields:
        rec = store_recommendation(db, f)
        evs = db.query(IrrigationEvent).filter(IrrigationEvent.field_id == f.id) \
            .order_by(IrrigationEvent.irrigated_at.desc()).limit(2).all()
        for e in evs:
            e.recommendation_id = rec.id
            e.demo = True
    db.commit()
