# Reporting note: historical "w/o graph repair" keys mean joint removal of graph repair and branch-exchange refinement.
#!/usr/bin/env python3
"""
run_experiments.py -- run the R1 simulation suite (resumable, multi-core).

  python run_experiments.py                    # full suite, all cores, seeds 1-30
  python run_experiments.py --suite smoke      # 2 seeds x 3 configs, quick check
  python run_experiments.py --workers 12 --suite main
  python run_experiments.py --list             # print the configurations

Every (scenario, configuration, seed) writes
  runs/<scenario>/<configuration>/seed_XX.csv    per-epoch raw log
  runs/<scenario>/<configuration>/seed_XX.json   per-run summary (incl. config SHA-256 prefix)
Existing .json files are skipped, so the command can be re-run after an interruption.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import time
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from sim.controller import Episode, Variant, summarize   # noqa: E402
from sim.network import build_truth, load_net             # noqa: E402

SCEN = {"main": ROOT / "config/ieee33_main.json", "severe": ROOT / "config/ieee33_severe.json",
        "f2_25-29": ROOT / "config/ieee33_f2_25-29.json", "f2_27-28": ROOT / "config/ieee33_f2_27-28.json",
        "storage_rich": ROOT / "config/ieee33_storage_rich.json"}


def lean_suite():
    """R2 pre-declared suite (PREREGISTRATION_R2.md): OSI, ERB and V-aware scoring removed."""
    def L(name, **kw):
        base = dict(adaptive=False, erb=False, v_aware=False)
        base.update(kw)
        return Variant(name, **base)
    full = L("RH-Lean")
    snap = L("Snapshot-Lean", mode="snapshot", horizon=1)
    main = [full, snap,
            L("RH-Lean w/o graph repair", repair=False, local_search=False),
            L("RH-Lean w/o local search", local_search=False)]
    main += [L(f"RH-Lean Tp={tp}", horizon=tp) for tp in (1, 2, 3, 7, 10)]
    main += [L(f"RH-Lean noise{e}", error_pct=e) for e in (0, 5, 15, 25)]
    main += [L("RH-Lean Tp=1 noise0", horizon=1, error_pct=0)]
    main += [L(f"RH-Lean AR1 noise{e}", error_pct=e, noise_model="ar1") for e in (10, 25)]
    main += [L("RH-Lean Bias+10%", bias=0.10), L("RH-Lean Bias-10%", bias=-0.10)]
    main += [L(f"RH-Lean SoC0={s}", soc0=s) for s in (0.2, 0.4)] + [L("Snapshot-Lean SoC0=0.2", mode="snapshot", horizon=1, soc0=0.2)]
    jobs = [("main", v) for v in main]
    for sc in ("severe", "f2_25-29", "f2_27-28"):
        jobs += [(sc, full), (sc, snap), (sc, L("RH-Lean Tp=1", horizon=1))]
    jobs += [("storage_rich", v) for v in (full, snap, L("RH-Lean Tp=1", horizon=1), L("RH-Lean Tp=3", horizon=3),
                                          L("RH-Lean noise0", error_pct=0), L("RH-Lean Tp=1 noise0", horizon=1, error_pct=0))]
    return jobs


def suite(name: str):
    V = Variant
    main = [
        V("Full RH-SAGM-GWO"),
        V("RH-FixedWeight", adaptive=False),
        V("Snapshot-SAGM", mode="snapshot", horizon=1),
        # mechanism ablations (Table III)
        V("RH + Raw OSI", beta=1.0, deadband=0.0),
        V("RH + Filtered (no dead band)", deadband=0.0),
        V("Nominal-voltage repair", v_aware=False),
        V("w/o ERB", erb=False),
        V("w/o graph repair", repair=False, local_search=False),
        V("w/o local search", local_search=False),
    ]
    main += [V(f"Tp={tp}", horizon=tp) for tp in (1, 2, 3, 7, 10)]                       # Table IV
    for e in (5, 10, 15, 25):                                                             # Fig. 4
        for b in (0.1, 0.3, 0.5, 1.0):
            if e == 10 and b == 0.3:
                continue                                                                  # = Full
            main.append(V(f"noise{e}_beta{b}", beta=b, error_pct=e))
    main += [V(f"SoC0={s}", soc0=s) for s in (0.2, 0.4)]                                  # new robustness
    main += [V(f"AR1 noise{e}", error_pct=e, noise_model="ar1") for e in (10, 25)]
    main += [V("Bias+10% noise10", error_pct=10, bias=0.10), V("Bias-10% noise10", error_pct=10, bias=-0.10)]
    main += [V(f"Snapshot SoC0={s}", mode="snapshot", horizon=1, soc0=s) for s in (0.2,)]
    severe = [V("Full RH-SAGM-GWO"), V("RH-FixedWeight", adaptive=False),
              V("Snapshot-SAGM", mode="snapshot", horizon=1), V("RH + Raw OSI", beta=1.0, deadband=0.0)]
    faults = [V("Full RH-SAGM-GWO"), V("RH-FixedWeight", adaptive=False), V("Snapshot-SAGM", mode="snapshot", horizon=1)]
    fault_jobs = [(s, v) for s in ("f2_25-29", "f2_27-28") for v in faults]
    if name == "main":
        return [("main", v) for v in main]
    if name == "severe":
        return [("severe", v) for v in severe]
    if name == "faults":
        return fault_jobs
    if name == "lean":
        return lean_suite()
    if name == "smoke":
        return [("main", v) for v in main[:3]]
    return [("main", v) for v in main] + [("severe", v) for v in severe] + fault_jobs


def slug(s: str) -> str:
    return "".join(c if c.isalnum() or c in "=.-_" else "_" for c in s)


def task(args):
    scen, var, seed, out = args
    d = Path(out) / scen / slug(var.name)
    d.mkdir(parents=True, exist_ok=True)
    js = d / f"seed_{seed:02d}.json"
    if js.exists():
        return ("skip", scen, var.name, seed, 0.0)
    t0 = time.perf_counter()
    net = load_net(SCEN[scen])
    rows = Episode(net, build_truth(net), var, seed).run()
    import pandas as pd
    pd.DataFrame(rows).to_csv(d / f"seed_{seed:02d}.csv", index=False)
    s = summarize(rows, net, var, seed)
    s["scenario"] = scen
    s["wall_s"] = time.perf_counter() - t0
    js.write_text(json.dumps(s, default=float, indent=1))
    return ("done", scen, var.name, seed, s["wall_s"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--suite", default="all", choices=["all", "main", "severe", "faults", "smoke", "lean"])
    ap.add_argument("--seeds", default="1-30")
    ap.add_argument("--workers", type=int, default=os.cpu_count())
    ap.add_argument("--out", default=str(ROOT / "runs"))
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    lo, hi = (int(v) for v in a.seeds.split("-")) if "-" in a.seeds else (int(a.seeds), int(a.seeds))
    seeds = list(range(lo, hi + 1)) if a.suite != "smoke" else [1, 2]
    jobs = suite(a.suite)
    if a.list:
        for s, v in jobs:
            print(f"{s:7s} {v}")
        print(f"{len(jobs)} configurations x {len(seeds)} seeds")
        return
    Path(a.out).mkdir(parents=True, exist_ok=True)
    import numba, numpy, scipy  # noqa
    manifest = {"started": time.strftime("%Y-%m-%d %H:%M:%S"), "python": sys.version, "platform": platform.platform(),
                "cpu_count": os.cpu_count(), "workers": a.workers, "numpy": numpy.__version__,
                "numba": numba.__version__, "suite": a.suite, "seeds": seeds,
                "configs": {k: str(v.relative_to(ROOT)) for k, v in SCEN.items()}}
    (Path(a.out) / f"manifest_{time.strftime('%Y%m%d_%H%M%S')}.json").write_text(json.dumps(manifest, indent=2))
    tasks = [(s, v, seed, a.out) for s, v in jobs for seed in seeds]
    # longest first (no-repair and long horizons) for better load balance
    tasks.sort(key=lambda x: -(x[1].horizon + (5 if not x[1].repair else 0)))
    print(f"{len(tasks)} runs on {a.workers} workers -> {a.out}", flush=True)
    t0 = time.time(); n_done = 0
    with Pool(a.workers) as pool:
        for st, scen, name, seed, w in pool.imap_unordered(task, tasks):
            n_done += 1
            el = time.time() - t0
            eta = el / n_done * (len(tasks) - n_done)
            print(f"[{n_done:4d}/{len(tasks)}] {st:4s} {scen:6s} {name:30s} seed {seed:2d} {w:6.1f}s  "
                  f"elapsed {el/60:5.1f} min  ETA {eta/60:5.1f} min", flush=True)
    print("finished. next: python aggregate_results.py")


if __name__ == "__main__":
    main()
