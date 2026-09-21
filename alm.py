"""Translate forecast errors into ALM terms: NII surprise and implied hedge size.

Stylised book: a constant EUR 100bn of household savings per country (BALANCE_EUR
in config). Not the actual size of either market, a round number so the results
read directly: a 1 percentage point error for a full year is EUR 1bn of NII.
"""

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from config import BALANCE_EUR, FIG_DIR, MA_WINDOW, RESULTS_DIR


def nii_surprise(predicted: pd.Series, actual: pd.Series, balance: float = BALANCE_EUR) -> pd.Series:
    """Annual NII surprise in EUR from planning deposit costs with the model.

    Monthly interest cost = balance * rate / 100 / 12 (rates are % per annum).
    Positive = the bank paid savers less than it planned, so NII came in above plan.
    Negative = it paid more than planned, so NII came in below plan.
    """
    monthly = balance * (predicted - actual) / 100 / 12
    return monthly.groupby(monthly.index.year).sum()


def implied_hedge(beta: float, balance: float = BALANCE_EUR) -> float:
    """Balance that behaves like fixed-rate funding: (1 - beta) * balance.

    Pricing side only. A real deposit model combines this with a volume model of
    how much of the balance is stable and for how long.
    """
    return (1.0 - beta) * balance


def nii_table(forecasts: dict) -> pd.DataFrame:
    """Annual NII surprise in EUR millions for every (sample, model).

    The naive benchmark rows come through the same dict, so they are priced the
    same way as the models.
    """
    rows = {}
    for key, f in forecasts.items():
        rows[key] = nii_surprise(f["predicted"], f["actual"]) / 1e6
    table = pd.DataFrame(rows).T
    table.index.names = ["sample", "model"]
    table.columns.name = None

    # flag a partial final year
    months = next(iter(forecasts.values())).index
    last_year = months[-1].year
    n_last = int((months.year == last_year).sum())
    if n_last < 12:
        table = table.rename(columns={last_year: f"{last_year} ({n_last}m)"})

    table["total"] = table.sum(axis=1)
    return table


def hedge_table(results: pd.DataFrame) -> pd.DataFrame:
    """Implied hedge notional per sample for the two linear long-run specifications.

    The asymmetric models share the linear long run, so their hedge is identical.
    The level-dependent model is left out: it was not identified.
    """
    keep = results[results["model"].isin(["linear", f"linear MA{MA_WINDOW}"])]
    out = keep[["sample", "model", "pt@0%"]].rename(columns={"pt@0%": "beta"}).copy()
    out["hedge_eur_bn"] = implied_hedge(out["beta"]) / 1e9
    return out


def plot_nii(nii: pd.DataFrame, out_path) -> None:
    """Annual NII surprise for the models that tell the story, NL and BE side by side."""
    series = [
        ("pre-ZLB", "linear", "Linear, trained to 2013"),
        ("full", "linear", "Linear, trained to 2021"),
        ("full", "asymmetric", "Asymmetric, trained to 2021"),
    ]
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5), sharey=True)
    year_cols = [c for c in nii.columns if c != "total"]
    x = np.arange(len(year_cols))
    width = 0.8 / len(series)

    for ax, country in zip(axes, ["NL", "BE"]):
        for k, (sample, model, label) in enumerate(series):
            key = (f"{country} {sample}", model)
            if key not in nii.index:
                continue
            ax.bar(x + (k - 1) * width, nii.loc[key, year_cols] / 1e3, width, label=label)
        ax.axhline(0, color="black", lw=0.8)
        ax.set_xticks(x, [str(c) for c in year_cols])
        ax.set_title(country)
        ax.set_ylabel("NII surprise, EUR bn (EUR 100bn book)")
    axes[0].legend(frameon=False, fontsize=8)
    fig.text(0.5, -0.02, "Positive = paid savers less than planned (NII above plan). "
             "Negative = paid more than planned.", ha="center", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_path, dpi=150, bbox_inches="tight")


if __name__ == "__main__":
    from loader import load_data
    from models import run_all

    results, forecasts = run_all(load_data())
    if "error" in results:
        results = results[results["error"].isna()]

    nii = nii_table(forecasts)
    hedge = hedge_table(results)

    pd.set_option("display.width", 200)
    pd.set_option("display.float_format", lambda x: f"{x:8.0f}")
    print(f"ANNUAL NII SURPRISE, EUR millions, on a EUR {BALANCE_EUR / 1e9:.0f}bn savings book")
    print("positive = NII above plan (paid savers less than the model predicted)\n")
    print(nii.to_string())

    pd.set_option("display.float_format", lambda x: f"{x:8.2f}")
    print("\nIMPLIED HEDGE, (1 - beta) x balance, EUR bn")
    print(hedge.to_string(index=False))

    RESULTS_DIR.mkdir(exist_ok=True)
    FIG_DIR.mkdir(exist_ok=True)
    nii.to_csv(RESULTS_DIR / "nii_surprise.csv")
    hedge.to_csv(RESULTS_DIR / "implied_hedge.csv", index=False)
    plot_nii(nii, FIG_DIR / "fig_nii_surprise.png")
    print(f"\nSaved results to {RESULTS_DIR} and chart to {FIG_DIR / 'fig_nii_surprise.png'}")