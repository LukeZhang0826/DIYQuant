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
