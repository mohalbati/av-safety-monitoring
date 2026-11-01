"""
Run the whole analysis: detectability, test coverage, CUSUM design, a simulated
release timeline, a scored risk register and an automatically generated
one-page release health report.      python scripts/run_all.py   (about 1 minute)
"""
import os, sys, json, html
import numpy as np, pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy.stats import gamma, beta
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from avmon.rates import OUTCOMES, LEADING_INDICATOR, FLEET_MILES_PER_WEEK, FLEET_MILES_PER_MONTH
from avmon.power import miles_to_detect_one_sample, miles_to_detect_two_sample, tests_for_zero_failures
from avmon.monitor import PoissonCUSUM, calibrate_cusum, run_length, bayes_prob_increase

ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT = os.path.join(ROOT, "results"); os.makedirs(OUT, exist_ok=True)
RO_MILES = 271.3
COL = {"All reported crashes": "#2A78D6", "Any-injury crashes": "#EB6834", "Airbag deployment": "#7A4FB0",
       "Serious injury or worse": "#B3261E", "Leading indicator (assumed)": "#1E7A4C"}
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
metrics = {k: v[0] for k, v in OUTCOMES.items()}
metrics[LEADING_INDICATOR[0]] = LEADING_INDICATOR[1]
summary = {"fleet_miles_per_week_M": FLEET_MILES_PER_WEEK, "fleet_miles_per_month_M": FLEET_MILES_PER_MONTH}

# 1. Detectability: exposure and calendar time to detect a regression -----------------
R = [0.10, 0.25, 0.50, 1.00]
rows = []
for name, lam in metrics.items():
    for r in R:
        M1 = miles_to_detect_one_sample(lam, r)
        M2 = miles_to_detect_two_sample(lam, r)
        rows.append(dict(metric=name, rate_per_M_mi=round(lam, 4), regression=f"+{int(r*100)}%",
                         miles_M_vs_known_baseline=round(M1, 2), weeks_vs_known_baseline=round(M1 / FLEET_MILES_PER_WEEK, 1),
                         miles_M_release_vs_release=round(M2, 1), weeks_release_vs_release=round(M2 / FLEET_MILES_PER_WEEK, 1)))
det = pd.DataFrame(rows); det.to_csv(os.path.join(OUT, "table1_detectability.csv"), index=False)
fig, ax = plt.subplots(figsize=(9.5, 4.6))
for name in metrics:
    d = det[det.metric == name]
    wk = [miles_to_detect_one_sample(metrics[name], r) / FLEET_MILES_PER_WEEK for r in R]
    ax.plot([int(r * 100) for r in R], wk, "o-", color=COL[name], label=name, lw=2)
ax.set_yscale("log"); ax.set_xticks([10, 25, 50, 100]); ax.set_xticklabels(["+10%", "+25%", "+50%", "+100%"])
for y, lab in ((4, "1 month"), (52, "1 year"), (520, "10 years")):
    ax.axhline(y, color="#9AA5B3", lw=0.8, ls="--"); ax.text(101, y * 1.08, lab, fontsize=8, color="#5B6472", ha="right")
ax.set_xlabel("Size of the regression (increase in event rate)"); ax.set_ylabel("Weeks of whole-fleet driving to detect\n(80% power, 5% false-alarm, log scale)")
ax.set_title("How long field data needs to catch a regression", loc="left", fontsize=11)
ax.legend(fontsize=8, frameon=False, loc="upper left", bbox_to_anchor=(1.01, 1.0)); fig.tight_layout()
fig.savefig(os.path.join(OUT, "fig1_detectability.png"), dpi=170); plt.close(fig)

# 2. Test coverage for a scenario library ------------------------------------------------
cov = pd.DataFrame([dict(target_failure_prob=p, confidence=c, zero_failure_runs_needed=tests_for_zero_failures(p, c))
                    for p in (0.1, 0.01, 0.001, 0.0001) for c in (0.9, 0.95, 0.99)])
cov.to_csv(os.path.join(OUT, "table2_test_coverage.csv"), index=False)

# 3. CUSUM design per metric: weekly counts, tuned for +25%, 5-year mean interval between false alarms per metric
DESIGN_R, ARL0 = 0.25, 260
cus = []
designs = {}
for i, (name, lam) in enumerate(metrics.items()):
    m0 = lam * FLEET_MILES_PER_WEEK
    h, k = calibrate_cusum(m0, DESIGN_R, arl0_target=ARL0, seed=10 + i)
    designs[name] = (m0, h)
    row = dict(metric=name, expected_weekly_count=round(m0, 3), k=round(k, 3), h=round(h, 2),
               ARL0_weeks=round(run_length(m0, k, h, 3000, 6000, seed=100 + i).mean(), 0))
    for r in (0.25, 0.5, 1.0):
        rl = run_length((1 + r) * m0, k, h, 3000, 4000, seed=200 + i)
        row[f"weeks_to_alarm_+{int(r*100)}%_median"] = float(np.median(rl))
    cus.append(row)
cus = pd.DataFrame(cus); cus.to_csv(os.path.join(OUT, "table3_cusum_design.csv"), index=False)

# 4. Simulated release timeline: 104 weeks, releases every 4 weeks, regression at week 60 ------
rng = np.random.default_rng(2026)
WEEKS, T_REG, RATIO = 104, 60, 1.5
timeline = {}
fig, axes = plt.subplots(len(metrics), 1, figsize=(9, 8.5), sharex=True)
for ax, (name, lam) in zip(axes, metrics.items()):
    m0, h = designs[name]
    mult = np.where(np.arange(1, WEEKS + 1) >= T_REG, RATIO, 1.0)
    x = rng.poisson(m0 * mult)
    c = PoissonCUSUM(m0, DESIGN_R, h); s, alarms = c.path(x, reset=True)
    false_al = [a for a in alarms if a < T_REG]; true_al = [a for a in alarms if a >= T_REG]
    post = x[T_REG - 1:]
    p_inc = bayes_prob_increase(int(post.sum()), FLEET_MILES_PER_WEEK * len(post), lam)
    timeline[name] = dict(false_alarms_before_change=false_al, first_detection_week=true_al[0] if true_al else None,
                          detection_delay_weeks=(true_al[0] - T_REG + 1) if true_al else None,
                          alarms_after_change=len(true_al), final_S_over_h=float(s[-1] / h),
                          events_after_change=int(post.sum()), expected_before=float(m0 * len(post)),
                          bayes_P_rate_up=p_inc)
    for w in range(4, WEEKS + 1, 4):
        ax.axvline(w, color="#E6EAEF", lw=0.6, zorder=0)
    ax.plot(np.arange(1, WEEKS + 1), np.minimum(s / h, 1.0), color=COL[name], lw=1.6)
    ax.axhline(1, color="#B3261E", lw=1, ls="--"); ax.axvline(T_REG, color="#5B6472", lw=1)
    for a_ in false_al:
        ax.plot(a_, 1.0, "v", color="#9AA5B3", ms=7)
    for a_ in true_al[:1]:
        ax.plot(a_, 1.0, "v", color="#B3261E", ms=8)
    ax.set_ylabel("S / h", fontsize=8); ax.set_ylim(0, 1.35)
    lab = name + (f"  ·  detected week {true_al[0]} ({true_al[0] - T_REG + 1} wk after change)" if true_al else "  ·  not detected")
    lab += f"  ·  false alarms: {len(false_al)}"
    ax.text(1, 1.3, lab, fontsize=8.5, va="top")
axes[0].set_title("Simulated two years of 4-weekly releases: a +50% regression enters at week 60 (grey line).\nCUSUM restarts after each alarm; red = detection, grey = false alarm", loc="left", fontsize=10.5)
axes[-1].set_xlabel("Week (light lines = 4-weekly releases)")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig2_release_timeline.png"), dpi=170); plt.close(fig)
json.dump(timeline, open(os.path.join(OUT, "timeline_demo.json"), "w"), indent=1)

# 5. Scored risk register (ISO 31000: identify -> analyse -> evaluate -> treat -> monitor) ----
reg = pd.read_csv(os.path.join(ROOT, "data", "risk_register.csv"))
q = lambda a, p: gamma.ppf(p, a, scale=1 / RO_MILES) * 100
recs = []
for x in reg.itertuples():
    if pd.notna(x.crashes):
        n, k = int(x.crashes), int(x.injury_crashes)
        recs.append(dict(crash_rate_per_M_mi=round(n / RO_MILES, 3),
                         P_injury_given_crash_pct=round(100 * beta.median(k + 0.5, n - k + 0.5), 1),
                         injury_crashes_per_100M_mi_median=round(q(k + 0.5, 0.5), 1),
                         injury_crashes_per_100M_mi_5pct=round(q(k + 0.5, 0.05), 1),
                         injury_crashes_per_100M_mi_95pct=round(q(k + 0.5, 0.95), 1)))
    else:
        recs.append(dict(crash_rate_per_M_mi=None, P_injury_given_crash_pct=None, injury_crashes_per_100M_mi_median=None,
                         injury_crashes_per_100M_mi_5pct=None, injury_crashes_per_100M_mi_95pct=None))
reg = pd.concat([reg, pd.DataFrame(recs)], axis=1)
reg.to_csv(os.path.join(OUT, "table4_risk_register_scored.csv"), index=False)
d = reg.dropna(subset=["injury_crashes_per_100M_mi_median"]).sort_values("injury_crashes_per_100M_mi_median")
fig, ax = plt.subplots(figsize=(8.5, 4.2))
yy = np.arange(len(d))
ax.errorbar(d.injury_crashes_per_100M_mi_median, yy,
            xerr=[d.injury_crashes_per_100M_mi_median - d.injury_crashes_per_100M_mi_5pct,
                  d.injury_crashes_per_100M_mi_95pct - d.injury_crashes_per_100M_mi_median],
            fmt="o", color="#2A78D6", ecolor="#2A78D6", capsize=3)
import textwrap
ax.set_yticks(yy); ax.set_yticklabels([f"{i}  " + "\n      ".join(textwrap.wrap(t, 34)) for i, t in zip(d.id, d.hazard)], fontsize=8.5)
for yv, p in zip(yy, d.P_injury_given_crash_pct):
    ax.text(ax.get_xlim()[1] if False else d.injury_crashes_per_100M_mi_95pct.max() * 1.05, yv, f"P(injury | crash) {p:.0f}%", va="center", fontsize=8, color="#5B6472")
ax.set_xlabel("Injury crashes per 100 million miles (median and 90% interval)")
ax.set_title("Risk register: data-based hazards ranked by injury-crash rate", loc="left", fontsize=11)
fig.tight_layout(); fig.savefig(os.path.join(OUT, "fig3_risk_register.png"), dpi=170); plt.close(fig)

p_fa = {n: float(np.mean(run_length(designs[n][0], ((1 + DESIGN_R) * designs[n][0] - designs[n][0]) / np.log(1 + DESIGN_R),
                                   designs[n][1], 4000, 105, seed=300 + j) <= 104)) for j, n in enumerate(metrics)}
fw = 1 - np.prod([1 - v for v in p_fa.values()])

# 6. Automatically generated one-page release health report --------------------------------
def status(t):
    if t["alarms_after_change"]:
        return ("RED", "#B3261E")
    return ("AMBER", "#C27A00") if t["final_S_over_h"] >= 0.5 else ("GREEN", "#1E7A4C")

lines = []
for name, t in timeline.items():
    st, colr = status(t)
    lines.append((name, st, colr, t))
red = [n for n, st, _, _ in lines if st == "RED"]
det25 = det[det.regression == "+25%"].set_index("metric")
top = reg.dropna(subset=["injury_crashes_per_100M_mi_median"]).sort_values("injury_crashes_per_100M_mi_median", ascending=False)
gaps = reg[reg.status == "Data gap"]
bluf = (f"{len(red)} of {len(lines)} monitored metrics alarmed after a simulated +50% regression entered at week {T_REG}: "
        + ", ".join(red) + f". Slowest to alarm: {max(red, key=lambda n: timeline[n]['detection_delay_weeks'])} ({max(timeline[n]['detection_delay_weeks'] for n in red)} weeks). Recommend holding the next release and bisecting the week-{T_REG} release.") if red else \
       "No metric is in alarm; continue the release cadence."
rows_html = "".join(
    f"<tr><td>{html.escape(n)}</td><td><b style='color:{c}'>{st}</b></td>"
    f"<td>{t['first_detection_week'] or '–'}</td><td>{len(t['false_alarms_before_change'])}</td>"
    f"<td>{t['events_after_change']} vs {t['expected_before']:.1f}</td><td>{t['bayes_P_rate_up']:.3f}</td></tr>"
    for n, st, c, t in lines)
det_html = "".join(f"<tr><td>{html.escape(m)}</td><td>{det25.loc[m,'weeks_vs_known_baseline']:,.1f}</td></tr>" for m in metrics)
top_html = "".join(f"<tr><td>{x.id}</td><td>{html.escape(x.hazard)}</td><td>{x.injury_crashes_per_100M_mi_median:.1f} "
                   f"({x.injury_crashes_per_100M_mi_5pct:.1f}–{x.injury_crashes_per_100M_mi_95pct:.1f})</td><td>{html.escape(x.status)}</td></tr>"
                   for x in top.head(3).itertuples())
gap_html = "".join(f"<li>{x.id}: {html.escape(x.hazard)} — owner {html.escape(x.owner_team)}</li>" for x in gaps.itertuples())
page = f"""<!doctype html><html><head><meta charset='utf-8'><title>Release health report (demo)</title>
<style>body{{font-family:Arial,sans-serif;max-width:860px;margin:24px auto;color:#16202C;font-size:14px}}
h1{{font-size:22px;margin:0}} h2{{font-size:15px;margin:18px 0 6px;color:#1F5FAF}} table{{border-collapse:collapse;width:100%}}
td,th{{border-bottom:1px solid #DDE1E6;padding:4px 6px;text-align:left}} th{{background:#EEF2F7}} .bluf{{background:#FFF4EC;border-left:4px solid #EB6834;padding:8px 12px}}
.note{{color:#5B6472;font-size:12px}}</style></head><body>
<h1>Release health report — simulated fleet, week {WEEKS}</h1>
<p class='note'>Generated automatically by scripts/run_all.py. Simulated data on baseline rates from public NHTSA SGO reports (Repo 1); not Waymo internal data.</p>
<div class='bluf'><b>Bottom line.</b> {html.escape(bluf)}</div>
<h2>1. Monitoring status (Poisson CUSUM tuned for +25%, one false alarm per metric every 5 years on average)</h2>
<table><tr><th>Metric</th><th>Status</th><th>First alarm after week {T_REG}</th><th>False alarms before</th><th>Events since week {T_REG} vs expected</th><th>P(rate increased)</th></tr>{rows_html}</table>
<p class='note'>With five metrics each tuned to one false alarm per five years, the chance of at least one false alarm somewhere in two years is {fw:.0%}: every alarm needs a fast, cheap triage step.</p>
<h2>2. What field data can and cannot catch</h2>
<p>Weeks of whole-fleet driving ({FLEET_MILES_PER_WEEK:.1f}M miles/week) to detect a +25% regression with 80% power:</p>
<table><tr><th>Metric</th><th>Weeks</th></tr>{det_html}</table>
<p>Serious-injury regressions cannot be caught from field outcomes on any release timescale: release gating must rely on scenario testing and leading indicators.</p>
<h2>3. Top data-based risks (injury crashes per 100M miles, 90% interval)</h2>
<table><tr><th>ID</th><th>Hazard</th><th>Rate</th><th>Treatment status</th></tr>{top_html}</table>
<h2>4. Data gaps to close</h2><ul>{gap_html}</ul>
<h2>5. Recommended actions</h2><ol><li>Hold the next release; bisect the week-{T_REG} release with the scenario library.</li>
<li>Add the alarmed scenario types to the regression test set.</li><li>Instrument leading indicators for H6–H8 so they can be monitored.</li></ol>
</body></html>"""
open(os.path.join(OUT, "release_health_report.html"), "w").write(page)


summary.update(dict(
    serious_25pct_weeks=float(det25.loc["Serious injury or worse", "weeks_vs_known_baseline"]),
    serious_25pct_years=float(det25.loc["Serious injury or worse", "weeks_vs_known_baseline"]) / 52,
    anyinj_25pct_weeks=float(det25.loc["Any-injury crashes", "weeks_vs_known_baseline"]),
    allcrash_25pct_weeks=float(det25.loc["All reported crashes", "weeks_vs_known_baseline"]),
    lead_25pct_weeks=float(det25.loc[LEADING_INDICATOR[0], "weeks_vs_known_baseline"]),
    tests_1pct_95=tests_for_zero_failures(0.01, 0.95), timeline=timeline,
    p_false_alarm_2y=p_fa, familywise_false_alarm_2y=fw))
json.dump(summary, open(os.path.join(OUT, "summary.json"), "w"), indent=1, default=float)
print(det.to_string(index=False)); print(cus.to_string(index=False)); print(json.dumps(timeline, indent=1))
