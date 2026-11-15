"""Rolling-horizon / snapshot self-healing episode: OSI supervision, SAGM-GWO, plant, logging."""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, asdict

import numpy as np

from . import core
from .evaluator import Evaluator
from .network import Net, Truth, forecast, noise
from .optimizer import ERB, GWOParams, rank_value, search


@dataclass
class Variant:
    name: str
    mode: str = "rh"              # "rh" | "snapshot"
    horizon: int = 5
    adaptive: bool = True         # OSI-dependent weights (False -> fixed alpha(c))
    beta: float = 0.30
    deadband: float = 0.02
    repair: bool = True
    v_aware: bool = True
    erb: bool = True
    error_pct: float = 10.0
    noise_model: str = "white"
    soc0: float | None = None
    local_search: bool = True
    bias: float = 0.0


def alpha_weights(cfg, x):
    o = cfg["osi"]
    a1 = o["alpha1_min"] + (o["alpha1_max"] - o["alpha1_min"]) / (1 + math.exp(-o["tau"] * (x - o["c"])))
    pi = o["pi"]
    return np.array([a1, pi[0] * (1 - a1), pi[1] * (1 - a1), pi[2] * (1 - a1)])


def components(net: Net, closed, avail):
    par = list(range(net.nb))

    def f(i):
        while par[i] != i:
            par[i] = par[par[i]]; i = par[i]
        return i
    for e in range(net.nl):
        if closed[e] and avail[e]:
            a, b = f(net.fbus[e]), f(net.tbus[e])
            if a != b:
                par[a] = b
    return np.array([f(i) for i in range(net.nb)])


class Episode:
    def __init__(self, net: Net, truth: Truth, var: Variant, seed: int, gwo: GWOParams | None = None):
        self.net, self.tr, self.var, self.seed = net, truth, var, seed
        self.ev = Evaluator(net)
        self.gwo = gwo or GWOParams(**{k: net.cfg["optimizer"][k] for k in ("agents", "max_iter", "stagnation")},
                                    init_flip=net.cfg["optimizer"]["init_flip_prob"],
                                    eta_min=net.cfg["erb"]["eta_min"], eta_max=net.cfg["erb"]["eta_max"],
                                    gamma=net.cfg["erb"]["gamma"],
                                    local_search=net.cfg["optimizer"].get("local_search", "none") == "branch_exchange",
                                    ls_max_passes=net.cfg["optimizer"].get("ls_max_passes", 3))
        self.W = net.cfg["window_steps"]
        self.eps_l, self.eps_p = noise(seed, self.W, var.error_pct, var.noise_model, net.cfg["forecast"]["ar1_rho"],
                                       var.bias)
        self.rng = np.random.default_rng([seed, 104729])
        self.erb = ERB(net.cfg["erb"]["threshold"], net.cfg["erb"]["lambda"]) if var.erb else None
        r = net.cfg["objective_refs"]
        self.Eref, self.Vref, self.Sref = r["energy_kwh"], r["vdi"], r["switching"]

    # ------------------------------------------------------------------ helpers
    def plant(self, closed, u0, t, soc, cur_state, repair=True):
        n, tr = self.net, self.tr
        m = self.ev(closed, u0.reshape(-1, 1), np.zeros(n.nl), repair, cur_state, tr.avail[t],
                    tr.pd[t:t + 1], tr.qd[t:t + 1], tr.pv[t:t + 1], soc).copy()
        out = dict(closed=self.ev.out_closed.copy(), served=self.ev.out_served0.copy(), V=self.ev.out_V0.copy(),
                   P=self.ev.out_P0.copy(), Q=self.ev.out_Q0.copy(), I=self.ev.out_I0.copy(),
                   bessp=self.ev.out_bessp0.copy(), soc=self.ev.out_soc1.copy())
        return m, out

    def loadability(self, closed, t, pd_f, qd_f, pv_f, soc):
        """max scale s.t. current topology serves the forecast pattern without shedding."""
        n = self.net
        pdm, qdm = pd_f.mean(0, keepdims=True), qd_f.mean(0, keepdims=True)
        u0 = np.zeros((n.bess_bus.size, 1))
        lo, hi = 0.0, 3.0

        def ok(s):
            m = self.ev(closed, u0, np.zeros(n.nl), True, closed, self.tr.avail[t], pdm * s, qdm * s, pv_f[:1], soc)
            return m[core.M_NSHED] == 0 and m[core.M_DEEN] == 0
        if ok(hi):
            lo = hi
        else:
            for _ in range(12):
                mid = 0.5 * (lo + hi)
                if ok(mid):
                    lo = mid
                else:
                    hi = mid
        served = self.ev  # noqa
        comp = components(n, closed, self.tr.avail[t])
        rooted = {comp[0]} | {comp[g] for g in n.bess_bus if n.is_gfm[g]}
        en = np.array([comp[i] in rooted for i in range(n.nb)])
        cap = max(lo, 1e-6) * pdm[0][en].sum()
        rho = pdm[0].sum() / cap if cap > 0 else 1e3
        # R1 revision: L = rho/(1+rho) instead of clip(rho, 0, 1); monotone, parameter-free,
        # L = 0.5 at the loadability limit and keeps resolving overload beyond it.
        return float(rho / (1.0 + rho)), float(rho)

    def deficit(self, closed, t, pd_f, pv_f, soc):
        n = self.net
        comp = components(n, closed, self.tr.avail[t])
        crit_comps = {comp[i] for i in range(n.nb) if n.crit[i]}
        sup = 0.0
        for bi, g in enumerate(n.bess_bus):
            if comp[g] in crit_comps:
                e_avail = (soc[bi] - n.soc_res[bi]) * n.bess_cap[bi]
                sup += max(0.0, min(n.bess_p[bi], e_avail * n.eta[bi] / n.cfg["dt_h"]))
        for i in range(n.nb):
            if comp[i] in crit_comps:
                sup += pv_f[:, i].mean() + n.dg_cap[i]
        crit = max(pd_f[:, n.crit].sum(1).mean(), 1e-6)
        return max(0.0, 1.0 - sup / crit)

    def pattern(self, t, pd_f, pv_f, soc, closed):
        n = self.net
        v = np.concatenate([[pd_f.sum(1).mean() / n.pd_base.sum(), pv_f.sum(1).mean() / max(n.pv_cap.sum(), 1),
                             soc.mean()], self.tr.avail[t].astype(float), closed.astype(float)])
        return v / math.sqrt(v.size)

    # ------------------------------------------------------------------ episode
    def run(self):
        n, tr, var, cfg = self.net, self.tr, self.var, self.net.cfg
        W = self.W
        soc = np.full(n.bess_bus.size, var.soc0 if var.soc0 is not None else n.soc0[0])
        state = n.init_state.copy()
        T = var.horizon
        # pre-fault steady state provides the k-1 electrical state for t = 0
        pre_avail = np.ones(n.nl, np.bool_)
        self.ev(state, np.zeros((n.bess_bus.size, 1)), np.zeros(n.nl), True, state, pre_avail,
                tr.pd[:1], tr.qd[:1], tr.pv[:1], soc)
        prevP, prevQ, prevV = self.ev.out_P0.copy(), self.ev.out_Q0.copy(), self.ev.out_V0.copy()
        osi_f = osi_held = None
        U_prev = np.zeros((n.bess_bus.size, T))
        hold_u = np.zeros(n.bess_bus.size)
        last_dir = {}
        rows = []
        o = cfg["osi"]
        a_fixed = alpha_weights(cfg, o["c"])
        for t in range(W):
            t0 = time.perf_counter()
            avail = tr.avail[t]
            state = (state & avail).astype(np.int8)
            pd_f, qd_f, pv_f = forecast(n, tr, t, T, self.eps_l, self.eps_p)
            Lt, rho = self.loadability(state, t, pd_f, qd_f, pv_f, soc)
            Dt = self.deficit(state, t, pd_f, pv_f, soc)
            raw = float(np.clip(o["omega"][0] * Lt + o["omega"][1] * Dt, 0, 1))
            osi_f = raw if osi_f is None else var.beta * raw + (1 - var.beta) * osi_f
            if osi_held is None or abs(osi_f - osi_held) > var.deadband:
                osi_held = osi_f
            alpha = alpha_weights(cfg, osi_held) if var.adaptive else a_fixed
            vv = np.maximum(prevV[n.fbus] if var.v_aware else np.ones(n.nl), cfg["v_min"])
            vv = np.where(prevV[n.fbus] > 0, vv, 1.0) if var.v_aware else vv
            w = n.r * ((prevP / 1000) ** 2 + (prevQ / 1000) ** 2) / vv ** 2
            w = np.where(state > 0, w, 0.0)          # previously open branches carry zero prior flow
            optimize = var.mode == "rh" or t in tr.fault_epochs or t == 0
            iters = n_eval = 0
            fallback = 0
            raw_adm = np.nan
            if optimize:
                sw_idx = np.where(n.switchable & avail)[0]
                adm_count = [0, 0]

                def _score(bits, U):
                    m = self.ev(bits, U, w, var.repair, state, avail, pd_f, qd_f, pv_f, soc)
                    J = (alpha[0] * m[core.M_PENS] / self.Eref + alpha[1] * m[core.M_LOSS] / self.Eref
                         + alpha[2] * m[core.M_VDI] / self.Vref + alpha[3] * m[core.M_NSW] / self.Sref)
                    return rank_value(J, m), J, m.copy(), self.ev.out_closed.copy()

                def fitness(bits, U):
                    r = _score(bits, U)
                    adm_count[0] += r[2][core.M_RAWADM]; adm_count[1] += 1
                    return r

                def local_fitness(bits, U):
                    # Branch-exchange is a refinement stage and must not be included in the
                    # raw GWO-candidate admissibility denominator.
                    return _score(bits, U)
                pat = self.pattern(t, pd_f, pv_f, soc, state) if self.erb is not None else None
                mem = None
                if self.erb is not None:
                    mem, _ = self.erb.retrieve(pat)
                U_init = np.concatenate([U_prev[:, 1:], U_prev[:, -1:]], axis=1)[:, :T]
                import dataclasses
                gp = dataclasses.replace(self.gwo, local_search=var.local_search and self.gwo.local_search)
                bits, U, best, iters, n_eval = search(fitness, state, sw_idx, U_init, self.rng, gp, mem,
                                                      topo=(n.fbus, n.tbus, n.nb, avail),
                                                      local_fitness=local_fitness)
                raw_adm = adm_count[0] / max(adm_count[1], 1)
                rank, J, mbest, closed_rel = best
                if rank >= 1e6:                       # no admissible candidate -> safe fallback
                    fallback = 1
                    closed_rel = state.copy()
                    U = np.zeros_like(U)
                if self.erb is not None and not fallback:
                    self.erb.store(pat, (bits, U))
                U_prev = U
                u0 = U[:, 0]
                hold_u = u0.copy()
                rel_closed = closed_rel
            else:
                rel_closed = state.copy()
                u0 = hold_u
            mp, out = self.plant(rel_closed, u0, t, soc, state, repair=not bool(fallback))
            if rank_value(0.0, mp) >= 1e6:
                fallback = 1
                u0 = np.zeros(n.bess_bus.size)
                mp, out = self.plant(state.copy(), u0, t, soc, state, repair=False)
                hold_u = u0.copy()
            if rank_value(0.0, mp) >= 1e6:
                raise RuntimeError(f"No admissible released action: seed={self.seed}, t={t}, metrics={mp.tolist()}")
            # switching bookkeeping (executed operations)
            ops = 0; rev = 0
            for e in range(n.nl):
                if avail[e] and out["closed"][e] != state[e]:
                    ops += 1
                    d = 1 if out["closed"][e] > state[e] else -1
                    if e in last_dir and last_dir[e] != d:
                        rev += 1
                    last_dir[e] = d
            pdem_c = tr.pd[t][n.crit].sum()
            served_c = sum(tr.pd[t][i] for i in range(n.nb) if n.crit[i] and out["served"][i])
            rows.append(dict(
                t=t, rho=rho, osi_raw=raw, osi_f=osi_f, osi_held=osi_held, L=Lt, D=Dt, alpha1=alpha[0],
                optimized=int(optimize), iterations=iters, evaluations=n_eval, fallback=fallback,
                raw_candidate_admissible=raw_adm,
                ens_kwh=mp[core.M_ENS], ens_crit_kwh=mp[core.M_ENSC], pens=mp[core.M_PENS],
                demand_kwh=tr.pd[t].sum() * cfg["dt_h"], crit_demand_kwh=pdem_c * cfg["dt_h"],
                crit_deficit_frac=(pdem_c - served_c) / pdem_c if pdem_c > 0 else 0.0,
                loss_kwh=mp[core.M_LOSS], vdi=mp[core.M_VDI], vmin=mp[core.M_VMIN], max_loading=mp[core.M_IMAXR],
                vmax=mp[core.M_VMAX], final_nonconvergence=int(mp[core.M_FINAL_NONCONV]),
                voltage_violations=int(mp[core.M_VVIOL]), bess_violations=int(mp[core.M_BESSVIOL]),
                reserve_step_violations=int(mp[core.M_RESERVE_STEP]), terminal_deficit_kwh=mp[core.M_TERM],
                release_gate_pass=True,
                overloads=int(mp[core.M_OVERLOAD]), shed_events=int(mp[core.M_NSHED]), soc_violations=int(mp[core.M_SOCVIOL]),
                switch_ops=ops, reversals=rev, served_buses=int(out["served"].sum()),
                soc_mean=float(out["soc"].mean()), soc_min=float(out["soc"].min()),
                soc_vec=";".join(f"{v:.5f}" for v in out["soc"]),
                bess_p_kw=";".join(f"{p:.2f}" for p in out["bessp"]),
                open_branches=";".join(str(e + 1) for e in range(n.nl) if not out["closed"][e]),
                runtime_s=time.perf_counter() - t0,
            ))
            state = out["closed"].astype(np.int8)
            soc = out["soc"]
            prevP, prevQ, prevV = out["P"], out["Q"], out["V"]
        return rows


def summarize(rows, net: Net, var: Variant, seed: int):
    import pandas as pd
    d = pd.DataFrame(rows)
    W = len(d)
    rda = 100.0 * d.crit_deficit_frac.sum() * net.cfg["dt_h"] / 24.0
    opt = d[d.optimized == 1]
    return dict(
        configuration=var.name, seed=seed, cfg_hash=net.cfg_hash,
        cum_ens_kwh=d.ens_kwh.sum(), ens_crit_kwh=d.ens_crit_kwh.sum(), weighted_ens=d.pens.sum(),
        critical_restoration_percent=100.0 * (1 - d.ens_crit_kwh.sum() / d.crit_demand_kwh.sum()),
        rda_percent_day=rda,
        switching_actions=int(d.switch_ops.sum()), switching_reversals=int(d.reversals.sum()),
        average_vdi_pu=d.vdi.mean(), avg_power_loss_kw=d.loss_kwh.sum() / (W * net.cfg["dt_h"]),
        min_v_pu=d.vmin.min(), max_loading_ratio=d.max_loading.max(), overload_events=int(d.overloads.sum()),
        fallback_epochs=int(d.fallback.sum()), soc_violations=int(d.soc_violations.sum()),
        success=int(d.fallback.sum() == 0 and d.ens_crit_kwh.sum() < 1e-6 and d.soc_violations.sum() == 0),
        mean_iterations=opt.iterations.mean() if len(opt) else np.nan,
        mean_epoch_runtime_s=opt.runtime_s.mean() if len(opt) else np.nan,
        raw_candidate_admissible_frac=opt.raw_candidate_admissible.mean() if len(opt) else np.nan,
        final_soc_mean=d.soc_mean.iloc[-1],
        **{f"var_{k}": v for k, v in asdict(var).items() if k != "name"},
    )
