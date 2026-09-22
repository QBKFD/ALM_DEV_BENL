from pathlib import Path

# Paths. Every file reads locations from here.
ROOT        = Path(__file__).resolve().parent
DATA_DIR    = ROOT / "data"
RAW_CSV     = DATA_DIR / "raw.csv"
FIG_DIR     = ROOT / "figures"
RESULTS_DIR = ROOT / "results"

# Sample windows. Every modelling file reads from here, nothing is hardcoded elsewhere.
START = {
    "nl": "2000-01",
    "be": "2006-10",   # BE reporting gap 2003-01 to 2006-09, possible definition break at MIR start
}

PRE_ZLB_END = "2013-12"   # before deposit rates hit the floor
TRAIN_END   = "2021-12"   # last month used for estimation
TEST_START  = "2022-01"   # out-of-sample: the hiking cycle
HIKE_END    = "2024-06"   # last month before the ECB's first cut
EASE_START  = "2024-07"

MA_WINDOW = 60            # months, reference rate for the moving-average models

# Naive benchmark: the deposit rate moves a fixed fraction of the change in 3M Euribor.
# No single fraction can be picked without looking at the test period, so the benchmark
# runs across this grid and the result is read as a range of betas, never one number.
NAIVE_BETAS = [round(0.10 + 0.05 * i, 2) for i in range(13)]   # 0.10 to 0.70

# ALM translation: stylised savings book, constant balance, same size for both countries
BALANCE_EUR = 100e9