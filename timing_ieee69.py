#!/usr/bin/env python3
"""
timing_ieee69.py -- decision-epoch wall-clock timing on the IEEE 69-bus feeder (Tp = 5).

Feeder: MATPOWER case69 (validated: base loss 224.99 kW, Vmin 0.9092 p.u.) plus the five
standard tie lines 11-43, 13-21, 15-46, 50-59, 27-65 (Baran & Wu 1989 / Das 2006 data).
Only runtime is reported; no performance comparison is made on this case.

  python timing_ieee69.py --seeds 1-10
"""
from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from sim.controller import Episode, Variant      # noqa: E402
from sim.network import build_truth, load_net    # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="1-10")
    a = ap.parse_args()
    lo, hi = (int(v) for v in a.seeds.split("-"))
    net = load_net(ROOT / "config/ieee69_timing.json"); tr = build_truth(net)
    Episode(net, tr, Variant("warmup", horizon=1), 0).run()          # JIT compile outside timing
    rows = []
    for s in range(lo, hi + 1):
        for r in Episode(net, tr, Variant("RH-Lean", adaptive=False, erb=False, v_aware=False), s).run():
            rows.append(dict(seed=s, t=r["t"], runtime_s=r["runtime_s"], iterations=r["iterations"],
                             evaluations=r["evaluations"]))
    d = pd.DataFrame(rows)
    q = d.runtime_s.quantile([0.05, 0.5, 0.95]).to_dict()
    res = dict(system="IEEE69", horizon=5, n_epochs=len(d), mean_s=d.runtime_s.mean(), p5_s=q[0.05],
               median_s=q[0.5], p95_s=q[0.95], max_s=d.runtime_s.max(), mean_evaluations=d.evaluations.mean(),
               machine=platform.processor() or platform.machine(), python=sys.version.split()[0])
    (ROOT / "results_r2").mkdir(exist_ok=True)
    d.to_csv(ROOT / "results_r2/ieee69_epoch_timing_raw.csv", index=False)
    (ROOT / "results_r2/ieee69_epoch_timing.json").write_text(json.dumps(res, indent=2, default=float))
    print(json.dumps(res, indent=2, default=float))


if __name__ == "__main__":
    main()
