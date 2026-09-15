# AgriFlow — Irrigation Decision Engine (`rules-1.0`)

The engine is the product's core (§14). It is deliberately **transparent**: a deterministic rules
baseline with no hidden randomness, fully unit-testable (§76.8), with every output traceable to a
named input. Master spec section numbers in (§n). Version string `engine_version: "rules-1.0"` is
stored on every recommendation so results are reproducible and auditable.

## 1. Inputs (per §14)

| Input | Source | Freshness rule |
|---|---|---|
| Crop + growth stage | `fields.crop_id`, `fields.growth_stage_code` | current DB value |
| Soil type + parameters | `fields.soil_type_id` → `soil_types` (FC, WP, bulk density, WHC) | reference data, labeled `is_estimate` when from defaults (§9) |
| Soil moisture | latest `sensor_readings`/manual readings for the field | ≤12 h fresh for full credit; >48 h treated as absent (§39) |
| Weather (temp, humidity, wind) | `WeatherProvider` snapshot | last cached fetch (§51) |
| Rain forecast (next 24–48 h) | forecast rows: rain probability + rain mm | provider freshness |
| Recent rainfall (24 h / 72 h / 7 d) | provider history + observed entries | — |
| Historical irrigation | `irrigation_events`, `days_since_last_irrigation` | — |
| Field area | `fields.area` (converted to ha) | for liter conversion |
| Irrigation method | `fields.irrigation_method` | for efficiency factor (§16) |
| ET₀ / ETc | computed (Hargreaves, §17, ADR-002) | labeled `estimated` always |

Missing inputs do not block a recommendation — they reduce confidence and emit warnings (§39, §72).

## 2. Water-requirement formula (§17, §18)

Daily crop water demand:

```
ETc = ET0 × Kc(stage)
```

- `ET0` — reference evapotranspiration (mm/day), **FAO-56 Hargreaves** from daily min/max
  temperature:
  `ET0 = 0.0023 × (Tmean + 17.8) × sqrt(Tmax − Tmin) × Ra`
  - `Tmax`, `Tmin` — daily max/min air temperature (°C) from weather data
  - `Tmean = (Tmax + Tmin) / 2`
  - `sqrt(Tmax − Tmin)` — diurnal temperature range term, a proxy for humidity/solar variability
  - `Ra` — extraterrestrial radiation (mm/day equivalent), computed from latitude and day of year
    (standard FAO-56 tables/formulas; no invented constants)
  - Hargreaves is used because only temperatures are reliably available everywhere; it is an
    **estimate**, documented as such (ADR-002, §17 "do not fabricate scientific values").
- `Kc(stage)` — crop coefficient per growth stage, read from `crop_growth_stages.kc` (configurable
  DB data, §7/§8/§17 — never hard-coded), typical stages GERMINATION→HARVEST.

Net irrigation requirement over a planning horizon `d` days (from today):

```
IrrNet = Σ_{t=1..d} ETc(t)  −  Reff  −  AvailableSoilWaterDepletion(d)
IrrGross = max(0, IrrNet) / E_app
```

- `Reff` — effective rainfall. Forecast rain counts when `rain_prob ≥ rain_prob_gate` (default
  50%): `Reff = Σ rain_mm(t) × f(prob(t))`, with `f = 1.0` when prob ≥ 70%, linear ramp below the
  gate, `0` under the gate. Past-72-h rain that percolated is folded into soil water, not double-counted.
- `AvailableSoilWaterDepletion` — water the crop can still extract:
  `ASWD = max(0, (SM_current − SM_will) / 100 × D_root × WHC_mm_per_m)`
  - `SM_current` — latest volumetric soil moisture (%) with source + age
  - `SM_will` — soil wilting point %
  - `D_root` — current effective rooting depth (mm), interpolated from `crops.root_depth_mm` by stage
  - `WHC_mm_per_m` — soil water-holding capacity per meter depth
- `E_app` — application efficiency of the irrigation method (§4 table).
- Depth-to-volume: `liters = IrrGross(mm) × area_ha × 10,000` — 1 mm over 1 ha = 10,000 L, so
  18 mm on 1 ha ≈ 180,000 L exactly as the §18 example shows.

**Everything this formula returns is labeled an estimate** with the §18 wording and a
`rec.disclaimer` key — "Do not claim precision beyond the quality of the input data" (§18).

## 3. Soil-moisture band logic per crop stage (§16)

Thresholds derive from soil physics, not magic numbers:

```
Tension band (crop stage aware):
  depletion_allowed = MAD × (FC − WP)          # MAD = management allowable depletion
  target_moisture   = FC − depletion_allowed
  critical_moisture = FC − (MAD + 0.10) × (FC − WP)
```

- Default `MAD = 0.55` for normal stages; **`critical_MAD = 0.40` when the current stage is flagged
  `critical` in the crop DB** (§8, §16 "increase sensitivity during critical growth stages") —
  i.e. flowering/fruiting crops may deplete less before irrigation triggers.
- Bands → state:
  - `SM ≥ FC − 0.25×(FC−WP)` — **wet**: no irrigation; warning if drainage risk (clay + heavy rain forecast).
  - `target < SM < wet band` — **adequate**: status `ok`, monitor.
  - `critical < SM ≤ target` — **approaching**: status `review`; recommendation `irrigation_needed=true`
    with LOW/MEDIUM urgency depending on trend (ETc, temp, rain).
  - `SM ≤ critical` — **deficit**: `irrigation_needed=true`, urgency HIGH, escalating to CRITICAL
    if also in a critical stage or Tmax > 35 °C.
- Per-field overrides: crop/stage rows may carry explicit min/max targets; soil custom rows use
  their stored FC/WP. Missing FC/WP falls back to soil-type reference values which are returned
  with `is_estimate: true` and lower confidence (§9, §20).
- If no soil moisture exists at all: engine still answers using ETc/weather, status `unknown`→
  LOW confidence with warning `warnings.no_moisture` — it does **not** pretend a value exists (§72).

## 4. Rain deferral (§16, §24)

Before finalizing, the engine checks the forecast window:

```
expected_effective_rain(48h) = Σ rain_mm(d) where prob(d) ≥ rain_prob_gate (50%)
if expected_effective_rain ≥ rain_defer_mm (8.0) and urgency < HIGH:
    defer: recommended_time shifts past the rain event,
           add reason reasons.rain_expected (i18n key + params),
           amount reduced by Reff (§2)
if urgency ≥ HIGH (critical deficit): recommend anyway + warning warnings.rain_overlap
```

Recent rainfall (last 72 h) likewise reduces `IrrNet` through soil water, "depending on
soil/crop conditions" (§16): sandy soils credit less (faster drainage/evaporation), clay more, via
soil-specific retention factors from the DB.

## 5. Irrigation-method efficiency factors (§16 "different methods have different efficiencies")

`E_app` divides the gross requirement. Initial configurable defaults (agronomy-literature ranges;
stored in DB, editable by admin, not hard-coded in engine code — §7 rule, §17 "allow validated
coefficients to be configured later"):

| Method | E_app default | Notes |
|---|---|---|
| drip | 0.90 | high uniformity, low evaporation loss |
| sprinkler | 0.75 | wind losses; wind > 20 km/h adds warning |
| furrow | 0.60 | |
| flood | 0.50 | |
| manual | 0.60 | typical hose/labour practice |
| other | 0.60 | conservative fallback |

These are **assumptions, documented as such** (§17 "Document assumptions"); per-field measured
efficiency can replace them later without engine changes.

## 6. Timing recommendation (§14 `recommended_time`)

Morning window (roughly 05:30–09:00 local) is preferred: lower ET, less wind, disease-risk tradeoff
vs evening wetness. Deferral logic (§4) can push to "after the rain event". Output ships as an i18n
key + window: `{"key": "time.tomorrow_morning", "window_start": ..., "window_end": ...}`.
CRITICAL urgency → `time.today`. Keys from the shared namespace (contract i18n section).

## 7. Confidence scoring rubric (§20)

Confidence is a **transparent additive rubric**, not a probability from a model — the docs and UI
must not imply scientific validation it doesn't have (§20).

| Factor (contract `conf.*` keys) | Weight | Condition |
|---|---|---|
| has_recent_moisture | +0.30 | reading ≤ 12 h old (sensor or manual both count; sensor +0.32) |
| stale_moisture | +0.15 (partial) | 12–48 h old |
| missing_moisture | +0.00 | > 48 h or none; `warnings.stale_moisture`/`warnings.no_moisture` |
| weather_available | +0.25 | provider returned data this cycle |
| weather_unavailable | +0.00 | reason `weather.not_configured`/`weather.unavailable` |
| known_crop_stage | +0.15 | crop + stage set with Kc rows present |
| known_soil | +0.15 | soil type with non-estimate FC/WP |
| measured_soil_defaults | +0.08 | reference-value fallback still useful, less trusted |
| irrigation_history_present | +0.10 | ≥ 3 recorded events |

`score = clamp(Σ weights, 0, 1)` (weights sum to ≤ 1.05 by design caps). Level mapping:
`≥0.75 HIGH`, `≥0.50 MEDIUM`, `<0.50 LOW`. Every factor ships in `confidence.factors` as
`{key, ok}` so the UI literally renders the §20 checklist — including which checks **failed** and why.

## 8. Urgency mapping (§14)

| Urgency | Trigger |
|---|---|
| CRITICAL | SM ≤ critical band AND (critical stage OR Tmax > 35 °C) |
| HIGH | SM ≤ critical band |
| MEDIUM | SM in approaching band AND no effective rain in 48 h |
| LOW | SM approaching with rain possible, or adequate-but-high-ETc trend |
| — (needed=false) | wet/adequate bands or rain deferral covers the horizon |

`irrigation_needed` is true at LOW and above; LOW still deferrable by rain.

## 9. Safety rails (§38, §66, §76.18)

Hard invariants the engine and every future model must obey:

1. **Recommendation only.** No pump control, no actuation of any kind from this system (§66).
2. **Rules bound the model.** When ML joins (§38): `final = rules_govern(ML prediction +
   safety constraints + agronomic rules)`; rules may block or clamp model output (e.g. ML asks for
   90 mm on clay flood — rail clamps to per-method max single-event depth, default 25 mm), never
   the reverse.
3. **No unsafe amounts:** clamps — max single-event depth per method; min 24 h between CRITICAL
   events unless overridden by agronomist; zero on saturated soil.
4. **No fabricated inputs:** provider `none` or sensor dead ⇒ degrade confidence + warn (§72).
5. **Explainability is mandatory:** a recommendation with zero reasons is a bug; CI test asserts
   every reason/warning key resolves in en.json AND hi.json (§19, contract i18n rule).
6. **Human override always upstream of harm:** agronomist overrides are logged who/when/what/why
   (§46, §47) and never silently re-applied by the engine.

## 10. Explanations and labeling — exact mechanics (§15, §19, §76.17)

- `reasons[]` and `warnings[]` are `{key, params}` objects against shared namespaces
  (`reasons.soil_below_target`, `reasons.rain_expected`, `warnings.stale_moisture`, …). The engine
  never emits prose; the UI translates (§30, §67). Params carry the numbers so the sentence shows
  actual values: `{"key":"reasons.soil_below_target","params":{"value":31,"target":45}}`.
- Every value in a payload carries its provenance class:
  - **measured** — from farmer entry or sensor (`source: "manual"|"sensor"` on readings, `kind:"observed"` rainfall)
  - **forecast** — provider prediction (`kind:"forecast"`)
  - **estimated** — computed by AgriFlow (ET₀/ETc rows `kind:"estimated"`; water requirement is
    `estimated_water_requirement`; liters `estimated_liters`)
  - **model prediction** — reserved; nothing emits this in rules-1.0. If ML lands, outputs must
    carry `engine_version: "ml-x.y"` + prediction provenance (ml.md §6).
- `inputs_digest` freezes the exact inputs used, so "why did it say 18 mm last Tuesday?" is
  answerable from the stored row (§19) and charts can annotate changes.
- The disclaimer key is always set (`disclaimer_key: "rec.disclaimer"` — decision support, not
  guaranteed advice, §1).

## 11. Worked example

Field A: wheat, VEGETATIVE (Kc 1.15), loam (FC 30%, WP 12%, WHC 150 mm/m), root depth 400 mm,
SM 22% (sensor, 5 h old), Tmax 36/Tmin 24 → ET₀ 6.1 mm, forecast rain 48 h: 1 mm @ 20% prob,
no recent rain, area 1 ha, drip.

```
ETc = 6.1 × 1.15 = 7.0 mm/day; horizon d = 3 days → demand 21.0 mm
Reff = 0 (prob below gate)
ASWD = (22−12)/100 × 0.4 m × 150 mm/m = 6.0 mm  (22% is inside band: target = 30 − 0.55×18 ≈ 20.1
       → actually adequate-margin: SM 22 > 20.1, so approaching/wet boundary — engine emits
       irrigation_needed true at LOW only if 3-day horizon drains SM below target:
       forecast SM after 3 d = 22 − (21−6)/0.4/150×100 … → below target ⇒ review/LOW–MEDIUM)
IrrNet(3d) = 21.0 − 6.0 = 15.0 mm → IrrGross = 15.0 / 0.90 ≈ 16.7 → round 17 mm
liters = 17 × 10,000 × 1 = 170,000 L
confidence = .30 + .25 + .15 + .15 + .10 = 0.95 → capped HIGH; reasons: ETc trend, stage, temp.
```

The §14 example JSON (18 mm, 0.82, "tomorrow morning", MEDIUM) is exactly this shape with SM 19%
and a 20% rain probability noted as low.

## 12. Testing contract (§57)

Golden unit tests pin: Hargreaves against published FAO worked examples; band edges; rain deferral
boundary (7.9 vs 8.0 mm); efficiency divisors; confidence rubric monotonicity (removing an input
never raises score); urgency ladder; every reason/warning key has en+hi entries; determinism (same
inputs_digest ⇒ same recommendation). Integration test covers user→farm→field→weather→rec→event (§57).
