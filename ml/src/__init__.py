"""AgriFlow ML pipeline — rules-first, ML-proven (master spec 34–38).

Honesty rules baked in:
  * Training labels are WEAK labels derived from what actually happened
    (farmer irrigated after a recommendation, or feedback said "not useful"),
    NOT assumed ground truth.
  * The model ships DISABLED. It is promoted only when it beats the rules
    baseline on held-out data by the margin in evaluate.py AND an agronomist
    signs off (docs/ml.md).
  * Safety rules can still veto model output (spec 38) — predictions are
    decision support, never pump control.

Datasets are exported from the API database by `export_dataset.py` (run
against production/SQLite copy); this package never fabricates data.
"""
