"""
Baseline event rates and fleet exposure.

Rates are per million miles (IPMM) for Waymo rider-only operations, taken from
the companion analysis av-safety-bayesian-analysis (DOI 10.5281/zenodo.23732384):
NHTSA Standing General Order crash reports, 271.3 million rider-only miles through
June 2026. Posterior medians with a Jeffreys prior.

Each entry: (rate per million miles, source label).
"""

OUTCOMES = {
    "All reported crashes":     (1934 / 271.3, "PUBLISHED-DERIVED: 1,934 crashed vehicles / 271.3M mi (Repo 1)"),
    "Any-injury crashes":       (0.612,        "PUBLISHED-DERIVED: posterior median, 166 events (Repo 1, Table 2)"),
    "Airbag deployment":        (0.266,        "PUBLISHED-DERIVED: posterior median, 72 events (Repo 1, Table 2)"),
    "Serious injury or worse":  (0.023,        "PUBLISHED-DERIVED: posterior median, 6 events (Repo 1, Table 2)"),
}

# A frequent leading indicator (e.g. hard-braking or near-miss events flagged by
# on-board triggers). Not public: ASSUMED, illustrative only.
LEADING_INDICATOR = ("Leading indicator (assumed)", 100.0, "ASSUMED: 100 events per million miles")

# Fleet exposure. DERIVED: 542 crashes in Jan-Jun 2026 (Repo 1, Table 10) at
# 7.13 crashes per million miles -> about 76M miles in six months -> 12.7M miles per month.
FLEET_MILES_PER_MONTH = 542 / (1934 / 271.3) / 6.0          # million miles per month
FLEET_MILES_PER_WEEK = FLEET_MILES_PER_MONTH * 12 / 52       # million miles per week
