"""
Animation of the simulated two-year release history (same seed and designs as run_all.py).
    python scripts/make_monitoring_video.py results/monitoring.mp4 results/monitoring_last_frame.png
Needs FFmpeg on the PATH.
"""
import sys, os, numpy as np
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "src"))
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, FFMpegWriter
from avmon.rates import OUTCOMES, LEADING_INDICATOR, FLEET_MILES_PER_MONTH
from avmon.monitor import PoissonCUSUM, calibrate_cusum
import pandas as pd
t3 = pd.read_csv(os.path.join(ROOT, "results", "table3_cusum_design.csv"))
H = dict(zip(t3.metric, t3.h)); M0 = dict(zip(t3.metric, t3.expected_weekly_count))
names = list(t3.metric)
gen_order = list(names)
order = ["Leading indicator (assumed)", "All reported crashes", "Airbag deployment", "Any-injury crashes", "Serious injury or worse"]
names = [n for n in order if n in names]
COL = {"All reported crashes": "#2A78D6", "Any-injury crashes": "#EB6834", "Airbag deployment": "#7A4FB0",
       "Serious injury or worse": "#B3261E", "Leading indicator (assumed)": "#1F9D74"}
rng = np.random.default_rng(2026)
W, TR, R = 104, 60, 1.5
S = {}; AL = {}
for n in gen_order:
    m0, h = M0[n], H[n]
    x = rng.poisson(m0 * np.where(np.arange(1, W + 1) >= TR, R, 1.0))
    s, al = PoissonCUSUM(m0, 0.25, h).path(x, reset=True); S[n] = np.minimum(s / h, 1.0); AL[n] = al
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 15})
fig, axes = plt.subplots(len(names), 1, figsize=(16, 9), dpi=100, sharex=True)
fig.patch.set_facecolor("#F6F5F1")
fig.subplots_adjust(left=0.06, right=0.78, top=0.85, bottom=0.08, hspace=0.35)
title = fig.text(0.06, 0.94, "", fontsize=24, weight="bold", color="#14213D")
sub = fig.text(0.06, 0.905, "Poisson CUSUM per metric, weekly fleet counts. Alarm when the statistic reaches the dashed line; chart resets after each alarm.", fontsize=14, color="#4A5568")
lines, dots, labs, vl = [], [], [], []
for ax, n in zip(axes, names):
    ax.set_facecolor("#FFFFFC"); ax.set_xlim(1, W); ax.set_ylim(0, 1.15); ax.set_yticks([0, 1]); ax.set_yticklabels(["0", "h"])
    ax.axhline(1, color="#B3261E", ls="--", lw=1)
    for sp in ("top", "right"): ax.spines[sp].set_visible(False)
    ln, = ax.plot([], [], color=COL[n], lw=2.4); lines.append(ln)
    d, = ax.plot([], [], "v", ms=13, color="#B3261E"); dots.append(d)
    g, = ax.plot([], [], "v", ms=13, color="#9AA3AF"); dots.append(g)
    ax.text(1.5, 1.22, n, transform=ax.transData, fontsize=15, weight="bold", color=COL[n])
    labs.append(fig.text(0.80, 0, "", fontsize=16, color="#14213D", va="center"))
    vl.append(ax.axvline(TR, color="#5B6472", lw=1.5, alpha=0))
axes[-1].set_xlabel("Week")
FR = W + 30
def upd(f):
    t = min(f + 1, W)
    title.set_text(f"Week {t}" + ("   ·   a +50% regression entered at week 60" if t >= TR else "   ·   no regression yet"))
    for i, (ax, n) in enumerate(zip(axes, names)):
        lines[i].set_data(np.arange(1, t + 1), S[n][:t])
        tr = [a for a in AL[n] if TR <= a <= t]; fa = [a for a in AL[n] if a < TR and a <= t]
        dots[2*i].set_data(tr, [1.08]*len(tr)); dots[2*i+1].set_data(fa, [1.08]*len(fa))
        vl[i].set_alpha(0.9 if t >= TR else 0)
        y = ax.get_position(); yc = (y.y0 + y.y1) / 2; labs[i].set_y(yc)
        if tr: labs[i].set_text(f"ALARM week {tr[0]}\n{tr[0]-TR+1} wk after change"); labs[i].set_color("#B3261E")
        elif fa: labs[i].set_text(f"False alarm week {fa[0]}\n(triage, then reset)"); labs[i].set_color("#5B6472")
        elif t >= TR: labs[i].set_text("watching…"); labs[i].set_color("#4A5568")
        else: labs[i].set_text("in control"); labs[i].set_color("#1F9D74")
    return lines
anim = FuncAnimation(fig, upd, frames=FR, blit=False)
anim.save(sys.argv[1], writer=FFMpegWriter(fps=8, codec="libx264", extra_args=["-pix_fmt", "yuv420p", "-preset", "veryfast", "-crf", "24"]))
upd(FR - 1); fig.savefig(sys.argv[2], dpi=100, facecolor=fig.get_facecolor())
print({n: AL[n] for n in names})
