#!/usr/bin/env python3
import argparse, json, sys
from pathlib import Path
from multiprocessing import Pool
import numpy as np, pandas as pd

ROOT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT))
from sim.network import load_net, build_truth
from sim.evaluator import Evaluator
import threephase as tp

_NET=None; _TR=None
def init_worker():
    global _NET,_TR
    _NET=load_net(ROOT/"config/ieee33_main.json")
    _TR=build_truth(_NET)

def job(arg):
    seed,rowd,prev_soc=arg
    net,tr=_NET,_TR
    t=int(rowd["t"])
    opened={int(x)-1 for x in str(rowd["open_branches"]).split(";") if str(x) not in ("","nan")}
    closed=np.array([0 if e in opened else 1 for e in range(net.nl)],np.int8)
    closed=(closed & tr.avail[t]).astype(np.int8)
    bp=np.array([float(x) for x in str(rowd["bess_p_kw"]).split(";")])
    u=(bp/net.bess_p).reshape(-1,1)
    ev=Evaluator(net)
    ev(closed,u,np.zeros(net.nl),False,closed,tr.avail[t],
       tr.pd[t:t+1],tr.qd[t:t+1],tr.pv[t:t+1],np.asarray(prev_soc,float))
    cap=dict(t=t,aux=ev.out_aux0.copy(),closed=ev.out_closed.copy(),
             served=ev.out_served0.copy(),V=ev.out_V0.copy())
    Dz,rt,alive=tp.tree_matrix(net,cap["closed"],tr.avail[t],cap["aux"])
    rows=[]
    for cfg in ("BR","PA"):
        al=tp.balanced_alloc(net,cap["aux"]) if cfg=="BR" else tp.phase_aware_alloc(net,tr,t,cap,Dz,rt,alive)
        V,J=tp.pf3(net,Dz,rt,alive,tp.injections(net,tr,t,cap,al))
        vui,vmag,legs=tp.metrics(net,V,J,rt,alive,None,al,cap["aux"])
        disp=tp.phase_dispatch_record(net,V,J,rt,alive,al,cap["aux"])
        rows.append(dict(seed=seed,t=t,config=cfg,max_vui=float(vui.max()),vmin_phase=float(vmag[alive].min()),
                         n_under=int((vmag[alive]<tp.VMIN-1e-9).sum()),max_leg_kva=float(legs.max()),
                         leg_over=int((legs>tp.LEG_KVA+1e-6).sum()),
                         bess_phase_dispatch=json.dumps(disp,separators=(",",":"))))
    return rows

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--seeds",required=True)
    ap.add_argument("--workers",type=int,default=48)
    ap.add_argument("--out",required=True)
    a=ap.parse_args()
    lo,hi=map(int,a.seeds.split("-"))
    jobs=[]
    for seed in range(lo,hi+1):
        d=pd.read_csv(ROOT/f"runs_r2/main/RH-Lean/seed_{seed:02d}.csv").sort_values("t")
        for _,r in d.iterrows():
            t=int(r.t)
            if t==0:
                prev=np.full(5,0.6)
            else:
                prev=np.array([float(x) for x in str(d.iloc[t-1].soc_vec).split(";")])
            jobs.append((seed,r.to_dict(),prev))
    with Pool(a.workers,initializer=init_worker) as p:
        rr=list(p.imap_unordered(job,jobs,chunksize=1))
    out=[x for pair in rr for x in pair]
    pd.DataFrame(out).sort_values(["config","seed","t"]).to_csv(a.out,index=False)
    print(f"wrote {a.out}: {len(out)} rows")
if __name__=="__main__": main()
