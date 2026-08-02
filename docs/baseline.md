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
```
