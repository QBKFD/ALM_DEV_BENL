"""Tests on simulated data with known parameters, so they run without the ECB file."""

import numpy as np
import pandas as pd
import pytest

from alm import implied_hedge, nii_surprise
from config import NAIVE_BETA
from loader import get_sample
from models import (ECMResult, fit_asymmetric_ecm, fit_linear_ecm, forecast_oos,
                    forecast_path, naive_fixed_beta, naive_no_change)


def simulate(n=500, theta0=0.5, theta1=0.4, b=0.05, g_above=-0.1, g_below=-0.1, seed=0):
    """Deposit rate following a known ECM around a random-walk market rate."""
    rng = np.random.default_rng(seed)
    idx = pd.period_range("1980-01", periods=n, freq="M")
    m = 2.0 + np.cumsum(rng.normal(0, 0.15, n))
    d = np.empty(n)
    d[0] = theta0 + theta1 * m[0]
    for t in range(1, n):
        gap = d[t - 1] - (theta0 + theta1 * m[t - 1])
        g = g_above if gap > 0 else g_below
        d[t] = d[t - 1] + b * (m[t] - m[t - 1]) + g * gap + rng.normal(0, 0.03)
    return pd.DataFrame({"d": d, "m": m}, index=idx)


def manual_result(g_above=-0.2, g_below=-0.2, theta0=0.5, theta1=0.4):
    """ECMResult with hand-set parameters, to test forecast mechanics exactly."""
    return ECMResult(name="manual", equilibrium=lambda x: theta0 + theta1 * np.asarray(x, float),
                     longrun_params={}, a=0.0, b=0.0, gamma_above=g_above,
                     gamma_below=g_below, coint_p=0.0, n=0)


# ---------------------------------------------------------------- estimation

def test_linear_ecm_recovers_known_parameters():
    res = fit_linear_ecm(simulate())
    assert res.longrun_params["theta1"] == pytest.approx(0.4, abs=0.05)
    assert res.gamma_above == pytest.approx(-0.1, abs=0.05)
    assert res.coint_p < 0.05


def test_pass_through_in_unit_interval_and_speed_negative():
    res = fit_linear_ecm(simulate())
    assert 0 <= res.pass_through(0.0) <= 1
    assert res.gamma_above < 0 and res.gamma_below < 0


def test_symmetric_model_has_one_speed():
    res = fit_linear_ecm(simulate())
    assert res.gamma_above == res.gamma_below
    assert np.isnan(res.asym_p)


def test_asymmetric_ecm_detects_asymmetry():
    res = fit_asymmetric_ecm(simulate(n=800, g_above=-0.3, g_below=-0.03, seed=1))
    assert res.gamma_above < res.gamma_below
    assert res.asym_p < 0.05


# ---------------------------------------------------------------- forecasting

def test_forecast_converges_to_equilibrium():
    m_path = pd.Series(3.0, index=pd.period_range("2022-01", periods=200, freq="M"))
    pred = forecast_path(manual_result(), m_path, d0=0.0)
    assert pred.iloc[-1] == pytest.approx(0.5 + 0.4 * 3.0, abs=1e-6)


def test_asymmetric_forecast_uses_the_right_speed():
    res = manual_result(g_above=-0.5, g_below=0.0)
    m_path = pd.Series(3.0, index=pd.period_range("2022-01", periods=12, freq="M"))
    eq = 0.5 + 0.4 * 3.0
    above = forecast_path(res, m_path, d0=eq + 1.0)
    below = forecast_path(res, m_path, d0=eq - 1.0)
    assert above.iloc[-1] < eq + 0.01                    # overpaid savers: corrected down
    assert below.iloc[-1] == pytest.approx(eq - 1.0)     # underpaid: no correction


def test_forecast_uses_no_realised_deposit_rates():
    data = simulate()
    train, history = data.iloc[:400], data.copy()
    res = fit_linear_ecm(train)
    start = str(data.index[400])
    base = forecast_oos(res, history, start)

    history.loc[history.index[400]:, "d"] += 5.0   # change every realised d in the test window
    assert forecast_oos(res, history, start).equals(base)


# ---------------------------------------------------------------- naive benchmarks

SPLIT = 400   # the simulated month the benchmarks are anchored just before


def naive_setup(data=None):
    """Simulated history plus the start month, so the anchor is data.index[SPLIT - 1]."""
    data = simulate() if data is None else data
    return data, str(data.index[SPLIT])


def test_naive_no_change_holds_the_last_observed_rate():
    data, start = naive_setup()
    pred = naive_no_change(data, start)
    assert list(pred.index) == list(data.index[SPLIT:])
    assert (pred == data["d"].iloc[SPLIT - 1]).all()


def test_naive_fixed_beta_passes_through_the_market_move():
    data, start = naive_setup()
    pred = naive_fixed_beta(data, start, beta=0.3)
    d0, m0 = data["d"].iloc[SPLIT - 1], data["m"].iloc[SPLIT - 1]
    expected = d0 + 0.3 * (data["m"].iloc[SPLIT:] - m0)
    pd.testing.assert_series_equal(pred, expected, check_names=False)


def test_naive_fixed_beta_defaults_to_the_configured_beta():
    data, start = naive_setup()
    pd.testing.assert_series_equal(naive_fixed_beta(data, start),
                                   naive_fixed_beta(data, start, beta=NAIVE_BETA))


def test_naive_fixed_beta_with_zero_beta_is_no_change():
    data, start = naive_setup()
    pd.testing.assert_series_equal(naive_fixed_beta(data, start, beta=0.0),
                                   naive_no_change(data, start), check_names=False)


def test_naive_benchmarks_use_no_realised_deposit_rates():
    data, start = naive_setup()
    base = naive_no_change(data, start), naive_fixed_beta(data, start)

    data.loc[data.index[SPLIT]:, "d"] += 5.0   # change every realised d in the test window
    assert naive_no_change(data, start).equals(base[0])
    assert naive_fixed_beta(data, start).equals(base[1])


def test_naive_benchmarks_need_no_estimation_window():
    """Only the anchor month and the market path matter, not the history before it."""
    data, start = naive_setup()
    short = data.iloc[SPLIT - 1:]
    pd.testing.assert_series_equal(naive_no_change(short, start), naive_no_change(data, start))
    pd.testing.assert_series_equal(naive_fixed_beta(short, start), naive_fixed_beta(data, start))


# ---------------------------------------------------------------- data and ALM

def test_get_sample_rejects_missing_values_inside_window():
    idx = pd.period_range("2015-01", "2022-06", freq="M")
    data = pd.DataFrame({"nl_savings": 1.0, "euribor3m": 1.0}, index=idx)
    data.loc["2018-03", "nl_savings"] = np.nan
    with pytest.raises(ValueError, match="missing values"):
        get_sample(data, "nl", window="full", start="2015-01")


def test_nii_surprise_scale_and_sign():
    idx = pd.period_range("2022-01", "2022-12", freq="M")
    actual = pd.Series(1.0, index=idx)
    predicted = actual + 1.0                     # model 1pp too high for a full year
    out = nii_surprise(predicted, actual, balance=100e9)
    assert out.loc[2022] == pytest.approx(1e9)   # paid 1bn less than planned: NII above plan


def test_implied_hedge():
    assert implied_hedge(0.3, balance=100e9) == pytest.approx(70e9)