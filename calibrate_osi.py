#!/usr/bin/env python3
"""
calibrate_osi.py -- held-out calibration of the OSI sigmoid (c, tau), R1 revision.

Protocol (fixed before any performance comparison):
  * variant RH-FixedWeight (weights do not depend on c or tau, so the OSI trajectory it
    logs is independent of the parameters being calibrated);
  * calibration seeds 101-110 (disjoint from evaluation seeds 1-30), main scenario;
  * pool OSI_f over all epochs and seeds;
  * c   = median(OSI_f)
  * tau = 2 ln 9 / (P95 - P5)   -> the 10-90 % sigmoid transition spans the P5-P95 range.
Only the OSI distribution is inspected; no ENS or other performance metric is read.
The result is written into both scenario configs and config/osi_calibration.json.
"""
import json
import math
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from sim.network import load_net, build_truth          # noqa: E402
from sim.controller import Episode, Variant            # noqa: E402

CAL_SEEDS = list(range(101, 111))


def one(seed):
    net = load_net(ROOT / "config/ieee33_main.json")
    rows = Episode(net, build_truth(net), Variant("RH-FixedWeight", adaptive=False), seed).run()
    return [r["osi_f"] for r in rows], [r["rho"] for r in rows]


def main(workers=2):
    with Pool(workers) as p:
        res = p.map(one, CAL_SEEDS)
    osi = np.array([v for r in res for v in r[0]])
    rho = np.array([v for r in res for v in r[1]])
    p5, p50, p95 = np.percentile(osi, [5, 50, 95])
    c = float(p50)
    tau = float(2 * math.log(9) / max(p95 - p5, 1e-6))
    rec = {"protocol": __doc__.strip().splitlines()[2:10], "seeds": CAL_SEEDS, "variant": "RH-FixedWeight",
           "n_samples": int(osi.size), "osi_f_p5": p5, "osi_f_p50": p50, "osi_f_p95": p95,
           "osi_f_min": float(osi.min()), "osi_f_max": float(osi.max()),
           "rho_p5_p50_p95": [float(v) for v in np.percentile(rho, [5, 50, 95])],
           "c": round(c, 4), "tau": round(tau, 3),
           "manuscript_values": {"c": 0.75, "tau": 12.0}}
    (ROOT / "config/osi_calibration.json").write_text(json.dumps(rec, indent=2))
    for name in ("ieee33_main.json", "ieee33_severe.json"):
        p = ROOT / "config" / name
        cfg = json.loads(p.read_text())
        cfg["osi"]["c"] = rec["c"]; cfg["osi"]["tau"] = rec["tau"]
        cfg["osi"]["calibration"] = "config/osi_calibration.json (held-out seeds 101-110, RH-FixedWeight)"
        p.write_text(json.dumps(cfg, indent=2))
    print(json.dumps(rec, indent=2))


if __name__ == "__main__":
    main()
