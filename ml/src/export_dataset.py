"""Export a training dataset from the AgriFlow database (read-only).

One row per (recommendation, ±72h outcome window):

  features:   soil moisture + age, weather/forecast, ET0/ETc proxy, crop/stage
              one-hots, soil one-hots, days since last irrigation, method eff.
  label_need: 1 if the farmer irrigated within 48h after the recommendation OR
              feedback marked the recommendation useful AND they irrigated;
              0 if they explicitly did not irrigate after a "needed" rec or
              the feedback said not useful for a "not needed" rec.
              Rows with no observable outcome are DROPPED (weak labels only).
  target_mm:  amount applied (mm) for regression, when recorded.

Usage:
    python export_dataset.py --db-url sqlite:///../../services/api/agriflow.db \
        --out ../datasets/train_v1.csv --min-rows 100
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import timedelta

sys.path.insert(0, ".")  # services/api for models
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import (
    FarmerFeedback, Field, IrrigationEvent, IrrigationRecommendation,
    SoilMoistureReading,
)


def export(db_url: str, out_path: str, min_rows: int) -> int:
    engine = create_engine(db_url)
    rows: list[dict] = []
    with Session(engine) as db:
        recs = db.scalars(select(IrrigationRecommendation)
                          .order_by(IrrigationRecommendation.computed_at)).all()
        for rec in recs:
            f = db.get(Field, rec.field_id)
            if f is None:
                continue
            dig = rec.inputs_digest_json or {}
            m_val = (dig.get("moisture") or {}).get("value")
            if m_val is None:
                continue  # engine assumed moisture — not a trustworthy training row
            # outcome within 48h after recommendation
            nxt = db.scalars(select(IrrigationEvent)
                             .where(IrrigationEvent.field_id == f.id,
                                    IrrigationEvent.irrigated_at >= rec.computed_at,
                                    IrrigationEvent.irrigated_at <= rec.computed_at + timedelta(hours=48))
                             .order_by(IrrigationEvent.irrigated_at)).first()
            fb = db.scalars(select(FarmerFeedback)
                            .where(FarmerFeedback.recommendation_id == rec.id)).first()
            label = None
            if nxt is not None:
                label = 1
            elif fb is not None and fb.useful is False and not rec.irrigation_needed:
                label = 1  # "not needed" was wrong → they needed it (no event captured)
            elif fb is not None and fb.did_irrigate is False:
                label = 0
            elif fb is not None and fb.useful is True:
                label = int(rec.irrigation_needed)
            if label is None:
                continue
            rows.append({
                "field_id": f.id,
                "moisture_pct": m_val,
                "moisture_age_h": (dig.get("moisture") or {}).get("age_hours", 24),
                "rain_next_24h_pct": dig.get("rain_next_24h_pct", 0),
                "rain_next_48h_mm": dig.get("rain_next_48h_mm", 0),
                "recent_rain_72h_mm": dig.get("recent_rain_72h_mm", 0),
                "et0_mm": dig.get("et0_mm") or 0,
                "etc_mm": dig.get("etc_mm") or 0,
                "depletion_pct": dig.get("depletion_pct") or 0,
                "crop": dig.get("crop", ""), "stage": dig.get("stage", ""),
                "soil": f.soil_type.name, "method": f.irrigation_method.value,
                "area_ha": f.area * (0.404686 if f.area_unit == "acre" else 1.0),
                "days_since_irrigation": None,
                "label_need": label,
                "target_mm": (nxt.amount_mm if nxt and nxt.amount_mm else ""),
            })
    if len(rows) < min_rows:
        print(f"REFUSING to export: only {len(rows)} labeled rows (<{min_rows}). "
              "Keep running the rules engine and collecting data (docs/ml.md).")
        return len(rows)
    with open(out_path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows -> {out_path}")
    return len(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-url", required=True)
    ap.add_argument("--out", default="../datasets/train_v1.csv")
    ap.add_argument("--min-rows", type=int, default=100)
    export(ap.parse_args().db_url, ap.parse_args().out, ap.parse_args().min_rows)
