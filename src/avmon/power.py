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


def expected_events_to_detect(r, power=0.8, alpha=0.05, confirm=500):
    """Expected baseline events mu0 = lam0*M after which the exact test's power never falls below `power`.

    Exact, without a grid. Because counts are whole numbers, the critical count c steps up by one at
    mu0 = J_n, where P(N >= n | J_n) = alpha (J_n = gammaincinv(n, alpha)). Between two steps power rises
    smoothly; just after each step it drops (the saw-tooth). The lowest power of the tooth with critical
    count n is therefore at its left edge, P(N >= n | (1+r) J_{n-1}). We find the last tooth whose
    lowest point is below the target and return the point inside it where power reaches the target.
    P(N >= n | mu) = gammainc(n, mu) (regularized lower incomplete gamma function).
    """
    from scipy.special import gammainc, gammaincinv
    last, n = None, 2
    while True:
        bottom = gammainc(n, (1 + r) * gammaincinv(n - 1, alpha))
        if bottom < power:
            last = n
        elif last is not None and n > last + confirm:
            break
        n += 1
    J_prev, J_n = gammaincinv(last - 1, alpha), gammaincinv(last, alpha)
    x = gammaincinv(last, power) / (1 + r)        # where power reaches the target inside that tooth
    return float(min(max(x, J_prev), J_n)) * (1 + 1e-9)   # tiny margin against floating-point round-off


def miles_to_detect_one_sample(lam0, r, power=0.8, alpha=0.05):
    """Smallest exposure (million miles) after which power stays >= target (exact Poisson test).
    The answer depends on lam0 only through mu0 = lam0 * M (see expected_events_to_detect)."""
    return expected_events_to_detect(r, power, alpha) / lam0


def miles_to_detect_two_sample(lam0, r, power=0.8, alpha=0.05):
    """Million miles per release (each arm) to detect rate ratio 1+r; normal approx on log ratio."""
    lam1 = (1 + r) * lam0
    z = norm.ppf(1 - alpha) + norm.ppf(power)
    return float(z**2 * (1 / lam0 + 1 / lam1) / np.log(1 + r) ** 2)


def tests_for_zero_failures(p_max, confidence=0.95):
    """Scenario runs with zero failures needed to show P(failure) < p_max at the given confidence."""
    return int(np.ceil(np.log(1 - confidence) / np.log(1 - p_max)))
