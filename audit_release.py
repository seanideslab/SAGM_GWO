
"""Read-only validation of the published common-hardware experiment archive."""
from pathlib import Path
import json, hashlib, csv
import pandas as pd
from scipy.stats import wilcoxon
ROOT=Path(__file__).resolve().parent
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
manifest=json.loads((ROOT/'provenance/manifest.json').read_text())
renames=json.loads((ROOT/'provenance/source_path_renames.json').read_text())
for name,h in manifest['source_hashes'].items():
 assert digest(ROOT/renames.get(name,name).replace('\\','/'))==h, name
counts={}
for folder,expected in [('runs_r2',1080),('supplement_runs',120),('development_runs',19)]:
 files=list((ROOT/folder).rglob('seed_*.json'));assert len(files)==expected
 counts[folder]=len(files)
 for f in files:
  j=json.loads(f.read_text());c=f.with_suffix('.csv')
  assert digest(c)==j['_csv_sha256'],str(c)
  a=pd.read_csv(c);assert len(a)==24 and a.t.tolist()==list(range(24)),str(c)
main=pd.read_csv(ROOT/'results_r2/machine_main_runs.csv')
assert len(main)==1080 and main.groupby(['scenario','configuration']).size().eq(30).all()
assert int(main.fallback_epochs.sum())==1
for name in ['reserve','lambda']:
 a=pd.read_csv(ROOT/f'results_r2/{name}_sweep_runs.csv')
 assert len(a)==90 and a.fallback_epochs.sum()==0
ph=pd.read_csv(ROOT/'results_3ph/epochs.csv')
assert len(ph)==1440 and ph.groupby(['seed','config']).size().eq(24).all()
assert set(ph.seed)==set(range(1,31))
br=ph[ph.config=='BR'].set_index(['seed','t']).sort_index()
pa=ph[ph.config=='PA'].set_index(['seed','t']).sort_index()
assert br.index.equals(pa.index) and (br.ens_kwh-pa.ens_kwh).abs().max()<1e-9
max_net_error=0.
for a,b in zip(br.bess_phase_dispatch,pa.bess_phase_dispatch):
 x,y=json.loads(a),json.loads(b)
 assert set(x)==set(y)
 for bus in x:
  for k in ['p_kw','q_kvar']:
   max_net_error=max(max_net_error,abs(sum(x[bus][k])-sum(y[bus][k])))
assert max_net_error<1e-9
g=ph.groupby(['config','seed']).agg(vmin=('vmin_phase','min'),vui=('max_vui','max'))
print('Source hashes and complete run checkpoints PASS:',counts)
print('Phase voltage test p =',wilcoxon(g.loc['PA'].vmin,g.loc['BR'].vmin,alternative='greater').pvalue)
print('Phase maximum net P/Q mismatch =',max_net_error)
for cfg in ['BR','PA']:
 a=ph[ph.config==cfg]
 print(cfg,'undervoltage epochs=',int((a.n_under>0).sum()),'leg-overload epochs=',int((a.leg_over>0).sum()),'mean worst voltage=',g.loc[cfg].vmin.mean())
benchfiles=list((ROOT/'results_r2').glob('misocp_benchmark*.csv'))
assert len(benchfiles)==3
for f in benchfiles:
 b=pd.read_csv(f);assert len(b)==8 and set(b.t)==set(range(0,24,3))
 assert b.sagm_infeasible.sum()==0
 print(f.name,b.misocp_status.value_counts().to_dict(),'search means:',b.sagm_runtime_s.min(),b.sagm_runtime_s.max())
parts=list((ROOT/'results_r2/bench_parts').glob('*.sagm_seeds.csv'))
assert len(parts)==24
for f in parts:assert len(pd.read_csv(f))==30
t=pd.read_csv(ROOT/'results_r2/ieee69_epoch_timing_raw.csv')
assert len(t)==240
print('PASS: 24 fixed benchmark epochs / 720 search trials; 240 IEEE69 timing epochs.')
print('CAPA excluded. Numerical feasibility claims remain restricted to the stated models.')
