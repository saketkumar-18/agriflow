"""Compare the trained model against the RULES baseline on the same held-out split.

The model is deployable ONLY if:
  safety_cost(model) < safety_cost(rules)  AND  f1(model) >= f1(rules)
Otherwise the rules engine stays in production (spec 34: deploy only if ML improves).

Run AFTER train.py, with --csv pointing at the same dataset used for training:
    python evaluate.py --csv ../datasets/train_v1.csv --model-dir ../models/current
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import confusion_matrix, f1_score
from sklearn.model_selection import train_test_split

sys.path.insert(0, ".")  # train.py sits next to this file
sys.path.insert(1, str(Path(__file__).resolve().parents[2] / "services" / "api"))  # rules engine
from train import FEATURES_CAT, FEATURES_NUM, FN_WEIGHT, load  # noqa: E402


def rules_prediction(row) -> int:
    """Replay the shipped rule thresholds at export time (documented approximation:
    depletion over MAD => need). Keeps the comparison honest — same signal source."""
    from app.engine import compute_recommendation, EngineInput, MoistureInput
    from datetime import datetime, timezone
    stage = str(row.get("stage", "VEGETATIVE"))
    inp = EngineInput(
        crop_name=str(row.get("crop", "")), crop_id=0, growth_stage=stage,
        kc=1.0, critical_stage=stage in ("FLOWERING", "FRUITING"),
        root_depth_mm=700, field_capacity_pct=22, wilting_point_pct=8,
        bulk_density=None, area_ha=float(row.get("area_ha", 1.0)),
        irrigation_method=str(row.get("method", "flood")),
        moisture=MoistureInput(float(row["moisture_pct"]), "manual",
                               datetime.now(timezone.utc)),
        rain_prob_next24_pct=float(row.get("rain_next_24h_pct", 0)),
        forecast_rain_mm_48h=float(row.get("rain_next_48h_mm", 0)),
        recent_rain_mm_72h=float(row.get("recent_rain_72h_mm", 0)),
        et0_mm=float(row.get("et0_mm", 0)) or None,
        weather_available=True)
    return int(compute_recommendation(inp).irrigation_needed)


def cost(cm) -> float:
    return float((cm * np.array([[1.0, FN_WEIGHT], [FN_WEIGHT, 1.0]])[1]).sum()) / max(1, cm.sum())


def main(csv_path: str, model_dir: str) -> dict:
    df = load(csv_path)
    y = df["label_need"]
    X = df[FEATURES_NUM + FEATURES_CAT]
    if y.nunique() < 2:
        return {"deployable": False, "reason": "single-class dataset"}
    _, Xte, _, yte = train_test_split(X, y, test_size=0.25, random_state=7, stratify=y)
    raw = pd.read_csv(csv_path).iloc[Xte.index]

    rules_pred = raw.apply(rules_prediction, axis=1).to_numpy()
    rules_cm = confusion_matrix(yte, rules_pred, labels=[0, 1])
    rules = {"f1": round(float(f1_score(yte, rules_pred, zero_division=0)), 3),
             "safety_cost": round(cost(rules_cm), 3), "confusion_matrix": rules_cm.tolist()}

    model = {"f1": None, "safety_cost": None}
    mpath = Path(model_dir) / "clf_need.joblib"
    if mpath.exists():
        clf = joblib.load(mpath)
        mp = clf.predict(Xte)
        mcm = confusion_matrix(yte, mp, labels=[0, 1])
        model = {"f1": round(float(f1_score(yte, mp, zero_division=0)), 3),
                 "safety_cost": round(cost(mcm), 3), "confusion_matrix": mcm.tolist()}
        deploy = model["safety_cost"] < rules["safety_cost"] and model["f1"] >= rules["f1"]
    else:
        deploy = False

    result = {"baseline_rules": rules, "model": model,
              "deployable": bool(deploy),
              "note": "Even when deployable, rules remain as safety rails (spec 38) "
                      "and every ML recommendation keeps its explanation + confidence."}
    Path(model_dir).mkdir(parents=True, exist_ok=True)
    (Path(model_dir) / "comparison.json").write_text(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--model-dir", default="../models/current")
    print(json.dumps(main(ap.parse_args().csv, ap.parse_args().model_dir), indent=2))
