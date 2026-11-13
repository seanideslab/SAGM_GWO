# Reporting note: historical "w/o graph repair" keys mean joint removal of graph repair and branch-exchange refinement.
#!/usr/bin/env python3
"""Reproduce Table III ablation RDA and raw-admissibility diagnostics (30 matched seeds)."""
from __future__ import annotations
import argparse, sys
from multiprocessing import Pool
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from sim.network import load_net, build_truth
from sim.controller import Episode, Variant, summarize

def one(arg):
    kind, seed=arg
    net=load_net(ROOT/"config/ieee33_main.json"); tr=build_truth(net)
    if kind=="no_ls":
        v=Variant("w/o branch-exchange refinement",horizon=5,adaptive=False,erb=False,v_aware=False,local_search=False,error_pct=10)
    else:
        v=Variant("w/o graph repair",horizon=5,adaptive=False,erb=False,v_aware=False,repair=False,local_search=False,error_pct=10)
    s=summarize(Episode(net,tr,v,seed).run(),net,v,seed); s["ablation"]=kind
    return s

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--workers",type=int,default=4); a=ap.parse_args()
    jobs=[(k,s) for k in ("no_ls","no_repair") for s in range(1,31)]
    with Pool(a.workers) as p: out=p.map(one,jobs)
    d=pd.DataFrame(out).sort_values(["ablation","seed"])
    d.to_csv(ROOT/"results_r2/ablation_rda_runs.csv",index=False)
    d.groupby("ablation")[["cum_ens_kwh","ens_crit_kwh","rda_percent_day","success","raw_candidate_admissible_frac"]].agg(["mean","std"]).to_csv(ROOT/"results_r2/ablation_rda_stats.csv")
if __name__=="__main__": main()
