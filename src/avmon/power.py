"""
Exposure needed to detect a regression, and tests needed for a scenario library.

One-sample (exact Poisson): the baseline rate lam0 is known well from long fleet
history; after a release we observe N events in M million miles and alarm if
P(N >= n | lam0*M) <= alpha. Power = P(N >= c | lam1*M), lam1 = (1+r)*lam0.

Two-sample (normal approximation on the log rate ratio): the new release and the
previous one each accumulate M million miles; Var(log ratio) ~ 1/(lam0 M) + 1/(lam1 M).
"""
import numpy as np
from scipy.stats import poisson, norm


def _critical(mu0, alpha):
    """Smallest c with P(N >= c | mu0) <= alpha."""
    return int(poisson.isf(alpha, mu0)) + 1


def power_one_sample(M, lam0, r, alpha=0.05):
    mu0, mu1 = lam0 * M, (1 + r) * lam0 * M
    c = _critical(mu0, alpha)
    return poisson.sf(c - 1, mu1)


def miles_to_detect_one_sample(lam0, r, power=0.8, alpha=0.05, M_max=1e5):
    """Smallest exposure (million miles) after which power stays >= target (exact Poisson)."""
    grid = np.geomspace(1e-3, M_max, 4000)
    p = np.array([power_one_sample(M, lam0, r, alpha) for M in grid])
    ok = p >= power
    if not ok.any():
        return np.inf
    # first M after which the (saw-tooth) power never falls below target again
    last_bad = np.where(~ok)[0]
    idx = last_bad[-1] + 1 if len(last_bad) else 0
    return float(grid[idx]) if idx < len(grid) else np.inf


def miles_to_detect_two_sample(lam0, r, power=0.8, alpha=0.05):
    """Million miles per release (each arm) to detect rate ratio 1+r; normal approx on log ratio."""
    lam1 = (1 + r) * lam0
    z = norm.ppf(1 - alpha) + norm.ppf(power)
    return float(z**2 * (1 / lam0 + 1 / lam1) / np.log(1 + r) ** 2)


def tests_for_zero_failures(p_max, confidence=0.95):
    """Scenario runs with zero failures needed to show P(failure) < p_max at the given confidence."""
    return int(np.ceil(np.log(1 - confidence) / np.log(1 - p_max)))
