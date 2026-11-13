#!/usr/bin/env python3
"""
aggregate_results.py -- build the R1 tables, figure data and paired statistics from runs/.

Outputs (results_r1/):
  all_runs.csv                      one row per (scenario, configuration, seed)
  table_II_main.csv                 RH vs snapshot (mean, SD, success n/30 + Clopper-Pearson)
  table_III_mechanisms.csv          filtering / repair / ERB ablations
  table_IV_horizon.csv              horizon-length sensitivity
  fig4_noise_beta.csv               forecast-noise x beta grid
  table_robustness.csv              initial SoC, AR(1) correlated errors
  table_severe.csv                  severe scenario (F2 = 2-3)
  fig3_trajectories.csv             mean per-epoch trajectories (main comparison)
  paired_tests.csv                  Wilcoxon + Hodges-Lehmann exact CI + Holm
  checks.md                         integrity checks of the raw runs
  REPORT.md                         human-readable summary
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

RUNS = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "runs"
OUT = ROOT / "results_r1"
FULL = "Full RH-SAGM-GWO"
METRICS = ["cum_ens_kwh", "ens_crit_kwh", "critical_restoration_percent", "rda_percent_day", "switching_actions",
           "switching_reversals", "average_vdi_pu", "avg_power_loss_kw", "min_v_pu", "mean_iterations",
           "mean_epoch_runtime_s", "raw_candidate_admissible_frac", "fallback_epochs"]


def load():
    rows = [json.loads(p.read_text()) for p in RUNS.glob("*/*/seed_*.json")]
    if not rows:
        sys.exit("no runs found under runs/")
    return pd.DataFrame(rows)


def cp_interval(k, n, alpha=0.05):
    lo = stats.beta.ppf(alpha / 2, k, n - k + 1) if k > 0 else 0.0
    hi = stats.beta.ppf(1 - alpha / 2, k + 1, n - k) if k < n else 1.0
    return 100 * lo, 100 * hi


def summary(df, configs, metrics, scenario="main"):
    out = []
    for c in configs:
        g = df[(df.scenario == scenario) & (df.configuration == c)]
        if g.empty:
            continue
        row = {"configuration": c, "n_runs": len(g)}
        for m in metrics:
            row[f"{m}_mean"] = g[m].mean(); row[f"{m}_sd"] = g[m].std(ddof=1)
        k = int(g.success.sum()); lo, hi = cp_interval(k, len(g))
        row.update(success_n=k, success_ci95=f"{lo:.1f}-{hi:.1f}%")
        out.append(row)
    return pd.DataFrame(out)


def checks(df):
    lines = ["# Integrity checks of runs/", ""]
    ok = True
    for (s, c), g in df.groupby(["scenario", "configuration"]):
        seeds = sorted(g.seed)
        if seeds != list(range(1, 31)):
            lines.append(f"- WARN {s}/{c}: seeds {seeds[:3]}...{seeds[-3:]} (n={len(seeds)})")
    for s, g in df.groupby("scenario"):
        h = g.cfg_hash.unique()
        lines.append(f"- {'OK  ' if len(h) == 1 else 'FAIL'} scenario {s}: config hash {list(h)}")
        ok &= len(h) == 1
    for col in ["switching_actions", "switching_reversals", "fallback_epochs", "overload_events", "soc_violations"]:
        bad = (df[col] < 0) | (df[col] != df[col].round())
        lines.append(f"- {'OK  ' if not bad.any() else 'FAIL'} {col}: non-negative integers")
        ok &= not bad.any()
    for col in ["critical_restoration_percent"]:
        bad = (df[col] < -1e-9) | (df[col] > 100 + 1e-9)
        lines.append(f"- {'OK  ' if not bad.any() else 'FAIL'} {col} within [0,100]")
        ok &= not bad.any()
    lines.append(f"- {'OK  ' if df.success.isin([0, 1]).all() else 'FAIL'} success is binary per run")
    lines.append(f"- INFO overload events after shedding (should be 0): {int(df.overload_events.sum())}")
    return ok, "\n".join(lines)


FAMILY = [  # (scenario, baseline, proposed, metric, lower_is_better)
    ("main", "Snapshot-SAGM", FULL, "cum_ens_kwh", True),
    ("main", "RH-FixedWeight", FULL, "cum_ens_kwh", True),
    ("main", "Snapshot-SAGM", FULL, "average_vdi_pu", True),
    ("main", "RH-FixedWeight", FULL, "switching_actions", True),
    ("main", "RH + Raw OSI", FULL, "switching_reversals", True),
    ("main", "RH + Raw OSI", FULL, "cum_ens_kwh", True),
    ("main", "Nominal-voltage repair", FULL, "cum_ens_kwh", True),
    ("main", "Nominal-voltage repair", FULL, "min_v_pu", False),
    ("main", "w/o ERB", FULL, "mean_iterations", True),
    ("main", "w/o graph repair", FULL, "cum_ens_kwh", True),
    ("main", "w/o local search", FULL, "cum_ens_kwh", True),
    ("main", "Tp=1", FULL, "cum_ens_kwh", True),
    ("severe", "Snapshot-SAGM", FULL, "cum_ens_kwh", True),
    ("severe", "RH-FixedWeight", FULL, "cum_ens_kwh", True),
    ("severe", "Snapshot-SAGM", FULL, "ens_crit_kwh", True),
    ("f2_27-28", "Snapshot-SAGM", FULL, "cum_ens_kwh", True),
    ("f2_25-29", "Snapshot-SAGM", FULL, "cum_ens_kwh", True),
]


def paired(df):
    out = []
    for scen, base, prop, m, lower in FAMILY:
        a = df[(df.scenario == scen) & (df.configuration == base)].set_index("seed")[m]
        b = df[(df.scenario == scen) & (df.configuration == prop)].set_index("seed")[m]
        idx = a.index.intersection(b.index)
        if len(idx) < 6:
            continue
        x, y = a.loc[idx].to_numpy(float), b.loc[idx].to_numpy(float)
        d = x - y if lower else y - x
        if np.allclose(d, 0):
            p, W = 1.0, np.nan
        else:
            w = stats.wilcoxon(x, y, zero_method="wilcox", alternative="two-sided")
            p, W = w.pvalue, w.statistic
        hl, lo, hi, conf = hodges_lehmann_ci(d)
        out.append(dict(scenario=scen, metric=m, baseline=base, proposed=prop, n=len(idx),
                        improvement="baseline-proposed" if lower else "proposed-baseline",
                        mean_baseline=x.mean(), mean_proposed=y.mean(), W=W, p=p,
                        HL=hl, CI_low=lo, CI_high=hi, CI_conf=conf, rank_biserial=rank_biserial(d),
                        n_zero=int((d == 0).sum())))
    res = pd.DataFrame(out)
    if len(res):
        res["p_holm"] = holm(res.p.to_numpy())
    return res


def trajectories():
    rows = []
    for c in [FULL, "RH-FixedWeight", "Snapshot-SAGM"]:
        for p in sorted((RUNS / "main" / c.replace(" ", "_")).glob("seed_*.csv")):
            d = pd.read_csv(p)
            d["configuration"] = c
            d["crit_served_pct"] = 100 * (1 - d.crit_deficit_frac)
            d["cum_ens_kwh"] = d.ens_kwh.cumsum()
            d["cum_weighted_ens"] = d.pens.cumsum()
            rows.append(d[["configuration", "t", "crit_served_pct", "soc_mean", "cum_ens_kwh", "cum_weighted_ens",
                           "osi_raw", "osi_f", "alpha1", "ens_kwh"]])
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows).groupby(["configuration", "t"]).mean().reset_index()


def main():
    OUT.mkdir(exist_ok=True)
    df = load()
    df.to_csv(OUT / "all_runs.csv", index=False)
    ok, txt = checks(df)
    (OUT / "checks.md").write_text(txt + "\n")
    M = METRICS
    t2 = summary(df, [FULL, "RH-FixedWeight", "Snapshot-SAGM"], M); t2.to_csv(OUT / "table_II_main.csv", index=False)
    t3 = summary(df, [FULL, "RH + Raw OSI", "RH + Filtered (no dead band)", "Nominal-voltage repair", "w/o ERB",
                      "w/o graph repair", "w/o local search"], M)
    t3.to_csv(OUT / "table_III_mechanisms.csv", index=False)
    hz = summary(df, ["Tp=1", "Tp=2", "Tp=3", FULL, "Tp=7", "Tp=10"], M); hz.to_csv(OUT / "table_IV_horizon.csv", index=False)
    grid = []
    for e in (5, 10, 15, 25):
        for b in (0.1, 0.3, 0.5, 1.0):
            name = FULL if (e == 10 and b == 0.3) else f"noise{e}_beta{b}"
            g = df[(df.scenario == "main") & (df.configuration == name)]
            if len(g):
                grid.append(dict(error_pct=e, beta=b, n=len(g), ens_mean=g.cum_ens_kwh.mean(), ens_sd=g.cum_ens_kwh.std(),
                                 reversals_mean=g.switching_reversals.mean(), reversals_sd=g.switching_reversals.std(),
                                 switching_mean=g.switching_actions.mean()))
    pd.DataFrame(grid).to_csv(OUT / "fig4_noise_beta.csv", index=False)
    rob = summary(df, [FULL, "SoC0=0.4", "SoC0=0.2", "Snapshot-SAGM", "Snapshot SoC0=0.2", "AR1 noise10", "AR1 noise25",
                       "Bias+10% noise10", "Bias-10% noise10"], M)
    rob.to_csv(OUT / "table_robustness.csv", index=False)
    sev = summary(df, [FULL, "RH-FixedWeight", "Snapshot-SAGM", "RH + Raw OSI"], M, scenario="severe")
    sev.to_csv(OUT / "table_severe.csv", index=False)
    flt = []
    for sc, lab in [("f2_25-29", "25-29 (benign tie)"), ("f2_27-28", "27-28"), ("main", "3-4 (main)"), ("severe", "2-3 (severe)")]:
        t_ = summary(df, [FULL, "RH-FixedWeight", "Snapshot-SAGM"], M, scenario=sc)
        if len(t_):
            t_.insert(0, "f2_location", lab); flt.append(t_)
    flt = pd.concat(flt) if flt else pd.DataFrame()
    flt.to_csv(OUT / "table_fault_location.csv", index=False)
    pt = paired(df); pt.to_csv(OUT / "paired_tests.csv", index=False)
    tr = trajectories(); tr.to_csv(OUT / "fig3_trajectories.csv", index=False)

    def fmt(t, cols):
        if t.empty:
            return "(no runs)\n"
        show = t[["configuration", "n_runs"] + [f"{c}_mean" for c in cols] + ["success_n"]].copy()
        return show.round(3).to_markdown(index=False) + "\n"
    rep = ["# R1 simulation results", "", f"Integrity checks: {'all passed' if ok else 'SEE checks.md (FAIL present)'}", "",
           "## Table II (main scenario)", fmt(t2, ["cum_ens_kwh", "ens_crit_kwh", "critical_restoration_percent",
                                                  "switching_actions", "average_vdi_pu", "avg_power_loss_kw"]),
           "## Table III (mechanisms)", fmt(t3, ["cum_ens_kwh", "rda_percent_day", "switching_reversals",
                                                "mean_iterations", "min_v_pu", "raw_candidate_admissible_frac"]),
           "## Table IV (horizon)", fmt(hz, ["cum_ens_kwh", "rda_percent_day", "mean_epoch_runtime_s", "switching_actions"]),
           "## Robustness", fmt(rob, ["cum_ens_kwh", "ens_crit_kwh", "switching_reversals", "fallback_epochs"]),
           "## Severe scenario (F2 = 2-3)", fmt(sev, ["cum_ens_kwh", "ens_crit_kwh", "critical_restoration_percent",
                                                     "rda_percent_day", "switching_actions"]),
           "## Fault-location robustness", (flt[["f2_location", "configuration", "n_runs", "cum_ens_kwh_mean",
               "ens_crit_kwh_mean", "switching_actions_mean", "success_n"]].round(3).to_markdown(index=False)
               if len(flt) else "(no runs)") + "\n",
           "## Paired tests (Wilcoxon, HL exact 95% CI, Holm)",
           (pt.round(4).to_markdown(index=False) if len(pt) else "(insufficient runs)") + "\n"]
    (OUT / "REPORT.md").write_text("\n".join(rep))
    print("\n".join(rep))


if __name__ == "__main__":
    main()
