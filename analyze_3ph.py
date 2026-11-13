"""Apply the PREREG_3PH.md decision rule to results_3ph/epochs.csv."""
import numpy as np
import pandas as pd
from scipy.stats import wilcoxon

d = pd.read_csv("results_3ph/epochs.csv")
g = d.groupby(["config", "seed"]).agg(max_vui=("max_vui", "max"), vmin=("vmin_phase", "min"),
                                      bal_vmin=("bal_vmin", "min"), under_ep=("n_under", lambda s: int((s > 0).sum())),
                                      vui2_ep=("max_vui", lambda s: int((s > 0.02).sum())),
                                      leg_over=("leg_over", "sum"), max_leg=("max_leg_kva", "max"),
                                      ens=("ens_kwh", "sum")).reset_index()
br, pa = g[g.config == "BR"].set_index("seed"), g[g.config == "PA"].set_index("seed")
print(g.groupby("config")[["max_vui", "vmin", "bal_vmin", "under_ep", "vui2_ep", "leg_over", "max_leg", "ens"]]
      .agg(["mean", "std", "min", "max"]).T.round(4).to_string())
a_runs = int(((br.max_vui > 0.02) | ((br.vmin < 0.95) & (br.bal_vmin >= 0.95 - 1e-9))).sum())
rel = (br.max_vui - pa.max_vui) / br.max_vui
p = wilcoxon(br.max_vui, pa.max_vui, alternative="greater").pvalue
pv = wilcoxon(pa.vmin, br.vmin, alternative="greater").pvalue
new_over = int((pa.leg_over > br.leg_over).sum())
print(f"\n(a) runs with hidden phase-level problem: {a_runs}/30  -> {'PASS' if a_runs >= 10 else 'FAIL'}")
print(f"(b) max-VUI reduction median {100*rel.median():.1f}%  Wilcoxon p={p:.2e}  new leg overloads={new_over}"
      f" -> {'PASS' if (p < 0.05 and rel.median() >= 0.20 and new_over == 0) else 'FAIL'}")
print(f"    worst-phase voltage: BR mean {br.vmin.mean():.4f}, PA mean {pa.vmin.mean():.4f}, Wilcoxon p={pv:.2e}")
print(f"    epochs with phase V<0.95 (sum over runs): BR {br.under_ep.sum()}, PA {pa.under_ep.sum()}")
