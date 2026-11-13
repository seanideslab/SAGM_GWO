#!/usr/bin/env python3
"""Validation tests for the R1 simulator. Run: python tests/test_validation.py  (or pytest)."""
import dataclasses
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sim import core                              # noqa: E402
from sim.evaluator import Evaluator               # noqa: E402
from sim.network import build_truth, load_net     # noqa: E402


def _no_der(net, vmin=0.85):
    e = np.zeros(0)
    n = dataclasses.replace(net, bess_bus=np.zeros(0, np.int64), bess_cap=e, bess_p=e, bess_s=e, soc_min=e,
                            soc_max=e, soc_res=e, eta=e, soc0=e)
    n.cfg = dict(net.cfg); n.cfg["v_min"] = vmin
    return n


def _pf(net, closed):
    ev = Evaluator(net)
    m = ev(closed, np.zeros((0, 1)), np.zeros(net.nl), True, net.init_state, np.ones(net.nl, bool),
           net.pd_base[None], net.qd_base[None], np.zeros((1, net.nb)), np.zeros(0), dg_on=False)
    return m


def test_ieee33_base_loss():
    n = _no_der(load_net(ROOT / "config/ieee33_main.json"))
    m = _pf(n, n.init_state)
    assert abs(m[core.M_LOSS] - 210.998) < 0.01 and abs(m[core.M_VMIN] - 0.9038) < 1e-3 and m[core.M_ENS] == 0


def test_ieee33_baran_wu_optimum():
    n = _no_der(load_net(ROOT / "config/ieee33_main.json"))
    c = np.ones(n.nl, np.int8); c[[6, 8, 13, 31, 36]] = 0
    assert abs(_pf(n, c)[core.M_LOSS] - 139.551) < 0.01


def test_ieee69_base_loss():
    n = _no_der(load_net(ROOT / "config/ieee69_timing.json"))
    m = _pf(n, n.init_state)
    assert abs(m[core.M_LOSS] - 224.991) < 0.01 and abs(m[core.M_VMIN] - 0.9092) < 1e-3


def test_repair_makes_radial_and_no_repair_rejects_cycles():
    n = _no_der(load_net(ROOT / "config/ieee33_main.json"))
    ev = Evaluator(n)
    allc = np.ones(n.nl, np.int8)
    args = (np.zeros((0, 1)), np.random.default_rng(0).random(n.nl))
    m = ev(allc, *args, True, n.init_state, np.ones(n.nl, bool), n.pd_base[None], n.qd_base[None],
           np.zeros((1, n.nb)), np.zeros(0), dg_on=False)
    assert m[core.M_RAWCYC] == 1 and ev.out_closed.sum() == n.nb - 1
    m = ev(allc, *args, False, n.init_state, np.ones(n.nl, bool), n.pd_base[None], n.qd_base[None],
           np.zeros((1, n.nb)), np.zeros(0), dg_on=False)
    assert m[core.M_STRUCT_INF] == 1


def test_voltvar_raises_voltage():
    net = load_net(ROOT / "config/ieee33_main.json"); net.cfg["v_min"] = 0.85
    ev = Evaluator(net)
    kw = dict(dg_on=False)
    base = (np.zeros((net.bess_bus.size, 1)), np.zeros(net.nl), True, net.init_state, np.ones(net.nl, bool),
            net.pd_base[None], net.qd_base[None], np.zeros((1, net.nb)), net.soc0)
    v_with = ev(net.init_state, *base, **kw)[core.M_VMIN]
    v_without = _pf(_no_der(net), net.init_state)[core.M_VMIN]
    assert v_with > v_without + 0.005


def test_rda_identity():
    assert abs(100 * 6.27 / 4608 - 0.1360677) < 1e-4


def test_events():
    for name, br in [("ieee33_main", "3-4"), ("ieee33_severe", "2-3"), ("ieee33_f2_25-29", "25-29")]:
        net = load_net(ROOT / f"config/{name}.json"); tr = build_truth(net)
        e = net.branch_index(br)
        assert tr.avail[3, e] and not tr.avail[4, e]


if __name__ == "__main__":
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f(); print("PASS", k)
