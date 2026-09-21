import pandas as pd

from config import MA_WINDOW, PRE_ZLB_END, RAW_CSV, START, TEST_START, TRAIN_END


def load_data(path=RAW_CSV) -> pd.DataFrame:
    data = pd.read_csv(path, index_col="period")
    data.index = pd.PeriodIndex(data.index, freq="M")
    # Challenger A reference rate: trailing average of 3M Euribor.
    # Needs MA_WINDOW months of Euribor history before the first sample month.
    data[f"euribor_ma{MA_WINDOW}"] = data["euribor3m"].rolling(MA_WINDOW).mean()
    return data


def get_sample(data: pd.DataFrame, country: str, product: str = "savings",
               window: str = "full", start: str | None = None,
               market: str = "euribor3m") -> pd.DataFrame:
    """
    Return a clean two-column frame: d (deposit rate) and m (reference market rate).

    window: "pre_zlb" = start to PRE_ZLB_END
            "full"    = start to TRAIN_END
            "test"    = TEST_START to last available deposit rate
    start:  override the country start, e.g. "2006-10" to run NL on the BE window
    market: "euribor3m" or the moving-average column, e.g. "euribor_ma60"
    """
    df = pd.DataFrame({
        "d": data[f"{country}_{product}"],
        "m": data[market],
    })

    first = start or START[country]
    if window == "pre_zlb":
        df = df.loc[first:PRE_ZLB_END]
    elif window == "full":
        df = df.loc[first:TRAIN_END]
    elif window == "test":
        df = df.loc[TEST_START:]
        df = df.loc[:df["d"].last_valid_index()]   # drop the publication-lag month
    else:
        raise ValueError(f"unknown window: {window}")

    if df.isna().any().any():
        raise ValueError(f"{country} {product} {window} ({market}): missing values inside the window")
    return df