"""
Sequential field monitoring.

Poisson CUSUM (Lucas, 1985) on weekly event counts X_t with expected count
m0 = lam0 * miles_per_week in control and m1 = (1+r) m0 for the regression we
want to catch quickly:
    k = (m1 - m0) / ln(m1/m0),  S_t = max(0, S_{t-1} + X_t - k),  alarm if S_t >= h.
h is calibrated by simulation for a target in-control average run length (ARL0),
i.e. the mean time between false alarms.

Bayesian check: P(lam_new > lam0 | data) with a Jeffreys Gamma(N + 1/2, M) posterior.
"""
import numpy as np
from scipy.stats import gamma


class PoissonCUSUM:
    def __init__(self, m0, r, h):
        self.m0, self.m1 = m0, (1 + r) * m0
        self.k = (self.m1 - self.m0) / np.log(self.m1 / self.m0)
        self.h = h

    def path(self, x, reset=False):
        """CUSUM statistic per period. With reset=True the statistic restarts at 0 after
        each alarm (an investigation found the cause or cleared it). Returns (S, alarm periods, 1-based)."""
        s, out, alarms = 0.0, [], []
        for t, xi in enumerate(x, start=1):
            s = max(0.0, s + xi - self.k)
            out.append(s)
            if s >= self.h:
                alarms.append(t)
                if reset:
                    s = 0.0
        return np.array(out), alarms


def run_length(m_true, k, h, n_sims=4000, t_max=2000, seed=0):
    """Monte Carlo run lengths (weeks to first alarm) for weekly Poisson(m_true) counts."""
    rng = np.random.default_rng(seed)
    S = np.zeros(n_sims)
    rl = np.full(n_sims, t_max, float)
    alive = np.ones(n_sims, bool)
    for t in range(1, t_max + 1):
        x = rng.poisson(m_true, n_sims)
        S = np.where(alive, np.maximum(0.0, S + x - k), S)
        hit = alive & (S >= h)
        rl[hit] = t
        alive &= ~hit
        if not alive.any():
            break
    return rl


def calibrate_cusum(m0, r, arl0_target=104, seed=1):
    """Find h giving in-control ARL ~ arl0_target weeks (bisection on simulated ARL)."""
    k = ((1 + r) * m0 - m0) / np.log(1 + r)
    lo, hi = 0.0, 50.0 + 20 * k
    for _ in range(30):
        h = 0.5 * (lo + hi)
        arl = run_length(m0, k, h, n_sims=1500, t_max=int(arl0_target * 8), seed=seed).mean()
        if arl < arl0_target:
            lo = h
        else:
            hi = h
    return 0.5 * (lo + hi), k


def bayes_prob_increase(n_events, miles, lam0):
    """Posterior P(rate > lam0) with a Jeffreys prior: Gamma(n + 1/2, rate=miles)."""
    return float(gamma.sf(lam0, n_events + 0.5, scale=1.0 / miles))


def arl_markov(m_true, k, h, steps_per_unit=None, max_states=5000):
    """Average run length of a Poisson CUSUM by the Markov-chain method (Brook and Evans, 1972).

    The CUSUM statistic is placed on a grid of width 1/steps_per_unit; k is rounded to that
    grid. States 0..H-1 are in control; reaching H (= h on the grid) is an alarm.
    ARL from the zero state = [(I - R)^-1 1]_0. Independent check of the simulated run lengths.
    """
    from scipy.stats import poisson
    if steps_per_unit is None:
        # pick the grid that represents k most exactly, within the state budget
        cands = [m for m in range(100, 1201) if h * m <= max_states] or [100]
        steps_per_unit = min(cands, key=lambda m: abs(k * m - round(k * m)) / 1.0)
    m = steps_per_unit
    K, H = int(round(k * m)), int(np.ceil(h * m - 1e-9))
    xmax = int(poisson.isf(1e-12, m_true)) + 2
    px = poisson.pmf(np.arange(xmax + 1), m_true)
    R = np.zeros((H, H))
    for i in range(H):
        j = i + np.arange(xmax + 1) * m - K
        j = np.maximum(j, 0)
        ok = j < H
        np.add.at(R[i], j[ok], px[ok])
    arl = np.linalg.solve(np.eye(H) - R, np.ones(H))
    return float(arl[0])


def shewhart_limit(m0, arl0_target):
    """Smallest weekly count c with P(X >= c | m0) <= 1/arl0_target (one-sided Shewhart c-chart)."""
    from scipy.stats import poisson
    c = int(poisson.isf(1.0 / arl0_target, m0)) + 1
    return c


def shewhart_arl(m_true, c):
    from scipy.stats import poisson
    p = poisson.sf(c - 1, m_true)
    return float(1.0 / p) if p > 0 else np.inf
