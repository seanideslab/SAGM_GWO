
import sys, json, numpy as np, pandas as pd
from multiprocessing import Pool
from pathlib import Path
ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from sim.network import load_net, build_truth
from sim.controller import Episode, Variant, summarize
CFG=ROOT/'config/ieee33_main.json'
variants=[
    Variant("fixed_noerb", adaptive=False, erb=False, v_aware=False, local_search=True),
    Variant("adaptive_noerb", adaptive=True, erb=False, v_aware=False, local_search=True),
    Variant("fixed_erb", adaptive=False, erb=True, v_aware=False, local_search=True),
]
def one(args):
    name, seed = args
    var=next(v for v in variants if v.name==name)
    net=load_net(CFG)
    rows=Episode(net, build_truth(net), var, seed).run()
    s=summarize(rows, net, var, seed)
    return {"variant":name,"seed":seed,**{k:s.get(k) for k in s}}
if __name__=="__main__":
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("--lo",type=int); ap.add_argument("--hi",type=int); ap.add_argument("--out")
    a=ap.parse_args()
    tasks=[(v.name,s) for s in range(a.lo,a.hi+1) for v in variants]
    with Pool(min(8,len(tasks))) as p:
        r=p.map(one,tasks)
    pd.DataFrame(r).to_csv(a.out,index=False)
    print(pd.DataFrame(r).groupby("variant").mean(numeric_only=True)[["ens_kwh","switching","iterations"]])
