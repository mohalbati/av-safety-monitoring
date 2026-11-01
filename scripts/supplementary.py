"""
Supplementary analyses for the technical report (run after scripts/run_all.py).

S1  Staged rollout: detection time when a release runs on part of the fleet
S2  Power curves of the exact Poisson test (saw-tooth behaviour)
S3  Baseline-rate uncertainty: detection time across the posterior of the baseline
S4  Test coverage with allowed failures, a Bayesian alternative and the OC curve
S5  CUSUM run-length curves; Markov-chain (Brook-Evans) verification of the simulation
S6  CUSUM versus a Shewhart weekly-count chart with the same false-alarm interval
S7  Family-wise false alarms as a function of the number of charts and their ARL0
S8  Overdispersion: false-alarm interval of a Poisson-designed chart when counts are overdispersed
S9  Leading-indicator coupling: detection time when the indicator moves only partly with the outcome
S10 Bayesian sequential check in the simulated history
S11 Risk register: ranking probabilities from the posteriors

python scripts/supplementary.py      (about 2 minutes)
"""
import os, sys, json
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import gamma, beta, poisson, binom
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from avmon.rates import OUTCOMES, LEADING_INDICATOR, FLEET_MILES_PER_WEEK
from avmon.power import power_one_sample, miles_to_detect_one_sample, tests_for_zero_failures
from avmon.monitor import PoissonCUSUM, run_length, arl_markov, shewhart_limit, shewhart_arl, bayes_prob_increase

ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT = os.path.join(ROOT, "results")
W = FLEET_MILES_PER_WEEK
RO_MILES = 271.3
COL = {"All reported crashes": "#2A78D6", "Any-injury crashes": "#EB6834", "Airbag deployment": "#7A4FB0",
       "Serious injury or worse": "#B3261E", "Leading indicator (assumed)": "#1E7A4C"}
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
metrics = {k: v[0] for k, v in OUTCOMES.items()}
metrics[LEADING_INDICATOR[0]] = LEADING_INDICATOR[1]
design = pd.read_csv(os.path.join(OUT, "table3_cusum_design.csv")).set_index("metric")
S = {}


def save(fig, name):
    fig.tight_layout(); fig.savefig(os.path.join(OUT, name), dpi=170); plt.close(fig)


# S1 staged rollout -----------------------------------------------------------------------
F = [0.05, 0.10, 0.25, 0.50, 1.00]
rows = []
for name, lam in metrics.items():
    M = miles_to_detect_one_sample(lam, 0.25)
    for f in F:
        rows.append(dict(metric=name, fleet_fraction=f, weeks_to_detect_25pct=round(M / (f * W), 1)))
t5 = pd.DataFrame(rows); t5.to_csv(os.path.join(OUT, "table5_staged_rollout.csv"), index=False)
fig, ax = plt.subplots(figsize=(8.8, 4.3))
for name in metrics:
    d = t5[t5.metric == name]
    ax.plot(d.fleet_fraction * 100, d.weeks_to_detect_25pct, "o-", color=COL[name], label=name, lw=2)
ax.set_xscale("log"); ax.set_yscale("log"); ax.set_xticks([5, 10, 25, 50, 100]); ax.set_xticklabels(["5%", "10%", "25%", "50%", "100%"])
for y, lab in ((4, "1 month"), (52, "1 year")):
    ax.axhline(y, color="#9AA5B3", lw=0.8, ls="--"); ax.text(5.2, y * 1.1, lab, fontsize=8, color="#5B6472")
ax.set_xlabel("Share of the fleet running the new release"); ax.set_ylabel("Weeks to detect a +25% regression\n(80% power, 5% false alarm)")
ax.set_title("Staged rollout: a 10% canary needs ten times longer", loc="left", fontsize=11)
ax.legend(fontsize=8, frameon=False, loc="upper left", bbox_to_anchor=(1.01, 1)); save(fig, "fig5_staged_rollout.png")
S["canary10_allcrash_weeks"] = float(t5[(t5.metric == "All reported crashes") & (t5.fleet_fraction == 0.1)].weeks_to_detect_25pct.iloc[0])
S["canary10_lead_weeks"] = float(t5[(t5.metric == LEADING_INDICATOR[0]) & (t5.fleet_fraction == 0.1)].weeks_to_detect_25pct.iloc[0])

# S2 power curves ----------------------------------------------------------------------------
fig, axes = plt.subplots(1, 2, figsize=(10, 3.9))
wk = np.linspace(0.05, 120, 900)
for name in ("All reported crashes", "Any-injury crashes", "Airbag deployment"):
    axes[0].plot(wk, [power_one_sample(w * W, metrics[name], 0.25) for w in wk], color=COL[name], label=name, lw=1.5)
axes[0].axhline(0.8, color="#5B6472", ls="--", lw=0.8); axes[0].set_xlabel("Weeks of whole-fleet driving"); axes[0].set_ylabel("Power to detect +25%")
axes[0].set_title("Power grows with exposure", loc="left", fontsize=10.5); axes[0].legend(fontsize=8, frameon=False)
wk2 = np.linspace(0.5, 40, 800)
axes[1].plot(wk2, [power_one_sample(w * W, metrics["Any-injury crashes"], 0.25) for w in wk2], color=COL["Any-injury crashes"], lw=1.2)
axes[1].plot(wk2, [power_one_sample(w * W, metrics["Any-injury crashes"], 0.0) for w in wk2], color="#5B6472", lw=1.2, label="false-alarm rate (no regression)")
axes[1].axhline(0.05, color="#B3261E", ls=":", lw=0.8)
axes[1].set_xlabel("Weeks"); axes[1].set_ylabel("Probability of alarm"); axes[1].legend(fontsize=8, frameon=False)
axes[1].set_title("Discrete counts: power is a saw-tooth (any-injury)", loc="left", fontsize=10.5)
save(fig, "fig6_power_curves.png")

# S3 baseline-rate uncertainty ---------------------------------------------------------------
cnt = {"Any-injury crashes": 166, "Airbag deployment": 72, "Serious injury or worse": 6}
rows = []
for name, k in cnt.items():
    for q in (0.05, 0.5, 0.95):
        lam = gamma.ppf(q, k + 0.5, scale=1 / RO_MILES)
        rows.append(dict(metric=name, events=k, baseline_quantile=q, rate_per_M_mi=round(lam, 4),
                         weeks_to_detect_25pct=round(miles_to_detect_one_sample(lam, 0.25) / W, 1)))
t6 = pd.DataFrame(rows); t6.to_csv(os.path.join(OUT, "table6_baseline_uncertainty.csv"), index=False)

# S4 test coverage with allowed failures, Bayesian, OC curve -----------------------------------
def runs_needed(p0, conf, c):
    n = c + 1
    while binom.cdf(c, n, p0) > 1 - conf:
        n += 1 if n < 200 else max(1, n // 200)
    lo, hi = max(c + 1, n - max(1, n // 200)), n
    for m in range(lo, hi + 1):
        if binom.cdf(c, m, p0) <= 1 - conf:
            return m
    return n


def bayes_runs(p0, conf):
    # Jeffreys prior Beta(1/2, 1/2); zero failures in n runs -> Beta(1/2, n + 1/2); need P(p < p0) >= conf
    n = 0
    while beta.cdf(p0, 0.5, n + 0.5) < conf:
        n = n + 1 if n < 100 else int(n * 1.01) + 1
    return n


rows = []
for p0 in (0.01, 0.001):
    for c in (0, 1, 2, 5):
        rows.append(dict(target_failure_prob=p0, allowed_failures=c, runs_needed_95pct=runs_needed(p0, 0.95, c)))
    rows.append(dict(target_failure_prob=p0, allowed_failures="0 (Bayesian, Jeffreys prior)", runs_needed_95pct=bayes_runs(p0, 0.95)))
t7 = pd.DataFrame(rows); t7.to_csv(os.path.join(OUT, "table7_test_plans.csv"), index=False)
n299 = tests_for_zero_failures(0.01, 0.95)
pp = np.geomspace(1e-4, 0.05, 300)
fig, ax = plt.subplots(figsize=(8.4, 3.9))
for c, ls in ((0, "-"), (1, "--"), (2, ":")):
    n = runs_needed(0.01, 0.95, c)
    ax.plot(pp * 100, binom.cdf(c, n, pp), ls, color="#2A78D6", lw=2, label=f"{n} runs, pass if ≤ {c} failures")
ax.axvline(1, color="#B3261E", lw=0.8); ax.text(1.05, 0.9, "target 1%", color="#B3261E", fontsize=8)
ax.set_xscale("log"); ax.set_xlabel("True failure probability of the scenario type (%)"); ax.set_ylabel("Probability the release passes")
ax.set_title("Operating characteristic: plans that tolerate a failure need more runs but pass good releases more often", loc="left", fontsize=10)
ax.legend(fontsize=8, frameon=False); save(fig, "fig7_test_oc_curve.png")
S["oc_pass_prob_at_0p1pct_zero_fail"] = float(binom.cdf(0, n299, 0.001))
S["oc_pass_prob_at_0p3pct_zero_fail"] = float(binom.cdf(0, n299, 0.003))

# S5 run-length curves + Markov-chain verification -------------------------------------------
shifts = [0.0, 0.10, 0.25, 0.50, 1.00]
rows, ver = [], []
for i, name in enumerate(metrics):
    m0, k, h = design.loc[name, "expected_weekly_count"], design.loc[name, "k"], design.loc[name, "h"]
    for r in shifts:
        mc = run_length((1 + r) * m0, k, h, 4000, 6000, seed=500 + 10 * i + int(r * 100))
        mk = arl_markov((1 + r) * m0, k, h)
        rows.append(dict(metric=name, shift=f"+{int(r*100)}%", ARL_simulated=round(mc.mean(), 1), ARL_markov_chain=round(mk, 1),
                         median_simulated=float(np.median(mc)), rel_diff_pct=round(100 * (mc.mean() - mk) / mk, 1)))
t8 = pd.DataFrame(rows); t8.to_csv(os.path.join(OUT, "table8_arl_verification.csv"), index=False)
fig, ax = plt.subplots(figsize=(8.8, 4.2))
for name in metrics:
    d = t8[t8.metric == name]
    ax.plot([0, 10, 25, 50, 100], d.ARL_markov_chain, "o-", color=COL[name], label=name, lw=2)
    ax.plot([0, 10, 25, 50, 100], d.ARL_simulated, "x", color="#16202C", ms=6)
ax.set_yscale("log"); ax.set_xlabel("Size of the regression (%)"); ax.set_ylabel("Average weeks to alarm (log scale)")
ax.set_title("CUSUM run length: Markov chain (lines) and simulation (crosses) agree", loc="left", fontsize=11)
ax.legend(fontsize=8, frameon=False, loc="upper left", bbox_to_anchor=(1.01, 1)); save(fig, "fig8_arl_curves.png")
S["arl_max_abs_rel_diff_pct"] = float(t8.rel_diff_pct.abs().max())

# S6 CUSUM vs Shewhart -------------------------------------------------------------------------
rows = []
for name in metrics:
    m0, k, h = design.loc[name, "expected_weekly_count"], design.loc[name, "k"], design.loc[name, "h"]
    c = shewhart_limit(m0, 260)
    a0 = shewhart_arl(m0, c)
    for r in (0.25, 0.5, 1.0):
        rows.append(dict(metric=name, shift=f"+{int(r*100)}%", shewhart_limit=c, shewhart_ARL0=round(a0, 0),
                         ARL_shewhart=round(shewhart_arl((1 + r) * m0, c), 1), ARL_cusum=round(arl_markov((1 + r) * m0, k, h), 1)))
t9 = pd.DataFrame(rows); t9.to_csv(os.path.join(OUT, "table9_cusum_vs_shewhart.csv"), index=False)

# S7 family-wise false alarms ------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(8.2, 3.9))
mm = np.arange(1, 21)
for a0, ls in ((104, ":"), (260, "-"), (520, "--"), (1040, "-.")):
    ax.plot(mm, 1 - np.exp(-104 * mm / a0), ls, lw=2, color="#2A78D6", label=f"ARL0 {a0} weeks per chart")
ax.axvline(5, color="#5B6472", lw=0.8); ax.text(5.2, 0.05, "5 charts (this study)", fontsize=8, color="#5B6472")
ax.set_xlabel("Number of monitored charts"); ax.set_ylabel("P(at least one false alarm in 2 years)")
ax.set_title("False alarms add up across charts", loc="left", fontsize=11); ax.legend(fontsize=8, frameon=False); save(fig, "fig9_familywise.png")
S["fw_5charts_260"] = float(1 - np.exp(-104 * 5 / 260)); S["fw_20charts_520"] = float(1 - np.exp(-104 * 20 / 520))

# S8 overdispersion ----------------------------------------------------------------------------
def arl_overdispersed(m0, k, h, cv, n=3000, tmax=4000, seed=0):
    rng = np.random.default_rng(seed)
    s = np.zeros(n); rl = np.full(n, tmax, float); alive = np.ones(n, bool)
    shape = 1 / cv**2 if cv > 0 else None
    for t in range(1, tmax + 1):
        lam = rng.gamma(shape, m0 / shape, n) if cv > 0 else np.full(n, m0)
        x = rng.poisson(lam)
        s = np.where(alive, np.maximum(0, s + x - k), s)
        hit = alive & (s >= h); rl[hit] = t; alive &= ~hit
        if not alive.any():
            break
    return rl.mean()


rows = []
for j, name in enumerate(["All reported crashes", "Any-injury crashes", "Leading indicator (assumed)"]):
    m0, k, h = design.loc[name, "expected_weekly_count"], design.loc[name, "k"], design.loc[name, "h"]
    for cv in (0.0, 0.05, 0.10, 0.20):
        rows.append(dict(metric=name, week_to_week_rate_cv=cv, ARL0_weeks=round(arl_overdispersed(m0, k, h, cv, seed=800 + j), 1)))
t10 = pd.DataFrame(rows); t10.to_csv(os.path.join(OUT, "table10_overdispersion.csv"), index=False)


def arl_od_shift(m0, k, h, cv, r, n=1500, tmax=3000, seed=0):
    return arl_overdispersed((1 + r) * m0, k, h, cv, n=n, tmax=tmax, seed=seed)


# recalibrate h for 10% week-to-week variation, then measure the cost in detection speed
rows = []
for j, name in enumerate(["All reported crashes", "Leading indicator (assumed)"]):
    m0, k, h = design.loc[name, "expected_weekly_count"], design.loc[name, "k"], design.loc[name, "h"]
    lo, hi = h, h * 20
    for _ in range(18):
        mid = 0.5 * (lo + hi)
        if arl_overdispersed(m0, k, mid, 0.10, n=1000, tmax=2600, seed=850 + j) < 260:
            lo = mid
        else:
            hi = mid
    h_new = 0.5 * (lo + hi)
    rows.append(dict(metric=name, h_poisson=h, h_recalibrated_cv10=round(h_new, 1),
                     ARL0_recalibrated=round(arl_overdispersed(m0, k, h_new, 0.10, n=2000, tmax=3000, seed=870 + j), 1),
                     ARL_25pct_poisson_counts_old_h=round(arl_markov(1.25 * m0, k, h), 1),
                     ARL_25pct_overdispersed_new_h=round(arl_od_shift(m0, k, h_new, 0.10, 0.25, seed=880 + j), 1)))
t10b = pd.DataFrame(rows); t10b.to_csv(os.path.join(OUT, "table10b_overdispersion_recalibrated.csv"), index=False)

# S9 leading-indicator coupling ---------------------------------------------------------------
name = "Leading indicator (assumed)"
m0, k, h = design.loc[name, "expected_weekly_count"], design.loc[name, "k"], design.loc[name, "h"]
rows = []
for b in (0.0, 0.05, 0.10, 0.25, 0.5, 1.0):
    rl = run_length((1 + 0.5 * b) * m0, k, h, 3000, 3000, seed=900 + int(b * 100))
    rows.append(dict(coupling=b, indicator_rise_pct=50 * b, median_weeks_to_alarm=float(np.median(rl)), mean_weeks_to_alarm=round(rl.mean(), 1)))
t11 = pd.DataFrame(rows); t11.to_csv(os.path.join(OUT, "table11_indicator_coupling.csv"), index=False)
fig, ax = plt.subplots(figsize=(8.2, 3.9))
ax.plot(t11.indicator_rise_pct, t11.median_weeks_to_alarm, "o-", color=COL[name], lw=2, label="leading-indicator CUSUM")
ax.axhline(design.loc["Serious injury or worse", "weeks_to_alarm_+50%_median"], color=COL["Serious injury or worse"], ls="--", lw=1.2,
           label="serious-injury CUSUM itself (median 70 weeks)")
ax.set_yscale("log"); ax.set_xlabel("Rise in the leading indicator when serious injuries rise 50% (%)")
ax.set_ylabel("Median weeks to alarm"); ax.set_title("A leading indicator helps only if it moves with the outcome", loc="left", fontsize=11)
ax.legend(fontsize=8, frameon=False); save(fig, "fig10_indicator_coupling.png")

# S10 Bayesian sequential check in the simulated history --------------------------------------
rng = np.random.default_rng(2026)
WEEKS, T_REG, RATIO = 104, 60, 1.5
fig, ax = plt.subplots(figsize=(8.8, 3.9))
first95 = {}
for name in design.index:
    m0 = design.loc[name, "expected_weekly_count"]
    x = rng.poisson(m0 * np.where(np.arange(1, WEEKS + 1) >= T_REG, RATIO, 1.0))
    post = [bayes_prob_increase(int(x[T_REG - 1:t].sum()), W * (t - T_REG + 1), metrics[name]) for t in range(T_REG, WEEKS + 1)]
    ax.plot(range(T_REG, WEEKS + 1), post, color=COL[name], lw=2, label=name)
    hit = [t for t, p in zip(range(T_REG, WEEKS + 1), post) if p >= 0.95]
    first95[name] = hit[0] - T_REG + 1 if hit else None
ax.axhline(0.95, color="#5B6472", ls="--", lw=0.8); ax.set_xlabel("Week"); ax.set_ylabel("P(rate increased | data since week 60)")
ax.set_title("Bayesian check on the simulated history: confidence that the rate rose", loc="left", fontsize=11)
ax.legend(fontsize=8, frameon=False, loc="lower right"); save(fig, "fig11_bayes_check.png")
S["bayes_weeks_to_95"] = first95

# S11 risk-register ranking probabilities -----------------------------------------------------
reg = pd.read_csv(os.path.join(ROOT, "data", "risk_register.csv")).dropna(subset=["crashes"])
rng = np.random.default_rng(11)
draws = {x.id: gamma.rvs(x.injury_crashes + 0.5, scale=1 / RO_MILES, size=20000, random_state=rng) * 100 for x in reg.itertuples()}
D = pd.DataFrame(draws)
ranks = D.rank(axis=1, ascending=False)
t12 = pd.DataFrame({"P_rank_1_pct": (ranks == 1).mean() * 100, "P_top_2_pct": (ranks <= 2).mean() * 100,
                    "median_rank": ranks.median()}).round(1)
t12.index.name = "id"; t12.to_csv(os.path.join(OUT, "table12_register_ranking.csv"))
S["P_H1_gt_H2"] = float((D["H1"] > D["H2"]).mean()); S["P_H3_gt_H4"] = float((D["H3"] > D["H4"]).mean())

json.dump(S, open(os.path.join(OUT, "supplementary_summary.json"), "w"), indent=1, default=float)
print(json.dumps(S, indent=1, default=float))
