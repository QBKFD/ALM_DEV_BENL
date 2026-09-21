import pandas as pd
from config import RAW_CSV
BASE = "https://data-api.ecb.europa.eu/service/data"

SERIES = {
    "be_savings": "MIR.M.BE.B.L23.D.R.A.2250.EUR.N",
    "nl_savings": "MIR.M.NL.B.L23.D.R.A.2250.EUR.N",
    "be_current": "MIR.M.BE.B.L21.A.R.A.2250.EUR.N",
    "nl_current": "MIR.M.NL.B.L21.A.R.A.2250.EUR.N",
    "euribor3m":  "FM.M.U2.EUR.RT.MM.EURIBOR3MD_.HSTA",
}
START = "1994-01"         # first month kept in the saved file
OUT = RAW_CSV


def ecb(key: str) -> pd.Series:
    """Fetch one ECB series as a sorted monthly Series."""
    flow, rest = key.split(".", 1)
    df = pd.read_csv(f"{BASE}/{flow}/{rest}?format=csvdata")
    idx = pd.PeriodIndex(df["TIME_PERIOD"], freq="M")
    values = pd.to_numeric(df["OBS_VALUE"], errors="coerce").to_numpy()
    return pd.Series(values, index=idx, name=key).sort_index()


def build_panel(series: dict, start: str) -> pd.DataFrame:
    """Pull all series, put them on one full monthly grid, trim to start."""
    data = pd.concat({k: ecb(v) for k, v in series.items()}, axis=1).sort_index()
    full = pd.period_range(data.index.min(), data.index.max(), freq="M")
    data = data.reindex(full)
    data.index.name = "period"
    return data.loc[start:]


def coverage(data: pd.DataFrame) -> pd.DataFrame:
    """First/last valid month per series and number of missing months in between."""
    out = pd.DataFrame({
        "first": data.apply(lambda s: s.first_valid_index()),
        "last":  data.apply(lambda s: s.last_valid_index()),
        "n_obs": data.notna().sum(),
    })
    out["span"] = [(l - f).n + 1 for f, l in zip(out["first"], out["last"])]
    out["gaps"] = out["span"] - out["n_obs"]
    return out


def gap_blocks(s: pd.Series) -> list[tuple]:
    """Contiguous blocks of missing months, only between first and last valid value."""
    s = s.loc[s.first_valid_index():s.last_valid_index()]
    missing = s[s.isna()].index
    if len(missing) == 0:
        return []
    ords = pd.Series(missing.asi8, index=missing)
    block = (ords.diff() != 1).cumsum()
    return [(g.index[0], g.index[-1], len(g)) for _, g in ords.groupby(block)]


if __name__ == "__main__":
    data = build_panel(SERIES, START)
    data.to_csv(OUT)
    print(f"Saved {len(data)} months x {data.shape[1]} series to {OUT}\n")

    print(coverage(data), "\n")
    for col in data.columns:
        for start, end, n in gap_blocks(data[col]):
            print(f"{col}: gap {start} to {end} ({n} months)")