"""Verification tests.   python tests/test_core.py"""
import os, sys, math
import numpy as np
from scipy.stats import poisson
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from avmon.power import power_one_sample, miles_to_detect_one_sample, tests_for_zero_failures, miles_to_detect_two_sample
from avmon.monitor import run_length, calibrate_cusum, bayes_prob_increase, PoissonCUSUM, arl_markov, shewhart_limit, shewhart_arl


def test_rule_of_three():
    # 95% confidence, zero failures: n ~ 3/p
    assert tests_for_zero_failures(0.01, 0.95) == 299
    assert abs(tests_for_zero_failures(0.001, 0.95) * 0.001 - 3.0) < 0.01


def test_false_alarm_rate_is_controlled():
    for M in (1.0, 10.0, 100.0):
        assert power_one_sample(M, 0.6, 0.0) <= 0.05 + 1e-12


def test_power_reaches_target_at_returned_exposure():
    M = miles_to_detect_one_sample(0.6, 0.5)
    for f in (1.0, 1.2, 2.0):
        assert power_one_sample(M * f, 0.6, 0.5) >= 0.8


def test_exposure_scales_inversely_with_rate():
    a, b = miles_to_detect_two_sample(1.0, 0.5), miles_to_detect_two_sample(10.0, 0.5)
    assert abs(a / b - 10.0) < 1e-9


def test_cusum_calibration_hits_target_arl():
    m0 = 1.8
    h, k = calibrate_cusum(m0, 0.25, arl0_target=100, seed=3)
    arl = run_length(m0, k, h, n_sims=4000, t_max=2000, seed=4).mean()
    assert 85 < arl < 115, arl


def test_cusum_detects_faster_when_rate_rises():
    m0 = 1.8
    h, k = calibrate_cusum(m0, 0.25, arl0_target=100, seed=3)
    assert run_length(1.5 * m0, k, h, 3000, 2000, seed=5).mean() < 0.4 * run_length(m0, k, h, 3000, 2000, seed=6).mean()


def test_cusum_reset_counts_alarms():
    c = PoissonCUSUM(1.0, 0.5, 2.0)
    s, alarms = c.path([10, 0, 10], reset=True)
    assert alarms == [1, 3] and s[0] >= 2.0


def test_bayes_probability_is_half_at_baseline_for_large_counts():
    p = bayes_prob_increase(10000, 10000.0, 1.0)
    assert 0.45 < p < 0.55


def test_markov_chain_arl_matches_simulation():
    # Brook-Evans Markov chain and Monte Carlo are independent ways to get the same run length
    for m0, h in ((1.8, 8.0), (0.3, 4.0)):
        k = (1.25 * m0 - m0) / np.log(1.25)
        mk = arl_markov(m0, k, h)
        mc = run_length(m0, k, h, n_sims=6000, t_max=20000, seed=8).mean()
        assert abs(mc - mk) / mk < 0.05, (m0, mk, mc)


def test_shewhart_limit_meets_false_alarm_target():
    for m0 in (0.07, 1.8, 20.8):
        c = shewhart_limit(m0, 260)
        assert shewhart_arl(m0, c) >= 260 and shewhart_arl(m0, c - 1) < 260


if __name__ == "__main__":
    for name, f in list(globals().items()):
        if name.startswith("test_"):
            f(); print("PASS", name)
