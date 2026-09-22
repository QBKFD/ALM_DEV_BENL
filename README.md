# Deposit pass-through models, tested out of sample on NL and BE savings

Personal project using public ECB data. It does not use, describe or reflect any
employer's data, models or methodology.

## The question

Banks price non-maturing deposits with pass-through models, usually an error
correction model estimated on a long history. Between 2000 and 2021 that history
was almost entirely a falling and then a floored rate environment. In 2022 the ECB
hiked from -0.5% to 4% in about a year, and from mid-2024 it cut again.

So I asked one question. If you had estimated the standard model on data ending in
2021, how wrong would it have been about Dutch and Belgian household savings rates
over the next four and a half years, and what would that have cost in NII terms?

Nothing here is refitted on data after the training window. Every forecast is
dynamic: each month uses the model's own previous prediction, never the realised
deposit rate.

## Data

All series come from the ECB Data Portal, pulled by `data_pull.py` into
`data/raw.csv`. I do not re-download in normal runs.

| Series | Code |
|---|---|
| NL household savings deposits | `MIR.M.NL.B.L23.D.R.A.2250.EUR.N` |
| BE household savings deposits | `MIR.M.BE.B.L23.D.R.A.2250.EUR.N` |
| NL household overnight deposits | `MIR.M.NL.B.L21.A.R.A.2250.EUR.N` |
| BE household overnight deposits | `MIR.M.BE.B.L21.A.R.A.2250.EUR.N` |
| 3M Euribor | `FM.M.U2.EUR.RT.MM.EURIBOR3MD_.HSTA` |

Deposit rates run to 2026-07. The NL sample starts in 2000-01. The BE sample starts
in 2006-10, because BE reporting has a gap from 2003-01 to 2006-09 and the
definition may break at the start of the MIR statistics.

## Method

Every model has the same two-step error correction structure. Step one estimates a
long-run equilibrium deposit rate given the market rate. Step two regresses the
monthly change in the deposit rate on the change in the market rate and on last
month's deviation from equilibrium, with Newey-West standard errors at 12 lags.

I test the ECM because it is the standard industry specification, so the point is
to see how it behaves rather than to find the best possible forecast. Failed
cointegration tests are part of the result rather than a reason to drop it. The
conclusions rest on a single rate cycle, so they are one observation, not evidence
about rate cycles in general. The split between the hiking phase and the easing
phase at June 2024 was chosen after looking at the forecast chart, not before.

Specifications:

| Model | Long run |
|---|---|
| linear | `d* = theta0 + theta1 * m` |
| linear MA60 | same, with `m` = 60 month trailing average of 3M Euribor |
| level-dependent | `d* = theta0 + beta(m) * m`, with `beta` logistic in the rate level |
| asymmetric | linear long run, adjustment speed split by the sign of the gap |
| asymmetric MA60 | same, on the moving average reference rate |

Samples:

| Label | Country | Estimation window |
|---|---|---|
| NL pre-ZLB | NL | 2000-01 to 2013-12 |
| NL full | NL | 2000-01 to 2021-12 |
| NL matched | NL | 2006-10 to 2021-12, the BE window |
| BE pre-ZLB | BE | 2006-10 to 2013-12 |
| BE full | BE | 2006-10 to 2021-12 |

The test window is 2022-01 to 2026-07 for every model. The hiking phase runs to
2024-06 and the easing phase from 2024-07.

### Naive benchmarks

Two benchmarks anchored on the last observed month before the test window, 2021-12.
Neither is estimated on anything, so there is one of each per country rather than
one per sample.

- **naive no-change**: the deposit rate never moves from its 2021-12 level.
- **naive fixed beta**: the deposit rate moves a fixed fraction of the change in 3M
  Euribor since 2021-12, with no dynamics.

The fixed beta benchmark is run across a grid rather than at one value. Any single
beta would have to be chosen, and I could only choose it by looking at what
pass-through turned out to be after 2022. That is look-ahead bias, and it would
flatter the benchmark. So `config.py` holds `NAIVE_BETAS`, 0.10 to 0.70 in steps of
0.05, `naive_fixed_beta` has no default beta, and the result is read as a range.

### Counting models that beat a benchmark

All such counts use distinct specifications only. The level-dependent model
converges back onto the linear fit in three of the five samples and reproduces it
to three decimals, so counting both would count one specification twice. Every
count below drops the level-dependent rows, which leaves 12 specifications for NL
and 8 for BE.

### NII translation

`alm.py` prices each forecast error on a stylised book of EUR 100bn of household
savings per country, held constant. That is not the size of either market. It is a
round number so a 1 percentage point error held for a year reads as EUR 1bn of NII.
Positive means the bank paid savers less than the model said it would, so NII came
in above plan.

## Results

Error is predicted minus actual, in percentage points. Positive bias means the
model predicted a higher savings rate than banks actually paid. `beta` is the
long-run pass-through at a 0% market rate. `Coint p` is the Engle-Granger p-value, and for the
level-dependent model it is an ADF p-value on the residuals of a nonlinear first
step, so it is indicative only.

| Sample | Model | beta | Coint p | RMSE | Bias | RMSE hiking | RMSE easing | NII total, EUR m |
|---|---|---|---|---|---|---|---|---|
| NL pre-ZLB | linear | 0.29 | 0.36 | 0.852 | +0.807 | 0.674 | 1.025 | +3,700 |
| NL pre-ZLB | linear MA60 | 0.58 | 0.06 | 0.441 | +0.053 | 0.374 | 0.509 | +242 |
| NL pre-ZLB | level-dependent | 0.00 | 0.15 | 0.895 | +0.855 | 0.734 | 1.056 | +3,919 |
| NL pre-ZLB | asymmetric | 0.29 | 0.36 | 0.934 | -0.779 | 0.797 | 1.076 | -3,572 |
| NL pre-ZLB | asymmetric MA60 | 0.58 | 0.06 | 0.505 | +0.139 | 0.336 | 0.652 | +639 |
| NL full | linear | 0.57 | 0.36 | 0.265 | +0.046 | 0.250 | 0.282 | +211 |
| NL full | linear MA60 | 0.72 | 0.05 | 0.565 | -0.356 | 0.663 | 0.418 | -1,631 |
| NL full | level-dependent | 0.57 | 0.17 | 0.265 | +0.046 | 0.250 | 0.282 | +211 |
| NL full | asymmetric | 0.57 | 0.36 | 0.553 | -0.422 | 0.560 | 0.545 | -1,932 |
| NL full | asymmetric MA60 | 0.72 | 0.05 | 0.568 | -0.346 | 0.669 | 0.416 | -1,584 |
| NL matched | linear | 0.53 | 0.72 | 0.371 | -0.208 | 0.453 | 0.235 | -951 |
| NL matched | linear MA60 | 0.76 | 0.19 | 0.580 | -0.389 | 0.682 | 0.425 | -1,784 |
| NL matched | level-dependent | 0.53 | 0.48 | 0.371 | -0.208 | 0.453 | 0.235 | -951 |
| NL matched | asymmetric | 0.53 | 0.72 | 0.819 | -0.687 | 0.785 | 0.859 | -3,149 |
| NL matched | asymmetric MA60 | 0.76 | 0.19 | 0.580 | -0.388 | 0.684 | 0.424 | -1,779 |
| BE pre-ZLB | linear | 0.24 | 0.54 | 0.586 | +0.556 | 0.622 | 0.538 | +2,548 |
| BE pre-ZLB | linear MA60 | 0.52 | 0.74 | 0.274 | -0.032 | 0.224 | 0.323 | -146 |
| BE pre-ZLB | level-dependent | 0.00 | 0.45 | 0.616 | +0.588 | 0.662 | 0.556 | +2,696 |
| BE pre-ZLB | asymmetric | 0.24 | 0.54 | 0.534 | +0.506 | 0.547 | 0.519 | +2,321 |
| BE pre-ZLB | asymmetric MA60 | 0.52 | 0.74 | 0.326 | +0.141 | 0.083 | 0.475 | +646 |
| BE full | linear | 0.37 | 0.22 | 0.413 | +0.382 | 0.419 | 0.406 | +1,753 |
| BE full | linear MA60 | 0.46 | 0.39 | 0.295 | +0.088 | 0.126 | 0.415 | +405 |
| BE full | level-dependent | 0.37 | 0.08 | 0.413 | +0.382 | 0.419 | 0.406 | +1,753 |
| BE full | asymmetric | 0.37 | 0.22 | 0.421 | +0.390 | 0.429 | 0.412 | +1,787 |
| BE full | asymmetric MA60 | 0.46 | 0.39 | 0.303 | +0.131 | 0.084 | 0.440 | +600 |
| NL benchmark | naive no-change |  |  | 1.232 | -1.065 | 1.028 | 1.440 | -4,882 |
| BE benchmark | naive no-change |  |  | 0.608 | -0.515 | 0.458 | 0.748 | -2,362 |

Full output is in `results/model_results.csv` and `results/nii_surprise.csv`. The
fixed beta grid has its own table, `results/benchmark_grid.csv`, further down.
Charts are in `figures/`.

### What the table shows

The Engle-Granger test never finds cointegration at 5% (lowest p-value 0.054).
That is across the 20 linear-family rows, where the test is the right one. The null
is no cointegration, and it is never rejected, so on its own terms the
specification does not hold on this data, in any sample, for either country. I
report the models anyway, because that is the specification banks use.

The training window matters more than the functional form. For NL, moving from the
pre-ZLB window to the full window cuts the linear model's RMSE from 0.852 to 0.265,
and cuts the NII total from EUR +3.7bn to EUR +0.2bn. The same change for BE cuts
RMSE from 0.586 to 0.413. Picking a different model within a window moves the
numbers much less than picking a different window.

The asymmetric split is never significant. Across the 10 asymmetric rows, the
lowest p-value on the equality of the two adjustment speeds is 0.058, and the rest
range up to 0.93. Estimating the split still changes the forecast a lot, and
usually for the worse. NL pre-ZLB goes from 0.852 to 0.934 and flips the NII sign,
and NL matched goes from 0.371 to 0.819. The extra parameter picks up noise.

The level-dependent model adds nothing. On NL full, NL matched and BE full it
converges back onto the linear fit and reproduces it to three decimals. On the two
pre-ZLB samples it puts pass-through at zero at a 0% rate, which is the logistic
fitting the floor rather than a level effect. `alm.py` leaves it out of the hedge
table for that reason.

Errors reverse sign between the two phases in most NL rows. `NL full linear` is
0.084 too low during the hikes and 0.202 too high during the cuts. A single RMSE
hides that, which is why the table splits the phases and why `figures/fig_forecasts.png`
is worth looking at next to it.

## How the models compare with the naive benchmarks

### No-change

Every distinct specification beats it, 12 of 12 in NL and 8 of 8 in BE. Assuming
savings rates never move at all is worse than any model here. That is the low bar,
and the models clear it.

### Fixed beta, across the grid

`results/benchmark_grid.csv` has the full table and
`figures/fig_benchmark_grid.png` plots it. Both curves are U-shaped, NL bottoming
at beta 0.35 and BE at 0.15.

| Country | Benchmark's own best | Best model | Median model | Betas beating the median model |
|---|---|---|---|---|
| NL | 0.389 at beta 0.35 | 0.265 | 0.567 | 0.25 to 0.45 (5 of 13) |
| BE | 0.243 at beta 0.15 | 0.274 | 0.370 | 0.10 to 0.25 (4 of 13) |

The two countries give different answers, so I do not summarise them together.

**NL: only the best models clear the benchmark, not the field.** No beta in the
grid beats the best NL model: at its own optimum of 0.35 the benchmark scores
0.389, against 0.265 for `NL full linear`. Most NL specifications do not clear it.
Across the competitive band, betas 0.25 to 0.45, only 2 to 4 of the 12 NL
specifications beat the benchmark, so 8 to 10 of them lose to it. A fixed beta
anywhere in that band also beats the median NL model at 0.567. The top of the NL
field is worth more than a rule of thumb. The middle of it is not.

**BE: the models are beaten outright.** At beta 0.15 the benchmark scores 0.243,
better than the best BE specification at 0.274. At beta 0.15 and 0.20 no estimated
BE specification beats it on RMSE at all. A one-number rule with no dynamics
forecast Belgian savings rates better than every model I fitted.

There is one qualification on the BE result, and it matters. Every beta I could
have estimated from pre-2022 BE data runs from 0.24 to 0.52. The winning range,
0.15 to 0.20, sits below all of it. So a rule better than every BE model existed,
but nothing in the pre-2022 data pointed at it. Reading 0.15 off the grid is only
possible because I can see the answer.

### Using each sample's own beta

The grid still leaves the choice of beta open. The test that closes it is to give
the naive rule the beta that sample itself estimated, which uses no post-2021
information, and compare it against that sample's own four specifications.

| Sample | Its estimated beta | Naive RMSE at that beta | Its four specifications | Result |
|---|---|---|---|---|
| NL pre-ZLB | 0.29 | 0.437 | 0.441, 0.505, 0.852, 0.934 | naive beats all four |
| NL full | 0.57 | 0.717 | 0.265, 0.553, 0.565, 0.568 | models beat it, 4 of 4 |
| NL matched | 0.53 | 0.717 | 0.371, 0.580, 0.580, 0.819 | models beat it, 3 of 4 |
| BE pre-ZLB | 0.24 | 0.335 | 0.274, 0.326, 0.534, 0.586 | models beat it, 2 of 4 |
| BE full | 0.37 | 0.611 | 0.295, 0.303, 0.413, 0.421 | models beat it, 4 of 4 |

In four of the five samples the estimated models beat a naive rule built from their
own pass-through. The exception is NL trained to 2013, where the naive rule at
0.437 beats all four specifications and the closest of them, MA60, loses by 0.004.

My reading is that the error correction machinery earns its place, but narrowly,
and only once it is estimated on data that includes the ZLB years. The NL pre-ZLB
sample is the clearest failure: everything it learned from 2000 to 2013 was worth
less than its own single pass-through number applied as a straight line. Against
that, the BE result shows a better rule existed that no amount of careful
estimation on pre-2022 data would have found.

## Limitations

The test covers one rate cycle, so every conclusion is one observation. The phase
split at June 2024 was chosen after seeing the forecasts, which means the phase
split results are descriptive, not a test. The fixed beta grid runs from 0.10 to
0.70, which is itself a choice, though it is a wide one and both curves turn well
inside it. The NII figures use a constant EUR 100bn
book and no volume model, so they scale a pricing error and nothing else. A real
deposit model pairs this with a model of how much balance stays and for how long.
Savings rates here are the ECB MIR outstanding-amounts rate, which is an average
across products and includes promotional and loyalty structures that the models
have no way to see.

## Running it

```
uv sync
uv run pytest
uv run python models.py         # estimation, out-of-sample and benchmark grid tables
uv run python alm.py            # NII surprise and implied hedge, writes results/ and figures/
uv run python plots.py          # rate history chart
uv run python forecast_plot.py  # actual against forecast paths
```

`data_pull.py` re-downloads `data/raw.csv` from the ECB. Everything else reads the
saved file, so the results reproduce without network access.

Tests run on simulated data with known parameters, so they do not need `data/raw.csv`.

## Files

| File | What it does |
|---|---|
| `config.py` | paths, sample windows, `NAIVE_BETAS`, book size. Nothing is hardcoded elsewhere |
| `data_pull.py` | fetches the ECB series into `data/raw.csv` |
| `loader.py` | loads the panel, builds the moving average, cuts clean samples |
| `models.py` | the ECM family, the naive benchmarks, the fixed beta grid, and the out-of-sample run |
| `alm.py` | NII surprise and implied hedge |
| `plots.py`, `forecast_plot.py` | charts |
| `tests/test_models.py` | tests on simulated data |
