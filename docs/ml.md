# AgriFlow — Machine Learning Roadmap & Pipeline

ML is **not** in the MVP (§78 Phase 1: "Do NOT implement: Complex ML"). This document defines the
discipline that governs when and how it arrives, per master spec §34–§38. Application code and ML
code stay separate (§76.9): everything below lives under `ml/` (src/, datasets/, notebooks/,
models/, evaluation/) and only writes through the recommendation schema in `docs/api-contract.md`.

## 1. The mandated sequence (§34)

```
Rule-based baseline (rules-1.0 — shipped, docs/irrigation-engine.md)
        ↓
Collect historical data (recommendations + events + feedback + readings, §21)
        ↓
Evaluate baseline (how often was rules-1.0 "right"?)
        ↓
Feature engineering (this doc, §35)
        ↓
ML model (RandomForest first, §34/§55)
        ↓
Compare ML vs baseline (this doc, §6 metrics + §7 gate)
        ↓
Deploy ONLY if ML improves performance — and still inside the safety rails (§38)
```

No neural networks to start with (§34). Random Forest first; XGBoost/LightGBM "where appropriate";
time-series models later; deep learning only if justified by data (§34, §55 — do not add libraries
without a reason).

## 2. Phase 0 — baseline as the teacher & the yardstick

`irrigation_recommendations` rows already persist everything needed: `inputs_digest`,
`engine_version`, urgency, confidence, reasons, expiry. `irrigation_events` record what the farmer
actually did; `farmer_feedback.useful` records judgment (§21). The rules engine is simultaneously
(1) the shipped product, (2) the labeling weak-signal, and (3) the incumbent any model must beat.

## 3. Data collection (§34)

What accumulates passively from day one:

- Decision context: full inputs_digest per recommendation (moisture+source+age, rain 24 h, ET₀,
  crop, stage, soil).
- Outcome: did the farmer irrigate (events, including against *not-irrigate* recommendations — a
  farmer irrigating anyway is a negative-class signal), how much (mm/liters), when relative to
  recommended window.
- Ground truth proxy: post-irrigation moisture trajectory from sensors/manual readings; crop-stage
  progression; feedback flags.
- Meta: engine_version, weather provider availability at decision time, override records (§46).

Minimum viable corpus before any training (documented gate, honest numbers over vibes):
**≥ 10 fields × 1 full crop season**, or ≥ 1,000 decision–outcome pairs, with moisture readings on
≥ 60% of days. Below that, models will overfit the seasonality of a single region — we say so
rather than ship them.

## 4. Features (§35)

Feature vector per (field, decision day). Directly from §35, plus engineered aggregates:

| Feature | Source | Type | Notes |
|---|---|---|---|
| soil_moisture | latest reading | float % | null-masked |
| moisture_age_hours | computed | float | staleness is itself informative (§39) |
| moisture_source | manual/sensor/none | categorical | sensor trusted differently |
| temperature | weather current | float °C | |
| humidity | weather current | float % | |
| rain_probability | forecast 24 h | float % | |
| forecast_rainfall | forecast 24–48 h mm | float | |
| recent_rainfall | 24h/72h/7d mm | floats | |
| wind_speed | weather | km/h | evaporative demand (§16) |
| solar_radiation | when available | MJ/m²/d | often missing → mask |
| crop_type | fields→crops | categorical | target-encoded or one-hot |
| growth_stage | fields | categorical ordinal | |
| soil_type | fields→soil_types | categorical | |
| field_area | fields | float ha | scale only for volume head |
| irrigation_method | fields | categorical | efficiency differs (§16) |
| days_since_last_irrigation | events | int | |
| historical_irrigation | events 30/90 d rolling mm, count | floats | |
| ET0, ETc | Hargreaves engine | floats | labeled estimate |
| (derived) 3-day moisture trend, vapor-pressure deficit, stage-days-into, rainy-season flag | | | |

Rules (§35 engineering discipline): no leakage — only data available at decision time; all
time-based splits; missing-value strategy is explicit (mask + indicator, never silent imputation);
feature pipeline is a single reusable module so training and serving cannot drift.

## 5. Targets (§36)

Start with the two §36 mandates; time-window prediction comes later.

1. **Classification** — `irrigate` vs `do_not_irrigate` over a 48 h action window. Label from the
   outcome stream: farmer irrigated within 48 h with no wetter rain ⇒ `irrigate`; adequate moisture
   held through ET without farmer action ⇒ `do_not_irrigate`; feedback-confirmed recommendations
   count as soft validation. Ambiguous cases are excluded from training, not guessed (counted and
   reported).
2. **Regression** — `estimated irrigation requirement` (mm actually applied, farmer records,
   adjusted by method efficiency) — the model learns "how much", evaluated against recorded events.
3. Later: recommended irrigation window (time prediction, §36) once event timestamps are dense.

## 6. Evaluation (§37)

Split by **field-season blocks, time-ordered** (train on earlier weeks, validate on later); never
random row splits (leakage). Report per-region/crop slices too — averages hide failures.

- Classification: precision, recall, F1, full confusion matrix (§37).
- Regression: MAE, RMSE, R² (§37).

### The asymmetric farm-safety cost framing (§37)

§37 is explicit that agricultural safety outweighs raw accuracy, and the two error types are NOT
equivalent:

- **False negative — model says "don't irrigate" when irrigation was needed** → crop stress/yield
  loss. On a critical-stage crop this is catastrophic for the farmer.
- **False positive — model says "irrigate" unnecessarily** → wasted water, energy cost, disease
  risk. Bad, but recoverable.

Therefore we define a cost-weighted score instead of chasing accuracy:

```
Cost = FN_count × C_fn + FP_count × C_fp        (C_fn = 5× C_fp initial policy weight)
```

`C_fn` uplift is larger during stages flagged `critical` (crop DB) — encoded per-sample weight in
both the training class_weight and the eval metric. Both error types are **tracked separately in
every report** (§37 "Track both error types"), with baseline (rules-1.0) numbers printed alongside.
Regression is evaluated with an asymmetric loss view too: under-prediction of mm (crop stress) is
reported separately from over-prediction (water waste).

Also always reported: calibration (a "confidence 0.8" prediction should be right ~80% of the time —
reliability diagram; our §20 confidence rubric must not be out-calibrated by the ML it joins),
behavior on stale/missing sensor data (§39 degradation must persist), and explainability output
(feature importances + per-decision top features feeding `reasons[]`).

## 7. Deployment gate (§34, §38)

An ML model ships **only** when ALL hold. Each item is a checked artifact in `ml/evaluation/`:

1. **Dataset threshold met** (§3 above), documented counts, no leakage audit findings.
2. **Beats rules-1.0** on the cost-weighted classification score AND on regression MAE, on a
   time-forward holdout, by a margin ≥ 10% relative — ties go to rules (simpler, explainable,
   §76.19).
3. **No slice regression**: not meaningfully worse for any crop/region with ≥ 50 decisions.
4. **Safety rails preserved (§38)** — architecture ships as:

```
ML prediction
     +
Safety constraints      →  rules layer clamps: max depth/method, saturation block,
Agronomic rules            deferral to real rain, critical-stage tightening
     ↓
Final recommendation     (rules may override/block unsafe model output; never the reverse)
```

   Concretely: the model proposes; `rules-1.0` guards; the merged output is what users see, with
   `engine_version: "rf-x.y"` and reason keys stating the prediction is a **model prediction**,
   distinct from measured/estimated values (contract & §15 labeling).
5. **Never controls equipment** (§38, §66): the ML ceiling is a recommendation a human may ignore;
   no closed loop to pumps exists or is added.
6. **Shadow mode first**: 2–4 weeks where the model scores silently next to rules-1.0, agreement/
   disagreement logged; promotion requires the shadow report to reproduce the offline win.
7. **Kill switch**: `ML_ENABLED=false` env (and per-field admin flag) reverts instantly to
   rules-1.0 with no data loss; rollback documented in deployment.md.
8. **Honesty review**: model card in `ml/models/<name>/MODEL_CARD.md` — training data window,
   known biases (region/crop coverage), error rates by type, "not validated agronomic advice"
   statement (§1, §20 "do not make confidence scores appear scientifically validated unless
   they actually are").

## 8. Tech & layout (§55)

Python, pandas, numpy, scikit-learn (RandomForest baselines for both heads). Optional later:
XGBoost/LightGBM/PyTorch — each requires a written justification in its model card. Training is a
batch job (`ml/src/train.py`, run manually or via a scheduled `ml_train` job on the worker, §50);
serving loads a versioned artifact through the same internal interface as the rules engine, behind
the gate above. Models stored in `ml/models/`, never in the API package; API code imports zero ML
libraries (§76.9).

## 9. What "success" looks like

Not leaderboard accuracy. Success = fewer critical-stage false negatives at equal-or-lower water
use than rules-1.0, measured on real farmer outcomes (§21 feedback + event streams), with the rules
layer still able to veto anything, and every claim in the UI still labeled measured/forecast/
estimated/predicted (§15).
