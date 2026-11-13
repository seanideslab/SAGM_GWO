#!/usr/bin/env python3
"""
aggregate_lean.py -- tables and pre-declared tests for the R2 lean suite (PREREGISTRATION_R2.md).
Reads runs_r2/, writes results_r2/.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from statistics_analysis import hodges_lehmann_ci, holm, rank_biserial  # noqa: E402

RUNS = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "runs_r2"
OUT = ROOT / "results_r2"
M = ["cum_ens_kwh", "ens_crit_kwh", "critical_restoration_percent", "switching_actions", "switching_reversals",
     "average_vdi_pu", "avg_power_loss_kw", "min_v_pu", "mean_iterations", "mean_epoch_runtime_s",
     "raw_candidate_admissible_frac", "fallback_epochs", "final_soc_mean"]

FAMILY = [  # pre-declared: (id, scenario, baseline, proposed, metric)
    ("H1-main", "main", "Snapshot-Lean", "RH-Lean", "cum_ens_kwh"),
    ("H1-severe", "severe", "Snapshot-Lean", "RH-Lean", "cum_ens_kwh"),
    ("H1-25-29", "f2_25-29", "Snapshot-Lean", "RH-Lean", "cum_ens_kwh"),
    ("H1-27-28", "f2_27-28", "Snapshot-Lean", "RH-Lean", "cum_ens_kwh"),
    ("H2a", "main", "RH-Lean w/o graph repair", "RH-Lean", "cum_ens_kwh"),
    ("H2b", "main", "RH-Lean w/o local search", "RH-Lean", "cum_ens_kwh"),
    ("H3", "storage_rich", "RH-Lean Tp=1", "RH-Lean", "cum_ens_kwh"),
    ("H3'", "main", "RH-Lean Tp=1", "RH-Lean", "cum_ens_kwh"),
    ("H4-main", "main", "RH-Lean", "RH-Lean noise0", "cum_ens_kwh"),
    ("H4-storage", "storage_rich", "RH-Lean", "RH-Lean noise0", "cum_ens_kwh"),
]


def cp(k, n, a=0.05):
    lo = stats.beta.ppf(a / 2, k, n - k + 1) if k > 0 else 0.0
    hi = stats.beta.ppf(1 - a / 2, k + 1, n - k) if k < n else 1.0
    return f"{100 * lo:.1f}-{100 * hi:.1f}%"


def table(df):
    rows = []
    for (s, c), g in df.groupby(["scenario", "configuration"]):
        r = {"scenario": s, "configuration": c, "n": len(g)}
        for m in M:
            r[m + "_mean"] = g[m].mean(); r[m + "_sd"] = g[m].std(ddof=1); r[m + "_median"] = g[m].median()
        k = int(g.success.sum()); r.update(success_n=k, success_ci95=cp(k, len(g)))
        rows.append(r)
    return pd.DataFrame(rows)


def tests(df):
    out = []
    for hid, s, base, prop, m in FAMILY:
        a = df[(df.scenario == s) & (df.configuration == base)].set_index("seed")[m]
        b = df[(df.scenario == s) & (df.configuration == prop)].set_index("seed")[m]
        idx = a.index.intersection(b.index)
        if len(idx) < 6:
            continue
        x, y = a.loc[idx].to_numpy(float), b.loc[idx].to_numpy(float)
        d = x - y
        if np.allclose(d, 0):
            p, W = 1.0, np.nan
        else:
            w = stats.wilcoxon(x, y, zero_method="wilcox"); p, W = w.pvalue, w.statistic
        hl, lo, hi, conf = hodges_lehmann_ci(d)
        out.append(dict(hypothesis=hid, scenario=s, baseline=base, proposed=prop, metric=m, n=len(idx),
                        mean_baseline=x.mean(), mean_proposed=y.mean(), median_baseline=np.median(x),
                        median_proposed=np.median(y), reduction_pct=100 * (x.mean() - y.mean()) / x.mean() if x.mean() else np.nan,
                        W=W, p=p, HL_reduction=hl, CI_low=lo, CI_high=hi, rank_biserial=rank_biserial(d)))
    r = pd.DataFrame(out)
    if len(r):
        r["p_holm"] = holm(r.p.to_numpy())
    return r


def checks(df):
    L = ["# Integrity checks (runs_r2)"]
    for s, g in df.groupby("scenario"):
        L.append(f"- {'OK  ' if g.cfg_hash.nunique() == 1 else 'FAIL'} {s}: hash {list(g.cfg_hash.unique())}")
    for (s, c), g in df.groupby(["scenario", "configuration"]):
        if sorted(g.seed) != list(range(1, 31)):
            L.append(f"- WARN {s}/{c}: n = {len(g)}")
    for col in ["switching_actions", "switching_reversals", "fallback_epochs", "overload_events", "soc_violations"]:
        bad = (df[col] < 0) | (df[col] != df[col].round())
        L.append(f"- {'OK  ' if not bad.any() else 'FAIL'} {col} non-negative integers")
    L.append(f"- {'OK  ' if df.success.isin([0, 1]).all() else 'FAIL'} success binary")
    return "\n".join(L)


def main():
    OUT.mkdir(exist_ok=True)
    df = pd.DataFrame([json.loads(p.read_text()) for p in RUNS.glob("*/*/seed_*.json")])
    if df.empty:
        sys.exit("no runs in " + str(RUNS))
    df.to_csv(OUT / "all_runs.csv", index=False)
    (OUT / "checks.md").write_text(checks(df) + "\n")
    t = table(df); t.to_csv(OUT / "summary_by_config.csv", index=False)
    r = tests(df); r.to_csv(OUT / "preregistered_tests.csv", index=False)
    show = t[["scenario", "configuration", "n", "cum_ens_kwh_mean", "cum_ens_kwh_sd", "cum_ens_kwh_median",
              "switching_actions_mean", "switching_reversals_mean", "mean_epoch_runtime_s_mean", "success_n"]]
    txt = ["# R2 lean results", "", checks(df), "", "## Summary", show.round(3).to_markdown(index=False), "",
           "## Pre-declared tests", r.round(4).to_markdown(index=False) if len(r) else "(none)"]
    (OUT / "REPORT.md").write_text("\n".join(txt) + "\n")
    print("\n".join(txt))


if __name__ == "__main__":
    main()
