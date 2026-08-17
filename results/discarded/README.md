# Discarded runs

## unpaired_design_2026-07-25

Smoke runs plus the first 11 runs of phase 1, executed under a design since
corrected. NOT valid experimental data — retained only as evidence of the
two defects the phase-1 checkpoint surfaced:

1. Query samples were drawn from the condition-specific seed, so every
   condition saw different queries (unpaired). Sample variance alone produced
   a severe-latency run 22 accuracy points ABOVE its baseline.
2. BATCH_INHERENT_STALENESS_S (10 s) exactly equalled the delay-knowledge
   horizon, zeroing the dominant classification feature in every batch run;
   that arm scored 0.438 on a balanced binary task — below chance.

Both are fixed and pinned by tests/test_paired_design.py.
