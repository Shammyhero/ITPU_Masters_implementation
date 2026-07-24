# Analysis notebooks

Created in Week 6 (statistical analysis) with reproducible seeds:

- `01_pilot_analysis.ipynb` — pilot go/no-go: does accuracy measurably degrade?
- `02_main_analysis.ipynb` — the five RQ analyses (Table 4.3 of the research
  plan): changepoint thresholds, two-way ANOVA + effect sizes, task
  comparison, pipeline boundary conditions.
- `03_airs_calibration.ipynb` — logistic regression -> AIRS weights,
  held-out validation, calibration curves. Exports `airs_calibration.json`
  consumed by `AIRSCalculator.from_calibration`.
