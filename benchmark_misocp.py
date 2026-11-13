#!/usr/bin/env python3
"""
benchmark_misocp.py -- External MISOCP benchmark for SAGM-GWO restoration decisions.

Mixed-integer second-order-cone (MISOCP) restoration / reconfiguration model on the
balanced branch-flow (DistFlow) relaxation [Farivar & Low 2013; Jabr et al. 2012;
Taylor & Hover 2012], solved with Gurobi (gurobipy).

Differences from the "template" code in the review report (and why):
  * Radiality is NOT imposed by |closed branches| = |N|-1 alone. Branch counting is
    necessary but not sufficient (it admits a loop plus an isolated island) and it is
    wrong whenever buses are intentionally de-energized or islanded. This model uses a
    directed spanning-forest formulation: every energized non-root bus has exactly one
    parent arc, and a single-commodity fictitious flow from the roots (substation and
    grid-forming BESS buses) certifies connectivity, which excludes cycles.
  * Islands are admissible only if rooted at a grid-forming (GFM) BESS (IEEE 1547.4
    style grid-forming source requirement); grid-following DG cannot energize an island.
  * Load pickup z_i in [0,1], DG and BESS dispatch, SoC dynamics (4g), SoC bounds and the
    terminal-reserve constraint (4h), charge/discharge exclusivity (4i) and converter
    apparent-power limits (4j) are modelled over a horizon of T epochs.
  * After solving, the topology and dispatch of the first epoch are re-evaluated with an
    exact nonlinear backward/forward sweep, so the SOC-relaxation exactness is reported
    instead of assumed.

Validation mode (--validate) solves the classical Baran-Wu IEEE 33-bus loss-minimum
reconfiguration (all 37 branches switchable, no DG). The published optimum opens
branches {7, 9, 14, 32, 37} (lines 7-8, 9-10, 14-15, 32-33, 25-29) with ~139.5 kW loss.

Solvers: Gurobi (reference; needs a full licence -- the pip "restricted" licence rejects
models with more than ~200 variables in quadratic constraints) or SCIP via --solver scip
(open source, slower, used to produce the archived validation results).

Usage examples
  python benchmark_misocp.py --validate
  python benchmark_misocp.py --epoch 0 --horizon 2
  python benchmark_misocp.py --epoch 4 --horizon 1 --soc 0.35 --f2-branch 2-3
"""
from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUT = ROOT / "results" / "misocp"


# --------------------------------------------------------------------------- data
@dataclass
class Case:
    name: str
    v_base_kv: float
    s_base_kva: float
    buses: list[int]
    pd_kw: dict[int, float]
    qd_kvar: dict[int, float]
    critical: set[int]
    branches: pd.DataFrame          # branch_id, from_bus, to_bus, r_pu, x_pu, imax_pu, status, switchable
    dg_kw: dict[int, float]
    bess_kwh: dict[int, float]
    bess_soc0: dict[int, float]
    root: int = 1
    pv_kw: dict = field(default_factory=dict)   # unity-pf PV available at the epoch (kW)

    @property
    def z_base(self) -> float:
        return self.v_base_kv ** 2 / (self.s_base_kva / 1000.0)

    @property
    def i_base_a(self) -> float:
        return self.s_base_kva * 1000.0 / (math.sqrt(3) * self.v_base_kv * 1000.0)


def load_ieee33(main_amp: float = 300.0, lateral_amp: float = 200.0) -> Case:
    bus = pd.read_csv(DATA / "ieee33_bus_data.csv")
    br = pd.read_csv(DATA / "ieee33_branch_data.csv")
    v_base, s_base = 12.66, 1000.0  # kV, kVA
    zb = v_base ** 2 / (s_base / 1000.0)
    ib = s_base * 1000.0 / (math.sqrt(3) * v_base * 1000.0)
    main_trunk = set(range(1, 18))  # branches 1..17 = substation-to-bus-18 trunk
    br = br.assign(
        r_pu=br.R / zb,
        x_pu=br.X / zb,
        imax_pu=[(main_amp if b in main_trunk else lateral_amp) / ib for b in br.branch_id],
    )
    return Case(
        name="IEEE33", v_base_kv=v_base, s_base_kva=s_base,
        buses=bus.bus_id.tolist(),
        pd_kw=dict(zip(bus.bus_id, bus.P_load.astype(float))),
        qd_kvar=dict(zip(bus.bus_id, bus.Q_load.astype(float))),
        critical=set(bus.bus_id[bus.critical_flag == 1]),
        branches=br,
        dg_kw={int(b): float(c) for b, c in zip(bus.bus_id, bus.dg_capacity) if c > 0},
        bess_kwh={int(b): float(c) for b, c in zip(bus.bus_id, bus.bess_capacity) if c > 0},
        bess_soc0={int(b): float(s) for b, s, c in zip(bus.bus_id, bus.bess_initial_soc, bus.bess_capacity) if c > 0},
    )


@dataclass
class Params:
    horizon: int = 1
    dt_h: float = 1.0
    v_min: float = 0.95
    v_max: float = 1.05
    lam_critical: float = 50.0
    lam_regular: float = 1.0
    w_loss: float = 1.0            # objective weight per kWh of feeder loss
    w_switch: float = 5.0          # objective weight per switching operation (kWh-equivalent)
    bess_p_kw: float = 60.0        # converter active-power rating (ASSUMPTION - state in Table I)
    bess_s_kva: float = 60.0       # converter apparent-power rating (ASSUMPTION)
    eta_ch: float = 0.95
    eta_dis: float = 0.95
    soc_min: float = 0.10
    soc_max: float = 0.95
    soc_reserve: float = 0.20      # terminal reserve E_res as SoC fraction
    dg_q_ratio: float = 0.44       # |Q_DG| <= ratio * P_DG,max (pf ~0.9)
    gfm_buses: tuple = ()          # buses whose BESS is grid-forming (default: all BESS buses)
    time_limit_s: float = 600.0
    mip_gap: float = 1e-4
    all_switchable: bool = False
    fix_full_pickup: bool = False
    no_der: bool = False
    binary_pickup: bool = False    # bus-level on/off load pickup (matches the simulator)
    hold_topology: bool = False    # switch states held over the horizon (move blocking, as in SAGM-GWO)
    w_ens: float = 1.0             # weight on priority-weighted ENS (kWh)
    w_vdi: float = 0.0             # weight on mean |V-1| (linearised as |v-1|/2)


@dataclass
class Scenario:
    faulted: set[int] = field(default_factory=set)          # branch_ids removed
    load_mult: list[dict[int, float]] = field(default_factory=list)   # per epoch {bus: mult}
    dg_mult: list[dict[int, float]] = field(default_factory=list)     # per epoch {bus: mult}
    soc0: dict[int, float] | None = None
    x_prev: dict[int, int] | None = None                   # switch states before the epoch
    pv_kw_t: list = field(default_factory=list)            # per-step PV availability {bus: kW}


def branch_id_from_label(case: Case, label: str) -> int:
    a, b = (int(s) for s in label.split("-"))
    m = case.branches[((case.branches.from_bus == a) & (case.branches.to_bus == b)) |
                      ((case.branches.from_bus == b) & (case.branches.to_bus == a))]
    if m.empty:
        raise ValueError(f"branch {label} not found")
    return int(m.branch_id.iloc[0])


def scenario_from_schedule(case: Case, epoch: int, horizon: int, f2_label: str,
                           soc: float | None) -> Scenario:
    """Builds the deterministic sequential-disturbance schedule seen at decision epoch `epoch`.
    Forecasts over the horizon are taken as the nominal (noise-free) schedule, i.e. the
    benchmark is a perfect-information reference for that epoch."""
    f1 = branch_id_from_label(case, "6-7")
    f2 = branch_id_from_label(case, f2_label)
    faulted = {f1} if epoch >= 0 else set()
    if epoch >= 4:
        faulted.add(f2)
    load_mult, dg_mult = [], []
    for k in range(epoch, epoch + horizon):
        lm = {b: 1.0 for b in case.buses}
        if 2 <= k < 6:            # D1 .. D2
            lm[14] = lm[17] = 1.4
        dm = {b: 1.0 for b in case.dg_kw}
        if k >= 3:                # R1 (no recovery event in the schedule)
            for b in (22, 26):
                if b in dm:
                    dm[b] = 0.10
        load_mult.append(lm)
        dg_mult.append(dm)
    soc0 = None if soc is None else {b: soc for b in case.bess_kwh}
    return Scenario(faulted=faulted, load_mult=load_mult, dg_mult=dg_mult, soc0=soc0)


# --------------------------------------------------------------------------- solver backend
class Backend:
    """Thin wrapper so the same model runs on Gurobi (gurobipy) or SCIP (pyscipopt).
    Gurobi is the reference solver; SCIP is an open-source fallback (pip's size-limited
    Gurobi licence cannot hold this model)."""

    def __init__(self, solver: str, name: str, verbose: bool, time_limit: float, gap: float):
        self.solver = solver
        if solver == "gurobi":
            import gurobipy as gp
            from gurobipy import GRB
            self.gp, self.GRB = gp, GRB
            self.m = gp.Model(name)
            self.m.Params.OutputFlag = 1 if verbose else 0
            self.m.Params.MIPGap = gap
            self.m.Params.TimeLimit = time_limit
        elif solver == "scip":
            import pyscipopt as ps
            self.ps = ps
            self.m = ps.Model(name)
            if not verbose:
                self.m.hideOutput()
            self.m.setParam("limits/time", time_limit)
            self.m.setParam("limits/gap", gap)
        else:
            raise ValueError(solver)

    def var(self, name, lb=0.0, ub=None, binary=False):
        if self.solver == "gurobi":
            GRB = self.GRB
            return self.m.addVar(lb=-GRB.INFINITY if lb is None else lb,
                                 ub=GRB.INFINITY if ub is None else ub,
                                 vtype=GRB.BINARY if binary else GRB.CONTINUOUS, name=name)
        return self.m.addVar(name=name, vtype="B" if binary else "C", lb=lb, ub=ub)

    def vars(self, name, keys, **kw):
        return {k: self.var(f"{name}[{k}]", **kw) for k in keys}

    def con(self, c):
        if self.solver == "gurobi":
            self.m.addConstr(c)
        else:
            self.m.addCons(c)

    def qsum(self, it):
        return (self.gp.quicksum if self.solver == "gurobi" else self.ps.quicksum)(it)

    def minimize(self, expr):
        if self.solver == "gurobi":
            self.m.setObjective(expr, self.GRB.MINIMIZE)
        else:
            self.m.setObjective(expr, "minimize")

    def optimize(self):
        self.m.optimize()
        if self.solver == "gurobi":
            GRB = self.GRB
            self.status = {GRB.OPTIMAL: "OPTIMAL", GRB.TIME_LIMIT: "TIME_LIMIT",
                           GRB.INFEASIBLE: "INFEASIBLE"}.get(self.m.Status, str(self.m.Status))
            self.has_sol = self.m.SolCount > 0
            self.size = (self.m.NumVars, self.m.NumConstrs + self.m.NumQConstrs)
        else:
            self.status = self.m.getStatus().upper()
            self.has_sol = self.m.getNSols() > 0
            self.size = (self.m.getNVars(), self.m.getNConss())

    def val(self, x):
        if isinstance(x, (int, float)):
            return float(x)
        if self.solver == "gurobi":
            return x.getValue() if hasattr(x, "getValue") else x.X
        return self.m.getVal(x)

    def objective(self):
        return self.m.ObjVal if self.solver == "gurobi" else self.m.getObjVal()

    def gap(self):
        return self.m.MIPGap if self.solver == "gurobi" else self.m.getGap()

    def bound(self):
        return self.m.ObjBound if self.solver == "gurobi" else self.m.getDualbound()


# --------------------------------------------------------------------------- model
def solve(case: Case, prm: Params, scn: Scenario, verbose: bool = False, solver: str = "gurobi") -> dict:
    T, dt = prm.horizon, prm.dt_h
    sb = case.s_base_kva
    N = case.buses
    nN = len(N)
    br = case.branches[~case.branches.branch_id.isin(scn.faulted)].copy()
    if prm.all_switchable:
        br["switchable"] = 1
    E = br.branch_id.tolist()
    fr = dict(zip(br.branch_id, br.from_bus))
    to = dict(zip(br.branch_id, br.to_bus))
    r = dict(zip(br.branch_id, br.r_pu))
    x_ = dict(zip(br.branch_id, br.x_pu))
    imax = dict(zip(br.branch_id, br.imax_pu))
    sw = {e for e, s in zip(br.branch_id, br.switchable) if s == 1}
    x0 = scn.x_prev or dict(zip(case.branches.branch_id, case.branches.status))
    arcs = [(e, fr[e], to[e]) for e in E] + [(e, to[e], fr[e]) for e in E]
    A = range(len(arcs))
    into = {j: [a for a in A if arcs[a][2] == j] for j in N}
    outof = {j: [a for a in A if arcs[a][1] == j] for j in N}

    dg = {} if prm.no_der else case.dg_kw
    bess = {} if prm.no_der else case.bess_kwh
    gfm = set(prm.gfm_buses) if prm.gfm_buses else set(bess)
    gfm &= set(bess)
    soc0 = scn.soc0 or case.bess_soc0
    lam = {j: (prm.lam_critical if j in case.critical else prm.lam_regular) for j in N}

    B = Backend(solver, "ADN_restoration_MISOCP", verbose, prm.time_limit_s, prm.mip_gap)
    q = B.qsum
    TT = range(T)
    AT = [(a, t) for a in A for t in TT]
    NT = [(j, t) for j in N for t in TT]
    b = B.vars("b", AT, binary=True)            # arc closed and oriented i->j
    P = B.vars("P", AT, lb=None)
    Q = B.vars("Q", AT, lb=None)
    L = B.vars("l", AT)
    F = B.vars("F", AT)                         # fictitious connectivity flow
    v = B.vars("v", NT, ub=prm.v_max ** 2)
    e_ = B.vars("e", NT, binary=True)
    z = B.vars("z", NT, ub=1.0, binary=prm.binary_pickup)
    dev = B.vars("dev", NT)
    rt = B.vars("root", NT, binary=True)
    sF = B.vars("sF", NT)
    Psub = B.vars("Psub", TT)
    Qsub = B.vars("Qsub", TT, lb=None)
    GT = [(g, t) for g in dg for t in TT]
    ST = [(g, t) for g in bess for t in TT]
    pv = {} if prm.no_der else case.pv_kw
    PVT = [(g, t) for g in pv for t in TT]
    Ppv = B.vars("Ppv", PVT)
    Pdg = B.vars("Pdg", GT)
    Qdg = B.vars("Qdg", GT, lb=None)
    Pch = B.vars("Pch", ST)
    Pdis = B.vars("Pdis", ST)
    Qb = B.vars("Qb", ST, lb=None)
    uch = B.vars("uch", ST, binary=True)
    udis = B.vars("udis", ST, binary=True)
    En = B.vars("E", [(g, t) for g in bess for t in range(T + 1)])
    nsw = B.vars("nsw", [(e, t) for e in sw for t in TT])
    xc = {(e, t): b[idx, t] + b[idx + len(E), t] for idx, e in enumerate(E) for t in TT}

    M_v = prm.v_max ** 2
    for t in TT:
        for j in N:
            if j == case.root:
                B.con(e_[j, t] == 1); B.con(rt[j, t] == 1); B.con(v[j, t] == 1.0)
            elif j not in gfm:
                B.con(rt[j, t] == 0)
            B.con(rt[j, t] <= e_[j, t])
            # spanning forest: an energized non-root bus has exactly one parent arc
            B.con(q(b[a, t] for a in into[j]) == e_[j, t] - rt[j, t])
            # connectivity certificate: roots supply one unit to every energized bus
            B.con(sF[j, t] <= nN * rt[j, t])
            B.con(q(F[a, t] for a in into[j]) - q(F[a, t] for a in outof[j]) + sF[j, t] == e_[j, t])
            B.con(v[j, t] >= prm.v_min ** 2 * e_[j, t])
            B.con(v[j, t] <= prm.v_max ** 2 * e_[j, t])
            B.con(z[j, t] <= e_[j, t])
            if prm.fix_full_pickup:
                B.con(z[j, t] == 1)
            pd_ = case.pd_kw[j] * scn.load_mult[t].get(j, 1.0) / sb
            qd_ = case.qd_kvar[j] * scn.load_mult[t].get(j, 1.0) / sb
            gen_p, gen_q = 0, 0
            if j == case.root:
                gen_p, gen_q = Psub[t], Qsub[t]
            if j in dg:
                gen_p = gen_p + Pdg[j, t]; gen_q = gen_q + Qdg[j, t]
            if j in pv:
                gen_p = gen_p + Ppv[j, t]
            if j in bess:
                gen_p = gen_p + Pdis[j, t] - Pch[j, t]; gen_q = gen_q + Qb[j, t]
            B.con(q(P[a, t] - r[arcs[a][0]] * L[a, t] for a in into[j])
                  - q(P[a, t] for a in outof[j]) + gen_p == pd_ * z[j, t])           # (4a)
            B.con(q(Q[a, t] - x_[arcs[a][0]] * L[a, t] for a in into[j])
                  - q(Q[a, t] for a in outof[j]) + gen_q == qd_ * z[j, t])           # (4b)
        for a in A:
            e, i, j = arcs[a]
            B.con(b[a, t] <= e_[i, t]); B.con(b[a, t] <= e_[j, t])
            B.con(F[a, t] <= nN * b[a, t])
            B.con(L[a, t] <= imax[e] ** 2 * b[a, t])                                  # (4e)
            drop = v[i, t] - v[j, t] - 2 * (r[e] * P[a, t] + x_[e] * Q[a, t]) + (r[e] ** 2 + x_[e] ** 2) * L[a, t]
            B.con(drop <= M_v * (1 - b[a, t]))                                       # (4c), big-M
            B.con(drop >= -M_v * (1 - b[a, t]))
            B.con(P[a, t] * P[a, t] + Q[a, t] * Q[a, t] <= v[i, t] * L[a, t])         # SOC relaxation of (4d)
        for e in E:
            if e not in sw:
                B.con(xc[e, t] == e_[fr[e], t])        # non-switchable line closed when energized
                B.con(e_[fr[e], t] == e_[to[e], t])
            else:
                prev = x0.get(e, 0) if t == 0 else xc[e, t - 1]
                B.con(nsw[e, t] >= xc[e, t] - prev)
                B.con(nsw[e, t] >= prev - xc[e, t])
        pvk = scn.pv_kw_t[t] if scn.pv_kw_t else pv
        for g in pv:
            B.con(Ppv[g, t] <= pvk.get(g, 0.0) / sb * e_[g, t])
        if prm.hold_topology and t > 0:
            for e in E:
                B.con(xc[e, t] == xc[e, 0])
        for j in N:
            B.con(dev[j, t] >= 0.5 * (v[j, t] - 1.0) - 2.0 * (1 - e_[j, t]))
            B.con(dev[j, t] >= 0.5 * (1.0 - v[j, t]) - 2.0 * (1 - e_[j, t]))
        for g in dg:
            pmax = case.dg_kw[g] * scn.dg_mult[t].get(g, 1.0) / sb
            qmax = prm.dg_q_ratio * case.dg_kw[g] / sb
            B.con(Pdg[g, t] <= pmax * e_[g, t])
            B.con(Qdg[g, t] <= qmax * e_[g, t]); B.con(Qdg[g, t] >= -qmax * e_[g, t])
        for g in bess:
            pr, sr = prm.bess_p_kw / sb, prm.bess_s_kva / sb
            cap = case.bess_kwh[g] / sb
            B.con(Pch[g, t] <= pr * uch[g, t]); B.con(Pdis[g, t] <= pr * udis[g, t])        # (4i)
            B.con(uch[g, t] + udis[g, t] <= e_[g, t])                                        # (4j)
            B.con((Pdis[g, t] - Pch[g, t]) * (Pdis[g, t] - Pch[g, t]) + Qb[g, t] * Qb[g, t] <= sr ** 2)
            B.con(Qb[g, t] <= sr * e_[g, t]); B.con(Qb[g, t] >= -sr * e_[g, t])
            B.con(En[g, t + 1] == En[g, t] + prm.eta_ch * Pch[g, t] * dt - Pdis[g, t] * dt / prm.eta_dis)  # (4g)
            B.con(En[g, t + 1] >= prm.soc_min * cap); B.con(En[g, t + 1] <= prm.soc_max * cap)   # (4h)
    for g in bess:
        cap = case.bess_kwh[g] / sb
        B.con(En[g, 0] == soc0[g] * cap)
        B.con(En[g, T] >= prm.soc_reserve * cap)                                             # terminal reserve

    w_ens = q(lam[j] * case.pd_kw[j] * scn.load_mult[t].get(j, 1.0) * dt * (1 - z[j, t]) for j in N for t in TT)
    loss_kwh = q(r[arcs[a][0]] * sb * dt * L[a, t] for a in A for t in TT)
    n_sw = q(nsw[e, t] for e in sw for t in TT) if sw else 0
    vdi = q(dev[j, t] for j in N for t in TT) * (1.0 / (nN * T))
    B.minimize(prm.w_ens * w_ens + prm.w_loss * loss_kwh + prm.w_switch * n_sw + prm.w_vdi * vdi)

    t0 = time.perf_counter()
    B.optimize()
    wall = time.perf_counter() - t0
    X = B.val
    res = {"solver": solver, "status": B.status, "runtime_s": round(wall, 3),
           "n_vars": B.size[0], "n_constraints": B.size[1]}
    if not B.has_sol:
        return res
    res["mip_gap"] = B.gap()
    res["bound"] = B.bound()
    res["objective"] = B.objective()
    epochs = []
    for t in TT:
        closed = sorted(e for e in E if X(b[E.index(e), t]) + X(b[E.index(e) + len(E), t]) > 0.5)
        open_ = sorted(set(case.branches.branch_id) - set(closed))
        zt = {j: min(1.0, max(0.0, X(z[j, t]))) for j in N}
        ens = sum(case.pd_kw[j] * scn.load_mult[t].get(j, 1.0) * (1 - zt[j]) * dt for j in N)
        ens_c = sum(case.pd_kw[j] * scn.load_mult[t].get(j, 1.0) * (1 - zt[j]) * dt for j in N if j in case.critical)
        resid = max(X(v[arcs[a][1], t]) * X(L[a, t]) - X(P[a, t]) ** 2 - X(Q[a, t]) ** 2 for a in A)
        epochs.append({
            "epoch": t, "open_branches": open_,
            "roots": sorted(j for j in N if X(rt[j, t]) > 0.5),
            "deenergized_buses": sorted(j for j in N if X(e_[j, t]) < 0.5),
            "ens_kwh": round(ens, 3), "ens_critical_kwh": round(ens_c, 3),
            "loss_kw_relaxed": round(sum(r[arcs[a][0]] * X(L[a, t]) for a in A) * sb, 3),
            "max_soc_residual_pu": resid,
            "switch_ops": round(sum(X(nsw[e, t]) for e in sw), 3),
            "z": zt,
            "pens_kwh": sum(lam[j] * case.pd_kw[j] * scn.load_mult[t].get(j, 1.0) * (1 - zt[j]) * dt for j in N),
            "vdi_lin": sum(X(dev[j, t]) for j in N) / nN,
            "bess_p_kw": {g: (X(Pdis[g, t]) - X(Pch[g, t])) * sb for g in bess},
            "inj_kw": {j: ((X(Pdg[j, t]) if j in dg else 0) + (X(Ppv[j, t]) if j in pv else 0) + (X(Pdis[j, t]) - X(Pch[j, t]) if j in bess else 0)) * sb for j in N},
            "inj_kvar": {j: ((X(Qdg[j, t]) if j in dg else 0) + (X(Qb[j, t]) if j in bess else 0)) * sb for j in N},
            "v_root": {j: math.sqrt(max(X(v[j, t]), 0)) for j in N if X(rt[j, t]) > 0.5},
            "soc_end": {g: X(En[g, t + 1]) / (case.bess_kwh[g] / sb) for g in bess},
        })
    res["epochs"] = epochs
    res["ens_kwh_total"] = round(sum(ep["ens_kwh"] for ep in epochs), 3)
    return res


# --------------------------------------------------------------------------- exact AC check
def bfs_power_flow(case: Case, closed: list[int], roots: dict[int, float], z: dict[int, float],
                   inj_kw: dict[int, float], inj_kvar: dict[int, float], load_mult: dict[int, float],
                   tol: float = 1e-6, max_iter: int = 100) -> dict:
    """Exact balanced backward/forward sweep on each energized tree (root -> slack voltage)."""
    br = case.branches.set_index("branch_id").loc[closed]
    adj: dict[int, list[tuple[int, int]]] = {}
    for e, row in br.iterrows():
        adj.setdefault(row.from_bus, []).append((row.to_bus, e))
        adj.setdefault(row.to_bus, []).append((row.from_bus, e))
    sb = case.s_base_kva
    total_loss, vmin, iters_max, overload = 0.0, 9.9, 0, 0.0
    for root, vroot in roots.items():
        order, parent, pbranch, seen = [root], {root: None}, {}, {root}
        k = 0
        while k < len(order):
            u = order[k]; k += 1
            for w, e in adj.get(u, []):
                if w not in seen:
                    seen.add(w); parent[w] = u; pbranch[w] = e; order.append(w)
        S = {j: complex(case.pd_kw[j] * load_mult.get(j, 1.0) * z.get(j, 0) - inj_kw.get(j, 0),
                        case.qd_kvar[j] * load_mult.get(j, 1.0) * z.get(j, 0) - inj_kvar.get(j, 0)) / sb
             for j in order}
        V = {j: complex(vroot, 0) for j in order}
        for it in range(max_iter):
            # backward sweep: nodal currents accumulated into the branch feeding each bus
            Ib = {j: (S[j] / V[j]).conjugate() for j in order}
            for j in reversed(order[1:]):
                Ib[parent[j]] += Ib[j]
            Vn = {root: complex(vroot, 0)}
            for j in order[1:]:
                row = br.loc[pbranch[j]]
                Vn[j] = Vn[parent[j]] - complex(row.r_pu, row.x_pu) * Ib[j]
            dv = max(abs(Vn[j] - V[j]) for j in order)
            V = Vn
            if dv < tol:
                break
        iters_max = max(iters_max, it + 1)
        for j in order[1:]:
            row = br.loc[pbranch[j]]
            total_loss += row.r_pu * abs(Ib[j]) ** 2 * sb
            overload = max(overload, abs(Ib[j]) / row.imax_pu)
        vmin = min(vmin, min(abs(V[j]) for j in order))
    return {"loss_kw_exact": round(total_loss, 3), "vmin_pu_exact": round(vmin, 4),
            "max_loading_ratio": round(overload, 3), "bfs_iterations": iters_max}


def ac_check(case: Case, res: dict, scn: Scenario, t: int = 0) -> dict:
    ep = res["epochs"][t]
    closed = sorted(set(case.branches.branch_id) - set(ep["open_branches"]))
    return bfs_power_flow(case, closed, ep["v_root"], ep["z"], ep["inj_kw"], ep["inj_kvar"], scn.load_mult[t])


def pick_solver(choice: str = "auto") -> str:
    """'auto': Gurobi if a full licence is available (size-limited pip licence rejected), else SCIP."""
    if choice != "auto":
        return choice
    try:
        import gurobipy as gp
        m = gp.Model(); m.Params.OutputFlag = 0
        x = m.addVars(400, lb=-1, ub=1); y = m.addVars(400, ub=1)
        for i in range(400):
            m.addConstr(x[i] * x[i] <= y[i])
        m.optimize()
        return "gurobi"
    except Exception:
        return "scip"


# --------------------------------------------------------------------------- CLI
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--validate", action="store_true", help="Baran-Wu IEEE33 loss-minimum reconfiguration check")
    ap.add_argument("--epoch", type=int, default=0)
    ap.add_argument("--horizon", type=int, default=1)
    ap.add_argument("--soc", type=float, default=None, help="BESS SoC at the decision epoch (default: initial SoC)")
    ap.add_argument("--f2-branch", default="2-3", help="F2 location; manuscript says 2-3, data/event_schedule.csv says 25-29")
    ap.add_argument("--time-limit", type=float, default=600.0)
    ap.add_argument("--solver", choices=["gurobi", "scip", "auto"], default="auto")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    a.solver = pick_solver(a.solver)

    case = load_ieee33()
    OUT.mkdir(parents=True, exist_ok=True)
    if a.validate:
        prm = Params(horizon=1, all_switchable=True, fix_full_pickup=True, no_der=True,
                     w_switch=0.0, lam_critical=0, lam_regular=0, v_min=0.90, time_limit_s=a.time_limit)
        scn = Scenario(load_mult=[{}], dg_mult=[{}])
        res = solve(case, prm, scn, a.verbose, a.solver)
        res["ac_check"] = ac_check(case, res, scn)
        base = bfs_power_flow(case, case.branches.branch_id[case.branches.status == 1].tolist(), {1: 1.0},
                              {j: 1.0 for j in case.buses}, {}, {}, {})
        res["base_case_ac"] = base
        tag = f"validation_baran_wu_{a.solver}"
    else:
        prm = Params(horizon=a.horizon, time_limit_s=a.time_limit)
        scn = scenario_from_schedule(case, a.epoch, a.horizon, a.f2_branch, a.soc)
        res = solve(case, prm, scn, a.verbose, a.solver)
        if "epochs" in res:
            res["ac_check"] = ac_check(case, res, scn)
        tag = f"restoration_epoch{a.epoch}_T{a.horizon}_F2_{a.f2_branch}_{a.solver}"
    for ep in res.get("epochs", []):
        for k in ("z", "inj_kw", "inj_kvar"):
            ep[k] = {str(j): round(val, 4) for j, val in ep[k].items() if abs(val) > 1e-6}
    (OUT / f"{tag}.json").write_text(json.dumps(res, indent=2, default=str))
    summary = {k: v for k, v in res.items() if k != "epochs"}
    if "epochs" in res:
        summary["epoch0"] = {k: res["epochs"][0][k] for k in
                             ("open_branches", "roots", "deenergized_buses", "ens_kwh", "ens_critical_kwh",
                              "loss_kw_relaxed", "max_soc_residual_pu", "switch_ops")}
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    main()
