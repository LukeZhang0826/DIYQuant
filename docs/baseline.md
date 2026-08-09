# Baseline: what the strategy actually does

The number every later change has to beat. Produced by `python scripts/validate.py`,
recorded 2026-08-01 against the local parquet store (503 tickers, 2018-01-02 to
2026-07-22).

Read the walk-forward number. It is the only one on this page that comes from data
the parameters had not seen.

## Headline (out-of-sample, walk-forward)

Rolling 3-year train / 1-year test, parameters chosen per window on training Sharpe,
scored only on the test slice that follows. Test spans 2021-01-04 to 2026-01-08.

| | Strategy | Equal-weight universe |
|---|---|---|
| Total return | **+93.3%** | **+112.1%** |
| CAGR | +14.1% | |
| Sharpe (ann.) | 0.52 | |
| Max drawdown | -48.9% | |

**The strategy underperforms buying the universe and doing nothing, by 18.7
percentage points, while taking a 49% drawdown to do it.** That is the finding.
It is not a bug and it is not a reason to stop: it is the first honest measurement
this project has ever had, and it is what the rest of the roadmap gets judged
against.

Per window, strategy vs benchmark:

| Train | Test | Chosen | Strategy | Universe |
|---|---|---|---|---|
| 2018-01..2020-12 | 2021 | 10/50 | -1.7% | +32.6% |
| 2019-01..2021-12 | 2022 | 10/50 | **+35.8%** | -10.1% |
| 2020-01..2023-01 | 2023 | 10/50 | +21.2% | +21.7% |
| 2021-01..2024-01 | 2024 | 10/50 | -6.5% | +23.4% |
| 2022-01..2025-01 | 2025 | 10/50 | +27.8% | +18.4% |

The shape is textbook trend-following: it earns its keep when the market falls
(2022, +35.8% against a -10.1% market) and bleeds against strong bull years. That
is a real property worth knowing, not noise, and it is the strongest argument for
the market-neutral direction in `roadmap-vision.md`.

## The configured parameters were never the good ones

The walk-forward chose **10/50 in all five windows**, never the 20/50 in
`config/settings.yaml`. Five independent training slices agreeing is a finding
rather than a fluke. Over the same 2021-2026 span:

| Config | Return |
|---|---|
| Fixed 20/50 (configured) | +19.4% |
| Fixed 10/50 | +93.3% |
| Walk-forward (picked 10/50 each window) | +93.3% |

Changing the default to 10/50 is tempting and should wait: that comparison is
itself in-sample over 2021-2026, which is exactly the reasoning this harness
exists to stop. The walk-forward number already reflects using 10/50, so nothing
is being lost by leaving the config alone until there is a reason beyond one
period.

## How much optimism the naive version was adding

`--in-sample` over the full 2018-2026 history with fixed 20/50: **-15.1%** against
a **+276.1%** universe, max drawdown -76.5%, hit rate 43.9% of 567 positions.

Different period from the walk-forward, so do not compare the two directly. It is
recorded because it is what a single-pass backtest would have reported, and the
gap between "-15.1%, looks broken" and "+93.3%, still loses to the index" is the
difference measurement makes.

## Ablations: which parts of the pipeline earn their place

Selection, hysteresis and the short leg were all built on reasoning, because until
this harness existed there was nothing to check them against. `python scripts/ablate.py`
runs each one out-of-sample. Benchmark is +112.1% in every row.

| Config | Return | Excess | Sharpe | Beta | Alpha | MaxDD |
|---|---|---|---|---|---|---|
| **baseline** 5 pos, hyst 10 | +93.3% | -18.7% | 0.52 | -0.66 | +35.9% | -48.9% |
| 1 position | +46.8% | -65.3% | 0.57 | -0.79 | +68.6% | -91.6% |
| 10 positions | +52.3% | -59.7% | 0.41 | -0.58 | +25.2% | -38.1% |
| 20 positions | +15.5% | -96.6% | 0.25 | -0.37 | +13.8% | -43.5% |
| 50 positions | -28.5% | -140.5% | -0.19 | -0.21 | -0.7% | -53.4% |
| hysteresis off | +163.0% | +50.9% | 0.64 | -0.64 | +41.6% | -49.3% |
| hysteresis 20 | +100.9% | -11.2% | 0.53 | -0.63 | +36.0% | -47.0% |
| long only | +805.6% | +693.5% | 1.29 | +1.20 | +32.5% | -36.1% |
| zero costs | +114.1% | +2.1% | 0.56 | -0.66 | +38.0% | -47.5% |

Volatility sizing was measured later, on 2026-08-08, after the live account halted. Those
rows carry a `gross` column, the mean sum of absolute weights, because they are the first
configs that can choose to hold less than the whole account. Every row above is at 1.00 by
construction, and the baseline was re-run alongside these and reproduced to the decimal.

| Config | Return | Excess | Sharpe | Beta | Alpha | MaxDD | Gross |
|---|---|---|---|---|---|---|---|
| **baseline** flat 20% cap | +93.3% | -18.7% | 0.52 | -0.66 | +35.9% | -48.9% | 1.00 |
| vol-scaled 0.3%/day | +77.0% | -35.1% | 0.77 | -0.13 | +14.8% | -17.3% | 0.41 |
| vol-scaled 0.4%/day (shipped) | +107.1% | -5.0% | 0.78 | -0.17 | +19.8% | -22.6% | 0.54 |
| vol-scaled 0.5%/day | +132.4% | +20.4% | 0.77 | -0.23 | +24.1% | -27.1% | 0.64 |
| vol-scaled 0.8%/day | +113.2% | +1.1% | 0.60 | -0.45 | +29.1% | -36.8% | 0.85 |

### Volatility sizing earns its place, and the return column is not why

Read the monotone columns first, because those are the ones carrying a mechanism rather
than noise. Gross exposure (0.41, 0.54, 0.64, 0.85), drawdown (-17.3%, -22.6%, -27.1%,
-36.8%), beta (-0.13, -0.17, -0.23, -0.45) and alpha (+14.8%, +19.8%, +24.1%, +29.1%) all
move in lockstep with the target. That is what a real effect looks like: turn the dial, the
result tracks it. The 0.4% row was run separately to confirm the shipped setting rather
than interpolated from its neighbours, and it landed between them on every column.

Return does **not** behave that way. It climbs to 0.5% and then falls away (+77.0%,
+107.1%, +132.4%, +113.2%), so it is the column to distrust, and choosing a setting because
it maximised return here is exactly the mistake this document exists to prevent.

**Sharpe rises from 0.52 to 0.77-0.78 and stays flat across 0.3%, 0.4% and 0.5%.** A result
that holds across a range of settings is worth far more than a peak at one of them, because
there is no single lucky value doing the work.

Alpha appears to fall, from +35.9% to +19.8%, and that reading is an artefact of exposure.
Alpha is not scaled for how invested the book is. Per unit of gross exposure the shipped
config runs **+36.7%/yr against the baseline's +35.9%**, so the stock-picking is not being
damaged, it is being applied to a smaller book. The falling *absolute* alpha is the cost of
holding less, which is the trade being offered and is charged honestly to the same curve.

The beta side-effect was not designed and is worth noticing: **-0.66 to -0.17**. The names
with the highest volatility were also the high-beta ones the ranking metric kept shorting,
so cutting their size cut most of the accidental market exposure with them. This does not
make the book market-neutral and does not replace Stage 5, which should still target beta
deliberately rather than inherit a better accident.

**0.4% was shipped even though 0.5% returned more.** Be clear about what is being given up:
0.5% beat the equal-weight universe by +20.4% and 0.4% still trails it by -5.0%. The reason
is that return is the column that does not track the dial, and the purpose of this change
was never to beat the benchmark. It was to make the 3% daily kill-switch reachable only by
a genuine portfolio event instead of by one name gapping overnight. 0.4% leaves more
headroom for that: on the real 2026-08-04 book it turns a -5.39% mark-to-market day into
-1.78%, where 0.5% would land near -2.2% and closer to the limit it exists to respect.
Sharpe is flat across 0.3-0.5, so nothing risk-adjusted is being sacrificed to buy that
headroom.

Beating the benchmark is a Stage 5 problem. A book running -0.17 beta against an index that
rose 112% is not going to out-return it, and sizing was never going to fix that.

**Read this as diagnosis, not as a leaderboard.** Nine configs against one test period
is multiple testing: the best of nine beats the baseline by some margin on luck alone.
Adopting a winner because it won here relocates the overfitting rather than removing it.
What the table is good for is effect size and consistency.

### The short leg spends the alpha, it does not create it

Long-only returns +805.6% against the baseline's +93.3%, and the obvious conclusion is
wrong. Alpha barely moves (+35.9% to +32.5%, slightly *down*) while beta swings from
**-0.66 to +1.20**. Nearly all of that +693pp is flipped market exposure in a market that
rose, not better stock picking.

So the finding is not "shorting is bad". The selection carries about the same skill
either way, and the short leg spends it fighting the market. Measured at leg level on
the baseline config: the long leg runs +0.47 beta on 0.61 gross weight, the short leg
**-1.18 beta on 0.36 gross weight**, netting a -0.71 book beta out of +0.25 net dollar
exposure. The cause is the ranking metric: `strength = |fast - slow| / slow` takes an
absolute value, so it ranks on trend magnitude regardless of direction, and the largest
downward gaps in a bull market belong to high-beta names. Median beta of names shorted
was **1.84** against **1.38** for names longed.

Do not read the alpha column as an absolute. It is measured against a survivorship-biased
benchmark, so ~35%/yr is inflated by an unknown amount. It is a relative signal across
rows, which is what it is used for here.

### Selection earns its place; hysteresis does not

Concentration is monotone, in return and in alpha: 5 slots (+93.3%, alpha +35.9%) beats
10 (+52.3%, +25.2%) beats 20 (+15.5%, +13.8%) beats 50 (-28.5%, -0.7%). Diluting the
ranking dilutes the skill, which is the ranking doing real work. The selection layer was
built on reasoning alone and now has evidence behind it.

One slot is not better than five: higher alpha (+68.6%) at a **-91.6% drawdown**, which
is a wipeout rather than a strategy. Five is a defensible point on that curve.

**Hysteresis costs roughly 70 percentage points.** Off: +163.0%. At 10: +93.3%. At 20:
+100.9%. It exists to avoid churn costs, but the zero-costs row prices all transaction
costs at only ~21pp, so the buffer spends far more in missed rotation than it ever saves
in fees. That reasoning was wrong and only measurement could have shown it. Worth
revisiting, and worth re-validating on data these nine runs have not touched.

### What this argues for

A selection signal with persistent alpha wrapped in an accidental, unmanaged -0.66 beta
is the case for **Stage 5 (market-neutral)** ahead of Stage 2. Neutralising the exposure
deliberately keeps the alpha; going long-only trades it for market direction and
contradicts the market-neutral thesis in `roadmap-vision.md`. The config is deliberately
left unchanged on the strength of this table.

## Is SMA crossover the best signal available? Measured 2026-08-08, answer: no challenger won

`scripts/compare_signals.py` scores alternative signals through the same pipeline, so the
only thing differing between rows is the rule deciding what to hold. Candidates were fixed
before anything ran and chosen from published prior evidence, not by searching this data.
Every row runs under the shipped volatility sizing.

**Read the 21-year table, not the 8-year one.** Both are here because the difference between
them is the most useful thing this exercise produced.

### 2005-2026, ~18 test windows: the one to trust

| Signal | Return | Excess | Sharpe | Beta | Alpha | MaxDD | Gross | Alpha/gross |
|---|---|---|---|---|---|---|---|---|
| **baseline** SMA 20/50 | +788.5% | -682.3% | 0.66 | +0.09 | +13.1% | -46.1% | 0.65 | **+20.2%** |
| SMA, risk-adjusted ranking | +480.9% | -989.9% | 0.60 | +0.20 | +8.2% | -33.1% | 0.90 | +9.1% |
| momentum 12-1 | +1447.5% | -23.3% | 0.86 | +0.41 | +10.1% | -38.7% | 0.89 | +11.3% |
| reversal 5d | -88.8% | -1559.6% | -0.64 | +0.17 | -13.7% | -91.6% | 0.82 | -16.7% |

### 2018-2026, 5 test windows: kept only as a cautionary tale

| Signal | Return | Excess | Sharpe | Beta | Alpha | MaxDD | Gross | Alpha/gross |
|---|---|---|---|---|---|---|---|---|
| **baseline** SMA 20/50 | +107.1% | -5.0% | 0.78 | -0.17 | +19.8% | -22.6% | 0.54 | +36.7% |
| SMA, risk-adjusted ranking | +72.0% | -40.1% | 0.63 | +0.28 | +8.3% | -47.2% | 0.87 | +9.5% |
| momentum 12-1 | +338.2% | **+226.2%** | 1.38 | +0.77 | +19.6% | -20.1% | 0.80 | +24.5% |
| reversal 5d | -44.0% | -156.1% | -0.59 | +0.14 | -12.5% | -51.4% | 0.81 | -15.4% |

### Thirteen more years turned +226% of excess into -23%

Momentum on five windows looks like the best thing ever measured in this repo, beating the
equal-weight universe by 226 percentage points. On eighteen windows it does not beat the
universe at all. Nothing about the strategy changed; only the number of independent periods
it was asked to survive.

Per window on the short sample it won 3 of 5, and almost the entire margin was 2024 alone
(+109.4% against SMA's +7.4%). It also lost 2022, the only falling market there, returning
+4.2% where SMA made +20.5% against a benchmark of -10.1%. Five windows was never enough to
tell a strategy from a good year, and this is the measurement that proves it rather than
asserts it.

**Keep this in mind before promoting anything from any table in this document.** The
ablation rows above rest on the same five windows.

**Nothing was promoted. The config still runs SMA 20/50.** Reasons, in order of how much
they should be trusted:

### Momentum's short-sample edge was one window

Per-window on the 5-window sample, out-of-sample, momentum against SMA:

| Test window | Benchmark | SMA | Momentum | Difference |
|---|---|---|---|---|
| 2021 | +32.6% | +8.2% | +2.8% | -5.4% |
| 2022 | -10.1% | **+20.5%** | +4.2% | -16.3% |
| 2023 | +21.7% | +11.7% | +29.1% | +17.4% |
| 2024 | +23.4% | +7.4% | **+109.4%** | **+102.0%** |
| 2025 | +18.4% | +32.5% | +51.4% | +18.9% |

Three wins in five, with almost the entire margin in 2024. Remove that one year and
momentum compounds to +109% against SMA's +93%: an edge of 16 percentage points, not 226.
Momentum also **loses in the only falling market in the sample**, returning +4.2% in 2022
where the SMA made +20.5% against a benchmark of -10.1%. Paying for a bull market by giving
up the bear-year property is the opposite of what this project is trying to build.

### And what is left is exposure, not picking

The finding that survived both samples independently, which is why it is the one to act on.
Momentum keeps more of its return by deploying more capital and carrying more beta, not by
choosing better. Per unit of gross exposure:

| Sample | SMA | Momentum |
|---|---|---|
| 2018-2026 | +36.7%/yr | +24.5%/yr |
| 2005-2026 | +20.2%/yr | +11.3%/yr |

Roughly two to one for the existing selection, in both. Momentum does win on Sharpe (0.86 vs
0.66) and drawdown (-38.7% vs -46.1%) over 21 years, and those are real, but Sharpe rewards
beta in a market that rose 1470%, so it is the contaminated measure here.

### The ranking metric was not the defect

Worth recording because it was a confident prediction that turned out wrong, and wrong in
both samples. The ablation blamed `strength = |fast - slow| / slow` for shorting high-beta
names by construction, so `SmaCrossover(rank_by="risk_adjusted")` divides that gap by
realized volatility. Over 21 years it cut alpha from +13.1% to +8.2% and alpha per unit of
exposure from +20.2% to +9.1%. Preferring calm names means volatility sizing then gives them
*larger* positions, so gross exposure rose to 0.90 and dragged returns down with it. It does
reduce drawdown (-46.1% to -33.1%), which is the one thing in its favour and is a sizing
effect rather than a selection one. The ranking metric stays as it is.

### Reversal is the control, and it failed as it should

At -88.8% over 21 years with a -91.6% drawdown it is not merely a losing strategy, it is a
wipeout. That is what says the harness is not simply rewarding whatever gets tested, which
is the live risk when every other candidate is a trend follower.

### Everything here trails buying the index, and the gap is overstated

Both trend followers lose badly to the equal-weight universe over 21 years: SMA by 682
percentage points, momentum by 23. That is uncomfortable and it should be read with the
survivorship caveat weighted heavily, because the caveat compounds with time. The universe
is *today's* S&P 500 membership projected back to 2005, so every company that was in the
index then and later failed or was removed is missing. The benchmark holds all of them
equally and therefore banks the full survivor premium; the strategies hold five at a time
and bank much less of it. The 21-year gap is inflated by an unknown but large amount, and
the honest reading is that cross-signal comparisons hold while absolute excess does not.

Fixing that needs point-in-time index membership, which this project does not have and
which is the single biggest known hole in every number in this document.

### How to reproduce the deep history

`config/settings.yaml` keeps `data.start` at 2018-01-01, which is all the live pipeline
needs. The research store is pulled separately:

```
python scripts/backfill.py --start 2005-01-01   # ~4 min, overwrites data/bars
python -u scripts/compare_signals.py --jobs 4   # ~11 min
```

## What this baseline does not cover

- **The sentiment gate is not in it.** Nothing persists news, and yfinance serves
  only recent headlines, so there is no way to reconstruct what FinBERT would have
  said in 2019. The live ledger's `sentiment_gates` rows are the only real record
  and cover about two weeks. `news_scores` now captures every scored headline so
  this becomes answerable later; until then, any claim about the gate's value is
  unmeasured.
- **Survivorship bias.** The universe is *today's* index membership, so every
  window contains only companies that made it in and stayed. Absolute returns are
  optimistic by an unknown amount. Fixing it needs point-in-time constituent
  history, which this project does not have. Comparisons between two configs over
  the same universe stay meaningful; the absolute numbers do not.
- **Close-to-close execution.** The backtest fills at the close of the bar after
  the signal; live submits market-on-open and fills at the next open. Both respect
  no-look-ahead, but they are not the same fill.
- **No capacity or borrow modelling.** Shorts are assumed freely available at the
  same cost as longs, which is not true for the harder-to-borrow names.

## Reproducing

```
python scripts/backfill.py          # refresh the local store first
python scripts/validate.py          # walk-forward (the number to quote)
python scripts/validate.py --in-sample
python scripts/ablate.py            # the component table above (~15 min, 503 tickers)
```
