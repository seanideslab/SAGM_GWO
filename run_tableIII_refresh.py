# Reporting note: historical "w/o graph repair" keys mean joint removal of graph repair and branch-exchange refinement.
#!/usr/bin/env python3
"""Refresh Table III metrics after separating GWO raw-candidate admissibility from branch-exchange evaluations."""
from __future__ import annotations
import argparse, sys, time
from multiprocessing import Pool
from pathlib import Path
import pandas as pd
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from sim.network import load_net, build_truth
from sim.controller import Episode, Variant, summarize

VARS={
 "full": Variant("Full RH framework", adaptive=False, erb=False, v_aware=False, local_search=True),
 "no_branch": Variant("w/o branch-exchange refinement", adaptive=False, erb=False, v_aware=False, local_search=False),
 "no_repair": Variant("w/o graph repair", adaptive=False, erb=False, v_aware=False, repair=False, local_search=False),
}
def run_one(arg):
    key,seed=arg
    net=load_net(ROOT/"config/ieee33_main.json"); tr=build_truth(net); var=VARS[key]
    rows=Episode(net,tr,var,seed).run()
    s=summarize(rows,net,var,seed); s["variant_key"]=key
    return s
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--variant",choices=VARS,required=True)
    ap.add_argument("--seeds",default="1-30"); ap.add_argument("--workers",type=int,default=8)
    a=ap.parse_args(); lo,hi=[int(x) for x in a.seeds.split("-")]
    _=run_one((a.variant,0))
    with Pool(a.workers) as p:
        out=list(p.imap_unordered(run_one,[(a.variant,s) for s in range(lo,hi+1)]))
    d=pd.DataFrame(out).sort_values("seed")
    od=ROOT/"results_r2"; od.mkdir(exist_ok=True)
    f=od/f"tableIII_refresh_{a.variant}_seeds{lo}-{hi}.csv"; d.to_csv(f,index=False)
    print(d[["cum_ens_kwh","ens_crit_kwh","rda_percent_day","raw_candidate_admissible_frac","success"]].agg(["mean","std"]).round(5).to_string())
if __name__=="__main__": main()
