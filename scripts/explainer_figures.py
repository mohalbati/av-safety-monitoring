"""
Worked examples and illustrative figures for Section 5 of the technical report
("The methods explained step by step").

    python scripts/explainer_figures.py

Writes results/figE1_*.png ... results/figE10_*.png and results/explainer_numbers.json.
Every number quoted in the worked examples of Section 5 is printed here, so the
text can be checked against the code.
"""
import os, sys, json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import poisson, norm, gamma, beta, binom, nbinom

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "src"))
from avmon.rates import OUTCOMES, LEADING_INDICATOR, FLEET_MILES_PER_WEEK as W
from avmon.power import _critical, power_one_sample, miles_to_detect_one_sample, miles_to_detect_two_sample
from avmon.monitor import PoissonCUSUM, arl_markov, run_length, shewhart_limit, shewhart_arl, bayes_prob_increase

OUT = os.path.join(ROOT, "results")
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
BLUE, ORANGE, PURPLE, RED, GREEN, GREY = "#2A78D6", "#EB6834", "#7A4FB0", "#B3261E", "#1E7A4C", "#5B6472"
N = {}  # numbers for the text


def save(fig, name):
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, name), dpi=170)
    plt.close(fig)


lam = {k: v[0] for k, v in OUTCOMES.items()}
lam[LEADING_INDICATOR[0]] = LEADING_INDICATOR[1]
m0 = {k: v * W for k, v in lam.items()}
N["W"] = W
N["weekly_means"] = m0

# ---------------------------------------------------------------- E1 Poisson
sev, inj, allc = m0["Serious injury or worse"], m0["Any-injury crashes"], m0["All reported crashes"]
N["poisson"] = {
    "serious_P0": poisson.pmf(0, sev), "serious_P1": poisson.pmf(1, sev), "serious_Pge2": poisson.sf(1, sev),
    "inj_P0": poisson.pmf(0, inj), "inj_P1": poisson.pmf(1, inj), "inj_P2": poisson.pmf(2, inj), "inj_Pge7": poisson.sf(6, inj),
    "all_P20": poisson.pmf(20, allc), "all_sd": np.sqrt(allc), "all_P_le_15": poisson.cdf(15, allc), "all_P_ge_30": poisson.sf(29, allc),
}
# binomial limit: one week of driving cut into one-mile pieces
n_pieces = int(round(W * 1e6)); p_piece = lam["Any-injury crashes"] / 1e6
N["binomial_limit"] = {"n": n_pieces, "p": p_piece, "binom_P0": binom.pmf(0, n_pieces, p_piece),
                       "binom_P2": binom.pmf(2, n_pieces, p_piece), "pois_P0": poisson.pmf(0, n_pieces * p_piece),
                       "pois_P2": poisson.pmf(2, n_pieces * p_piece)}

fig, axes = plt.subplots(1, 3, figsize=(10.5, 3.2))
for ax, (lab, mu, col, xs) in zip(axes, [("Serious injury or worse", sev, RED, np.arange(0, 5)),
                                          ("Any-injury crashes", inj, ORANGE, np.arange(0, 10)),
                                          ("All reported crashes", allc, BLUE, np.arange(5, 40))]):
    ax.bar(xs, poisson.pmf(xs, mu), color=col, width=0.8)
    ax.set_title(f"{lab}\nexpected {mu:.3g} per week", loc="left", fontsize=9.5)
    ax.set_xlabel("events in one week"); ax.set_ylabel("probability")
fig.suptitle("The Poisson distribution of weekly counts for three metrics", x=0.01, ha="left", fontsize=10.5)
save(fig, "figE1_poisson.png")

# ---------------------------------------------------------------- E2 exact test
lam_i = lam["Any-injury crashes"]
M_inj = miles_to_detect_one_sample(lam_i, 0.25)
mu0, mu1 = lam_i * M_inj, 1.25 * lam_i * M_inj
c = _critical(mu0, 0.05)
N["exact_test"] = {"M": M_inj, "weeks": M_inj / W, "mu0": mu0, "mu1": mu1, "c": c,
                   "alpha_actual": poisson.sf(c - 1, mu0), "power": poisson.sf(c - 1, mu1),
                   "normal_c": mu0 + 1.645 * np.sqrt(mu0)}
xs = np.arange(80, 190)
fig, ax = plt.subplots(figsize=(9, 3.8))
ax.bar(xs, poisson.pmf(xs, mu0), color="#9DBFEA", width=1.0, label=f"no regression: expected {mu0:.1f} events")
ax.bar(xs, poisson.pmf(xs, mu1), color="#F5B394", width=1.0, alpha=0.75, label=f"+25% regression: expected {mu1:.1f} events")
ax.bar(xs[xs >= c], poisson.pmf(xs[xs >= c], mu0), color=BLUE, width=1.0, label=f"false alarm (α = {N['exact_test']['alpha_actual']:.3f})")
ax.axvline(c - 0.5, color=RED, lw=1.5, ls="--")
ax.text(c + 1, ax.get_ylim()[1] * 0.92, f"critical count c = {c}\nalarm if N ≥ {c}", color=RED, fontsize=9)
ax.text(165, 0.022, f"power = {N['exact_test']['power']:.3f}\n(orange area right of c)", color=ORANGE, fontsize=9)
ax.set_xlabel(f"number of any-injury crashes observed in M = {M_inj:.1f} million miles ({M_inj / W:.1f} weeks)")
ax.set_ylabel("probability"); ax.legend(frameon=False, fontsize=8.5, loc="upper left")
ax.set_title("The exact Poisson test for a +25% regression in any-injury crashes", loc="left", fontsize=10.5)
save(fig, "figE2_exact_test.png")

# ---------------------------------------------------------------- E3 events rule
za, zb = norm.ppf(0.95), norm.ppf(0.80)
rr = np.linspace(0.08, 1.05, 200)
approx = (za + zb * np.sqrt(1 + rr)) ** 2 / rr ** 2
exact = {}
for r in (0.10, 0.25, 0.50, 1.00):
    exact[r] = miles_to_detect_one_sample(lam_i, r) * lam_i
N["events_rule"] = {"za": za, "zb": zb, "approx": {r: (za + zb * np.sqrt(1 + r)) ** 2 / r ** 2 for r in exact},
                    "exact": exact}
fig, ax = plt.subplots(figsize=(9, 3.6))
ax.plot(rr * 100, approx, color=GREY, lw=2, label="normal approximation (formula in Section 5.3)")
ax.plot([r * 100 for r in exact], list(exact.values()), "o", color=RED, ms=7, label="exact Poisson test (Table 3)")
for r, v in exact.items():
    ax.annotate(f"{v:.0f}", (r * 100, v), textcoords="offset points", xytext=(6, 6), fontsize=9, color=RED)
ax.set_yscale("log"); ax.set_xlabel("size of the regression (%)"); ax.set_ylabel("expected baseline events needed")
ax.legend(frameon=False); ax.set_title("Detecting a regression needs a fixed number of expected events", loc="left", fontsize=10.5)
save(fig, "figE3_events_rule.png")

# ---------------------------------------------------------------- two-sample, staged
N["two_sample_inj25"] = {"z_sum": za + zb, "inv_sum": 1 / lam_i + 1 / (1.25 * lam_i), "ln2": np.log(1.25) ** 2,
                         "M": miles_to_detect_two_sample(lam_i, 0.25)}
N["staged_inj25_10pct"] = M_inj / (0.10 * W)

# ---------------------------------------------------------------- E4 Bayesian baseline (serious injury)
k_si, miles = 6, 271.3
post = gamma(k_si + 0.5, scale=1 / miles)
N["baseline_post_serious"] = {"shape": k_si + 0.5, "mean": post.mean(), "median": post.median(),
                              "p05": post.ppf(0.05), "p95": post.ppf(0.95), "mle": k_si / miles}
x = np.linspace(1e-4, 0.065, 600)
fig, ax = plt.subplots(1, 2, figsize=(10.5, 3.4))
ax[0].plot(x, x ** -0.5 / (x ** -0.5).max() * 1.0, color=GREY, lw=2, label="Jeffreys prior ∝ λ^(−1/2) (shape only)")
lik = poisson.pmf(k_si, x * miles); ax[0].plot(x, lik / lik.max(), color=ORANGE, lw=2, label="likelihood: 6 events in 271.3M mi")
pd_ = post.pdf(x); ax[0].plot(x, pd_ / pd_.max(), color=RED, lw=2.4, label="posterior Gamma(6.5, 271.3)")
ax[0].set_xlabel("serious-injury rate λ (per million miles)"); ax[0].set_ylabel("relative height")
ax[0].legend(frameon=False, fontsize=8); ax[0].set_title("prior × likelihood → posterior", loc="left", fontsize=9.5)
ax[1].plot(x, post.pdf(x), color=RED, lw=2)
for q, lab in ((0.05, "5th"), (0.5, "median"), (0.95, "95th")):
    v = post.ppf(q); ax[1].axvline(v, color=GREY, ls="--", lw=1)
    ax[1].text(v, ax[1].get_ylim()[1] * 0.9 if q != 0.5 else ax[1].get_ylim()[1] * 0.75, f" {lab}\n {v:.4f}", fontsize=8.5)
ax[1].fill_between(x, post.pdf(x), where=(x >= post.ppf(0.05)) & (x <= post.ppf(0.95)), color=RED, alpha=0.15)
ax[1].set_xlabel("serious-injury rate λ (per million miles)"); ax[1].set_ylabel("probability density")
ax[1].set_title("90% of the belief lies in the shaded range", loc="left", fontsize=9.5)
fig.suptitle("Bayesian updating of the serious-injury baseline rate", x=0.01, ha="left", fontsize=10.5)
save(fig, "figE4_bayes_baseline.png")

# ---------------------------------------------------------------- E5 test coverage
n299 = int(np.ceil(np.log(0.05) / np.log(0.99)))
nb = next(n for n in range(1, 5000) if beta.cdf(0.01, 0.5, n + 0.5) >= 0.95)
n_c1 = next(n for n in range(1, 5000) if binom.cdf(1, n, 0.01) <= 0.05)
N["coverage"] = {"ln005": np.log(0.05), "ln099": np.log(0.99), "ratio": np.log(0.05) / np.log(0.99), "n0": n299,
                 "P0_at_299": 0.99 ** 299, "P0_at_298": 0.99 ** 298,
                 "pass_p0001": 0.999 ** 299, "pass_p0003": 0.997 ** 299, "n_c1": n_c1,
                 "c1_check": binom.cdf(1, n_c1, 0.01), "n_bayes": nb, "bayes_check": beta.cdf(0.01, 0.5, nb + 0.5),
                 "rule3_1pct": 3 / 0.01}
nn = np.arange(0, 700)
fig, ax = plt.subplots(1, 2, figsize=(10.5, 3.5))
for p, col in ((0.03, ORANGE), (0.01, RED), (0.003, PURPLE)):
    ax[0].plot(nn, (1 - p) ** nn, color=col, lw=2, label=f"true failure probability {p:.1%}")
ax[0].axhline(0.05, color=GREY, ls="--", lw=1); ax[0].axvline(n299, color=RED, ls=":", lw=1.2)
ax[0].text(n299 + 8, 0.6, f"n = {n299}:\n(0.99)^{n299} = {0.99 ** n299:.4f} < 0.05", color=RED, fontsize=8.5)
ax[0].set_xlabel("number of runs n"); ax[0].set_ylabel("P(all n runs pass)")
ax[0].legend(frameon=False, fontsize=8); ax[0].set_title("A bad scenario type rarely passes many runs", loc="left", fontsize=9.5)
pp = np.linspace(0, 0.03, 500)
ax[1].plot(pp * 100, beta.pdf(pp, 0.5, nb + 0.5), color=GREEN, lw=2)
ax[1].fill_between(pp * 100, beta.pdf(pp, 0.5, nb + 0.5), where=pp <= 0.01, color=GREEN, alpha=0.2)
ax[1].axvline(1, color=GREY, ls="--", lw=1)
ax[1].text(1.1, ax[1].get_ylim()[1] * 0.5, f"P(p < 1%) = {N['coverage']['bayes_check']:.3f}\nafter {nb} failure-free runs\nposterior Beta(0.5, {nb + 0.5})", fontsize=8.5)
ax[1].set_xlabel("failure probability p (%)"); ax[1].set_ylabel("posterior density")
ax[1].set_title("Bayesian view: belief about p after the runs", loc="left", fontsize=9.5)
fig.suptitle("Sizing a scenario test plan", x=0.01, ha="left", fontsize=10.5)
save(fig, "figE5_test_coverage.png")

# ---------------------------------------------------------------- E6 CUSUM mechanics (simulated history, all crashes)
design = pd.read_csv(os.path.join(OUT, "table3_cusum_design.csv")).set_index("metric")
rng = np.random.default_rng(2026)
WEEKS, T_REG = 104, 60
mult = np.where(np.arange(1, WEEKS + 1) >= T_REG, 1.5, 1.0)
hist = {name: rng.poisson(m * mult) for name, m in m0.items()}  # same draw order as run_all.py
xa = hist["All reported crashes"]
h_all = float(design.loc["All reported crashes", "h"])
cus = PoissonCUSUM(allc, 0.25, h_all)
s, al = cus.path(xa, reset=True)
wk = np.arange(1, WEEKS + 1)
N["cusum_all"] = {"m0": allc, "m1": 1.25 * allc, "ln": np.log(1.25), "k": cus.k, "h": h_all,
                  "weeks_50_61": {int(w): int(xa[w - 1]) for w in range(50, 62)},
                  "S_50_61": {int(w): round(float(s[w - 1]), 2) for w in range(50, 62)},
                  "first_alarm": [a for a in al if a >= T_REG][0],
                  "drift_in": allc - cus.k, "drift_50": 1.5 * allc - cus.k, "drift_25": 1.25 * allc - cus.k}
lo, hi = 44, 64
fig, ax = plt.subplots(2, 1, figsize=(9, 5.2), sharex=True)
cols = [BLUE if w < T_REG else ORANGE for w in wk[lo - 1:hi]]
ax[0].bar(wk[lo - 1:hi], xa[lo - 1:hi], color=cols)
ax[0].axhline(cus.k, color=RED, ls="--", lw=1.3); ax[0].text(hi + 0.6, cus.k, f"k = {cus.k:.2f}", color=RED, va="center", fontsize=9)
ax[0].axhline(allc, color=GREY, ls=":", lw=1); ax[0].text(hi + 0.6, allc - 2.5, f"m₀ = {allc:.2f}", color=GREY, va="center", fontsize=9)
ax[0].set_xlim(lo - 0.8, hi + 3.5); ax[0].set_ylabel("crashes in the week"); ax[0].set_title("Weekly counts (blue: before the regression; orange: after, +50%)", loc="left", fontsize=9.5)
ax[1].plot(wk[lo - 1:hi], s[lo - 1:hi], color=BLUE, lw=2)
ax[1].plot(wk[lo - 1:hi], s[lo - 1:hi], "o", color=BLUE, ms=4)
ax[1].axhline(h_all, color=RED, ls="--", lw=1.3); ax[1].text(hi + 0.6, h_all, f"h = {h_all:.2f}", color=RED, va="center", fontsize=9)
ax[1].axvline(T_REG - 0.5, color=GREY, lw=1); ax[1].text(T_REG - 0.4, h_all * 1.25, "regression\nstarts", fontsize=8.5, color=GREY)
for a in al:
    if lo <= a <= hi:
        ax[1].plot(a, s[a - 1], "v", color=RED, ms=9)
ax[1].set_ylabel("CUSUM statistic S"); ax[1].set_xlabel("week")
ax[1].set_title("S adds (count − k) each week, never goes below 0, alarms at h and restarts", loc="left", fontsize=9.5)
fig.suptitle("How the CUSUM works, on the simulated history of all reported crashes", x=0.01, ha="left", fontsize=10.5)
save(fig, "figE6_cusum_mechanics.png")

# serious injury intuition: n events within t weeks reach h if n - k t >= h (ignoring the floor at 0)
ks, hs = float(design.loc["Serious injury or worse", "k"]), float(design.loc["Serious injury or worse", "h"])
N["cusum_serious"] = {"k": ks, "h": hs, "window": {n: (n - hs) / ks for n in (4, 5, 6)}}

# ---------------------------------------------------------------- E7 Markov toy example (k = 1, h = 3, m = 0.5)
mt = 0.5
p = poisson.pmf(np.arange(10), mt)
R = np.array([[p[0] + p[1], p[2], p[3]],
              [p[0], p[1], p[2]],
              [0.0, p[0], p[1]]])
L = np.linalg.solve(np.eye(3) - R, np.ones(3))
sim = run_length(mt, 1.0, 3.0, n_sims=200000, t_max=20000, seed=7).mean()
N["markov_toy"] = {"p": p[:5].tolist(), "R": R.tolist(), "alarm_prob": (1 - R.sum(1)).tolist(), "L": L.tolist(),
                   "sim_ARL": sim, "brook_evans_fn": arl_markov(mt, 1.0, 3.0, steps_per_unit=1)}
dot = f"""digraph M {{ rankdir=LR; nodesep=0.5; ranksep=1.0; bgcolor="white";
 node [shape=circle, style=filled, fillcolor="#EAF2FB", color="{BLUE}", fontname="DejaVu Sans", fontsize=13, width=0.9, fixedsize=true];
 edge [fontname="DejaVu Sans", fontsize=10, color="{GREY}"];
 s0 [label="S = 0"]; s1 [label="S = 1"]; s2 [label="S = 2"];
 A [label="ALARM\\nS ≥ 3", shape=doublecircle, fillcolor="#FDE7E5", color="{RED}", width=1.05];
 s0 -> s0 [label="X = 0 or 1\\n{R[0,0]:.4f}"]; s0 -> s1 [label="X = 2\\n{R[0,1]:.4f}"]; s0 -> s2 [label="X = 3\\n{R[0,2]:.4f}"];
 s0 -> A [label="X ≥ 4\\n{1 - R[0].sum():.4f}", color="{RED}", fontcolor="{RED}"];
 s1 -> s0 [label="X = 0\\n{R[1,0]:.4f}"]; s1 -> s1 [label="X = 1\\n{R[1,1]:.4f}"]; s1 -> s2 [label="X = 2\\n{R[1,2]:.4f}"];
 s1 -> A [label="X ≥ 3\\n{1 - R[1].sum():.4f}", color="{RED}", fontcolor="{RED}"];
 s2 -> s1 [label="X = 0\\n{R[2,1]:.4f}"]; s2 -> s2 [label="X = 1\\n{R[2,2]:.4f}"];
 s2 -> A [label="X ≥ 2\\n{1 - R[2].sum():.4f}", color="{RED}", fontcolor="{RED}"];
 labelloc="t"; fontname="DejaVu Sans"; fontsize=13;
 label="A toy CUSUM as a Markov chain: weekly count X ~ Poisson(0.5), k = 1, h = 3";
}}"""
open(os.path.join(OUT, "_figE7.dot"), "w").write(dot)
os.system(f"dot -Tpng -Gdpi=170 {os.path.join(OUT, '_figE7.dot')} -o {os.path.join(OUT, 'figE7_markov_toy.png')}")
os.remove(os.path.join(OUT, "_figE7.dot"))

# ---------------------------------------------------------------- Shewhart, family-wise
c_si = shewhart_limit(sev, 260)
N["shewhart_serious"] = {"c": c_si, "P_ge2": poisson.sf(c_si - 1, sev), "ARL0": shewhart_arl(sev, c_si),
                         "ARL_50": shewhart_arl(1.5 * sev, c_si)}
c_in = shewhart_limit(inj, 260)
N["shewhart_inj"] = {"c": c_in, "P": poisson.sf(c_in - 1, inj), "ARL0": shewhart_arl(inj, c_in), "c_minus1_P": poisson.sf(c_in - 2, inj)}
N["familywise"] = {"one_chart_2y": 1 - np.exp(-104 / 260), "five_charts_2y": 1 - np.exp(-5 * 104 / 260),
                   "twenty_520": 1 - np.exp(-20 * 104 / 520), "geom_check": 1 - (1 - 1 / 260) ** 104}

# ---------------------------------------------------------------- E8 overdispersion
lead = m0[LEADING_INDICATOR[0]]
N["overdispersion"] = {nm: {"m0": m, "var_pois": m, "var_nb_10": m + 0.01 * m * m, "sd_pois": np.sqrt(m),
                            "sd_nb_10": np.sqrt(m + 0.01 * m * m), "ratio": (m + 0.01 * m * m) / m}
                       for nm, m in (("lead", lead), ("all", allc), ("inj", inj), ("serious", sev))}
fig, ax = plt.subplots(1, 2, figsize=(10.5, 3.4))
for a_, (mm, lab) in zip(ax, ((lead, "Leading indicator (292 per week)"), (allc, "All reported crashes (20.8 per week)"))):
    v = 0.10; r_ = 1 / v ** 2; pnb = r_ / (r_ + mm)
    xs = np.arange(int(mm - 4.5 * np.sqrt(mm + v * v * mm * mm)), int(mm + 4.5 * np.sqrt(mm + v * v * mm * mm)))
    xs = xs[xs >= 0]
    a_.plot(xs, poisson.pmf(xs, mm), color=BLUE, lw=2, label="pure Poisson")
    a_.plot(xs, nbinom.pmf(xs, r_, pnb), color=ORANGE, lw=2, label="rate varies 10% week to week")
    a_.set_title(lab, loc="left", fontsize=9.5); a_.set_xlabel("events in one week"); a_.set_ylabel("probability")
    a_.legend(frameon=False, fontsize=8)
fig.suptitle("Week-to-week variation widens the distribution of frequent counts much more than rare ones", x=0.01, ha="left", fontsize=10.5)
save(fig, "figE8_overdispersion.png")

# ---------------------------------------------------------------- E9 coupling: expected weekly increment of the CUSUM
k_lead = float(design.loc[LEADING_INDICATOR[0], "k"]); h_lead = float(design.loc[LEADING_INDICATOR[0], "h"])
rises = np.array([0, 0.025, 0.05, 0.125, 0.25, 0.5])
N["coupling"] = {"m0": lead, "k": k_lead, "h": h_lead,
                 "increment": {float(r): lead * (1 + r) - k_lead for r in rises},
                 "sd": float(np.sqrt(lead))}
rr = np.linspace(0, 0.5, 300)
fig, ax = plt.subplots(figsize=(9, 3.6))
ax.plot(rr * 100, lead * (1 + rr) - k_lead, color=GREEN, lw=2)
ax.axhline(0, color=GREY, lw=1)
ax.axvline((k_lead / lead - 1) * 100, color=RED, ls="--", lw=1)
ax.text((k_lead / lead - 1) * 100 + 0.6, 40, f"break-even rise\n{(k_lead / lead - 1) * 100:.1f}%", color=RED, fontsize=9)
for r in rises:
    ax.plot(r * 100, lead * (1 + r) - k_lead, "o", color=GREEN)
ax.set_xlabel("rise of the leading indicator when serious injuries rise 50% (%)")
ax.set_ylabel("expected weekly change of S\n(m − k, events per week)")
ax.set_title("The chart drifts upward only if the indicator rises more than the gap between m₀ and k", loc="left", fontsize=10)
save(fig, "figE9_coupling_drift.png")

# ---------------------------------------------------------------- Bayesian check (serious injury, simulated history)
tl = json.load(open(os.path.join(OUT, "summary.json")))["timeline"]["Serious injury or worse"]
M_post = W * (WEEKS - T_REG + 1)
N["bayes_check_serious"] = {"N": tl["events_after_change"], "M": M_post, "lam0": lam["Serious injury or worse"],
                            "shape": tl["events_after_change"] + 0.5,
                            "P": bayes_prob_increase(tl["events_after_change"], M_post, lam["Serious injury or worse"]),
                            "post_median": gamma.median(tl["events_after_change"] + 0.5, scale=1 / M_post)}

# ---------------------------------------------------------------- E10 risk register
reg = pd.read_csv(os.path.join(ROOT, "data", "risk_register.csv")).dropna(subset=["crashes"])
rng = np.random.default_rng(1)
draws = {}
info = {}
for _, rw in reg.iterrows():
    n, k = int(rw.crashes), int(rw.injury_crashes)
    draws[rw.id] = rng.gamma(k + 0.5, 1 / 271.3, 20000) * 100
    info[rw.id] = {"n": n, "k": k, "crash_rate": n / 271.3, "p_inj_median": beta.median(k + 0.5, n - k + 0.5),
                   "p_inj_mean": (k + 0.5) / (n + 1), "inj_rate_median_100M": gamma.median(k + 0.5, scale=1 / 271.3) * 100,
                   "inj_rate_p05": gamma.ppf(0.05, k + 0.5, scale=1 / 271.3) * 100, "inj_rate_p95": gamma.ppf(0.95, k + 0.5, scale=1 / 271.3) * 100}
N["register"] = info
N["register_P_H1_gt_H2"] = float(np.mean(draws["H1"] > draws["H2"]))
N["register_P_H3_gt_H4"] = float(np.mean(draws["H3"] > draws["H4"]))
fig, ax = plt.subplots(1, 2, figsize=(10.5, 3.4))
for hid, col in (("H1", BLUE), ("H2", ORANGE)):
    ax[0].hist(draws[hid], bins=80, color=col, alpha=0.6, density=True, label=f"{hid}: median {np.median(draws[hid]):.1f}")
ax[0].set_xlabel("injury crashes per 100 million miles"); ax[0].set_ylabel("density"); ax[0].legend(frameon=False, fontsize=8.5)
ax[0].set_title(f"H1 above H2 in {N['register_P_H1_gt_H2']:.1%} of 20,000 draws", loc="left", fontsize=9.5)
pp = np.linspace(0, 1, 500)
for hid, col in (("H3", RED), ("H4", PURPLE), ("H5", GREEN)):
    n, k = info[hid]["n"], info[hid]["k"]
    ax[1].plot(pp * 100, beta.pdf(pp, k + 0.5, n - k + 0.5), color=col, lw=2, label=f"{hid}: {k} injuries in {n} crashes")
ax[1].set_xlabel("P(injury | crash) (%)"); ax[1].set_ylabel("density"); ax[1].legend(frameon=False, fontsize=8.5)
ax[1].set_title("Severity: how likely a crash is to injure", loc="left", fontsize=9.5)
fig.suptitle("Uncertainty in the risk register: ranking by rate (left) and severity (right)", x=0.01, ha="left", fontsize=10.5)
save(fig, "figE10_register.png")


def _clean(o):
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    return o


json.dump(_clean(N), open(os.path.join(OUT, "explainer_numbers.json"), "w"), indent=1)
print(json.dumps(_clean(N), indent=1))
