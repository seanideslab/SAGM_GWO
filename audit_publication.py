"""Verify the delivered archive, without starting simulations (standard library only)."""
from pathlib import Path
import csv
import hashlib
import json
import math

ROOT = Path(__file__).resolve().parent

def read_json(p):
    return json.loads(p.read_text(encoding='utf-8-sig'))

def rows(p):
    with p.open(encoding='utf-8-sig', newline='') as f:
        return list(csv.DictReader(f))

def require(condition, message):
    if not condition:
        raise ValueError(message)

def main():
    manifest = read_json(ROOT / 'rerun_control/manifest.json')
    for name, digest in manifest['source_hashes'].items():
        p = ROOT / name.replace('\\', '/')
        require(p.is_file(), f'Missing source: {name}')
        require(hashlib.sha256(p.read_bytes()).hexdigest() == digest, f'Source changed: {name}')
    counts = {}
    unsuccessful = []
    epochs = 0
    for folder, expected in [('runs_r2', 1080), ('supplement_runs', 120), ('development_runs', 19)]:
        count = 0
        for p in sorted((ROOT / folder).rglob('seed_*.json')):
            summary = read_json(p)
            require('_csv_sha256' in summary, f'Missing CSV digest: {p}')
            datafile = p.with_suffix('.csv')
            require(hashlib.sha256(datafile.read_bytes()).hexdigest() == summary['_csv_sha256'], f'CSV changed: {p}')
            data = rows(datafile)
            require([int(x['t']) for x in data] == list(range(24)), f'Incomplete epochs: {p}')
            for x in data:
                require(x['release_gate_pass'].lower() == 'true', f'Release gate failure: {p}')
                for k in ['final_nonconvergence', 'voltage_violations', 'bess_violations', 'reserve_step_violations', 'terminal_deficit_kwh', 'overloads', 'soc_violations', 'fallback']:
                    require(abs(float(x[k])) <= (1e-8 if k == 'terminal_deficit_kwh' else 0), f'{k} nonzero: {p}')
            require(math.isclose(sum(float(x['ens_kwh']) for x in data), float(summary['cum_ens_kwh']), abs_tol=1e-6), f'ENS mismatch: {p}')
            require(math.isclose(sum(float(x['ens_crit_kwh']) for x in data), float(summary['ens_crit_kwh']), abs_tol=1e-6), f'Critical ENS mismatch: {p}')
            if not summary['success']:
                unsuccessful.append({'file': str(p.relative_to(ROOT)), 'seed': summary['seed'], 'critical_ens_kwh': summary['ens_crit_kwh']})
            count += 1
            epochs += len(data)
        require(count == expected, f'{folder}: expected {expected}, got {count}')
        counts[folder] = count
    require(len(unsuccessful) == 1 and unsuccessful[0]['seed'] == 17 and math.isclose(unsuccessful[0]['critical_ens_kwh'],79.8), 'Unexpected unsuccessful-run accounting')
    phase = [x for p in sorted((ROOT / 'phase_runs').glob('*.csv')) for x in rows(p)]
    require(len(phase) == 1440, 'Incomplete phase replay')
    require(len({(x['seed'],x['t'],x['config']) for x in phase}) == 1440, 'Duplicate phase replay keys')
    require(all(float(x['leg_over']) == 0 for x in phase), 'Unexpected converter-leg overload')
    benchmark = [x for p in sorted((ROOT / 'results_r2').glob('misocp_benchmark_*_scip.csv')) for x in rows(p)]
    require(len(benchmark) == 24, 'Incomplete benchmarks')
    require(all(x['misocp_in_sim_gate_pass'].lower() == 'true' and int(x['sagm_infeasible']) == 0 for x in benchmark), 'Benchmark feasibility mismatch')
    seed_files = sorted((ROOT / 'results_r2/bench_parts').glob('*.sagm_seeds.csv'))
    require(len(seed_files) == 24, 'Missing benchmark seed files')
    for p in seed_files:
        data = rows(p)
        require(len(data) == 30 and {int(x['seed']) for x in data} == set(range(1,31)), f'Incomplete seeds: {p}')
    report = {'status': 'passed', 'source_hashes_verified': len(manifest['source_hashes']), 'controller_runs': counts, 'controller_epochs': epochs, 'fallback_epochs': 0, 'unsuccessful_runs': unsuccessful, 'phase_rows': len(phase), 'misocp_cases':len(benchmark), 'benchmark_search_runs':len(seed_files)*30, 'capa_included':False}
    (ROOT / 'audit').mkdir(exist_ok=True)
    (ROOT / 'audit/verification.json').write_text(json.dumps(report,indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__ == '__main__':
    main()
