# Pre-declared analysis plan — R2 "lean" re-simulation
Declared 2026-11-02 10:00 (Asia/Taipei), BEFORE any lean-method run was executed.

## Method under test ("RH-Lean")
Rolling-horizon re-optimisation with the physics-constrained graph search layer:
binary GWO (|tanh| rule) + DFS/Kruskal radial repair with lagged-flow edge scores (nominal voltage)
+ GFM source check + Baran–Wu branch-exchange local search + BESS reserve projection +
exact BFS screening + priority shedding. Fixed objective weights alpha = alpha(c) (alpha1 = 0.575,
remaining weights 0.142 each). Removed after R1 (no measurable benefit in runs/ of R1):
OSI-adaptive weights and filter, elite restoration bank, voltage-aware edge scoring.

## Hypotheses and tests (paired over seeds 1–30, two-sided Wilcoxon, Hodges–Lehmann exact 95 % CI,
## Holm correction over the whole family below)
* H1  RH-Lean < Snapshot-Lean in cumulative ENS, in each of the four F2 locations.
* H2a removing graph repair increases ENS; H2b removing local search increases ENS (main).
* H3  storage-rich scenario (200 kW / 400 kWh per BESS): Tp = 5 < Tp = 1 in ENS.
* H3' main scenario: Tp = 5 vs Tp = 1 (reported whatever the direction).
* H4  zero forecast noise vs 10 % noise, Tp = 5, main and storage-rich (forecast-error cost).
Secondary (descriptive, no test): horizon curve Tp = 1…10, noise 5–25 %, AR(1), ±10 % bias,
initial SoC 20/40/60 %, switching operations and reversals, runtime.

## Fixed
Configs: ieee33_main / severe / f2_25-29 / f2_27-28 / storage_rich (hashes logged per run).
No parameter, scenario or test may be changed after the runs start; all outcomes are reported.
