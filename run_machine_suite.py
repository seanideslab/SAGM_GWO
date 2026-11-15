"""Serial, checkpointed repeat study. Does not alter the simulator or frozen inputs."""
from pathlib import Path
import os, sys, json, hashlib, platform, subprocess, time, threading, zipfile, argparse
ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ[key] = "1"
import numpy as np
import pandas as pd
from sim.controller import Episode, Variant, summarize
from sim.network import load_net, build_truth
from run_experiments import lean_suite, SCEN, slug

RESULT = ROOT / "results_r2"
CONTROL = ROOT / "rerun_control"
LEAN = dict(adaptive=False, erb=False, v_aware=False)
ACTIVE = {"stage": "starting", "started": time.monotonic()}
COUNTS = {"completed": 0, "total": 1219}
def status(label):
    ACTIVE.update(stage=label, started=time.monotonic())
    print(f"[{time.strftime('%H:%M:%S')}] {label}", flush=True)

def atomic(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)

def source_hashes():
    files = list(ROOT.glob("*.py")) + list((ROOT/"sim").glob("*.py")) + list((ROOT/"tests").glob("*.py")) + list((ROOT/"config").glob("*.json")) + list((ROOT/"data").glob("*.csv"))
    return {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}

def warm():
    print("Warming evaluator outside reported timings...", flush=True)
    n = load_net(ROOT/"config/ieee33_main.json")
    Episode(n, build_truth(n), Variant("warmup", **LEAN), 0).run()

def cached_run(folder, seed, net, var, scenario, extra=None):
    js = folder/f"seed_{seed:02d}.json"
    csv = js.with_suffix(".csv")
    if js.exists():
        s = json.loads(js.read_text(encoding="utf-8"))
        d = pd.read_csv(csv)
        assert int(s["seed"]) == seed and len(d) == net.cfg["window_steps"]
        assert list(d.t.astype(int)) == list(range(net.cfg["window_steps"]))
        assert s["_csv_sha256"] == hashlib.sha256(csv.read_bytes()).hexdigest()
        COUNTS["completed"] += 1
        print(f"SKIP {scenario} {var.name} seed={seed}", flush=True)
        return s
    status(f"RUN {COUNTS['completed']+1}/{COUNTS['total']} {scenario} {var.name} seed={seed}")
    t0 = time.perf_counter()
    rows = Episode(net, build_truth(net), var, seed).run()
    d = pd.DataFrame(rows)
    s = summarize(rows, net, var, seed)
    s.update(scenario=scenario, wall_s=time.perf_counter()-t0)
    if extra: s.update(extra)
    s["min_soc"] = float(d.soc_min.min())
    atomic(csv, d.to_csv(index=False))
    s["_csv_sha256"] = hashlib.sha256(csv.read_bytes()).hexdigest()
    atomic(js, json.dumps(s, indent=2, default=float))
    atomic(CONTROL/"progress.json", json.dumps(dict(last_complete=str(js.relative_to(ROOT)),updated=time.strftime("%Y-%m-%d %H:%M:%S"))))
    COUNTS["completed"] += 1
    print(f"DONE {scenario} {var.name} seed={seed} ENS={s['cum_ens_kwh']:.3f} wall={s['wall_s']:.1f}s", flush=True)
    return s

def command(*args):
    status("COMMAND " + " ".join(args))
    subprocess.run([sys.executable,"-u",*args],check=True,cwd=ROOT)

def analysis_step(name, *args):
    marker=CONTROL/(name+".done")
    if marker.exists():return
    command(*args)
    atomic(marker,"completed")

def heartbeat():
    while True:
        time.sleep(60)
        elapsed=time.monotonic()-ACTIVE["started"]
        print(f"[{time.strftime('%H:%M:%S')}] {ACTIVE['stage']} | elapsed {elapsed/60:.1f} min | runs {COUNTS['completed']}/{COUNTS['total']}",flush=True)

def preflight():
    import scipy, numba, matplotlib, tabulate, pyscipopt
    from pyscipopt import Model
    model=Model();model.hideOutput();x=model.addVar(lb=0);model.setObjective(x);model.optimize()
    assert str(model.getStatus())=="optimal"
    assert len(lean_suite())==36
    nominal=json.loads((ROOT/"config/ieee33_main.json").read_text())
    lambda50=json.loads((ROOT/"config/ieee33_lambda50.json").read_text())
    assert {k:v for k,v in nominal.items() if not k.startswith("_")} == {k:v for k,v in lambda50.items() if not k.startswith("_")}
    assert nominal["bess"]["soc_reserve"]==0.2
    assert sys.version_info[:2]==(3,12)
    hwpath=ROOT/"hardware.json"
    if not hwpath.exists():raise RuntimeError("Run RUN_ALL.cmd to capture hardware.json first.")
    hw=json.loads(hwpath.read_text(encoding="utf-8-sig"))
    # New output folders may use other CPUs; resume still checks exact recorded hardware.
    assert float(hw["InstalledRAM_GiB"]) > 0, "Invalid memory metadata."
    info=dict(hardware=hw,python=sys.version,platform=platform.platform(),source_hashes=source_hashes(),
              packages=subprocess.check_output([sys.executable,"-m","pip","freeze"],text=True),
              timing="Serial; one active experiment; BLAS/OpenMP/Numba threads=1; warmup excluded",
              main_cases=1080,additional_sensitivity_cases=120)
    path=CONTROL/"manifest.json"
    if path.exists():
        old=json.loads(path.read_text())
        for key in ("hardware","python","source_hashes","packages"):
            if old[key]!=info[key]:raise RuntimeError(f"Resume blocked: {key} changed. Use a fresh extracted folder.")
    else:atomic(path,json.dumps(info,indent=2))
    print("Compatibility, solver and provenance checks passed.",flush=True)

def run_all(skip_misocp=False):
    RESULT.mkdir(exist_ok=True)
    preflight()
    analysis_step("validation","tests/test_validation.py")
    analysis_step("counter_validation","tests/test_counter_separation.py")
    analysis_step("repair_validation","tests/test_repair.py")
    warm()
    # The entire main suite is serial so its epoch timings are uncontended.
    main=[]
    for sc,v in lean_suite():
        n=load_net(SCEN[sc])
        for seed in range(1,31):
            main.append(cached_run(ROOT/"runs_r2"/sc/slug(v.name),seed,n,v,sc))
    main=pd.DataFrame(main)
    assert len(main)==1080
    main.to_csv(RESULT/"machine_main_runs.csv",index=False)
    analysis_step("main_analysis","aggregate_lean.py","runs_r2")
    base=main[(main.scenario=="main") & (main.configuration=="RH-Lean")].copy()
    assert len(base)==30
    # Matched nominal cases are reused, with no double-counting.
    reserve=[];priority=[]
    for seed in range(1,31):
        s=base[base.seed==seed].iloc[0].to_dict()
        reserve.append(dict(s,reserve=0.2,baseline_reused=True))
        priority.append(dict(s,lambda_critical=50,baseline_reused=True))
    for level in (0.1,0.3):
        n=load_net(ROOT/"config/ieee33_main.json",{"bess.soc_reserve":level})
        for seed in range(1,31):
            reserve.append(cached_run(ROOT/"supplement_runs"/f"reserve{int(level*100)}",seed,n,
                Variant(f"RH-Lean reserve{int(level*100)}",**LEAN),"reserve",dict(reserve=level,baseline_reused=False)))
    for level in (10,100):
        n=load_net(ROOT/f"config/ieee33_lambda{level}.json")
        for seed in range(1,31):
            priority.append(cached_run(ROOT/"supplement_runs"/f"lambda{level}",seed,n,
                Variant(f"lambda={level}",**LEAN),"lambda",dict(lambda_critical=level,baseline_reused=False)))
    pd.DataFrame(reserve).to_csv(RESULT/"reserve_sweep_runs.csv",index=False)
    pd.DataFrame(priority).to_csv(RESULT/"lambda_sweep_runs.csv",index=False)
    analysis_step("reserve_analysis","analyze_reserve_sweep.py")
    analysis_step("lambda_analysis","analyze_lambda_sweep.py")
    mechanism=main[(main.scenario=="main") & main.configuration.isin(["RH-Lean","RH-Lean w/o graph repair","RH-Lean w/o local search"])].copy()
    assert len(mechanism)==90
    mechanism.to_csv(RESULT/"mechanism_recount_runs.csv",index=False)
    mechanism.groupby("configuration")[["cum_ens_kwh","ens_crit_kwh","rda_percent_day","raw_candidate_admissible_frac"]].agg(["mean","std"]).to_csv(RESULT/"mechanism_recount_stats.csv")
    # Optional mechanisms remain a three-seed descriptive development audit.
    dev=[]
    n=load_net(ROOT/"config/ieee33_main.json")
    variants=[Variant("fixed_noerb",**LEAN),Variant("adaptive_noerb",adaptive=True,erb=False,v_aware=False),
              Variant("fixed_erb",adaptive=False,erb=True,v_aware=False)]
    for v in variants:
        for seed in range(101,104):
            dev.append(cached_run(ROOT/"development_runs"/v.name,seed,n,v,"development"))
    pd.DataFrame(dev).to_csv(RESULT/"osi_erb_development_audit.csv",index=False)
    # Repeat calibration as an audit only; never rewrite frozen parameters.
    cal=[]
    for seed in range(101,111):
        folder=ROOT/"development_runs"/"calibration"
        cached_run(folder,seed,n,Variant("RH-FixedWeight",adaptive=False),"calibration")
        cal.append(pd.read_csv(folder/f"seed_{seed:02d}.csv"))
    cal=pd.concat(cal,ignore_index=True);cal.to_csv(RESULT/"osi_calibration_audit.csv",index=False)
    p5,p50,p95=np.percentile(cal.osi_f,[5,50,95])
    atomic(RESULT/"osi_calibration_audit.json",json.dumps(dict(p5=p5,p50=p50,p95=p95,c=p50,
        tau=2*np.log(9)/max(p95-p5,1e-6),applied_to_config=False),indent=2))
    # Full phase replay with per-seed checkpoints and per-phase dispatch.
    import threephase
    phase=[]
    for seed in range(1,31):
        path=ROOT/"phase_runs"/f"seed_{seed:02d}.csv"
        if path.exists():d=pd.read_csv(path)
        else:
            status(f"BR/PA {seed}/30")
            d=pd.DataFrame(threephase.run_seed(seed))
            atomic(path,d.to_csv(index=False))
        assert len(d)==48 and d.groupby("config").size().to_dict()=={"BR":24,"PA":24}
        assert "bess_phase_dispatch" in d
        phase.append(d)
    d=pd.concat(phase).sort_values(["config","seed","t"])
    (ROOT/"results_3ph").mkdir(exist_ok=True)
    d.to_csv(ROOT/"results_3ph/epochs.csv",index=False)
    d.to_csv(RESULT/"threephase_epochs.csv",index=False)
    analysis_step("phase_analysis","analyze_3ph.py")
    analysis_step("timing69","timing_ieee69.py","--seeds","1-10")
    # SCIP comparisons run one epoch at a time, with identical 1800-s caps.
    for system,horizon in (() if skip_misocp else (("33",1),("33",5),("69",5))):
        analysis_step(f"bench{system}_{horizon}","benchmark_epochs.py","--system",system,
            "--horizon",str(horizon),"--solver","scip","--workers","1","--time-limit","1800","--sagm-seeds","30")
    command("summarize_repair.py")
    assert source_hashes()==json.loads((CONTROL/"manifest.json").read_text())["source_hashes"]
    atomic(CONTROL/("CONTROLLERS_COMPLETE.json" if skip_misocp else "COMPLETE.json"),json.dumps(dict(main_cases=1080,additional_sensitivity_cases=120,
        main_plus_sensitivity_cases=1200,phase_rows=1440,capa_included=False,
        benchmarks_complete=not skip_misocp,source_inputs_unchanged=True,finished=time.strftime("%Y-%m-%d %H:%M:%S")),indent=2))
    pack=ROOT/"SAGM_GWO_4050_RESULTS.zip"
    with zipfile.ZipFile(pack,"w",zipfile.ZIP_DEFLATED) as z:
        for folder in ("runs_r2","supplement_runs","development_runs","phase_runs","results_r2","results_3ph","rerun_control"):
            for p in (ROOT/folder).rglob("*"):
                if p.is_file() and p.name!="active.lock":z.write(p,p.relative_to(ROOT))
        z.write(ROOT/"hardware.json","hardware.json")
        for p in ROOT.glob("console_*.txt"):z.write(p,p.name)
    print(f"{'CONTROLLERS COMPLETE; run RUN_ALL.cmd to finish benchmarks' if skip_misocp else 'ALL COMPLETE'}: {pack}",flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser();ap.add_argument("--check-only",action="store_true")
    ap.add_argument("--plan",action="store_true");ap.add_argument("--skip-misocp",action="store_true");a=ap.parse_args()
    if a.plan:
        print(f"Main: {len(lean_suite())} x 30 = 1080; sensitivity: +120; development: 19; BR/PA: 30 seeds; IEEE69: 10 seeds; MISOCP: 24 epochs.");sys.exit()
    CONTROL.mkdir(exist_ok=True)
    import msvcrt
    lock=open(CONTROL/"active.lock","a+b");lock.seek(0);lock.write(b"1");lock.flush();lock.seek(0)
    try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:raise SystemExit("Another runner is already active. Do not start a second copy.")
    try:
        if a.check_only:preflight()
        else:
            threading.Thread(target=heartbeat,daemon=True).start()
            run_all(skip_misocp=a.skip_misocp)
    finally:lock.seek(0);msvcrt.locking(lock.fileno(),msvcrt.LK_UNLCK,1);lock.close()
