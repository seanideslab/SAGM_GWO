"""
Numba core of the simulator: DFS/Kruskal radial repair, source (grid-forming) check,
balanced backward/forward-sweep power flow on a forest, priority-based bus-level load
shedding, DG curtailment, BESS dispatch and SoC propagation over the prediction horizon.

One call to `evaluate` scores one candidate (switch states held over the horizon +
per-step BESS set-points). The same routine with T = 1 and measured data is the plant.

Units: kW / kvar / kWh at the interface; per-unit (S_base) inside the power flow.
"""
import math

import numpy as np
from numba import njit

# metrics layout
M_PENS, M_ENS, M_ENSC, M_LOSS, M_VDI, M_NSW, M_TERM, M_RAWCYC, M_RAWADM, M_VMIN, \
    M_NSHED, M_NCURT, M_NONCONV, M_OVERLOAD, M_STRUCT_INF, M_DEEN, M_SOCVIOL, M_IMAXR = range(18)
N_METRICS = 18


@njit(cache=True)
def _find(par, i):
    while par[i] != i:
        par[i] = par[par[i]]
        i = par[i]
    return i


@njit(cache=True)
def evaluate(closed_in, u, w, do_repair, cur_state,
             fbus, tbus, r, x, imax, avail, is_gfm, lam, crit,
             pd, qd, pvav, dgcap,
             bess_bus, bess_cap, bess_p, bess_s, soc0, soc_min, soc_max, soc_res, eta,
             vmin, vmax, dt, sb, project_reserve,
             out_closed, out_served0, out_V0, out_P0, out_Q0, out_I0, out_bessp0, out_soc1, metrics, out_aux0):
    nb = pd.shape[1]
    nl = fbus.size
    T = pd.shape[0]
    nbs = bess_bus.size
    for m in range(metrics.size):
        metrics[m] = 0.0

    # ---------------------------------------------------------- raw structure
    closed = np.zeros(nl, np.int8)
    for e in range(nl):
        if avail[e] and closed_in[e]:
            closed[e] = 1
    par = np.arange(nb)
    cyc = False
    for e in range(nl):
        if closed[e]:
            a = _find(par, fbus[e]); b = _find(par, tbus[e])
            if a == b:
                cyc = True
            else:
                par[a] = b
    rootany = np.zeros(nb, np.bool_)
    for i in range(nb):
        if i == 0 or is_gfm[i]:
            rootany[_find(par, i)] = True
    adm = not cyc
    for i in range(nb):
        if pd[0, i] > 0 and not rootany[_find(par, i)]:
            adm = False
    metrics[M_RAWCYC] = 1.0 if cyc else 0.0
    metrics[M_RAWADM] = 1.0 if adm else 0.0

    # ---------------------------------------------------------- repair
    fin = np.zeros(nl, np.int8)
    par = np.arange(nb)
    if do_repair:
        order_e = np.argsort(w)
        for q in range(nl):
            e = order_e[q]
            if closed[e]:
                a = _find(par, fbus[e]); b = _find(par, tbus[e])
                if a != b:
                    par[a] = b
                    fin[e] = 1
        rooted = np.zeros(nb, np.bool_)
        for i in range(nb):
            if i == 0 or is_gfm[i]:
                rooted[_find(par, i)] = True
        changed = True
        while changed:
            changed = False
            for q in range(nl):
                e = order_e[q]
                if avail[e] and fin[e] == 0:
                    a = _find(par, fbus[e]); b = _find(par, tbus[e])
                    if a != b and rooted[a] != rooted[b]:
                        par[a] = b
                        rooted[b] = True
                        fin[e] = 1
                        changed = True
    else:
        if cyc:
            metrics[M_STRUCT_INF] = 1.0
            for e in range(nl):
                out_closed[e] = closed[e]
            return
        for e in range(nl):
            fin[e] = closed[e]
            if closed[e]:
                a = _find(par, fbus[e]); b = _find(par, tbus[e])
                par[a] = b
    for e in range(nl):
        out_closed[e] = fin[e]
    nsw = 0.0
    for e in range(nl):
        if avail[e] and fin[e] != cur_state[e]:
            nsw += 1.0
    metrics[M_NSW] = nsw

    # ---------------------------------------------------------- roots and BFS order
    comp = np.empty(nb, np.int64)
    for i in range(nb):
        comp[i] = _find(par, i)
    rootbus = -np.ones(nb, np.int64)          # indexed by comp id
    c0 = comp[0]
    rootbus[c0] = 0
    best = np.zeros(nb)
    for bi in range(nbs):
        g = bess_bus[bi]
        c = comp[g]
        if is_gfm[g] and c != c0 and bess_p[bi] > best[c]:
            best[c] = bess_p[bi]
            rootbus[c] = g
    deg = np.zeros(nb + 1, np.int64)
    for e in range(nl):
        if fin[e]:
            deg[fbus[e] + 1] += 1
            deg[tbus[e] + 1] += 1
    for i in range(nb):
        deg[i + 1] += deg[i]
    adjv = np.empty(deg[nb], np.int64)
    adje = np.empty(deg[nb], np.int64)
    fillp = deg[:nb].copy()
    for e in range(nl):
        if fin[e]:
            adjv[fillp[fbus[e]]] = tbus[e]; adje[fillp[fbus[e]]] = e; fillp[fbus[e]] += 1
            adjv[fillp[tbus[e]]] = fbus[e]; adje[fillp[tbus[e]]] = e; fillp[tbus[e]] += 1
    order = np.empty(nb, np.int64)
    parent = -np.ones(nb, np.int64)
    pbr = -np.ones(nb, np.int64)
    myroot = -np.ones(nb, np.int64)
    n_ord = 0
    for i in range(nb):
        if rootbus[comp[i]] == i:
            head = n_ord
            order[n_ord] = i; n_ord += 1
            myroot[i] = i
            while head < n_ord:
                v = order[head]; head += 1
                for p in range(deg[v], deg[v + 1]):
                    wv = adjv[p]
                    if myroot[wv] < 0:
                        myroot[wv] = i; parent[wv] = v; pbr[wv] = adje[p]
                        order[n_ord] = wv; n_ord += 1
    energized = np.zeros(nb, np.bool_)
    for q in range(n_ord):
        energized[order[q]] = True
    slack_of_root = -np.ones(nb, np.int64)    # bess index acting as slack at an island root
    bess_at = -np.ones(nb, np.int64)
    for bi in range(nbs):
        bess_at[bess_bus[bi]] = bi
        if energized[bess_bus[bi]] and myroot[bess_bus[bi]] == bess_bus[bi] and bess_bus[bi] != 0:
            slack_of_root[bess_bus[bi]] = bi

    # ---------------------------------------------------------- horizon simulation
    E = np.empty(nbs)
    for bi in range(nbs):
        E[bi] = soc0[bi] * bess_cap[bi]
    z = np.empty(nl, np.complex128)
    for e in range(nl):
        z[e] = complex(r[e], x[e])
    alive = np.zeros(nb, np.bool_)
    V = np.ones(nb, np.complex128)
    J = np.zeros(nb, np.complex128)
    S = np.zeros(nb, np.complex128)
    served = np.zeros(nb, np.bool_)
    pvo = np.zeros(nb); dgo = np.zeros(nb); qdg = np.zeros(nb)
    qvv = np.zeros(nb); vprev = np.ones(nb)
    pb = np.zeros(nbs)
    efloor = np.zeros(nbs)
    vmin_all = 9.9
    vdi_sum = 0.0
    imax_ratio = 0.0
    for k in range(T):
        vv_iter = 0
        for i in range(nb):
            qvv[i] = 0.0; vprev[i] = 1.0
            alive[i] = energized[i]
            served[i] = energized[i] and pd[k, i] > 0
            pvo[i] = pvav[k, i] if energized[i] else 0.0
            dgo[i] = dgcap[i] if energized[i] else 0.0
        # R1 reserve projection: energy that must remain after step k so that the terminal
        # reserve is still reachable by charging at full rate in the remaining steps
        for bi in range(nbs):
            floor = soc_res[bi] * bess_cap[bi] - (T - k - 1) * bess_p[bi] * eta[bi] * dt
            efloor[bi] = max(soc_min[bi] * bess_cap[bi], floor)
        for bi in range(nbs):
            g = bess_bus[bi]
            p = u[bi, k] * bess_p[bi] if energized[g] else 0.0
            dmax = (E[bi] - efloor[bi]) * eta[bi] / dt           # may be negative -> forced charging
            cmax = max(0.0, (soc_max[bi] * bess_cap[bi] - E[bi]) / (eta[bi] * dt))
            dmax = min(dmax, bess_p[bi])
            if energized[g] and project_reserve:
                if p > dmax:
                    p = dmax
            elif p > max(0.0, (E[bi] - soc_min[bi] * bess_cap[bi]) * eta[bi] / dt):
                p = max(0.0, (E[bi] - soc_min[bi] * bess_cap[bi]) * eta[bi] / dt)
            if p < -cmax:
                p = -cmax
            if p < -bess_p[bi]:
                p = -bess_p[bi]
            pb[bi] = p
        for bi in range(nbs):
            if slack_of_root[bess_bus[bi]] == bi:
                pb[bi] = 0.0
        for it in range(nb + 40):
            # Grid-connected dispatchable DG: fixed power-factor mode, pf 0.9 (Q = 0.44*P_out),
            # IEEE Std 1547-2018 constant-pf mode. Islanded DG share the island reactive demand up to
            # 0.44*P_cap; the grid-forming BESS supplies the residual. PV inverters run at unity pf.
            for i in range(nb):
                qdg[i] = 0.44 * dgo[i] if (energized[i] and myroot[i] == 0) else 0.0
            for q in range(n_ord):
                rt = order[q]
                if parent[rt] < 0 and rt != 0:
                    qload = 0.0; qcap = 0.0
                    for i in range(nb):
                        if myroot[i] == rt:
                            if served[i]:
                                qload += qd[k, i]
                            if dgo[i] > 0:
                                qcap += 0.44 * dgcap[i]
                    if qcap > 0:
                        f = min(1.0, qload / qcap)
                        for i in range(nb):
                            if myroot[i] == rt and dgo[i] > 0:
                                qdg[i] = f * 0.44 * dgcap[i]
            # Grid-connected (non-slack) BESS: IEEE 1547-2018 Cat. B-shaped Volt-VAR using the
            # converter headroom sqrt(S^2 - P^2): full injection at V<=0.92, zero in 0.98-1.02,
            # full absorption at V>=1.08, linear in between (fixed point with the power flow).
            for i in range(nb):
                qvv[i] = 0.0
                if bess_at[i] >= 0 and slack_of_root[i] != bess_at[i] and alive[i] and myroot[i] == 0:
                    bi = bess_at[i]
                    qh = math.sqrt(max(bess_s[bi] ** 2 - pb[bi] ** 2, 0.0))
                    vv = vprev[i]
                    if vv <= 0.92:
                        f = 1.0
                    elif vv < 0.98:
                        f = (0.98 - vv) / 0.06
                    elif vv <= 1.02:
                        f = 0.0
                    elif vv < 1.08:
                        f = -(vv - 1.02) / 0.06
                    else:
                        f = -1.0
                    qvv[i] = f * qh
            for i in range(nb):
                inj = pvo[i] + dgo[i]
                if bess_at[i] >= 0 and slack_of_root[i] != bess_at[i]:
                    inj += pb[bess_at[i]]
                pl = pd[k, i] if served[i] else 0.0
                ql = qd[k, i] if served[i] else 0.0
                S[i] = complex((pl - inj) / sb, (ql - qdg[i] - qvv[i]) / sb)
                V[i] = 1.0 + 0j
            conv = False
            for sweep in range(40):
                for q in range(n_ord):
                    i = order[q]
                    J[i] = (S[i] / V[i]).conjugate()
                for q in range(n_ord - 1, -1, -1):
                    i = order[q]
                    if parent[i] >= 0:
                        J[parent[i]] += J[i]
                dv = 0.0
                for q in range(n_ord):
                    i = order[q]
                    if parent[i] >= 0:
                        vn = V[parent[i]] - z[pbr[i]] * J[i]
                        d = abs(vn - V[i])
                        if d > dv:
                            dv = d
                        V[i] = vn
                if dv < 1e-6:
                    conv = True
                    break
            if not conv:
                metrics[M_NONCONV] += 1.0
            # Volt-VAR fixed point: re-solve with updated reactive set-points (max 6 passes)
            dvv = 0.0
            for q in range(n_ord):
                i = order[q]
                d = abs(abs(V[i]) - vprev[i])
                if d > dvv:
                    dvv = d
                vprev[i] = abs(V[i])
            if conv and dvv > 1e-4 and vv_iter < 6:
                vv_iter += 1
                continue
            # ---- detect the most urgent violation
            vtype = 0      # 1 island deficit, 2 island surplus, 3 under-voltage, 4 over-voltage, 5 thermal
            vbus = -1
            vamount = 0.0
            for q in range(n_ord):
                i = order[q]
                if parent[i] < 0 and i != 0:
                    bi = slack_of_root[i]
                    ps = (V[i] * J[i].conjugate()).real * sb      # kW the GFM BESS must supply
                    qs = (V[i] * J[i].conjugate()).imag * sb
                    if project_reserve:
                        dmax = min(bess_p[bi], (E[bi] - efloor[bi]) * eta[bi] / dt)
                    else:
                        dmax = max(0.0, min(bess_p[bi], (E[bi] - soc_min[bi] * bess_cap[bi]) * eta[bi] / dt))
                    cmax = max(0.0, min(bess_p[bi], (soc_max[bi] * bess_cap[bi] - E[bi]) / (eta[bi] * dt)))
                    pcap = math.sqrt(max(bess_s[bi] ** 2 - qs * qs, 0.0))   # P headroom left by Q
                    if ps > min(dmax, pcap) + 1e-9:
                        vtype = 1; vbus = i; vamount = ps - min(dmax, pcap)
                        break
                    if ps < -min(cmax, pcap) - 1e-9:
                        if pcap <= 1e-9:
                            vtype = 1; vbus = i; vamount = 0.0      # reactive demand alone exceeds rating
                        else:
                            vtype = 2; vbus = i; vamount = -min(cmax, pcap) - ps
                        break
            if vtype == 0:
                worst = 9.9
                for q in range(n_ord):
                    i = order[q]
                    a = abs(V[i])
                    if (not conv) or a < vmin - 1e-9:
                        if a < worst:
                            worst = a; vtype = 3; vbus = i
                if vtype == 0:
                    for q in range(n_ord):
                        i = order[q]
                        if abs(V[i]) > vmax + 1e-9:
                            vtype = 4; vbus = i
                            break
            if vtype == 0:
                worstr = 1.0
                for q in range(n_ord):
                    i = order[q]
                    if parent[i] >= 0:
                        ratio = abs(J[i]) / imax[pbr[i]]
                        if ratio > worstr + 1e-9:
                            worstr = ratio; vtype = 5; vbus = i
            if vtype == 0:
                break
            # ---- corrective action
            if vtype == 2 or vtype == 4:
                rt = myroot[vbus]
                big = -1; bigv = 0.0
                for i in range(nb):
                    if myroot[i] == rt and dgo[i] > bigv:
                        bigv = dgo[i]; big = i
                if big >= 0:
                    cut = vamount if vtype == 2 else 0.3 * dgo[big]
                    dgo[big] = max(0.0, dgo[big] - max(cut, 1.0))
                else:
                    for i in range(nb):
                        if myroot[i] == rt and pvo[i] > bigv:
                            bigv = pvo[i]; big = i
                    if big >= 0:
                        cut = vamount if vtype == 2 else 0.3 * pvo[big]
                        pvo[big] = max(0.0, pvo[big] - max(cut, 1.0))
                metrics[M_NCURT] += 1.0
                if big < 0:
                    # nothing left to curtail: stop non-slack BESS discharge in this island
                    done = False
                    for i in range(nb):
                        if myroot[i] == rt and bess_at[i] >= 0 and slack_of_root[i] != bess_at[i] and pb[bess_at[i]] > 0:
                            pb[bess_at[i]] = 0.0
                            done = True
                    if not done:
                        break
                continue
            # shedding candidates: same island (1,3) or downstream subtree of overloaded branch (5)
            cand = -1
            best_l = 1e18; best_key = 1e18
            for i in range(nb):
                if not served[i]:
                    continue
                if vtype == 5:
                    j = i
                    inside = False
                    while j >= 0:
                        if j == vbus:
                            inside = True
                            break
                        j = parent[j]
                    if not inside:
                        continue
                else:
                    if myroot[i] != myroot[vbus]:
                        continue
                if vtype == 1:
                    key = pd[k, i] if pd[k, i] >= vamount else 1e9 - pd[k, i]
                else:
                    key = abs(V[i])
                if lam[i] < best_l - 1e-12 or (abs(lam[i] - best_l) <= 1e-12 and key < best_key):
                    best_l = lam[i]; best_key = key; cand = i
            if cand < 0:
                # cannot fix by shedding: de-energize the whole component
                rt = myroot[vbus]
                for i in range(nb):
                    if myroot[i] == rt:
                        served[i] = False; pvo[i] = 0.0; dgo[i] = 0.0; alive[i] = False
                        if bess_at[i] >= 0:
                            pb[bess_at[i]] = 0.0
                metrics[M_DEEN] += 1.0
                continue
            served[cand] = False
            metrics[M_NSHED] += 1.0
        # ---- step accounting
        ens = 0.0; pens = 0.0; ensc = 0.0; loss = 0.0; vd = 0.0; nen = 0
        for i in range(nb):
            if pd[k, i] > 0 and not served[i]:
                ens += pd[k, i] * dt
                pens += lam[i] * pd[k, i] * dt
                if crit[i]:
                    ensc += pd[k, i] * dt
        for q in range(n_ord):
            i = order[q]
            if alive[i]:
                a = abs(V[i])
                vd += abs(1.0 - a); nen += 1
                if a < vmin_all:
                    vmin_all = a
            if parent[i] >= 0:
                loss += r[pbr[i]] * abs(J[i]) ** 2 * sb * dt
                ratio = abs(J[i]) / imax[pbr[i]]
                if ratio > imax_ratio:
                    imax_ratio = ratio
                if ratio > 1.0 + 1e-6:
                    metrics[M_OVERLOAD] += 1.0
        metrics[M_ENS] += ens; metrics[M_PENS] += pens; metrics[M_ENSC] += ensc; metrics[M_LOSS] += loss
        vdi_sum += vd / nen if nen > 0 else 0.0
        # realised BESS powers (slack from power flow) and SoC update
        for bi in range(nbs):
            g = bess_bus[bi]
            if slack_of_root[g] == bi and alive[g]:
                pb[bi] = (V[g] * J[g].conjugate()).real * sb
            p = pb[bi]
            if p >= 0:
                E[bi] -= p / eta[bi] * dt
            else:
                E[bi] += -p * eta[bi] * dt
            if E[bi] < soc_min[bi] * bess_cap[bi] - 1e-6 or E[bi] > soc_max[bi] * bess_cap[bi] + 1e-6:
                metrics[M_SOCVIOL] += 1.0
            E[bi] = min(max(E[bi], 0.0), bess_cap[bi])
        if k == 0:
            for i in range(nb):
                out_served0[i] = 1 if served[i] else 0
                out_V0[i] = abs(V[i]) if alive[i] else 0.0
            for e in range(nl):
                out_P0[e] = 0.0; out_Q0[e] = 0.0; out_I0[e] = 0.0
            for q in range(n_ord):
                i = order[q]
                if parent[i] >= 0:
                    sflow = V[parent[i]] * J[i].conjugate() * sb
                    out_P0[pbr[i]] = sflow.real; out_Q0[pbr[i]] = sflow.imag
                    out_I0[pbr[i]] = abs(J[i])
            for bi in range(nbs):
                out_bessp0[bi] = pb[bi]
                out_soc1[bi] = E[bi] / bess_cap[bi]
            for i in range(nb):
                out_aux0[i, 0] = pvo[i] if alive[i] else 0.0
                out_aux0[i, 1] = dgo[i] if alive[i] else 0.0
                out_aux0[i, 2] = qdg[i] if alive[i] else 0.0
                out_aux0[i, 3] = 0.0
                out_aux0[i, 4] = qvv[i] if alive[i] else 0.0
                out_aux0[i, 5] = myroot[i] if alive[i] else -1
            for bi in range(nbs):
                g = bess_bus[bi]
                if alive[g]:
                    out_aux0[g, 3] = pb[bi]
                    if slack_of_root[g] == bi:
                        out_aux0[g, 4] = 1e9      # slack flag (Q set by the island)
    term = 0.0
    for bi in range(nbs):
        d = soc_res[bi] * bess_cap[bi] - E[bi]
        if d > 0:
            term += d
    metrics[M_TERM] = term
    metrics[M_VDI] = vdi_sum / T
    metrics[M_VMIN] = vmin_all
    metrics[M_IMAXR] = imax_ratio
