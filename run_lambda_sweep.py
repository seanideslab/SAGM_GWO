#!/usr/bin/env python3
"""Reviewer-requested lambda_critical sensitivity sweep: 10/50/100, seeds 1-30."""
from __future__ import annotations
import argparse, json, sys, time
from multiprocessing import Pool
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from sim.network import load_net, build_truth
from sim.controller import Episode, Variant, summarize

def run_one(arg):
    lam, seed = arg
    cfg=ROOT/f"config/ieee33_lambda{lam}.json"
    net=load_net(cfg); tr=build_truth(net)
    var=Variant(f"lambda={lam}", horizon=5, adaptive=False, erb=False, v_aware=False,
                error_pct=10.0, noise_model="white")
    t0=time.perf_counter()
    rows=Episode(net,tr,var,seed).run()
    s=summarize(rows,net,var,seed)
    s["lambda_critical"]=lam
    s["wall_s"]=time.perf_counter()-t0
    return s

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--seeds",default="1-30")
    ap.add_argument("--workers",type=int,default=8)
    ap.add_argument("--levels",default="10,50,100")
    a=ap.parse_args()
    lo,hi=[int(x) for x in a.seeds.split("-")]
    # warm JIT in parent so forked workers inherit compiled kernels on Linux.
    _=run_one((50,0))
    levels=[int(x) for x in a.levels.split(",")]
    jobs=[(lam,seed) for lam in levels for seed in range(lo,hi+1)]
    t0=time.time()
    with Pool(a.workers) as p:
        out=list(p.imap_unordered(run_one,jobs))
    d=pd.DataFrame(out).sort_values(["lambda_critical","seed"])
    outdir=ROOT/"results_r2"; outdir.mkdir(exist_ok=True)
    outcsv=outdir/f"lambda_sweep_runs_{'-'.join(map(str,levels))}_seeds{lo}-{hi}.csv"
    d.to_csv(outcsv,index=False)
    meta={"created":time.strftime("%Y-%m-%d %H:%M:%S"),"n_runs":len(d),
          "levels":levels,"seeds":[lo,hi],"elapsed_s":time.time()-t0}
    (outdir/"lambda_sweep_meta.json").write_text(json.dumps(meta,indent=2))
    print(d.groupby("lambda_critical")[["cum_ens_kwh","ens_crit_kwh","rda_percent_day",
                                        "switching_actions","final_soc_mean","success"]]
          .agg(["mean","std"]).round(4).to_string())

if __name__=="__main__":
    main()
