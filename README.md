# Reproducibility release — common-hardware rerun, 13 November 2026

This release replaces the earlier mixed-machine numerical package for the manuscript **Physics-Constrained Rolling-Horizon Self-Healing of Active Distribution Networks via Graph-Repaired Metaheuristic Search**.

## Scope and counts

| Group | Included evidence |
|---|---|
| Pre-declared main suite | 36 configurations × 30 seeds = 1,080 complete 24-epoch runs |
| Reserve and priority sweeps | 60 + 60 additional runs; nominal 30-seed baseline reused in each 90-row sweep |
| Optional OSI/ERB development | 3 settings × 3 development seeds = 9 runs |
| OSI calibration audit | 10 held-out runs; frozen calibration/configuration not rewritten |
| BR/PA phase replay | 30 seeds × 24 epochs × 2 configurations = 1,440 rows with phase P/Q/kVA |
| IEEE 69-bus controller timing | 10 seeds × 24 epochs = 240 epochs |
| MISOCP reference | 3 system/horizon combinations × 8 epochs = 24 cases |
| Matched SAGM search reference | 30 seeds per benchmark epoch = 720 search trials |

The 1,200 count comprises only the main suite plus the two additional sensitivity sweeps; it does not include development, phase replay, timing, or fixed-state benchmark trials. One fallback occurred in the 1,080-run suite; neither sensitivity sweep invoked fallback.

## Hardware and timing

AMD Ryzen 7 7840HS (8 cores/16 logical processors), 32 GB installed RAM (31.19 GiB OS-visible), Windows 11, Python 3.12.7. Experiments ran serially; numerical-library thread limits were set to one. No GPU computation was used. Exact package versions and source hashes are in provenance/manifest.json.

Table V uses full decision-epoch wall time, excluding JIT warm-up. IEEE 33/Tp=5 averages 0.230676 s; IEEE 69/Tp=5 averages 0.543608 s over 240 epochs. Table VI uses only the search call at fixed benchmark states. Its ranges are across the eight per-epoch 30-seed means, not individual-call extrema.

## Important updated findings

| Item | Current evidence |
|---|---|
| Main ENS (Snapshot / Tp=1 / Tp=5) | 3361.4 / 2242.9 / 2247.9 kWh |
| Joint removal of repair and refinement | 8201.2 kWh; the 3.6-fold increase is not attributable to repair alone |
| Refinement-only removal | 4965.2 kWh |
| Raw-candidate admissibility | Full 1.17±0.06%; no refinement 1.09±0.13%; neither mechanism 1.24±0.15% |
| BR / PA under-voltage epochs | 308 / 93 of 720 each; 69.8% reduction |
| BR / PA mean worst-phase voltage | 0.938662 / 0.946080 p.u.; residual violations remain |
| PA VUI reduction | Median 44.7% in per-seed maximum VUI |
| Inherited leg overload | Seed 16, t=0 and t=1; 58.6 kVA maximum in both replay modes |
| IEEE 33/Tp=1 SCIP | 8/8 optimal, 13–32 s |
| IEEE 33/Tp=5 SCIP | 3/8 optimal, 950–1716 s; 5 time-limited |
| IEEE 69/Tp=5 SCIP | 0/8 optimal; all time-limited; do not infer global optimality of SAGM |

All paper/reply numbers use this rerun. Earlier PA values of 99 under-voltage epochs, 0.948 p.u., 51% VUI reduction, and six overloaded epochs are superseded. No cross-platform cause is inferred from this numerical difference. The original uploaded result archive is retained separately; this package publishes the raw CSVs needed to verify the current results.

## File map and terminology

- runs_r2/: 1,080 paired CSV/JSON checkpoints, plus the IEEE 69 benchmark state trajectory.
- supplement_runs/: 120 additional reserve/priority runs.
- development_runs/: 19 development/calibration runs.
- phase_runs/ and results_3ph/epochs.csv: complete BR/PA phase dispatch.
- results_r2/: main, sensitivity, timing, and benchmark results; bench_parts/ contains each epoch's JSON and 30-seed search CSV.
- provenance/: recorded completion and environment/source manifest, with computer hostname removed for public distribution.
- audit_release.py: read-only checks and summary generation for this release.
- fresh_rerun.ps1: copies the exact experiment source/input files to a new directory for an optional fresh run; it does not reuse archived output checkpoints.
- sim/optimizer.py and sim/controller.py: separate raw GWO and local-fitness counters; source hashes match the executed version.
- run_reserve_sweep.py and run_lambda_sweep.py: included sweep drivers; run_machine_suite.py provides the full common-hardware run.
- PREREGISTRATION_R2.md and legacy paths retain historical identifiers solely for traceability.

| Archived code label | Manuscript label |
|---|---|
| RH-Lean | Full RH (SAGM-GWO), Tp=5 |
| Snapshot-Lean | Snapshot-SAGM |
| RH-Lean w/o graph repair | w/o graph repair **and branch-exchange refinement** |
| RH-Lean w/o local search | w/o branch-exchange refinement |

The joint ablation uses repair=False, local_search=False. Branch exchange operates on an admissible radial incumbent and was jointly disabled in that experiment. Its result does not isolate the independent effect of repair.

## Reproduce or inspect

For analysis only, use the recorded environment versions in provenance/manifest.json, then run:
    python audit_release.py

The original analysis scripts are retained byte-for-byte. They use paths relative to the repository root. To perform a fresh full rerun, run fresh_rerun.ps1 in PowerShell and follow its printed command. It creates a new directory rather than overwriting the published results. The full SCIP batch may require many hours (24 cases, up to 1,800 s each); it is not needed to inspect the existing data.

The numerical code and input hashes were verified against the completed-run manifest. All 1,219 complete-run CSV/JSON checkpoints pass SHA-256 and 24-epoch checks. Each of the 24 benchmark search files contains 30 trials. Both source integrity and recorded completion checks pass.

## Research boundary

CAPA/TPFR future research is excluded. BR/PA is a fixed balanced-trajectory replay diagnostic, not a closed-loop unbalanced controller. Preserving aggregate phase P/Q and shared SoC does not establish manufacturer-specific converter feasibility. Residual voltage violations and inherited island leg overloads remain in the data. MISOCP time-limit outcomes are incumbents with loose bounds, not certificates of optimality.

## Publication checklist

This is a prepared GitHub upload package; preparing it does not publish it. Upload its contents to the manuscript's repository before submission and verify the public link. The manuscript and response letter are delivered separately. No reviewer correspondence, console logs with local paths, or computer hostname is included in this public package.

## Figure 2 revision

figures/ contains the redrawn Algorithm 1 workflow, vector PDF/SVG, 600-dpi PNG and its plotting source. Only documentation/figure assets changed; all experiment sources and numerical results retain their executed hashes.

## AC-reference comparison and public driver name

The IEEE 33- and 69-bus incumbent comparisons use the exact AC re-evaluation. For IEEE 69/Tp=5, AC-re-evaluated SCIP incumbent ENS is 0.89–17.89 MWh; SAGM mean J is 79.3–99.98% lower. These differences are not optimality gaps. Raw CSV columns misocp_J/misocp_ens retain model-reported values; misocp_in_sim_J/misocp_in_sim_ens are AC-re-evaluated values. The comparison is 100*(sagm_J_mean/misocp_in_sim_J - 1).

The standalone OSI/ERB development driver is run_osi_erb_development.py. Its contents are byte-identical to the executed file, formerly tmp_osi_erb_sweep.py. provenance/manifest.json preserves the original execution record; provenance/source_path_renames.json maps that historical name to the public filename. Both audit_release.py and fresh_rerun.ps1 apply the mapping. Example: python run_osi_erb_development.py --lo 101 --hi 103 --out osi_erb_development.csv. This standalone driver uses multiprocessing; the published common-hardware results were generated serially by run_machine_suite.py.
