#!/usr/bin/env python3
"""
statistics_analysis.py -- Matched-seed paired statistics for the 30-run comparisons.

For every (baseline, proposed, metric) pair it reports
  * the two-sided Wilcoxon signed-rank test (exact null distribution when there are no
    ties/zeros, normal approximation with tie correction otherwise; SciPy >= 1.10),
  * the Hodges-Lehmann (HL) estimate of the paired shift = median of the Walsh averages
    of d_i = baseline_i - proposed_i,
  * the distribution-free (1 - alpha) confidence interval for that shift, obtained by
    inverting the signed-rank test: with C the lower alpha/2 critical value of the
    EXACT null distribution of W+, the CI is [W_(C+1), W_(M-C)] (1-indexed) over the M = n(n+1)/2
    sorted Walsh averages (Hollander, Wolfe & Chicken, Nonparametric Statistical Methods,
    3rd ed., Sec. 3.3). No normal approximation and no off-by-one rounding is used,
  * the matched-pairs rank-biserial correlation as an effect size,
  * Holm-Bonferroni adjusted p-values across all tests in the family.

Run consistency_check.py first: these statistics are only meaningful when the per-run
files are raw simulator outputs (integer counts, binary success flags, bounded %).

Usage
  python statistics_analysis.py                       # default comparison family
  python statistics_analysis.py --file results/x.csv --baseline A --proposed B --metric m
"""
from __future__ import annotations

import argparse
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "legacy_unverified" / "results"   # legacy files; R1 tests are run by aggregate_results.py
OUTDIR = ROOT / "legacy_unverified" / "statistics"

# (file, baseline, proposed, metric, lower_is_better)
DEFAULT_FAMILY = [
    ("table_vii_rh_vs_snapshot_30runs.csv", "Snapshot-SAGM", "Full RH-SAGM-GWO", "cum_ens_kwh", True),
    ("table_vii_rh_vs_snapshot_30runs.csv", "RH-FixedWeight", "Full RH-SAGM-GWO", "cum_ens_kwh", True),
    ("table_vii_rh_vs_snapshot_30runs.csv", "Snapshot-SAGM", "Full RH-SAGM-GWO", "total_switching_actions", True),
    ("table_vii_rh_vs_snapshot_30runs.csv", "Snapshot-SAGM", "Full RH-SAGM-GWO", "average_vdi_pu", True),
    ("table_viii_a_filter_osi_30runs.csv", "RH + Raw OSI", "RH + Filtered beta=0.3", "switching_reversals", True),
    ("table_viii_a_filter_osi_30runs.csv", "RH + Raw OSI", "RH + Filtered beta=0.3", "ens_kwh", True),
    ("table_viii_b_voltage_repair_30runs.csv", "Nominal MST", "Voltage-aware", "ens_kwh", True),
    ("table_viii_b_voltage_repair_30runs.csv", "Nominal MST", "Voltage-aware", "min_v_pu", False),
    ("table_viii_c_ablation_30runs.csv", "w/o ERB", "Full SAGM-GWO", "iterations", True),
]


@lru_cache(maxsize=None)
def signed_rank_null_cdf(n: int) -> np.ndarray:
    """Exact null distribution of W+ for n untied, non-zero differences (DP over ranks)."""
    maxw = n * (n + 1) // 2
    counts = np.zeros(maxw + 1, dtype=object)
    counts[0] = 1
    for k in range(1, n + 1):
        shifted = np.zeros_like(counts)
        shifted[k:] = counts[:-k]
        counts = counts + shifted
    pmf = np.array([c / 2 ** n for c in counts], dtype=float)
    return np.cumsum(pmf)


def hodges_lehmann_ci(d: np.ndarray, alpha: float = 0.05) -> tuple[float, float, float, float]:
    """HL shift estimate and exact distribution-free CI. Returns (hl, lo, hi, achieved_conf)."""
    d = np.asarray(d, dtype=float)
    n = d.size
    i, j = np.triu_indices(n)
    walsh = np.sort((d[i] + d[j]) / 2.0)
    M = walsh.size
    hl = float(np.median(walsh))
    cdf = signed_rank_null_cdf(n)
    # k = 1 + largest c with P(W+ <= c) <= alpha/2; CI = [W_(k), W_(M+1-k)] (1-indexed)
    k = int(np.searchsorted(cdf, alpha / 2.0, side="right"))
    if k == 0 or k > M - k + 1:
        return hl, float("nan"), float("nan"), float("nan")
    lo, hi = float(walsh[k - 1]), float(walsh[M - k])
    achieved = 1.0 - 2.0 * float(cdf[k - 1])
    return hl, lo, hi, achieved


def rank_biserial(d: np.ndarray) -> float:
    d = d[d != 0]
    if d.size == 0:
        return 0.0
    r = stats.rankdata(np.abs(d))
    return float((r[d > 0].sum() - r[d < 0].sum()) / r.sum())


def holm(p: np.ndarray) -> np.ndarray:
    p = np.asarray(p, dtype=float)
    order = np.argsort(p)
    m = p.size
    adj = np.empty(m)
    running = 0.0
    for k, idx in enumerate(order):
        running = max(running, (m - k) * p[idx])
        adj[idx] = min(1.0, running)
    return adj


def paired(df: pd.DataFrame, base: str, prop: str, metric: str) -> tuple[np.ndarray, np.ndarray]:
    a = df[df.configuration == base].set_index("seed")[metric]
    b = df[df.configuration == prop].set_index("seed")[metric]
    common = a.index.intersection(b.index)
    if len(common) < len(a) or len(common) < len(b):
        print(f"  ! seed mismatch for {base} vs {prop}: using {len(common)} matched seeds")
    return a.loc[common].to_numpy(float), b.loc[common].to_numpy(float)


def analyse(rows, alpha=0.05) -> pd.DataFrame:
    out = []
    for fname, base, prop, metric, lower_better in rows:
        df = pd.read_csv(RESULTS / fname)
        x, y = paired(df, base, prop, metric)
        d = x - y if lower_better else y - x       # positive = improvement of `proposed`
        n_zero = int(np.sum(d == 0))
        ties = len(np.unique(np.abs(d[d != 0]))) < np.sum(d != 0)
        method = "exact" if (n_zero == 0 and not ties and d.size <= 50) else "approx"
        w = stats.wilcoxon(x, y, alternative="two-sided", zero_method="wilcox",
                           method="exact" if method == "exact" else "approx", correction=method == "approx")
        hl, lo, hi, conf = hodges_lehmann_ci(d, alpha)
        out.append({
            "file": fname, "metric": metric, "baseline": base, "proposed": prop, "n_pairs": d.size,
            "improvement_direction": "baseline - proposed" if lower_better else "proposed - baseline",
            "median_baseline": np.median(x), "median_proposed": np.median(y),
            "W_statistic": w.statistic, "p_value": w.pvalue, "p_method": method,
            "HL_improvement": hl, "CI_low": lo, "CI_high": hi, "CI_achieved_conf": conf,
            "rank_biserial": rank_biserial(d), "n_zero_diffs": n_zero,
        })
    res = pd.DataFrame(out)
    res["p_holm"] = holm(res.p_value.to_numpy())
    res["significant_holm_0_05"] = res.p_holm < alpha
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file"); ap.add_argument("--baseline"); ap.add_argument("--proposed")
    ap.add_argument("--metric"); ap.add_argument("--higher-is-better", action="store_true")
    ap.add_argument("--alpha", type=float, default=0.05)
    a = ap.parse_args()
    rows = DEFAULT_FAMILY if not a.file else [(Path(a.file).name, a.baseline, a.proposed, a.metric, not a.higher_is_better)]
    res = analyse(rows, a.alpha)
    OUTDIR.mkdir(exist_ok=True)
    out = OUTDIR / "paired_wilcoxon_hodges_lehmann.csv"
    res.to_csv(out, index=False, float_format="%.6g")
    with pd.option_context("display.width", 200, "display.max_columns", 30):
        print(res[["metric", "baseline", "proposed", "p_value", "p_holm", "HL_improvement",
                   "CI_low", "CI_high", "rank_biserial"]].round(4).to_string(index=False))
    print(f"\nWrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
