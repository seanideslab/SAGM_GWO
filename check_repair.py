"""Fast preflight and a checkpointed pilot; never overwrites study outputs."""
from pathlib import Path
import os,sys,json,time,subprocess
ROOT=Path(__file__).resolve().parent
os.chdir(ROOT)
for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMBA_NUM_THREADS'):os.environ[k]='1'
import pandas as pd
from sim.network import load_net,build_truth
from sim.controller import Episode,summarize
from run_experiments import lean_suite,SCEN,slug

def main():
    for f in ('test_validation.py','test_counter_separation.py','test_repair.py'):
        subprocess.run([sys.executable,str(ROOT/'tests'/f)],check=True)
    folder=ROOT/'repair_checks';folder.mkdir(exist_ok=True)
    cases=[]
    for sc,v in lean_suite():
        if sc=='main' and v.name=='RH-Lean':cases.extend((sc,v,s) for s in (1,2,7,16,23))
        if sc=='storage_rich' and v.name=='RH-Lean noise0':cases.append((sc,v,7))
        if sc=='main' and v.name in ('RH-Lean w/o graph repair','RH-Lean w/o local search'):cases.append((sc,v,1))
    records=[]
    for i,(sc,v,seed) in enumerate(cases,1):
        print(f'PILOT {i}/{len(cases)} START {sc} {v.name} seed={seed}',flush=True)
        n=load_net(SCEN[sc]);start=time.perf_counter()
        rows=Episode(n,build_truth(n),v,seed).run();d=pd.DataFrame(rows)
        assert len(d)==24 and d.release_gate_pass.all()
        s=summarize(rows,n,v,seed);s.update(scenario=sc,wall_s=time.perf_counter()-start)
        records.append(s)
        d.to_csv(folder/f'{sc}_{slug(v.name)}_seed_{seed:02d}.csv',index=False)
        pd.DataFrame(records).to_csv(folder/'pilot_summary.csv',index=False)
        print(f'PILOT {i}/{len(cases)} DONE ENS={s["cum_ens_kwh"]:.3f} fallback={s["fallback_epochs"]} wall={s["wall_s"]:.1f}s',flush=True)
    (folder/'PASS.json').write_text(json.dumps({'tests':'passed','pilot_runs':len(records),'epochs':24*len(records),'finished':time.strftime('%Y-%m-%d %H:%M:%S')},indent=2))
    print('REPAIR CHECK PASSED. Next: RUN_ALL.cmd',flush=True)
if __name__=='__main__':main()
