"""Score the strategy the way the live pipeline actually runs it.

This is the Stage 1 instrument: the thing that says whether a change helped.
Without it, every later idea is judged on a feeling.

Two modes, and the difference between them is the point:

  --in-sample   one backtest over all history with fixed parameters. Fast, and
                the number is not evidence: the parameters were chosen knowing
                how the whole period turned out.
  (default)     walk-forward. Parameters are picked on each training slice and
                scored only on the test slice that follows, so every number
                reported comes from data those parameters never saw.

Quote the walk-forward number. Use --in-sample only to see how much optimism
the in-sample version was adding, which is itself worth knowing.

Both read the local parquet store, so run scripts/backfill.py first.

Usage:
  python scripts/validate.py                        # walk-forward, full universe
  python scripts/validate.py --in-sample            # single-pass comparison
  python scripts/validate.py --limit 50             # first 50 tickers, for speed
  python scripts/validate.py --train-years 4 --test-years 1
"""

import argparse
import sys
import time
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diyquant.backtest.portfolio import run_portfolio_backtest  # noqa: E402
from diyquant.backtest.walkforward import walk_forward  # noqa: E402
from diyquant.config import get_settings  # noqa: E402
from diyquant.data.store import load_bars  # noqa: E402
from diyquant.signals.technical.sma_crossover import SmaCrossover  # noqa: E402

# Coarse on purpose. A dense grid searched on a few thousand sessions finds
# noise and dresses it as a parameter, and every extra pair is another lottery
# ticket bought with the same evidence.
FAST_GRID = [5, 10, 20, 30]
SLOW_GRID = [50, 100, 150, 200]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument(
        "--in-sample", action="store_true", help="single pass, fixed params (not evidence)"
    )
    p.add_argument("--limit", type=int, help="use only the first N tickers")
    p.add_argument("--train-years", type=float, default=3.0)
    p.add_argument("--test-years", type=float, default=1.0)
    return p.parse_args()


def load_universe(limit: int | None) -> dict:
    settings = get_settings()
    tickers = settings.universe["tickers"]
    if limit:
        tickers = tickers[:limit]

    bars, missing = {}, 0
    for ticker in tickers:
        try:
            bars[ticker] = load_bars(ticker)
        except Exception:
            missing += 1
    if not bars:
        raise SystemExit("no bars in the local store: run scripts/backfill.py first")
    if missing:
        print(f"note: {missing} of {len(tickers)} tickers had no stored bars, skipped")
    return bars


def main() -> int:
    warnings.filterwarnings("ignore")
    args = parse_args()
    settings = get_settings()
    risk = settings.risk

    started = time.time()
    bars = load_universe(args.limit)
    span_start = min(b.index[0] for b in bars.values()).date()
    span_end = max(b.index[-1] for b in bars.values()).date()
    print(f"{len(bars)} tickers, {span_start} to {span_end}")
    print(
        f"selection: {risk.max_positions} positions, hysteresis rank {risk.hysteresis_rank}; "
        f"costs {settings.backtest.cost_bps}bps + {settings.backtest.slippage_bps}bps slippage\n"
    )

    if args.in_sample:
        params = settings.strategy.params
        print(f"=== In-sample, fixed {params} (NOT out-of-sample evidence) ===")
        result = run_portfolio_backtest(
            bars,
            SmaCrossover(**params),
            max_positions=risk.max_positions,
            hysteresis_rank=risk.hysteresis_rank,
            cost_bps=settings.backtest.cost_bps,
            slippage_bps=settings.backtest.slippage_bps,
        )
        print(result.summary())
    else:
        result = walk_forward(
            bars,
            SmaCrossover,
            grid={"fast": FAST_GRID, "slow": SLOW_GRID},
            max_positions=risk.max_positions,
            hysteresis_rank=risk.hysteresis_rank,
            cost_bps=settings.backtest.cost_bps,
            slippage_bps=settings.backtest.slippage_bps,
            train_years=args.train_years,
            test_years=args.test_years,
        )
        print(result.summary())

    print("\nSurvivorship warning: the universe is TODAY's index membership, so every")
    print("window only contains companies that made it in and stayed. Absolute returns")
    print("are optimistic; comparisons between configs over the same universe are not.")
    print(f"\n({time.time() - started:.0f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
