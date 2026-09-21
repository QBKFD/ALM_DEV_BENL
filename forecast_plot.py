"""Actual deposit rates from 2022 against each model's dynamic forecast.

Rows: training window (pre-ZLB, full). Columns: country (NL, BE).
RMSE hides compensating errors; the paths show them.
"""

import matplotlib.pyplot as plt
import pandas as pd

from config import FIG_DIR, MA_WINDOW, TEST_START
from loader import get_sample, load_data
from models import fit_asymmetric_ecm, fit_linear_ecm, forecast_oos

SHOW_FROM = "2019-01"   # a little history before the test window for context

MODELS = [
    # (label, fit function, reference rate column, line style)
    ("linear", fit_linear_ecm, "euribor3m", "-"),
    (f"linear MA{MA_WINDOW}", fit_linear_ecm, f"euribor_ma{MA_WINDOW}", "--"),
    ("asymmetric", fit_asymmetric_ecm, "euribor3m", ":"),
]
WINDOWS = [("pre_zlb", "Trained to 2013"), ("full", "Trained to 2021")]
COUNTRIES = ["nl", "be"]


def main() -> None:
    data = load_data()
    test_start = pd.Period(TEST_START, freq="M").to_timestamp()

    fig, axes = plt.subplots(len(WINDOWS), len(COUNTRIES), figsize=(12, 8),
                             sharex=True, sharey=True)

    for i, (window, w_label) in enumerate(WINDOWS):
        for j, country in enumerate(COUNTRIES):
            ax = axes[i, j]

            # actual deposit rate and Euribor, from SHOW_FROM to the last published month
            test = get_sample(data, country, window="test")
            actual = data[f"{country}_savings"].loc[SHOW_FROM:test.index[-1]]
            euribor = data["euribor3m"].loc[SHOW_FROM:test.index[-1]]
            ax.plot(euribor.index.to_timestamp(), euribor, color="grey", lw=1, label="3M Euribor")
            ax.plot(actual.index.to_timestamp(), actual, color="black", lw=2, label="Actual savings rate")

            for label, fit, market, ls in MODELS:
                train = get_sample(data, country, window=window, market=market)
                history = pd.concat([
                    get_sample(data, country, window="full", market=market),
                    get_sample(data, country, window="test", market=market),
                ])
                res = fit(train, name=label)
                pred = forecast_oos(res, history, TEST_START)
                ax.plot(pred.index.to_timestamp(), pred, ls=ls, lw=1.6, label=label)

            ax.axvline(test_start, color="grey", ls=":", lw=1)
            ax.axhline(0, color="grey", lw=0.5)
            ax.set_title(f"{country.upper()}, {w_label}")
            if j == 0:
                ax.set_ylabel("% per annum")

    axes[0, 0].legend(frameon=False, fontsize=8, loc="upper left")
    fig.tight_layout()

    out = FIG_DIR / "fig_forecasts.png"
    out.parent.mkdir(exist_ok=True)
    fig.savefig(out, dpi=150)
    print(f"Saved {out}")
    plt.show()


if __name__ == "__main__":
    main()