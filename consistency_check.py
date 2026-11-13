#!/usr/bin/env python3
"""
consistency_check.py -- Audit the archived results before any statistics are computed.

Checks that per-run files look like raw simulator outputs and agree with the manuscript:
  C1  percentages lie in [0, 100]
  C2  count variables (switching actions, reversals, iterations) are non-negative integers
  C3  per-run success / feasibility flags are binary (0 or 100), not group rates
  C4  per-configuration mean AND SD land exactly on 1-decimal values (signature of draws
      rescaled to target summary statistics rather than raw outputs)
  C5  event schedule matches the manuscript text
  C6  RDA is consistent with critical-load ENS (RDA[%-day] ~= 100*ENS_crit/E_crit_day*days)
  C7  IEEE 69-bus file matches the standard benchmark (buses 2-6 carry no load)
  C8  every number in results/ that is quoted as a benchmark has a generating script

Exit code 1 if any check FAILS. Writes statistics/consistency_report.md.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent / "legacy_unverified"
RES = ROOT / "results"
DATA = ROOT.parent / "data"

MANUSCRIPT = {
    "F2_branch": "2-3",                 # Sec. V-B of the manuscript
    "critical_demand_kwh_day": 4608.0,  # Sec. VI-A
    "ens_critical_full_kwh": 6.27,
    "rda_full_percent_day": 2.8,
    "crit_restoration_snapshot": 99.67,
    "crit_restoration_full": 99.86,
}
PCT_COLS = re.compile(r"(percent|_pct)$")
COUNT_COLS = {"total_switching_actions", "switching_actions", "switching_reversals", "iterations"}
FLAG_COLS = {"success_rate_percent", "feasibility_percent"}

findings: list[tuple[str, str, str]] = []   # (check, status, message)


def add(check, ok, msg):
    findings.append((check, "PASS" if ok else "FAIL", msg))


def per_run_files():
    for p in sorted(RES.glob("*_30runs.csv")):
        df = pd.read_csv(p)
        if {"configuration", "seed"} <= set(df.columns):
            yield p, df


def main():
    for p, df in per_run_files():
        for c in df.columns:
            if PCT_COLS.search(c) and pd.api.types.is_numeric_dtype(df[c]):
                bad = df[(df[c] < 0) | (df[c] > 100)]
                add("C1", bad.empty, f"{p.name}:{c} -> {len(bad)} values outside [0,100]"
                    + (f" (e.g. {bad[c].iloc[0]})" if len(bad) else ""))
            if c in COUNT_COLS:
                nonint = (np.abs(df[c] - np.round(df[c])) > 1e-9).sum()
                neg = (df[c] < 0).sum()
                add("C2", nonint == 0 and neg == 0,
                    f"{p.name}:{c} -> {nonint} non-integer, {neg} negative per-run counts")
            if c in FLAG_COLS:
                nonbin = (~df[c].isin([0, 100])).sum()
                add("C3", nonbin == 0, f"{p.name}:{c} -> {nonbin} per-run values are not 0/100")
        num = [c for c in df.columns if c not in {"run_id", "seed", "configuration"}
               and pd.api.types.is_numeric_dtype(df[c])]
        exact = 0
        total = 0
        for cfg, g in df.groupby("configuration"):
            for c in num:
                if g[c].std() == 0:
                    continue
                total += 1
                m, s = g[c].mean(), g[c].std(ddof=1)
                if abs(m * 10 - round(m * 10)) < 5e-3 and abs(s * 10 - round(s * 10)) < 5e-3:
                    exact += 1
        add("C4", exact < max(2, 0.2 * total),
            f"{p.name}: {exact}/{total} (configuration, metric) groups have mean and SD exactly on 1-decimal values")

    ev = pd.read_csv(DATA / "event_schedule.csv").set_index("event_id")
    f2 = ev.loc["F2", "affected_bus_or_branch"].replace("branch:", "")
    add("C5", f2 == MANUSCRIPT["F2_branch"], f"event_schedule F2 = {f2}; manuscript F2 = {MANUSCRIPT['F2_branch']}")

    implied = 100 * MANUSCRIPT["ens_critical_full_kwh"] / MANUSCRIPT["critical_demand_kwh_day"]
    add("C6", abs(implied - MANUSCRIPT["rda_full_percent_day"]) < 0.1,
        f"RDA implied by ENS_crit = {implied:.3f} %-day (24 h window) vs reported {MANUSCRIPT['rda_full_percent_day']} %-day")
    t7 = pd.read_csv(RES / "table_vii_rh_vs_snapshot_30runs.csv")
    for cfg, key in [("Snapshot-SAGM", "crit_restoration_snapshot"), ("Full RH-SAGM-GWO", "crit_restoration_full")]:
        m = t7[t7.configuration == cfg].critical_load_restoration_percent.mean()
        add("C6", abs(m - MANUSCRIPT[key]) < 0.05,
            f"{cfg}: per-run critical restoration mean {m:.2f}% vs manuscript {MANUSCRIPT[key]}%")

    b69 = pd.read_csv(DATA / "ieee69_bus_data.csv")
    loads_2_6 = b69[b69.bus_id.between(2, 6)].P_load.sum()
    add("C7", loads_2_6 == 0, f"IEEE69 buses 2-6 total load = {loads_2_6} kW (standard case: 0 kW)")

    gap = pd.read_csv(RES / "table_viii_d_misocp_gap.csv")
    has_script = (ROOT.parent / "benchmark_misocp.py").exists() and any((RES / "misocp").glob("restoration_*.json")) \
        if (RES / "misocp").exists() else False
    add("C8", False if not has_script else "CPLEX" not in gap.to_string(),
        "table_viii_d_misocp_gap.csv quotes CPLEX v12.6 / >3600 s / <2.5% gap; no matching solver output is archived")

    lines = ["# Consistency report", "", "| Check | Status | Finding |", "|---|---|---|"]
    lines += [f"| {c} | {s} | {m} |" for c, s, m in findings]
    out = ROOT / "statistics" / "consistency_report.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    for c, s, m in findings:
        print(f"[{s}] {c}  {m}")
    nfail = sum(s == "FAIL" for _, s, _ in findings)
    print(f"\n{nfail} FAIL / {len(findings)} checks -> {out.relative_to(ROOT)}")
    sys.exit(1 if nfail else 0)


if __name__ == "__main__":
    main()
