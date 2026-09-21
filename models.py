"""Deposit pass-through models: champion and challengers.

Notation
    d_t : client deposit rate (% per annum)
    m_t : reference market rate (% per annum), 3M Euribor or its moving average

Every model has the same two-step error correction structure.

    Step 1, long run:   d*(m_t) = equilibrium deposit rate given the market rate
                        u_t     = d_t - d*(m_t)          (deviation from equilibrium)
    Step 2, short run:  dd_t    = a + b * dm_t + gamma * u_{t-1} + e_t

Symmetric models use one speed gamma. The asymmetric models split it by the sign
of the gap, so correction can be faster when savers are overpaid than when underpaid:

    dd_t = a + b * dm_t + gamma_above * max(u_{t-1}, 0) + gamma_below * min(u_{t-1}, 0) + e_t

Long-run equilibrium by model:

    Linear, asymmetric:  d*(m) = theta0 + theta1 * m
    Level-dependent:     d*(m) = theta0 + beta(m) * m
                         beta(m) = b_min + delta / (1 + exp(-k * (m - m0)))

The MA variants use m = trailing average of 3M Euribor instead of 3M Euribor itself.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.optimize import curve_fit
from statsmodels.tsa.stattools import adfuller, coint

from config import EASE_START, HIKE_END, MA_WINDOW, NAIVE_BETA, RESULTS_DIR, TEST_START
from loader import get_sample

HAC_LAGS = 12   # Newey-West lags for monthly data


def _adf_p(s: pd.Series) -> float:
    """ADF p-value. Silences a statsmodels FutureWarning about its return type."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", FutureWarning)
        return float(adfuller(s, autolag="AIC")[1])


@dataclass
class ECMResult:
    name: str
    equilibrium: Callable[[np.ndarray], np.ndarray]   # d*(m)
    longrun_params: dict
    a: float
    b: float
    gamma_above: float    # speed when the deposit rate is above equilibrium
    gamma_below: float    # speed when below; equal to gamma_above in symmetric models
    coint_p: float
    n: int
    asym_p: float = float("nan")   # p-value of H0: gamma_above == gamma_below
    sr_model: object = field(default=None, repr=False)

    def pass_through(self, m: float, h: float = 1e-4) -> float:
        """Marginal long-run pass-through at rate level m: the slope of d*(m)."""
        up, down = self.equilibrium(np.array([m + h])), self.equilibrium(np.array([m - h]))
        return float((up - down)[0] / (2 * h))


# ---------------------------------------------------------------- diagnostics

def unit_root_report(df: pd.DataFrame) -> pd.DataFrame:
    """ADF p-values in levels and differences. An ECM needs both series I(1)."""
    rows = {}
    for col in ["d", "m"]:
        s = df[col]
        rows[col] = {"adf_p_level": _adf_p(s), "adf_p_diff": _adf_p(s.diff().dropna())}
    return pd.DataFrame(rows).T


# ---------------------------------------------------------------- shared step 2

def _fit_short_run(d: pd.Series, m: pd.Series, u: pd.Series, asymmetric: bool = False):
    """Short-run ECM with HAC standard errors."""
    u_lag = u.shift(1)
    cols = {"dd": d.diff(), "dm": m.diff()}
    if asymmetric:
        cols["u_above"] = u_lag.clip(lower=0)   # positive part of the gap
        cols["u_below"] = u_lag.clip(upper=0)   # negative part of the gap
    else:
        cols["u_lag"] = u_lag
    frame = pd.DataFrame(cols).dropna()
    X = sm.add_constant(frame.drop(columns="dd"))
    return sm.OLS(frame["dd"], X).fit(cov_type="HAC", cov_kwds={"maxlags": HAC_LAGS})


def _speeds(sr, asymmetric: bool) -> tuple[float, float, float]:
    """Return gamma_above, gamma_below and the p-value for their equality."""
    if asymmetric:
        g_above, g_below = float(sr.params["u_above"]), float(sr.params["u_below"])
        asym_p = float(np.squeeze(sr.t_test("u_above - u_below = 0").pvalue))
        return g_above, g_below, asym_p
    g = float(sr.params["u_lag"])
    return g, g, float("nan")


# ---------------------------------------------------------------- linear family

def fit_linear_ecm(df: pd.DataFrame, name: str = "linear", asymmetric: bool = False) -> ECMResult:
    d, m = df["d"], df["m"]

    # Step 1: long-run relationship
    lr = sm.OLS(d, sm.add_constant(m)).fit()
    theta0, theta1 = float(lr.params["const"]), float(lr.params["m"])
    u = lr.resid

    # Engle-Granger test: plain ADF critical values are wrong on estimated residuals
    coint_p = float(coint(d, m)[1])

    # Step 2: short-run dynamics
    sr = _fit_short_run(d, m, u, asymmetric=asymmetric)
    g_above, g_below, asym_p = _speeds(sr, asymmetric)

    def equilibrium(x):
        return theta0 + theta1 * np.asarray(x, dtype=float)

    return ECMResult(
        name=name,
        equilibrium=equilibrium,
        longrun_params={"theta0": theta0, "theta1": theta1},
        a=float(sr.params["const"]),
        b=float(sr.params["dm"]),
        gamma_above=g_above,
        gamma_below=g_below,
        coint_p=coint_p,
        n=len(df),
        asym_p=asym_p,
        sr_model=sr,
    )


def fit_asymmetric_ecm(df: pd.DataFrame, name: str = "asymmetric") -> ECMResult:
    """Linear long run, adjustment speed split by the sign of the gap."""
    return fit_linear_ecm(df, name=name, asymmetric=True)


# ---------------------------------------------------------------- level-dependent

def _beta(m, b_min, delta, k, m0):
    """Logistic pass-through: b_min at low rates, b_min + delta at high rates."""
    return b_min + delta / (1.0 + np.exp(-k * (m - m0)))


def _level_equilibrium(m, theta0, b_min, delta, k, m0):
    return theta0 + _beta(m, b_min, delta, k, m0) * m


def fit_level_dependent_ecm(df: pd.DataFrame, name: str = "level-dependent",
                            p0: list | None = None) -> ECMResult:
    d, m = df["d"], df["m"]

    # Step 1: nonlinear least squares. delta >= 0 means beta rises with the rate level.
    names = ["theta0", "b_min", "delta", "k", "m0"]
    p0 = p0 or [0.0, 0.1, 0.3, 2.0, 2.0]
    lower = [-2.0, 0.0, 0.0, 0.1, -1.0]
    upper = [5.0, 1.0, 1.0, 20.0, 6.0]
    params, _ = curve_fit(_level_equilibrium, m.to_numpy(float), d.to_numpy(float),
                          p0=p0, bounds=(lower, upper), maxfev=20_000)

    def equilibrium(x):
        return _level_equilibrium(np.asarray(x, dtype=float), *params)

    u = d - equilibrium(m)

    # Engle-Granger critical values assume a linear first step, so this is indicative only
    coint_p = _adf_p(u)

    sr = _fit_short_run(d, m, u)
    g_above, g_below, asym_p = _speeds(sr, asymmetric=False)

    return ECMResult(
        name=name,
        equilibrium=equilibrium,
        longrun_params=dict(zip(names, map(float, params))),
        a=float(sr.params["const"]),
        b=float(sr.params["dm"]),
        gamma_above=g_above,
        gamma_below=g_below,
        coint_p=coint_p,
        n=len(df),
        asym_p=asym_p,
        sr_model=sr,
    )


# ---------------------------------------------------------------- forecasting

def forecast_path(res: ECMResult, m_path: pd.Series, d0: float) -> pd.Series:
    """Dynamic forecast.

    m_path starts at the last observed month t0 and runs through the horizon.
    d0 is the observed deposit rate at t0. Every later step uses the model's own
    previous forecast, never realised deposit rates.
    """
    m = m_path.to_numpy(dtype=float)
    eq = res.equilibrium(m)
    d = np.empty(len(m))
    d[0] = d0
    for t in range(1, len(m)):
        gap = d[t - 1] - eq[t - 1]
        gamma = res.gamma_above if gap > 0 else res.gamma_below
        d[t] = d[t - 1] + res.a + res.b * (m[t] - m[t - 1]) + gamma * gap
    return pd.Series(d[1:], index=m_path.index[1:], name=res.name)


def forecast_oos(res: ECMResult, history: pd.DataFrame, start: str) -> pd.Series:
    """Forecast from `start` onward, anchored on the observed month just before it."""
    t0 = pd.Period(start, freq="M") - 1
    return forecast_path(res, history["m"].loc[t0:], float(history["d"].loc[t0]))


# ---------------------------------------------------------------- naive benchmarks

NAIVE_NO_CHANGE = "naive no-change"
NAIVE_FIXED_BETA = "naive fixed beta"
BENCHMARK_MODELS = (NAIVE_NO_CHANGE, NAIVE_FIXED_BETA)


def _anchor(history: pd.DataFrame, start: str) -> tuple[float, pd.Series]:
    """Last observed deposit rate before `start`, and the market path from there."""
    t0 = pd.Period(start, freq="M") - 1
    return float(history["d"].loc[t0]), history["m"].loc[t0:]


def naive_no_change(history: pd.DataFrame, start: str) -> pd.Series:
    """The deposit rate never moves from its last observed level. Nothing is estimated."""
    d0, m = _anchor(history, start)
    return pd.Series(d0, index=m.index[1:], name=NAIVE_NO_CHANGE)


def naive_fixed_beta(history: pd.DataFrame, start: str, beta: float = NAIVE_BETA) -> pd.Series:
    """The deposit rate moves a fixed fraction beta of the market rate change since t0.

    A flat pass-through assumption, with no dynamics and no estimation.
    """
    d0, m = _anchor(history, start)
    return pd.Series(d0 + beta * (m.to_numpy(float)[1:] - float(m.iloc[0])),
                     index=m.index[1:], name=NAIVE_FIXED_BETA)


# ---------------------------------------------------------------- run everything

MODELS = [
    # (label, fit function, reference rate column)
    ("linear",                    fit_linear_ecm,          "euribor3m"),
    (f"linear MA{MA_WINDOW}",     fit_linear_ecm,          f"euribor_ma{MA_WINDOW}"),
    ("level-dependent",           fit_level_dependent_ecm, "euribor3m"),
    ("asymmetric",                fit_asymmetric_ecm,      "euribor3m"),
    (f"asymmetric MA{MA_WINDOW}", fit_asymmetric_ecm,      f"euribor_ma{MA_WINDOW}"),
]

SAMPLES = [
    # (label, country, window, start override)
    ("NL pre-ZLB", "nl", "pre_zlb", None),
    ("NL full",    "nl", "full",    None),
    ("NL matched", "nl", "full",    "2006-10"),   # NL on the BE window
    ("BE pre-ZLB", "be", "pre_zlb", None),
    ("BE full",    "be", "full",    None),
]

# The benchmarks estimate nothing, so there is one of each per country, not per sample.
BENCHMARK_SAMPLES = [
    # (label, country)
    ("NL benchmark", "nl"),
    ("BE benchmark", "be"),
]


def _rmse(e: pd.Series) -> float:
    return float(np.sqrt((e ** 2).mean()))


def _error_cols(pred: pd.Series, actual: pd.Series) -> dict:
    """Forecast errors over the test window, split into the hiking and easing phases."""
    err = pred - actual                # positive = predicted too high
    up, down = err.loc[:HIKE_END], err.loc[EASE_START:]
    return {
        "rmse": _rmse(err),
        "bias": float(err.mean()),
        "rmse_up": _rmse(up),
        "bias_up": float(up.mean()),
        "rmse_down": _rmse(down),
        "bias_down": float(down.mean()),
    }


def run_all(data: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Fit every model on every sample and forecast the test window.

    Returns the results table and a dict {(sample, model): DataFrame of actual and
    predicted deposit rates}, which alm.py uses for the NII translation.
    """
    rows, forecasts = [], {}
    for s_label, country, window, start in SAMPLES:
        for m_label, fit, market in MODELS:
            row = {"sample": s_label, "model": m_label}
            try:
                train = get_sample(data, country, window=window, start=start, market=market)
                test = get_sample(data, country, window="test", market=market)
                full = get_sample(data, country, window="full", start=start, market=market)
                history = pd.concat([full, test])

                res = fit(train, name=m_label)
                pred = forecast_oos(res, history, TEST_START)

                row.update({
                    "n": res.n,
                    "pt@0%": res.pass_through(0.0),
                    "pt@4%": res.pass_through(4.0),
                    "g_above": res.gamma_above,
                    "g_below": res.gamma_below,
                    "asym_p": res.asym_p,
                    "coint_p": res.coint_p,
                    **_error_cols(pred, test["d"]),
                })
                forecasts[(s_label, m_label)] = pd.DataFrame({"actual": test["d"], "predicted": pred})
            except Exception as exc:   # report and keep going
                row["error"] = f"{type(exc).__name__}: {exc}"
            rows.append(row)

    b_rows, b_forecasts = run_benchmarks(data)
    forecasts.update(b_forecasts)
    table = pd.concat([pd.DataFrame(rows), pd.DataFrame(b_rows)], ignore_index=True)
    table["n"] = table["n"].astype("Int64")   # benchmark rows have no n, keep the rest integer
    return table, forecasts


def run_benchmarks(data: pd.DataFrame) -> tuple[list[dict], dict]:
    """Score the two naive benchmarks on the test window, once per country.

    Same anchor and same error columns as the models, so the rows line up in the
    out-of-sample table. Neither benchmark is estimated on anything.
    """
    rows, forecasts = [], {}
    for s_label, country in BENCHMARK_SAMPLES:
        test = get_sample(data, country, window="test")
        history = pd.concat([get_sample(data, country, window="full"), test])
        for m_label, naive in [(NAIVE_NO_CHANGE, naive_no_change),
                               (NAIVE_FIXED_BETA, naive_fixed_beta)]:
            pred = naive(history, TEST_START)
            rows.append({"sample": s_label, "model": m_label,
                         **_error_cols(pred, test["d"])})
            forecasts[(s_label, m_label)] = pd.DataFrame({"actual": test["d"], "predicted": pred})
    return rows, forecasts


ESTIMATION_COLS = ["sample", "model", "n", "pt@0%", "pt@4%", "g_above", "g_below", "asym_p", "coint_p"]
FORECAST_COLS = ["sample", "model", "rmse", "bias", "rmse_up", "bias_up", "rmse_down", "bias_down"]


if __name__ == "__main__":
    from loader import load_data

    table, _ = run_all(load_data())

    pd.set_option("display.width", 200)
    pd.set_option("display.float_format", lambda x: f"{x:7.3f}")

    if "error" in table:
        failed = table[table["error"].notna()]
        if len(failed):
            print("FAILED FITS\n", failed[["sample", "model", "error"]].to_string(index=False), "\n")
        table = table[table["error"].isna()].drop(columns="error")

    estimated = table[~table["model"].isin(BENCHMARK_MODELS)]

    print("ESTIMATION (trained on data up to the end of each sample)")
    print(estimated[ESTIMATION_COLS].to_string(index=False))
    print("\nOUT-OF-SAMPLE, from", TEST_START, "(error = predicted - actual, percentage points)")
    print(table[FORECAST_COLS].to_string(index=False))

    RESULTS_DIR.mkdir(exist_ok=True)
    table.to_csv(RESULTS_DIR / "model_results.csv", index=False)
    print(f"\nSaved {RESULTS_DIR / 'model_results.csv'}")