#!/usr/bin/env python3
"""
feasibility_gate.py -- Island admissibility check and safe fallback for one decision epoch.

Reference implementation of the release gate described in Sec. IV-A/IV-E of the revised
manuscript. It is deliberately independent of the search kernel so it can be called on
any candidate topology produced by SAGM-GWO (or by any other optimizer).

Gate order for a candidate (closed-branch set + dispatch):
  G1  structure     : energized graph is a forest (no cycles), DFS O(|N|+|E|)
  G2  source        : every energized component contains exactly one admissible root:
                      the substation, or a grid-forming (GFM) BESS (IEEE Std 1547.4-2011
                      intentional-island guidance). Components that contain only
                      grid-following DG/PV are NOT admissible and are de-energized.
  G3  adequacy      : per island, available P from DG + BESS (SoC-, rating- and
                      terminal-reserve-limited) >= served load * (1 + loss margin)
  G4  electrical    : nonlinear power flow converges and V/I limits hold (delegated to
                      the caller's power-flow routine)
  G5  reserve       : projected SoC at t+Tp >= E_res (delegated to the horizon simulator)

Fallback when no candidate passes G1-G5 within the iteration budget:
  F1  keep the last released switch states of all non-faulted sections, open the
      switches that isolate the faulted section(s);
  F2  apply G2 to the resulting components; de-energize components without a root;
  F3  inside each island, shed load in ascending priority (regular before critical,
      larger blocks first within a class) until G3 holds; partial shedding is allowed
      only at buses flagged as sheddable-in-steps (default: whole-bus shedding);
  F4  every shed or de-energized load is booked as 100% ENS for that epoch.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class EpochState:
    load_kw: dict[int, float]
    critical: set[int]
    dg_avail_kw: dict[int, float]                 # grid-following DG/PV available this epoch
    bess_kwh: dict[int, float]                    # capacity
    bess_soc: dict[int, float]                    # current SoC (0-1)
    gfm_bess: set[int]                            # buses with grid-forming BESS
    bess_p_kw: float = 60.0
    soc_reserve: float = 0.20
    eta_dis: float = 0.95
    dt_h: float = 1.0
    loss_margin: float = 0.05
    substation: int = 1
    substation_alive: bool = True


@dataclass
class GateResult:
    admissible: bool
    islands: list[dict] = field(default_factory=list)
    reason: str = ""


def components(buses: list[int], closed_edges: list[tuple[int, int]]) -> tuple[list[set[int]], bool]:
    """Connected components and cycle flag via iterative DFS."""
    adj = {b: [] for b in buses}
    for u, v in closed_edges:
        adj[u].append(v)
        adj[v].append(u)
    seen, comps = set(), []
    for s in buses:
        if s in seen:
            continue
        comp, stack = set(), [s]
        seen.add(s)
        while stack:
            u = stack.pop()
            comp.add(u)
            for w in adj[u]:
                if w not in seen:
                    seen.add(w)
                    stack.append(w)
        comps.append(comp)
    # a simple graph component is a tree iff |E_c| = |N_c| - 1
    cyclic = any(sum(1 for u, v in closed_edges if u in c) > len(c) - 1 for c in comps)
    return comps, cyclic


def bess_available_kw(st: EpochState, b: int) -> float:
    """Available discharge power: min(converter rating, energy above terminal reserve)."""
    e_now = st.bess_soc[b] * st.bess_kwh[b]
    e_res = st.soc_reserve * st.bess_kwh[b]
    return max(0.0, min(st.bess_p_kw, (e_now - e_res) * st.eta_dis / st.dt_h))


def check(st: EpochState, buses: list[int], closed_edges: list[tuple[int, int]],
          served: dict[int, float] | None = None) -> GateResult:
    served = served if served is not None else dict(st.load_kw)
    comps, cyclic = components(buses, closed_edges)
    if cyclic:
        return GateResult(False, reason="G1: energized graph contains a cycle")
    islands = []
    for c in comps:
        has_sub = st.substation in c and st.substation_alive
        gfm = sorted(c & st.gfm_bess)
        root = "substation" if has_sub else ("GFM-BESS@" + "+".join(map(str, gfm)) if gfm else None)
        load = sum(served.get(b, 0.0) for b in c)
        supply = float("inf") if has_sub else (
            sum(st.dg_avail_kw.get(b, 0.0) for b in c) + sum(bess_available_kw(st, b) for b in c & set(st.bess_kwh)))
        if has_sub and len(gfm) > 0:
            root += " (+GFM in grid-following mode)"
        islands.append({"buses": sorted(c), "root": root, "load_kw": load, "supply_kw": supply,
                        "adequate": root is not None and supply >= load * (1 + st.loss_margin) - 1e-9,
                        "n_gfm": len(gfm)})
    bad = [i for i in islands if i["load_kw"] > 0 and (i["root"] is None or not i["adequate"])]
    if bad:
        why = "G2: island without grid-forming source" if any(i["root"] is None for i in bad) else "G3: island supply inadequate"
        return GateResult(False, islands, why)
    return GateResult(True, islands, "ok")


def fallback(st: EpochState, buses: list[int], closed_edges: list[tuple[int, int]]) -> dict:
    """F1-F4: keep topology, drop rootless components, shed by priority until adequate."""
    comps, cyclic = components(buses, closed_edges)
    if cyclic:
        raise ValueError("fallback requires the last released (radial) topology")
    served = dict(st.load_kw)
    log = []
    for c in comps:
        has_sub = st.substation in c and st.substation_alive
        gfm = c & st.gfm_bess
        if not has_sub and not gfm:
            for b in c:
                if served.get(b, 0) > 0:
                    log.append((b, served[b], "F2 de-energized: no grid-forming source"))
                    served[b] = 0.0
            continue
        if has_sub:
            continue
        supply = sum(st.dg_avail_kw.get(b, 0.0) for b in c) + sum(bess_available_kw(st, b) for b in c & set(st.bess_kwh))
        order = sorted((b for b in c if served.get(b, 0) > 0),
                       key=lambda b: (b in st.critical, -served[b]))   # regular first, larger first
        load = sum(served[b] for b in c)
        for b in order:
            if supply >= load * (1 + st.loss_margin):
                break
            log.append((b, served[b], "F3 shed " + ("critical" if b in st.critical else "regular")))
            load -= served[b]
            served[b] = 0.0
    ens = sum(st.load_kw[b] - served[b] for b in st.load_kw) * st.dt_h
    ens_c = sum(st.load_kw[b] - served[b] for b in st.load_kw if b in st.critical) * st.dt_h
    return {"served_kw": served, "ens_kwh": ens, "ens_critical_kwh": ens_c, "actions": log}


def _demo():
    """IEEE 33-bus, F1 (6-7) + F2 (2-3) faulted and isolated, no tie closed:
    shows which components are rootless and how the fallback sheds load."""
    from pathlib import Path
    root = Path(__file__).resolve().parent / "data"
    bus = pd.read_csv(root / "ieee33_bus_data.csv")
    br = pd.read_csv(root / "ieee33_branch_data.csv")
    faulted = {(6, 7), (2, 3)}
    closed = [(int(a), int(b)) for a, b, s in zip(br.from_bus, br.to_bus, br.status)
              if s == 1 and (a, b) not in faulted]
    st = EpochState(
        load_kw=dict(zip(bus.bus_id, bus.P_load.astype(float))),
        critical=set(bus.bus_id[bus.critical_flag == 1]),
        dg_avail_kw={int(b): float(c) for b, c in zip(bus.bus_id, bus.dg_capacity) if c > 0},
        bess_kwh={int(b): float(c) for b, c in zip(bus.bus_id, bus.bess_capacity) if c > 0},
        bess_soc={int(b): 0.6 for b, c in zip(bus.bus_id, bus.bess_capacity) if c > 0},
        gfm_bess={8, 18, 22, 26, 33},  # merged R1/R2 assumption: all five BESS grid-forming-capable
    )
    g = check(st, bus.bus_id.tolist(), closed)
    print("gate:", g.admissible, "-", g.reason)
    for i in g.islands:
        print(f"  island root={i['root']!s:<40} buses={len(i['buses']):>2} load={i['load_kw']:7.1f} kW "
              f"supply={i['supply_kw']:>7} adequate={i['adequate']}")
    fb = fallback(st, bus.bus_id.tolist(), closed)
    print(f"fallback ENS this epoch = {fb['ens_kwh']:.1f} kWh (critical {fb['ens_critical_kwh']:.1f} kWh), "
          f"{len(fb['actions'])} shedding actions")
    for a in fb["actions"][:8]:
        print("  ", a)


if __name__ == "__main__":
    _demo()
