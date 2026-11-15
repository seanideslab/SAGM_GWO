"""Fig. 2: reported SAGM-GWO execution aligned with Algorithm 1 (two-lane landscape layout).

Left lane: state update, lagged-flow scoring and the GWO search loop (steps 1-5).
Right lane: branch-exchange refinement, first-action release gate, execution/fallback and
state update (steps 6-8). Sized for a full-width figure (about 7.1 x 4.8 in) so that text is
printed at its nominal size.

Run from the repository root: python figures/draw_fig2.py
Writes PNG (600 dpi), PDF and SVG to outputs/. Requires matplotlib; Liberation Sans is used
when installed (otherwise the default sans-serif font).
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import FancyBboxPatch, Polygon

FONT = "Liberation Sans" if any("Liberation Sans" in f.name for f in font_manager.fontManager.ttflist) else "DejaVu Sans"
plt.rcParams.update({
    "font.family": FONT,
    "mathtext.fontset": "custom",
    "mathtext.rm": FONT,
    "mathtext.it": f"{FONT}:italic",
    "svg.fonttype": "none",
    "pdf.fonttype": 42,
})

NAVY = "#1F3A56"      # outlines, arrows, text
BADGE = "#2F5D7C"     # step-number squares (only filled colour)
GROUP = "#F3F5F7"     # very light grey for the step-4 group
LW = 0.9
DASH = (0, (3, 2))
UNIT = 0.07           # inches per drawing unit
TFS, SFS = 9.6, 7.9   # title / body font sizes (pt)

X0, X1 = 0.0, 102.0
Y0, Y1 = -3.9, 69.5
fig = plt.figure(figsize=((X1 - X0) * UNIT, (Y1 - Y0) * UNIT))
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(X0, X1)
ax.set_ylim(Y0, Y1)
ax.axis("off")

CHECKS = []  # (text artist, container x0, x1, y0, y1) for the overflow check


def box(x0, y0, x1, y1, fill="white", ls="-", lw=LW, r=0.9):
    ax.add_patch(FancyBboxPatch((x0, y0), x1 - x0, y1 - y0,
                                boxstyle=f"round,pad=0,rounding_size={r}",
                                fc=fill, ec=NAVY, lw=lw, ls=ls, zorder=2))


def badge(x, y, lab, w=3.9, h=3.9, fs=TFS):
    ax.add_patch(FancyBboxPatch((x, y - h / 2), w, h, boxstyle="round,pad=0,rounding_size=0.55",
                                fc=BADGE, ec="none", zorder=3))
    ax.text(x + w / 2, y, lab, ha="center", va="center", color="white",
            fontsize=fs, fontweight="bold", zorder=4)


def txt(x, y, s, fs=SFS, bold=False, ha="left", within=None, **kw):
    t = ax.text(x, y, s, ha=ha, va="center", fontsize=fs, color=NAVY,
                fontweight="bold" if bold else "normal", zorder=4, **kw)
    if within:
        CHECKS.append((t, *within))
    return t


def step(x0, y0, x1, y1, num, title, lines=(), bullets=False, title_gap=3.2, line_gap=2.45):
    box(x0, y0, x1, y1)
    ty = y1 - 2.45
    badge(x0 + 1.1, ty, num)
    lim = (x0, x1, y0, y1)
    txt(x0 + 6.0, ty, title, fs=TFS, bold=True, within=lim)
    for i, s in enumerate(lines):
        yy = ty - title_gap - line_gap * i
        if bullets:
            txt(x0 + 6.4, yy, "▪", fs=6.5)
            txt(x0 + 8.2, yy, s, within=lim)
        else:
            txt(x0 + 6.0, yy, s, within=lim)


def diamond(cx, cy, hw, hh, s):
    ax.add_patch(Polygon([(cx - hw, cy), (cx, cy + hh), (cx + hw, cy), (cx, cy - hh)],
                         closed=True, fc="white", ec=NAVY, lw=LW, zorder=2))
    txt(cx, cy, s, fs=8.4, bold=True, ha="center", linespacing=1.1, within=(cx - hw, cx + hw, cy - hh, cy + hh))


def line(pts, dashed=False):
    xs, ys = zip(*pts)
    ax.plot(xs, ys, color=NAVY, lw=LW, ls=DASH if dashed else "-", zorder=1)


def arrow(pts, dashed=False):
    """Polyline with an arrowhead at the last point; the shaft keeps the requested line style."""
    line(pts, dashed)
    (xa, ya), (xb, yb) = pts[-2], pts[-1]
    d = ((xb - xa) ** 2 + (yb - ya) ** 2) ** 0.5
    back = (xb - (xb - xa) / d * 0.8, yb - (yb - ya) / d * 0.8)
    ax.annotate("", xy=(xb, yb), xytext=back,
                arrowprops=dict(arrowstyle="-|>,head_length=0.5,head_width=0.25",
                                color=NAVY, lw=LW, shrinkA=0, shrinkB=0), zorder=5)


def label(x, y, s, ha="center"):
    txt(x, y, s, fs=8.4, bold=True, ha=ha)


# ---------------------------------------------------------------- left lane: steps 1-5
LL, LR = 4.0, 45.5
LC = (LL + LR) / 2

step(LL, 59.7, LR, 66.5, "1", "Update state and forecasts",
     ["Faults, topology, voltages, SoC; $T_p$-step forecasts"])
step(LL, 47.9, LR, 57.3, "2", "Form lagged-flow scores \u2014 Eq. (9)",
     ["Released P/Q with fixed nominal V",
      "Open edges: zero prior flow; start: pre-fault state"])
step(LL, 38.7, LR, 45.5, "3", "Generate GWO candidates",
     ["Switch states and BESS horizon set-points"])
arrow([(LC, 59.7), (LC, 57.3)])
arrow([(LC, 47.9), (LC, 45.5)])

# step 4 group
G0, G1 = 16.2, 36.3
box(LL, G0, LR, G1, fill=GROUP)
badge(LL + 1.1, G1 - 2.45, "4")
txt(LL + 6.0, G1 - 2.45, "Repair topology; project BESS", fs=TFS, bold=True, within=(LL, LR, G0, G1))
SX0, SX1 = LL + 3.0, LR - 3.0
subs = [("4a", ["DFS\u2013MST radial repair"], 30.0, 1.4),
        ("4b", ["Source check: substation or GFM root", "with sufficient P, Q and stored energy"], 24.4, 2.5),
        ("4c", ["BESS reserve projection"], 18.8, 1.4)]
for lab, ls_, yc, hh in subs:
    box(SX0, yc - hh, SX1, yc + hh, r=0.6, lw=0.7)
    badge(SX0 + 0.8, yc + (1.15 if len(ls_) > 1 else 0), lab, w=4.3, h=2.3, fs=7.8)
    for i, s_ in enumerate(ls_):
        off = (len(ls_) - 1) * 1.15 - 2.3 * i
        txt(SX0 + 6.0, yc + off, s_, fs=7.9, within=(SX0, SX1, yc - hh, yc + hh))
for (_, _, ya, ha_), (_, _, yb, hb) in zip(subs[:-1], subs[1:]):
    arrow([(LC, ya - ha_), (LC, yb + hb)])
arrow([(LC, 38.7), (LC, G1)])

step(LL, 7.0, LR, 13.8, "5", "Nonlinear screening and ranking",
     ["Backward/forward sweep; V, I and energy limits"])
arrow([(LC, G0), (LC, 13.8)])

# GWO loop decision
DY, DH = 0.7, 3.9
diamond(LC, DY, 9.0, DH, "GWO search\ncomplete?")
arrow([(LC, 7.0), (LC, DY + DH)])
arrow([(LC - 9.0, DY), (1.3, DY), (1.3, 42.1), (LL, 42.1)])
label(LC - 11.0, DY + 1.5, "No")

# ---------------------------------------------------------------- right lane: steps 6-8
RL, RR = 50.0, 99.5
GX = 47.75          # gutter carrying the "Yes" path from the GWO decision

arrow([(LC + 9.0, DY), (GX, DY), (GX, 60.5), (RL, 60.5)])
label(LC + 11.0, DY + 1.5, "Yes")

step(RL, 54.5, RR, 66.5, "6", "Branch-exchange refinement",
     ["Refine a radial incumbent",
      "Up to three refinement passes",
      "Reapply steps 4\u20135 to every trial move"], bullets=True)

C7 = 60.8          # centre line of step 7 and the release decision
arrow([(GX, 51.4), (C7, 51.4)], dashed=True)
txt(C7 + 1.6, 51.4, "No radial incumbent: bypass refinement", fs=7.5, style="italic")
txt(C7 + 1.6, 47.4, "Recheck measured inputs", fs=7.5, style="italic")
DY2, DH2 = 39.2, 4.2
arrow([(C7, 54.5), (C7, DY2 + DH2)])
diamond(C7, DY2, 10.0, DH2, "First action\nadmissible?")

# step 7 (Yes) and fallback (No)
S7L, S7R = RL, 71.6
FBL, FBR = 73.6, RR
B0, B1 = 18.2, 31.6
box(S7L, B0, S7R, B1)
lim7 = (S7L, S7R, B0, B1)
badge(S7L + 1.1, B1 - 2.45, "7")
txt(S7L + 6.0, B1 - 2.45, "Execute first", fs=TFS, bold=True, within=lim7)
txt(S7L + 6.0, B1 - 5.3, "action only", fs=TFS, bold=True, within=lim7)
txt(S7L + 6.0, B1 - 8.9, "Apply switch states", within=lim7)
txt(S7L + 6.0, B1 - 11.3, "and BESS set-points", within=lim7)
arrow([(C7, DY2 - DH2), (C7, B1)])
label(C7 - 2.0, DY2 - DH2 - 1.6, "Yes", ha="right")

box(FBL, B0, FBR, B1)
lim_fb = (FBL, FBR, B0, B1)
txt(FBL + 1.4, B1 - 2.45, "Deterministic fallback", fs=TFS, bold=True, within=lim_fb)
for i, s_ in enumerate(["Keep last released switches",
                        "De-energize unsourced areas",
                        "Shed regular before critical",
                        "Book unserved energy as ENS"]):
    yy = B1 - 5.6 - 2.2 * i
    txt(FBL + 1.6, yy, "\u25AA", fs=6.5)
    txt(FBL + 3.4, yy, s_, fs=7.6, within=lim_fb)
FC = (FBL + FBR) / 2
arrow([(C7 + 10.0, DY2), (FC, DY2), (FC, B1)])
label(C7 + 12.5, DY2 + 1.5, "No", ha="left")

# merge into step 8
MY = 15.7
line([(C7, B0), (C7, MY), (FC, MY), (FC, B0)])
M8 = (C7 + FC) / 2
arrow([(M8, MY), (M8, 13.2)])
step(RL, 6.0, RR, 13.2, "8", "Update released state and advance $t$",
     ["Topology, SoC and electrical quantities"])

# next-epoch feedback: step 8 -> step 1 along the right margin and the top edge
arrow([(RR, 9.6), (101.2, 9.6), (101.2, 68.6), (LC, 68.6), (LC, 66.5)])

txt((RL + RR) / 2, 2.4, "Reported configuration: fixed objective weights; ERB disabled.",
    fs=7.6, ha="center", style="italic")

# ---------------------------------------------------------------- overflow check
fig.canvas.draw()
rend = fig.canvas.get_renderer()
inv = ax.transData.inverted()
bad = []
for t, x0, x1, y0, y1 in CHECKS:
    (bx0, by0), (bx1, by1) = inv.transform(t.get_window_extent(rend).get_points())
    if not (bx0 >= x0 + 0.3 and bx1 <= x1 - 0.4 and by0 >= y0 + 0.2 and by1 <= y1 - 0.2):
        bad.append((t.get_text(), round(bx0, 2), round(bx1, 2), round(by0, 2), round(by1, 2), (x0, x1, y0, y1)))
assert not bad, "text overflow:\n" + "\n".join(map(str, bad))

out_dir = Path(__file__).resolve().parents[1] / "outputs"
out_dir.mkdir(exist_ok=True)
out = out_dir / "Fig2_SAGM_Workflow"
for ext, kw in [(".png", dict(dpi=600)), (".pdf", {}), (".svg", {})]:
    fig.savefig(out.with_suffix(ext), facecolor="white", **kw)
print("saved", out, f"{(X1 - X0) * UNIT:.2f} x {(Y1 - Y0) * UNIT:.2f} in")
