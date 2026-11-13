#!/usr/bin/env python3
"""
threephase.py -- private three-phase replay of the balanced RH-Lean trajectories (PREREG_3PH.md).

  python threephase.py --seeds 1-30 --workers 2
"""
from __future__ import annotations

import argparse
import json
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from sim.controller import Episode, Variant      # noqa: E402
from sim.network import build_truth, load_net    # noqa: E402

A = np.exp(2j * np.pi / 3)
VBAL = np.array([1.0, A ** 2, A])                 # phases a, b, c
# Z_abc = z1 * K for z0 = 3 z1: Zs = (z0 + 2 z1)/3 = 5/3 z1, Zm = (z0 - z1)/3 = 2/3 z1
K = np.full((3, 3), 2.0 / 3.0) + np.eye(3) * (1.0)
UNBAL = {13: (0.50, 0.30, 0.20), 16: (0.50, 0.30, 0.20)}     # buses 14, 17 (0-based)
PV_PHASE = 0                                                    # phase a
LEG_KVA = 30.0
AGG_KVA = 60.0
VMIN = 0.95


class CaptureEpisode(Episode):
    def plant(self, closed, u0, t, soc, cur_state):
        m, out = super().plant(closed, u0, t, soc, cur_state)
        self.cap.append(dict(t=t, aux=self.ev.out_aux0.copy(), closed=out["closed"].copy(),
                             served=out["served"].copy(), V=out["V"].copy()))
        return m, out

    def run(self):
        self.cap = []
        return super().run()


def tree_matrix(net, closed, avail, aux):
    """Dz[i,k] = sum of z_b over branches shared by the root paths of i and k (same tree)."""
    nb = net.nb
    root = aux[:, 5].astype(int)
    alive = root >= 0
    adj = [[] for _ in range(nb)]
    for e in range(net.nl):
        a, b = net.fbus[e], net.tbus[e]
        if closed[e] and avail[e] and alive[a] and alive[b]:
            adj[a].append((b, e)); adj[b].append((a, e))
    parent = -np.ones(nb, int); pz = np.zeros(nb, complex)
    order = []
    for r in np.unique(root[alive]):
        seen = {r}; stack = [r]; order.append(r)
        while stack:
            v = stack.pop()
            for w, e in adj[v]:
                if w not in seen:
                    seen.add(w); parent[w] = v; pz[w] = net.r[e] + 1j * net.x[e]
                    stack.append(w); order.append(w)
    # path matrix: Path[i, b] = 1 if branch (identified by child bus b) lies on root->i path
    path = np.zeros((nb, nb))
    for i in order:
        j = i
        while parent[j] >= 0:
            path[i, j] = 1.0
            j = parent[j]
    Dz = (path * pz[None, :]) @ path.T
    return Dz, root, alive


def injections(net, tr, t, cap, alloc):
    """Per-phase net load S (kVA), shape (nb, 3); alloc maps bess index -> (3 P legs, 3 Q legs)."""
    aux, served = cap["aux"], cap["served"]
    nb = net.nb
    S = np.zeros((nb, 3), complex)
    for i in range(nb):
        if aux[i, 5] < 0:
            continue
        if served[i]:
            w = UNBAL.get(i, (1 / 3, 1 / 3, 1 / 3))
            S[i] += np.array(w) * (tr.pd[t, i] + 1j * tr.qd[t, i])
        S[i, PV_PHASE] -= aux[i, 0]
        S[i] -= (aux[i, 1] + 1j * aux[i, 2]) / 3.0
    for bi, g in enumerate(net.bess_bus):
        if aux[g, 5] < 0 or aux[g, 4] >= 1e8:       # dead or island slack
            continue
        p, q = alloc[bi]
        S[g] -= p + 1j * q
    return S


def pf3(net, Dz, root, alive, S):
    sb3 = net.cfg["s_base_kva"] / 3.0
    nb = net.nb
    s = (S / sb3).reshape(-1)
    V0 = np.tile(VBAL, nb)
    DLF = np.kron(Dz, K)
    V = V0.copy()
    for _ in range(60):
        J = np.conj(s / V)
        Vn = V0 - DLF @ J
        if np.max(np.abs(Vn - V)) < 1e-7:
            V = Vn
            break
        V = Vn
    V = V.reshape(nb, 3)
    J = np.conj(s / V.reshape(-1)).reshape(nb, 3)
    return V, J


def metrics(net, V, J, root, alive, S, alloc, aux):
    sb3 = net.cfg["s_base_kva"] / 3.0
    V1 = (V[:, 0] + A * V[:, 1] + A ** 2 * V[:, 2]) / 3
    V2 = (V[:, 0] + A ** 2 * V[:, 1] + A * V[:, 2]) / 3
    vui = np.where(alive, np.abs(V2) / np.maximum(np.abs(V1), 1e-9), 0.0)
    vmag = np.where(alive[:, None], np.abs(V), 9.9)
    legs = []
    for bi, g in enumerate(net.bess_bus):
        if aux[g, 5] < 0:
            continue
        if aux[g, 4] >= 1e8:                          # island slack: supplies the island currents
            isrc = J[root == g].sum(0)
            legs.extend(np.abs(V[g] * np.conj(isrc)) * sb3)
        else:
            p, q = alloc[bi]
            legs.extend(np.abs(p + 1j * q))
    return vui, vmag, np.array(legs) if legs else np.zeros(1)


def balanced_alloc(net, aux):
    al = {}
    for bi, g in enumerate(net.bess_bus):
        P, Q = aux[g, 3], (aux[g, 4] if aux[g, 4] < 1e8 else 0.0)
        al[bi] = (np.full(3, P / 3), np.full(3, Q / 3))
    return al



def phase_dispatch_record(net, V, J, root, alive, alloc, aux):
    """Return per-BESS per-phase P/Q/S (kW/kvar/kVA). Island GFM roots use actual slack injection."""
    sb3 = net.cfg["s_base_kva"] / 3.0
    rec = {}
    for bi, g in enumerate(net.bess_bus):
        if aux[g, 5] < 0:
            continue
        bus = int(g) + 1
        if aux[g, 4] >= 1e8:
            # actual source injection required by the island on each phase
            isrc = J[root == g].sum(0)
            Sc = V[g] * np.conj(isrc) * sb3
            p = np.real(Sc); q = np.imag(Sc); s = np.abs(Sc)
        else:
            p, q = alloc[bi]
            s = np.abs(p + 1j*q)
        rec[bus] = {"p_kw": [float(x) for x in p],
                    "q_kvar": [float(x) for x in q],
                    "s_kva": [float(x) for x in s]}
    return rec

def phase_aware_alloc(net, tr, t, cap, Dz, root, alive):
    aux = cap["aux"]
    base = balanced_alloc(net, aux)
    ctl = [bi for bi, g in enumerate(net.bess_bus) if aux[g, 5] >= 0 and aux[g, 4] < 1e8]
    if not ctl:
        return base

    def unpack(x):
        al = dict(base)
        for j, bi in enumerate(ctl):
            dpa, dpb, dqa, dqb = x[4 * j:4 * j + 4]
            p0, q0 = base[bi]
            al[bi] = (p0 + np.array([dpa, dpb, -dpa - dpb]), q0 + np.array([dqa, dqb, -dqa - dqb]))
        return al

    def obj(x):
        al = unpack(x)
        V, J = pf3(net, Dz, root, alive, injections(net, tr, t, cap, al))
        vui, vmag, _ = metrics(net, V, J, root, alive, None, al, aux)
        return 1e4 * (np.sum(vui ** 2) + 10 * np.sum(np.maximum(0, VMIN - vmag[alive]) ** 2))

    def cons(x):
        al = unpack(x)
        margins = []
        for bi in ctl:
            s = np.abs(al[bi][0] + 1j * al[bi][1])
            margins.extend(LEG_KVA ** 2 - s ** 2)
            margins.append(AGG_KVA - np.sum(s))
        return np.asarray(margins, dtype=float)

    x0 = np.zeros(4 * len(ctl))
    r = minimize(obj, x0, method="SLSQP", constraints=[{"type": "ineq", "fun": cons}],
                 options=dict(maxiter=60, ftol=1e-9))
    x = r.x
    for _ in range(200):                              # back off towards x0 until all legs are within rating
        if np.all(cons(x) >= 0):
            break
        x = 0.98 * x
    if not (np.all(cons(x) >= 0) and obj(x) <= obj(x0)):
        x = x0
    return unpack(x)


def run_seed(seed):
    net = load_net(ROOT / "config/ieee33_main.json"); tr = build_truth(net)
    ep = CaptureEpisode(net, tr, Variant("RH-Lean", adaptive=False, erb=False, v_aware=False), seed)
    rows = ep.run()
    out = []
    for cap, row in zip(ep.cap, rows):
        t = cap["t"]
        Dz, root, alive = tree_matrix(net, cap["closed"], tr.avail[t], cap["aux"])
        bal_vmin = cap["V"][alive].min() if alive.any() else np.nan
        for cfg in ("BR", "PA"):
            al = balanced_alloc(net, cap["aux"]) if cfg == "BR" else phase_aware_alloc(net, tr, t, cap, Dz, root, alive)
            V, J = pf3(net, Dz, root, alive, injections(net, tr, t, cap, al))
            vui, vmag, legs = metrics(net, V, J, root, alive, None, al, cap["aux"])
            disp = phase_dispatch_record(net, V, J, root, alive, al, cap["aux"])
            out.append(dict(seed=seed, t=t, config=cfg, ens_kwh=row["ens_kwh"], bal_vmin=bal_vmin,
                            max_vui=vui.max(), mean_vui=vui[alive].mean(), vmin_phase=vmag[alive].min(),
                            n_under=int((vmag[alive] < VMIN - 1e-9).sum()), max_leg_kva=legs.max(),
                            leg_over=int((legs > LEG_KVA + 1e-6).sum()),
                            bess_phase_dispatch=json.dumps(disp, sort_keys=True)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="1-30")
    ap.add_argument("--workers", type=int, default=2)
    a = ap.parse_args()
    lo, hi = (int(v) for v in a.seeds.split("-"))
    with Pool(a.workers) as p:
        res = [r for rr in p.imap_unordered(run_seed, range(lo, hi + 1)) for r in rr]
    d = pd.DataFrame(res).sort_values(["config", "seed", "t"])
    (ROOT / "results_3ph").mkdir(exist_ok=True)
    d.to_csv(ROOT / "results_3ph/epochs.csv", index=False)
    print(d.groupby("config")[["max_vui", "vmin_phase", "n_under", "leg_over", "max_leg_kva"]].describe().T)


if __name__ == "__main__":
    main()
