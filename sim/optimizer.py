"""SAGM-GWO search kernel: binary GWO (V-shaped |tanh| flip rule) for switch states,
continuous GWO for BESS set-points, elite restoration bank (ERB) warm start, eq. (11)-(12)."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from . import core


@dataclass
class ERB:
    threshold: float = 0.85
    lam: float = 1.0
    patterns: list = field(default_factory=list)
    skeletons: list = field(default_factory=list)

    def similarity(self, p, q):
        nq = np.linalg.norm(p) * np.linalg.norm(q)
        if nq == 0:
            return 0.0
        return float(p @ q / nq * math.exp(-self.lam * float(np.sum((p - q) ** 2))))

    def retrieve(self, p):
        best, sk = 0.0, None
        for q, s in zip(self.patterns, self.skeletons):
            v = self.similarity(p, q)
            if v > best:
                best, sk = v, s
        return (sk, best) if best >= self.threshold else (None, best)

    def store(self, p, skeleton):
        self.patterns.append(p.copy())
        self.skeletons.append((skeleton[0].copy(), skeleton[1].copy()))


@dataclass
class GWOParams:
    agents: int = 30
    max_iter: int = 100
    stagnation: int = 20
    init_flip: float = 0.10
    eta_min: float = 0.20
    eta_max: float = 0.95
    gamma: float = 2.0
    local_search: bool = True      # R1: branch-exchange refinement of the GWO best (declared 2026-11-02)
    ls_max_passes: int = 3


def rank_value(J, m):
    """Reject residual physical violations, then rank admissible plans by J."""
    if not np.isfinite(J) or not np.all(np.isfinite(m)):
        return 1e9
    if m[core.M_STRUCT_INF] > 0:
        return 1e9
    if any(m[i] > 0 for i in (core.M_FINAL_NONCONV, core.M_VVIOL,
                              core.M_OVERLOAD, core.M_SOCVIOL, core.M_BESSVIOL)):
        return 1e8
    if m[core.M_RESERVE_STEP] > 0:
        return 1e6 + max(float(m[core.M_TERM]), 1.0)
    if m[core.M_TERM] > 1e-6:
        return 1e6 + m[core.M_TERM]
    return J


def search(fitness, cur_bits, sw_idx, U_init, rng, prm: GWOParams, memory=None, topo=None, local_fitness=None):
    """fitness(bits_full, U) -> (rank, J, metrics_copy, outputs).  Bits searched only on sw_idx."""
    D = sw_idx.size
    nbs, T = U_init.shape
    n = prm.agents
    B = np.tile(cur_bits[sw_idx].astype(float), (n, 1))
    Xs = rng.uniform(-1, 1, (n, D))          # continuous shadow positions driving the bit flips
    U = rng.uniform(-1, 1, (n, nbs, T))
    U[0] = U_init
    U[1] = 0.0
    flips = rng.random((n, D)) < prm.init_flip
    flips[:2] = False
    B[flips] = 1 - B[flips]
    mB = mU = None
    if memory is not None:
        mB = memory[0][sw_idx].astype(float)
        mU = memory[1][:, :T] if memory[1].shape[1] >= T else np.pad(memory[1], ((0, 0), (0, T - memory[1].shape[1])))
        B[2] = mB
        U[2] = mU
    full = cur_bits.copy()

    def ev(b, u):
        full[sw_idx] = b.astype(np.int8)
        return fitness(full, u)

    fit = np.empty(n); rec = [None] * n
    for i in range(n):
        rec[i] = ev(B[i], U[i]); fit[i] = rec[i][0]
    best_i = int(np.argmin(fit)); best = (fit[best_i], B[best_i].copy(), U[best_i].copy(), rec[best_i])
    stall, it_used, n_eval = 0, 0, n
    for r in range(prm.max_iter):
        it_used = r + 1
        a = 2.0 - 2.0 * r / prm.max_iter
        order = np.argsort(fit)
        L = order[:3]
        eta = prm.eta_min + (prm.eta_max - prm.eta_min) * (r / prm.max_iter) ** prm.gamma
        for i in range(n):
            # continuous GWO for set-points
            Xn = np.zeros((nbs, T)); Sn = np.zeros(D)
            for l in L:
                A = 2 * a * rng.random((nbs, T)) - a; C = 2 * rng.random((nbs, T))
                Xn += U[l] - A * np.abs(C * U[l] - U[i])
                Ab = 2 * a * rng.random(D) - a; Cb = 2 * rng.random(D)
                Sn += Xs[l] - Ab * np.abs(Cb * Xs[l] - Xs[i])
            Xn = np.clip(Xn / 3.0, -1, 1)
            Sn = Sn / 3.0
            step = Sn - Xs[i]                                       # continuous search update
            Xs[i] = Sn
            flip = rng.random(D) < np.abs(np.tanh(step))           # eq. (10): V-shaped |tanh| flip rule
            Bi = B[i].copy(); Bi[flip] = 1 - Bi[flip]
            if mB is not None:                                      # eq. (12) warm-start blending
                Xn = eta * Xn + (1 - eta) * mU
                take = rng.random(D) > eta
                Bi[take] = mB[take]
            U[i] = Xn; B[i] = Bi
            rec[i] = ev(B[i], U[i]); fit[i] = rec[i][0]; n_eval += 1
        bi = int(np.argmin(fit))
        if fit[bi] < best[0] - 1e-9:
            best = (fit[bi], B[bi].copy(), U[bi].copy(), rec[bi]); stall = 0
        else:
            stall += 1
            if stall >= prm.stagnation:
                break
    bits = cur_bits.copy(); bits[sw_idx] = best[1].astype(np.int8)
    if prm.local_search and best[0] < 1e9 and topo is not None and best[3][3] is not None:
        lf = local_fitness if local_fitness is not None else fitness
        bits, rec_ls, n_ls = branch_exchange(lf, best[3][3].astype(np.int8), best[2], best[3], sw_idx,
                                             topo, prm.ls_max_passes)
        n_eval += n_ls
        return bits, best[2], rec_ls, it_used, n_eval
    return bits, best[2], best[3], it_used, n_eval


def _tree_path(closed, fbus, tbus, nb, a, b):
    """Branch indices on the path a -> b in the forest given by `closed`; None if disconnected."""
    adj = [[] for _ in range(nb)]
    for e in np.nonzero(closed)[0]:
        adj[fbus[e]].append((tbus[e], e)); adj[tbus[e]].append((fbus[e], e))
    prev = {a: (None, None)}
    stack = [a]
    while stack:
        u = stack.pop()
        if u == b:
            break
        for v, e in adj[u]:
            if v not in prev:
                prev[v] = (u, e); stack.append(v)
    if b not in prev:
        return None
    path, u = [], b
    while prev[u][0] is not None:
        path.append(prev[u][1]); u = prev[u][0]
    return path


def branch_exchange(fitness, closed, U, rec, sw_idx, topo, max_passes):
    """Baran-Wu style branch exchange on the released (radial) topology: close one open
    switchable branch and open one switchable branch on the loop it creates (or just close it
    when it links two components). Best-improvement per open branch, repeated up to max_passes."""
    fbus, tbus, nb, avail = topo
    swset = set(int(e) for e in sw_idx)
    cur = closed.copy(); cur_rec = rec; n = 0
    for _ in range(max_passes):
        improved = False
        for e in sw_idx:
            if cur[e] or not avail[e]:
                continue
            path = _tree_path(cur, fbus, tbus, nb, fbus[e], tbus[e])
            cands = []
            if path is None:
                c = cur.copy(); c[e] = 1; cands.append(c)
            else:
                for b in path:
                    if b in swset:
                        c = cur.copy(); c[e] = 1; c[b] = 0; cands.append(c)
            best_c, best_r = None, cur_rec
            for c in cands:
                r = fitness(c, U); n += 1
                if r[0] < best_r[0] - 1e-9:
                    best_c, best_r = r[3].astype(np.int8) if r[3] is not None else c, r
            if best_c is not None:
                cur, cur_rec, improved = best_c, best_r, True
        if not improved:
            break
    return cur, cur_rec, n
