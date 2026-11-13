"""Python wrapper around the numba evaluator."""
from __future__ import annotations

import numpy as np

from . import core
from .network import Net


class Evaluator:
    def __init__(self, net: Net):
        self.net = net
        n = net
        self.out_closed = np.zeros(n.nl, np.int8)
        self.out_served0 = np.zeros(n.nb, np.int8)
        self.out_V0 = np.zeros(n.nb)
        self.out_P0 = np.zeros(n.nl); self.out_Q0 = np.zeros(n.nl); self.out_I0 = np.zeros(n.nl)
        self.out_bessp0 = np.zeros(n.bess_bus.size)
        self.out_soc1 = np.zeros(n.bess_bus.size)
        self.metrics = np.zeros(core.N_METRICS)
        self.out_aux0 = np.zeros((n.nb, 6))
        self.n_calls = 0

    def __call__(self, closed, u, w, repair, cur_state, avail, pd, qd, pv, soc, dg_on=True):
        n = self.net
        self.n_calls += 1
        core.evaluate(closed.astype(np.int8), np.ascontiguousarray(u, dtype=np.float64), w.astype(np.float64),
                      bool(repair), cur_state.astype(np.int8),
                      n.fbus, n.tbus, n.r, n.x, n.imax, avail.astype(np.bool_), n.is_gfm, n.lam, n.crit,
                      np.ascontiguousarray(pd), np.ascontiguousarray(qd), np.ascontiguousarray(pv),
                      n.dg_cap if dg_on else np.zeros(n.nb),
                      n.bess_bus, n.bess_cap, n.bess_p, n.bess_s, np.asarray(soc, float), n.soc_min, n.soc_max,
                      n.soc_res, n.eta, n.cfg["v_min"], n.cfg["v_max"], n.cfg["dt_h"], n.cfg["s_base_kva"],
                      bool(n.cfg["optimizer"].get("reserve_projection", False)),
                      self.out_closed, self.out_served0, self.out_V0, self.out_P0, self.out_Q0, self.out_I0,
                      self.out_bessp0, self.out_soc1, self.metrics, self.out_aux0)
        return self.metrics
