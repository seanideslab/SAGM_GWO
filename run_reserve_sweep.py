#!/usr/bin/env python3
"""Terminal-reserve sensitivity sweep (RESERVE_SWEEP.md).  python run_reserve_sweep.py --workers N"""
import argparse, json, os, sys, time
from multiprocessing import Pool
from pathlib import Path
import pandas as pd
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from sim.controller import Episode, Variant, summarize   # noqa: E402
from sim.network import build_truth, load_net             # noqa: E402
LEVELS = (0.10, 0.20, 0.30)
OUT = ROOT / "runs_r2" / "reserve_sweep"


def task(a):
    res, seed = a
    d = OUT / f"reserve{int(round(res * 100))}"; d.mkdir(parents=True, exist_ok=True)
    js = d / f"seed_{seed:02d}.json"
    if js.exists():
        return json.loads(js.read_text())
    net = load_net(ROOT / "config/ieee33_main.json", {"bess.soc_reserve": res})
    var = Variant(f"RH-Lean reserve{int(round(res * 100))}", adaptive=False, erb=False, v_aware=False)
    rows = Episode(net, build_truth(net), var, seed).run()
    pd.DataFrame(rows).to_csv(d / f"seed_{seed:02d}.csv", index=False)
    s = summarize(rows, net, var, seed); s["reserve"] = res
    s["min_soc"] = float(pd.DataFrame(rows).soc_min.min())
    js.write_text(json.dumps(s, default=float, indent=1))
    return s


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--workers", type=int, default=os.cpu_count())
    ap.add_argument("--seeds", default="1-30"); a = ap.parse_args()
    lo, hi = (int(v) for v in a.seeds.split("-"))
    jobs = [(r, s) for r in LEVELS for s in range(lo, hi + 1)]
    t0 = time.time()
    with Pool(a.workers) as p:
        out = []
        for i, s in enumerate(p.imap_unordered(task, jobs), 1):
            out.append(s); print(f"[{i}/{len(jobs)}] reserve {s['reserve']:.2f} seed {s['seed']:2d} "
                                 f"ENS {s['cum_ens_kwh']:.1f}  {(time.time()-t0)/60:.1f} min", flush=True)
    (ROOT / "results_r2").mkdir(exist_ok=True)
    pd.DataFrame(out).sort_values(["reserve", "seed"]).to_csv(ROOT / "results_r2/reserve_sweep_runs.csv", index=False)
    print("done")
