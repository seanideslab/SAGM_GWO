#!/usr/bin/env python3
"""
benchmark_epochs.py -- SAGM-GWO vs MISOCP reference on the same decision epochs (Sec. VII-F).

At each benchmark epoch t both methods start from the SAME state (switch states and per-BESS
SoC before t, read from a Full RH-SAGM-GWO state log of that system, seed 1) and solve the SAME
Tp-step problem with perfect information over the horizon (true load/PV incl. D1/R1; faults
known at t only):

  J = a1*PENS/E_ref + a2*Loss/E_ref + a3*mean VDI/V_ref + a4*N_sw     (a = OSI weights logged at t)

  MISOCP  : branch-flow SOC relaxation, bus-level binary pickup, spanning-forest radiality,
            GFM-rooted islands, BESS SoC dynamics + terminal reserve, switch states held over the
            horizon (same move blocking as SAGM-GWO), DG Q in [-0.44, 0.44] P_cap, BESS P/Q,
            VDI linearised. Optimistic reference (relaxation + free reactive dispatch).
  SAGM-GWO: the simulator's own search, 30 seeds; J from the exact AC evaluator.
  The MISOCP solution is also re-evaluated in the simulator (exact AC + shedding rule).

Benchmark epochs are fixed in advance: t = 0, 3, 6, ..., 21.

  python benchmark_epochs.py --system 33 --horizon 1 --solver gurobi
  python benchmark_epochs.py --system 33 --horizon 5 --solver gurobi
  python benchmark_epochs.py --system 69 --horizon 5 --solver gurobi --time-limit 3600
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import benchmark_misocp as bm                                        # noqa: E402
from sim import core                                                # noqa: E402
from sim.controller import Episode, Variant                         # noqa: E402
from sim.network import build_truth, load_net                       # noqa: E402
from sim.optimizer import rank_value, search                        # noqa: E402

CFG = {"33": ROOT / "config/ieee33_main.json", "69": ROOT / "config/ieee69_timing.json"}
EPOCHS = list(range(0, 24, 3))


def atomic_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(text, encoding='utf-8')
    os.replace(temp, path)


def misocp_case(net, tr, t):
    br = pd.read_csv(ROOT / "data" / net.cfg["branch_file"]).sort_values("branch_id")
    br = br.assign(r_pu=net.r, x_pu=net.x, imax_pu=net.imax, switchable=1)
    buses = list(range(1, net.nb + 1))
    return bm.Case(
        name=net.cfg["system"], v_base_kv=net.cfg["v_base_kv"], s_base_kva=net.cfg["s_base_kva"], buses=buses,
        pd_kw={j: float(tr.pd[t][j - 1]) for j in buses}, qd_kvar={j: float(tr.qd[t][j - 1]) for j in buses},
        critical={j for j in buses if net.crit[j - 1]}, branches=br,
        dg_kw={j: float(net.dg_cap[j - 1]) for j in buses if net.dg_cap[j - 1] > 0},
        bess_kwh={int(g) + 1: float(c) for g, c in zip(net.bess_bus, net.bess_cap)},
        bess_soc0={int(g) + 1: 0.0 for g in net.bess_bus},
        pv_kw={j: float(tr.pv[t][j - 1]) for j in buses if net.pv_cap[j - 1] > 0},
    )


def state_log(system, net, tr, path):
    if path.exists():
        return pd.read_csv(path)
    print(f"generating state log {path} (Full RH-SAGM-GWO, seed 1)", flush=True)
    rows = Episode(net, tr, Variant("Full RH-SAGM-GWO"), 1).run()
    path.parent.mkdir(parents=True, exist_ok=True)
    d = pd.DataFrame(rows); d.to_csv(path, index=False)
    return d


def J_of(alpha, m):
    return float(alpha[0] * m[core.M_PENS] / 100 + alpha[1] * m[core.M_LOSS] / 100 + alpha[2] * m[core.M_VDI] / 0.01
                 + alpha[3] * m[core.M_NSW])


LEAN = dict(adaptive=False, erb=False, v_aware=False)


def run_epoch(args):
    """One benchmark epoch (MISOCP + 30 SAGM seeds). Runs in its own process."""
    system, T, solver, t, sagm_seeds, time_limit, no_ls, logp, part = args
    if Path(part).exists():
        return json.loads(Path(part).read_text())
    net = load_net(CFG[system]); tr = build_truth(net)
    log = pd.read_csv(logp)
    cfg = net.cfg; refs = cfg["objective_refs"]; b = cfg["bess"]
    ep = Episode(net, tr, Variant("bench", horizon=T, **LEAN), 0)
    gwo = dataclasses.replace(ep.gwo, local_search=ep.gwo.local_search and not no_ls)
    a = argparse.Namespace(solver=solver, time_limit=time_limit, sagm_seeds=sagm_seeds, system=system)
    if t == 0:
        state = net.init_state.copy(); soc = net.soc0.copy()
    else:
        prev = log.iloc[t - 1]
        opened = {int(v) - 1 for v in str(prev.open_branches).split(";") if v and v != "nan"}
        state = np.array([0 if e in opened else 1 for e in range(net.nl)], np.int8)
        soc = np.array([float(v) for v in str(prev.soc_vec).split(";")])
    avail = tr.avail[t]
    state = (state & avail).astype(np.int8)
    a1 = float(log.iloc[t].alpha1)
    alpha = np.array([a1] + [p * (1 - a1) for p in cfg["osi"]["pi"]])
    pdh, qdh, pvh = tr.pd[t:t + T], tr.qd[t:t + T], tr.pv[t:t + T]
    avail_h = avail          # faults known at t only (same for both methods)
    # ---------------- MISOCP
    case = misocp_case(net, tr, t)
    case.bess_soc0 = {int(g) + 1: float(s) for g, s in zip(net.bess_bus, soc)}
    lm = [{j: (tr.pd[t + k][j - 1] / tr.pd[t][j - 1] if tr.pd[t][j - 1] > 0 else 1.0) for j in case.buses}
          for k in range(T)]
    pvt = [{j: float(tr.pv[t + k][j - 1]) for j in case.pv_kw} for k in range(T)]
    prm = bm.Params(horizon=T, v_min=cfg["v_min"], v_max=cfg["v_max"], lam_critical=cfg["lambda_critical"],
                    lam_regular=cfg["lambda_regular"], bess_p_kw=b["p_kw"], bess_s_kva=b["s_kva"], eta_ch=b["eta"],
                    eta_dis=b["eta"], soc_min=b["soc_min"], soc_max=b["soc_max"], soc_reserve=b["soc_reserve"],
                    gfm_buses=tuple(b["grid_forming_buses"]), time_limit_s=a.time_limit, all_switchable=True,
                    binary_pickup=True, hold_topology=True,
                    w_ens=alpha[0] / refs["energy_kwh"], w_loss=alpha[1] / refs["energy_kwh"],
                    w_vdi=alpha[2] / refs["vdi"], w_switch=alpha[3] / refs["switching"])
    scn = bm.Scenario(faulted={e + 1 for e in range(net.nl) if not avail_h[e]}, load_mult=lm,
                      dg_mult=[{}] * T, soc0=case.bess_soc0, x_prev={e + 1: int(state[e]) for e in range(net.nl)},
                      pv_kw_t=pvt)
    print(f"BENCHMARK IEEE{system} Tp={T} t={t}: SCIP START (limit {time_limit:.0f}s)", flush=True)
    r = bm.solve(case, prm, scn, False, a.solver)
    print(f"BENCHMARK IEEE{system} Tp={T} t={t}: SCIP {r['status']}", flush=True)
    atomic_text(Path(part).with_suffix('.solver.json'), json.dumps(r, default=lambda x: x.tolist() if hasattr(x,'tolist') else str(x)))
    row = dict(system=a.system, horizon=T, t=t, misocp_solver=a.solver, misocp_status=r["status"],
               misocp_runtime_s=r["runtime_s"], misocp_mip_gap=r.get("mip_gap"), misocp_J=r.get("objective"), misocp_bound=r.get("bound"),
               misocp_vars=r.get("n_vars"))
    if "epochs" in r:
        e0 = r["epochs"][0]
        row.update(misocp_ens=r["ens_kwh_total"], misocp_switch=e0["switch_ops"])
        closed_m = np.array([0 if (e + 1) in e0["open_branches"] else 1 for e in range(net.nl)], np.int8)
        u_m = np.array([[ep_k["bess_p_kw"].get(int(g) + 1, 0.0) / b["p_kw"] for ep_k in r["epochs"]]
                        for g in net.bess_bus])
        m = ep.ev(closed_m, u_m, np.zeros(net.nl), True, state, avail_h, pdh, qdh, pvh, soc)
        row.update(misocp_in_sim_J=J_of(alpha, m), misocp_in_sim_ens=float(m[core.M_ENS]),
                   misocp_in_sim_term_deficit=float(m[core.M_TERM]),
                   misocp_in_sim_gate_pass=bool(rank_value(J_of(alpha,m),m)<1e6))
    # ---------------- SAGM-GWO (same horizon, perfect information)
    ep.ev(state, np.zeros((net.bess_bus.size, 1)), np.zeros(net.nl), True, state, avail,
          tr.pd[t:t + 1], tr.qd[t:t + 1], tr.pv[t:t + 1], soc)
    P, Q, V = ep.ev.out_P0.copy(), ep.ev.out_Q0.copy(), ep.ev.out_V0.copy()
    vv = np.ones(net.nl)  # lean: nominal-voltage edge scores
    w = np.where(state > 0, net.r * ((P / 1000) ** 2 + (Q / 1000) ** 2) / vv ** 2, 0.0)
    Js, ens, rt = [], [], []
    seed_records = []
    for sd in range(1, a.sagm_seeds + 1):
        print(f"BENCHMARK IEEE{system} Tp={T} t={t}: SAGM {sd}/{a.sagm_seeds}",flush=True)
        def fitness(bits, U):
            m = ep.ev(bits, U, w, True, state, avail_h, pdh, qdh, pvh, soc)
            return rank_value(J_of(alpha, m), m), J_of(alpha, m), m.copy(), ep.ev.out_closed.copy()
        t0 = time.perf_counter()
        _, _, best, _, _ = search(fitness, state, np.where(net.switchable & avail)[0],
                                  np.zeros((net.bess_bus.size, T)), np.random.default_rng([sd, t, 31]), gwo,
                                  topo=(net.fbus, net.tbus, net.nb, avail))
        rt.append(time.perf_counter() - t0); Js.append(best[1] if best[0] < 1e6 else np.nan)
        ens.append(best[2][core.M_ENS])
        seed_records.append(dict(system=system,horizon=T,t=t,seed=sd,rank=float(best[0]),J=float(best[1]),ens=float(best[2][core.M_ENS]),search_runtime_s=rt[-1]))
    atomic_text(Path(part).with_suffix(".sagm_seeds.csv"), pd.DataFrame(seed_records).to_csv(index=False))
    valid_J = np.asarray(Js)[np.isfinite(Js)]
    row.update(sagm_ls=gwo.local_search, sagm_J_mean=float(valid_J.mean()) if len(valid_J) else None,
               sagm_J_sd=float(valid_J.std(ddof=1)) if len(valid_J)>1 else None,
               sagm_J_best=float(valid_J.min()) if len(valid_J) else None, sagm_infeasible=int(np.isnan(Js).sum()),
               sagm_ens_mean=np.mean(ens), sagm_runtime_s=np.mean(rt))
    if row.get("misocp_J") and row["sagm_J_mean"] is not None:
        row["gap_mean_pct"] = 100 * (row["sagm_J_mean"] - row["misocp_J"]) / max(abs(row["misocp_J"]), 1e-9)
    if row.get("misocp_bound") is not None and row["sagm_J_mean"] is not None:
        row["gap_to_bound_pct"] = 100 * (row["sagm_J_mean"] - row["misocp_bound"]) / max(abs(row["sagm_J_mean"]), 1e-9)
    if row.get("misocp_in_sim_J") and row["sagm_J_mean"] is not None:
        row["gap_vs_misocp_in_sim_pct"] = 100 * (row["sagm_J_mean"] - row["misocp_in_sim_J"]) / max(abs(row["misocp_in_sim_J"]), 1e-9)
    atomic_text(part, json.dumps(row, default=float))
    print(json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in row.items()}), flush=True)
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--system", default="33", choices=["33", "69"])
    ap.add_argument("--horizon", type=int, default=1)
    ap.add_argument("--solver", default="auto", choices=["auto", "scip", "gurobi"])
    ap.add_argument("--epochs", default=",".join(map(str, EPOCHS)))
    ap.add_argument("--sagm-seeds", type=int, default=30)
    ap.add_argument("--time-limit", type=float, default=900)
    ap.add_argument("--workers", type=int, default=8, help="epochs solved in parallel (one process each)")
    ap.add_argument("--no-ls", action="store_true", help="disable branch-exchange refinement (diagnostic)")
    ap.add_argument("--state-seed-log", default=None)
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    a.solver = bm.pick_solver(a.solver)
    print(f"MISOCP solver: {a.solver}", flush=True)
    T = a.horizon
    net = load_net(CFG[a.system]); tr = build_truth(net)
    logp = Path(a.state_seed_log) if a.state_seed_log else (
        ROOT / "runs_r2/main/RH-Lean/seed_01.csv" if a.system == "33" else ROOT / "runs_r2/bench69/seed_01.csv")
    if not logp.exists():
        print(f"generating state log {logp} (RH-Lean, seed 1)", flush=True)
        rows = Episode(net, tr, Variant("RH-Lean", **LEAN), 1).run()
        logp.parent.mkdir(parents=True, exist_ok=True); atomic_text(logp, pd.DataFrame(rows).to_csv(index=False))
    name = f"misocp_benchmark_ieee{a.system}_T{T}_{a.solver}{'_nols' if a.no_ls else ''}{a.tag}"
    parts = ROOT / "results_r2" / "bench_parts"; parts.mkdir(parents=True, exist_ok=True)
    epochs = [int(v) for v in a.epochs.split(",")]
    jobs = [(a.system, T, a.solver, t, a.sagm_seeds, a.time_limit, a.no_ls, str(logp), str(parts / f"{name}_t{t:02d}.json"))
            for t in epochs]
    from multiprocessing import Pool
    with Pool(min(a.workers, len(jobs))) as pool:
        out = pool.map(run_epoch, jobs)
    d = pd.DataFrame(out).sort_values("t")
    d.to_csv(ROOT / "results_r2" / f"{name}.csv", index=False)
    print(f"wrote results_r2/{name}.csv")


if __name__ == "__main__":
    main()
