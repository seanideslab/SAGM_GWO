"""Compare repaired results with the archived summaries; do not alter either dataset."""
from pathlib import Path
import json
import pandas as pd
ROOT=Path(__file__).resolve().parent
METRICS=('cum_ens_kwh','ens_crit_kwh','final_soc_mean','min_v_pu','max_loading_ratio','fallback_epochs','switching_actions','raw_candidate_admissible_frac')
def main():
    ref=ROOT/'baseline_reference.json'
    if not ref.exists():raise FileNotFoundError('baseline_reference.json is required for the final comparison')
    old=json.loads(ref.read_text());rows=[];missing=[]
    for b in old:
        f=ROOT/b['_path']
        if not f.exists():missing.append(b['_path']);continue
        a=json.loads(f.read_text())
        row={k:b.get(k) for k in ('scenario','configuration','seed')};row['path']=b['_path']
        for k in METRICS:
            if isinstance(a.get(k),(int,float)) and isinstance(b.get(k),(int,float)):
                row[k+'_old']=b[k];row[k+'_new']=a[k];row[k+'_delta']=a[k]-b[k]
        rows.append(row)
    out=ROOT/'results_r2';out.mkdir(exist_ok=True)
    d=pd.DataFrame(rows);d.to_csv(out/'repair_before_after.csv',index=False)
    cols=[c for c in d if c.endswith('_delta')]
    changed=((d[cols].abs()>1e-7).any(axis=1)).sum() if cols else 0
    # The separate benchmark state trajectory is not counted in the 1,219-run suite.
    mainmissing=[s for s in missing if not s.startswith('runs_r2/bench69/')]
    summary={'matched_runs':len(rows),'runs_with_changed_metrics':int(changed),'missing':mainmissing,
             'benchmark_state_log_missing':[s for s in missing if s.startswith('runs_r2/bench69/')]}
    benches=[]
    for f in (out/'bench_parts').glob('*_t[0-9][0-9].json'):
        r=json.loads(f.read_text());benches.append({k:r.get(k) for k in ('system','horizon','t','misocp_status','misocp_in_sim_gate_pass','sagm_infeasible')})
    summary['benchmarks']=benches
    (out/'repair_comparison_summary.json').write_text(json.dumps(summary,indent=2))
    print(f'REPAIR COMPARISON: {len(rows)} matched, {changed} changed; missing runs {len(mainmissing)}',flush=True)
    if mainmissing:raise RuntimeError('Incomplete repaired suite; see repair_comparison_summary.json')
if __name__=='__main__':main()
