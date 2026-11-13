"""Analyse the terminal-reserve sweep as declared in RESERVE_SWEEP.md."""
import itertools
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import wilcoxon
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from statistics_analysis import hodges_lehmann_ci, holm  # noqa: E402

ROOT = Path(__file__).resolve().parent
d = pd.read_csv(ROOT / "results_r2/reserve_sweep_runs.csv")
METRICS = ["cum_ens_kwh", "ens_crit_kwh", "switching_actions", "final_soc_mean", "min_soc", "fallback_epochs"]


summ = d.groupby("reserve")[METRICS].agg(["mean", "std"]).round(3)
print(summ.T.to_string())
rows = []
for m in METRICS:
    ps = []
    for lv in (0.10, 0.30):
        a = d[d.reserve == lv].set_index("seed")[m]; b = d[d.reserve == 0.20].set_index("seed")[m]
        diff = (a - b).loc[b.index]
        p = wilcoxon(diff).pvalue if np.any(diff != 0) else 1.0
        hl, lo, hi = hodges_lehmann_ci(diff.to_numpy())[:3] if np.any(diff != 0) else (0.0, 0.0, 0.0)
        ps.append(p); rows.append(dict(metric=m, comparison=f"{int(lv*100)}% vs 20%", mean_diff=diff.mean(),
                                       hl=hl, ci_lo=lo, ci_hi=hi, p=p))
    order = np.argsort(ps)
    adj = [None, None]
    run = 0.0
    for r, i in enumerate(order):
        run = max(run, min(1.0, ps[i] * (2 - r))); adj[i] = run
    rows[-2]["p_holm"], rows[-1]["p_holm"] = adj
out = pd.DataFrame(rows)
print(out.round(4).to_string())
out.to_csv(ROOT / "results_r2/reserve_sweep_stats.csv", index=False)
(ROOT / "results_r2/reserve_sweep_summary.json").write_text(json.dumps(
    {f"{int(r*100)}%": {m: float(d[d.reserve == r][m].mean()) for m in METRICS} for r in (0.1, 0.2, 0.3)}, indent=1))
