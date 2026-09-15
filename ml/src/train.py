"""Train RandomForest baselines for need-classification and mm-regression.

Gate (docs/ml.md): the model is only worth deploying if it beats the rules
baseline on the SAME held-out split, under the asymmetric farm-safety cost:
missing a real irrigation need (false negative) costs a crop; unnecessary
irrigation (false positive) costs water. A missed need weighs 3x in eval.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.metrics import (
    confusion_matrix, f1_score, mean_absolute_error, mean_squared_error,
    precision_score, r2_score, recall_score,
)
from sklearn.model_selection import train_test_split

FEATURES_NUM = ["moisture_pct", "moisture_age_h", "rain_next_24h_pct",
                "rain_next_48h_mm", "recent_rain_72h_mm", "et0_mm", "etc_mm",
                "depletion_pct", "area_ha", "days_since_irrigation"]
FEATURES_CAT = ["crop", "stage", "soil", "method"]
FN_WEIGHT = 3.0  # a missed irrigation need costs 3x an unnecessary one (docs/ml.md)


def load(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["days_since_irrigation"] = df["days_since_irrigation"].fillna(
        df["days_since_irrigation"].median() if df["days_since_irrigation"].notna().any() else 7)
    for c in FEATURES_CAT:
        df[c] = df[c].astype("category").cat.codes
    return df


def train(csv_path: str, model_dir: str) -> dict:
    df = load(csv_path)
    X = df[FEATURES_NUM + FEATURES_CAT]
    out: dict = {"n_rows": int(len(df)), "features": FEATURES_NUM + FEATURES_CAT}

    y = df["label_need"]
    if y.nunique() < 2 or len(y) < 60:
        out["classification"] = {"skipped": "not enough labeled variety/rows yet (collect more data)"}
    else:
        Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.25, random_state=7, stratify=y)
        clf = RandomForestClassifier(n_estimators=200, min_samples_leaf=5,
                                     class_weight="balanced", random_state=7)
        clf.fit(Xtr, ytr)
        pred = clf.predict(Xte)
        cm = confusion_matrix(yte, pred, labels=[0, 1])
        weighted = float((cm * np.array([[1.0, FN_WEIGHT], [FN_WEIGHT, 1.0]])[1]).sum()) / max(1, len(yte))
        out["classification"] = {
            "precision": round(float(precision_score(yte, pred, zero_division=0)), 3),
            "recall": round(float(recall_score(yte, pred, zero_division=0)), 3),
            "f1": round(float(f1_score(yte, pred, zero_division=0)), 3),
            "confusion_matrix": cm.tolist(),
            "safety_cost_per_case": round(weighted, 3),
        }
        joblib.dump(clf, Path(model_dir) / "clf_need.joblib")

    reg_df = df[df["target_mm"].notna() & (df["label_need"] == 1)]
    if len(reg_df) >= 60:
        Xr, yr = reg_df[FEATURES_NUM + FEATURES_CAT], reg_df["target_mm"]
        Xtr, Xte, ytr, yte = train_test_split(Xr, yr, test_size=0.25, random_state=7)
        reg = RandomForestRegressor(n_estimators=200, min_samples_leaf=5, random_state=7)
        reg.fit(Xtr, ytr)
        pr = reg.predict(Xte)
        out["regression"] = {
            "mae_mm": round(float(mean_absolute_error(yte, pr)), 2),
            "rmse_mm": round(float(np.sqrt(mean_squared_error(yte, pr))), 2),
            "r2": round(float(r2_score(yte, pr)), 3),
        }
        joblib.dump(reg, Path(model_dir) / "reg_mm.joblib")
    else:
        out["regression"] = {"skipped": f"only {len(reg_df)} rows with applied amounts (need 60+)"}

    Path(model_dir).mkdir(parents=True, exist_ok=True)
    (Path(model_dir) / "metrics.json").write_text(json.dumps(out, indent=2))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--model-dir", default="../models/current")
    args = ap.parse_args()
    Path(args.model_dir).mkdir(parents=True, exist_ok=True)
    print(json.dumps(train(args.csv, args.model_dir), indent=2))
