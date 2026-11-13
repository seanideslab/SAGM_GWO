"""Case data, frozen scenario (truth trajectories) and forecast generation."""
from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
KMAX = 12   # longest horizon supported


def config_hash(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


@dataclass
class Net:
    cfg: dict
    cfg_hash: str
    nb: int
    nl: int
    fbus: np.ndarray
    tbus: np.ndarray
    r: np.ndarray
    x: np.ndarray
    imax: np.ndarray
    init_state: np.ndarray
    switchable: np.ndarray
    branch_label: list
    pd_base: np.ndarray
    qd_base: np.ndarray
    lam: np.ndarray
    crit: np.ndarray
    is_gfm: np.ndarray
    pv_cap: np.ndarray
    dg_cap: np.ndarray
    bess_bus: np.ndarray
    bess_cap: np.ndarray
    bess_p: np.ndarray
    bess_s: np.ndarray
    soc_min: np.ndarray
    soc_max: np.ndarray
    soc_res: np.ndarray
    eta: np.ndarray
    soc0: np.ndarray

    def branch_index(self, label: str) -> int:
        a, b = (int(v) - 1 for v in label.split("-"))
        for e in range(self.nl):
            if {self.fbus[e], self.tbus[e]} == {a, b}:
                return e
        raise KeyError(label)


def load_net(cfg_path: Path, overrides: dict | None = None) -> Net:
    cfg = json.loads(Path(cfg_path).read_text())
    for k, v in (overrides or {}).items():          # dotted keys, e.g. "bess.soc0"
        d = cfg
        ks = k.split(".")
        for kk in ks[:-1]:
            d = d[kk]
        d[ks[-1]] = v
    bus = pd.read_csv(DATA / cfg.get("bus_file", "ieee33_bus_data.csv")).sort_values("bus_id")
    br = pd.read_csv(DATA / cfg.get("branch_file", "ieee33_branch_data.csv")).sort_values("branch_id")
    zb = cfg["v_base_kv"] ** 2 / (cfg["s_base_kva"] / 1000.0)
    ib = cfg["s_base_kva"] * 1000.0 / (math.sqrt(3) * cfg["v_base_kv"] * 1000.0)
    main = set(cfg["main_trunk_branch_ids"])
    imax = np.array([(cfg["thermal_main_amp"] if b in main else cfg["thermal_lateral_amp"]) / ib for b in br.branch_id])
    nb = len(bus)
    crit = np.zeros(nb, np.bool_)
    crit[np.array(cfg["critical_buses"]) - 1] = True
    lam = np.where(crit, cfg["lambda_critical"], cfg["lambda_regular"]).astype(float)
    pv_cap = np.zeros(nb); dg_cap = np.zeros(nb)
    for b, c in cfg["pv"].items():
        pv_cap[int(b) - 1] = c
    for b, c in cfg["dispatchable_dg"].items():
        dg_cap[int(b) - 1] = c
    bc = cfg["bess"]
    bb = np.array(bc["buses"]) - 1
    nbs = len(bb)
    is_gfm = np.zeros(nb, np.bool_)
    is_gfm[np.array(bc["grid_forming_buses"]) - 1] = True
    sw = np.ones(len(br), np.bool_) if cfg["all_lines_switchable"] else br.switchable.to_numpy().astype(bool)
    return Net(
        cfg=cfg, cfg_hash=config_hash(cfg_path) + ("" if not overrides else "+ovr"),
        nb=nb, nl=len(br),
        fbus=(br.from_bus.to_numpy() - 1).astype(np.int64), tbus=(br.to_bus.to_numpy() - 1).astype(np.int64),
        r=br.R.to_numpy() / zb, x=br.X.to_numpy() / zb, imax=imax,
        init_state=br.status.to_numpy().astype(np.int8), switchable=sw,
        branch_label=[f"{a}-{b}" for a, b in zip(br.from_bus, br.to_bus)],
        pd_base=bus.P_load.to_numpy(float), qd_base=bus.Q_load.to_numpy(float),
        lam=lam, crit=crit, is_gfm=is_gfm, pv_cap=pv_cap, dg_cap=dg_cap,
        bess_bus=bb.astype(np.int64), bess_cap=np.full(nbs, bc["energy_kwh"]), bess_p=np.full(nbs, bc["p_kw"]),
        bess_s=np.full(nbs, bc["s_kva"]), soc_min=np.full(nbs, bc["soc_min"]), soc_max=np.full(nbs, bc["soc_max"]),
        soc_res=np.full(nbs, bc["soc_reserve"]), eta=np.full(nbs, bc["eta"]), soc0=np.full(nbs, bc["soc0"]),
    )


def pv_shape(hour: float) -> float:
    if 6 <= hour < 18:
        return math.sin(math.pi * (hour + 0.5 - 6) / 12)
    return 0.0


@dataclass
class Truth:
    pd: np.ndarray        # (W+KMAX, nb)
    qd: np.ndarray
    pv: np.ndarray        # available PV
    avail: np.ndarray     # (W+KMAX, nl) bool, branch not faulted
    load_mult: np.ndarray # event multipliers (persisted in forecasts)
    pv_mult: np.ndarray
    fault_epochs: list


def build_truth(net: Net) -> Truth:
    c = net.cfg
    W = c["window_steps"]
    n = W + KMAX
    lm = np.ones((n, net.nb)); pm = np.ones((n, net.nb)); av = np.ones((n, net.nl), np.bool_)
    fault_epochs = []
    for ev in sorted(c["events"], key=lambda e: e["t"]):
        t0 = ev["t"]
        if ev["type"] == "fault":
            av[t0:, net.branch_index(ev["branch"])] = False
            fault_epochs.append(t0)
        elif ev["type"] == "load_mult":
            lm[t0:, np.array(ev["buses"]) - 1] = ev["mult"]
        elif ev["type"] == "pv_mult":
            pm[t0:, np.array(ev["buses"]) - 1] = ev["mult"]
    prof = np.array(c["load_profile"])
    hours = [(c["start_hour"] + t) % 24 for t in range(n)]
    lf = np.array([prof[h] for h in hours])
    pvs = np.array([pv_shape(h) for h in hours])
    pdm = net.pd_base[None, :] * lf[:, None] * lm
    qdm = net.qd_base[None, :] * lf[:, None] * lm
    pv = net.pv_cap[None, :] * pvs[:, None] * pm
    return Truth(pd=pdm, qd=qdm, pv=pv, avail=av, load_mult=lm, pv_mult=pm, fault_epochs=fault_epochs)


def noise(seed: int, W: int, error_pct: float, model: str = "white", rho: float = 0.8, bias: float = 0.0):
    """Feeder-wide multiplicative forecast errors eps[t, k] for load and PV (k = lead time).
    model: 'white' | 'ar1' (AR(1) over lead time) ; bias: systematic offset added to both (e.g. 0.10)."""
    rng = np.random.default_rng([seed, 7919])
    sig = error_pct / 100.0 / 1.96
    zl = rng.standard_normal((W, KMAX)); zp = rng.standard_normal((W, KMAX))
    if model == "white":
        return sig * zl + bias, sig * zp + bias
    el = np.empty_like(zl); ep = np.empty_like(zp)
    el[:, 0] = zl[:, 0]; ep[:, 0] = zp[:, 0]
    a = math.sqrt(1 - rho ** 2)
    for k in range(1, KMAX):
        el[:, k] = rho * el[:, k - 1] + a * zl[:, k]
        ep[:, k] = rho * ep[:, k - 1] + a * zp[:, k]
    return sig * el + bias, sig * ep + bias


def forecast(net: Net, tr: Truth, t: int, T: int, eps_l: np.ndarray, eps_p: np.ndarray):
    """Step 0 = measurement at t; steps k>=1 = nominal profile x persisted event multipliers x (1+eps)."""
    c = net.cfg
    prof = np.array(c["load_profile"])
    pd_f = np.empty((T, net.nb)); qd_f = np.empty((T, net.nb)); pv_f = np.empty((T, net.nb))
    pd_f[0] = tr.pd[t]; qd_f[0] = tr.qd[t]; pv_f[0] = tr.pv[t]
    for k in range(1, T):
        h = (c["start_hour"] + t + k) % 24
        f_l = prof[h] * tr.load_mult[t] * (1 + eps_l[t, k])
        pd_f[k] = net.pd_base * f_l
        qd_f[k] = net.qd_base * f_l
        pv_f[k] = np.maximum(0.0, net.pv_cap * pv_shape(h) * tr.pv_mult[t] * (1 + eps_p[t, k]))
    return pd_f, qd_f, pv_f
