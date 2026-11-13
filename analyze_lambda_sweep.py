#!/usr/bin/env python3
"""Analyze reviewer-requested lambda_critical sensitivity sweep."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import wilcoxon

ROOT=Path(__file__).resolve().parent
d=pd.read_csv(ROOT/"results_r2/lambda_sweep_runs.csv")
metrics=["cum_ens_kwh","ens_crit_kwh","rda_percent_day","switching_actions","final_soc_mean"]
summary=d.groupby("lambda_critical")[metrics+["success"]].agg(["mean","std","min","max"])
summary.to_csv(ROOT/"results_r2/lambda_sweep_stats.csv")

from statistics_analysis import hodges_lehmann_ci

rows=[]
base=d[d.lambda_critical==50].set_index("seed")
for lam in [10,100]:
    alt=d[d.lambda_critical==lam].set_index("seed")
    for metric in metrics:
        a=alt.loc[base.index,metric].to_numpy()
        b=base[metric].to_numpy()
        diff=a-b
        if np.allclose(diff,0):
            stat,p=0.0,1.0
        else:
            stat,p=wilcoxon(a,b,alternative="two-sided",zero_method="wilcox")
        hl,lo,hi=hodges_lehmann_ci(diff)[:3] if np.any(diff != 0) else (0.0,0.0,0.0)
        rows.append(dict(lambda_alt=lam,metric=metric,mean_alt=a.mean(),mean_nom=b.mean(),
                         mean_diff=diff.mean(),hl_shift=hl,ci95_lo=lo,ci95_hi=hi,p_raw=p))
r=pd.DataFrame(rows)
# Holm within each metric across the two comparisons
r["p_holm"]=np.nan
for metric,g in r.groupby("metric"):
    idx=list(g.index); ps=r.loc[idx,"p_raw"].to_numpy()
    order=np.argsort(ps); adj=np.empty_like(ps)
    prev=0.0
    m=len(ps)
    for rank,j in enumerate(order):
        val=(m-rank)*ps[j]
        prev=max(prev,val); adj[j]=min(prev,1.0)
    r.loc[idx,"p_holm"]=adj
r.to_csv(ROOT/"results_r2/lambda_sweep_pairwise.csv",index=False)
out={"summary_csv":"lambda_sweep_stats.csv","pairwise":r.to_dict(orient="records")}
(ROOT/"results_r2/lambda_sweep_summary.json").write_text(json.dumps(out,indent=2,default=float))
print(summary.round(4).to_string())
print()
print(r.round(5).to_string(index=False))
