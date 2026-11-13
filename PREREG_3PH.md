# Private three-phase diagnostic (option C) — fixed before any three-phase result

Written 2026-11-02, before the three-phase evaluator was run on any seed.
Purpose: decide whether a re-simulated phase-aware section is close enough to the
original VII-E claim to be put back into the manuscript.

## Plant trajectory
* Scenario: config/ieee33_main.json (frozen), RH-Lean (Tp = 5, adaptive/ERB/V-aware off),
  seeds 1–30, i.e. exactly the trajectories behind Table II.
* The balanced plan (topology, served buses, PV/DG output after curtailment, aggregate
  BESS P/Q) of every epoch is replayed on a three-phase feeder model. Shedding,
  topology and SoC trajectory are taken unchanged from the balanced run.

## Three-phase feeder model (fixed)
* Phase-impedance matrix of every line from its positive-sequence impedance with an
  assumed z0 = 3 z1 (Kron-reduced, multi-grounded neutral): Zs = (z0 + 2 z1)/3, Zm = (z0 − z1)/3.
* Loads: constant-power wye. Buses 14 and 17: phase split A/B/C = 0.50/0.30/0.20 of P and Q.
  All other loads balanced (1/3 each).
* PV at buses 22 and 26: single-phase, phase A. Dispatchable DG: balanced.
* Substation: ideal balanced source 1.0 p.u. Island GFM BESS: balanced positive-sequence
  terminal voltage 1.0 p.u.; its legs supply whatever unbalanced current the island draws.
* BESS converter legs: each leg ≤ 30 kVA (0.5 × 60 kVA); aggregate P/Q equal to the balanced plan.
* Unbalanced backward/forward sweep, tolerance 1e-7 p.u., max 60 sweeps.

## Configurations
1. BR — balanced replay: every BESS splits P and Q equally over its three legs.
2. PA — phase-selective BESS control: for each epoch, the legs of every grid-connected,
   non-slack BESS are re-allocated (same aggregate P and Q, so ENS and SoC are unchanged)
   by SLSQP minimising Σ_i VUI_i² + 10 Σ_{i,φ} max(0, 0.95 − |V_iφ|)², subject to the 30-kVA
   leg limit. Start point = BR allocation.
3. PA+T (secondary, exploratory) — PA plus phase-aware topology screening, only if time allows.

## Metrics (per run)
max VUI over energized buses and epochs; min phase voltage; number of epochs with any
phase voltage < 0.95 p.u.; number of epochs with VUI > 2%; BESS leg overloads (> 30 kVA).

## Decision rule for re-inclusion (fixed now)
Re-include a phase-aware section only if BOTH hold:
(a) BR shows a phase-level problem the balanced model hides — max VUI > 2% or phase
    voltage < 0.95 p.u. while the balanced model reported ≥ 0.95 — in at least 10 of 30 runs;
(b) PA lowers the per-run max VUI with a one-sided Wilcoxon signed-rank p < 0.05 and a
    median relative reduction ≥ 20%, with no new leg overloads.
If (a) fails, the manuscript states that the balanced-equivalent assumption is not
critical for this feeder (or omits the section). If (a) holds and (b) fails, the section
is not re-included. No parameter above is changed after results are seen; any extra
analysis is labelled exploratory.

## Addendum (implementation fix, before the 30-seed run)
Debugging on seed 1, epoch 3 showed SLSQP stopping at its 60-iteration limit with legs
violating the 30-kVA rating by < 1e-3 kVA², so the result was discarded and BR returned.
Fix: the SLSQP point is scaled back towards the BR allocation (factor 0.98 per step) until
every leg is within rating; it is kept only if its objective is not worse than BR.
Nothing else changed. Solver check: with balanced splits the three-phase sweep reproduces
the balanced voltages to 2.7e-8 p.u.
