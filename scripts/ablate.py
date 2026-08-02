"""Ablation study: does each piece of the pipeline earn its place?

Selection, hysteresis and the short side were all built on reasoning rather
than measurement, because until Stage 1 there was nothing to measure them with.
This runs each one out-of-sample against the baseline so the reasoning can be
confirmed or discarded.

Every row is a walk-forward result. Comparing configs in-sample would rank them
on how well they fit a period they were tuned on, which is the mistake the
harness exists to prevent, so it is not offered here even as an option.

**Read the output as diagnosis, not as a search for the best setting.** Running
nine configurations against the same test period is multiple testing: the best
of nine will beat the baseline by some margin on luck alone, and adopting the
winner because it won here would relocate the overfitting rather than remove
it. What the table is good for is showing whether a component's effect is large
and consistent across windows, or small enough to be noise. Anything promoted
out of this should be re-validated on data it has not now been measured on.

Usage:
  python scripts/ablate.py             # full universe, ~15 min
  python scripts/ablate.py --limit 80  # quicker, noisier
"""

import argparse
import sys
import time
import warnings
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diyquant.backtest.walkforward import walk_forward  # noqa: E402
from diyquant.config import get_settings  # noqa: E402
from diyquant.data.store import load_bars  # noqa: E402
from diyquant.signals.technical.sma_crossover import SmaCrossover  # noqa: E402

FAST_GRID = [5, 10, 20, 30]
SLOW_GRID = [50, 100, 150, 200]


class LongOnly:
    """SMA crossover with the short leg removed: -1 becomes flat.

    A diagnostic, not a strategy. The book averages roughly three longs and two
    shorts against a universe that rose 112%, so the question is whether the
    shortfall comes from shorting into a bull market or from the entry timing.
    Clipping the signal answers it without touching anything else.
    """

    def __init__(self, **params):
        self._inner = SmaCrossover(**params)

    def generate(self, bars: pd.DataFrame) -> pd.Series:
        return self._inner.generate(bars).clip(lower=0)

    def strength_series(self, bars: pd.DataFrame) -> pd.Series:
        return self._inner.strength_series(bars)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--limit", type=int, help="use only the first N tickers")
    return p.parse_args()


def main() -> int:
    warnings.filterwarnings("ignore")
    args = parse_args()
    settings = get_settings()
    risk = settings.risk

    tickers = (
        settings.universe["tickers"][: args.limit] if args.limit else settings.universe["tickers"]
    )
    bars = {}
    for ticker in tickers:
        try:
            bars[ticker] = load_bars(ticker)
        except Exception:
            pass
    if not bars:
        raise SystemExit("no bars in the local store: run scripts/backfill.py first")

    base = dict(
        max_positions=risk.max_positions,
        hysteresis_rank=risk.hysteresis_rank,
        cost_bps=settings.backtest.cost_bps,
        slippage_bps=settings.backtest.slippage_bps,
    )

    # (label, question it answers, strategy factory, overrides)
    runs = [
        ("baseline 5 pos, hyst 10", "the shipped config", SmaCrossover, {}),
        ("  1 position", "does concentration help?", SmaCrossover, {"max_positions": 1}),
        ("  10 positions", "", SmaCrossover, {"max_positions": 10}),
        ("  20 positions", "", SmaCrossover, {"max_positions": 20}),
        ("  50 positions", "", SmaCrossover, {"max_positions": 50}),
        ("  hysteresis off", "does the buffer pay?", SmaCrossover, {"hysteresis_rank": 5}),
        ("  hysteresis 20", "", SmaCrossover, {"hysteresis_rank": 20}),
        ("  long only", "is the short side the bleed?", LongOnly, {}),
        (
            "  zero costs",
            "how much do costs eat?",
            SmaCrossover,
            {"cost_bps": 0, "slippage_bps": 0},
        ),
    ]

    print(f"{len(bars)} tickers, walk-forward 3y train / 1y test, out-of-sample only\n")
    header = f"{'config':<26}{'return':>9}{'bench':>9}{'excess':>9}{'sharpe':>8}{'beta':>7}{'alpha':>8}{'maxDD':>8}"
    print(header)
    print("-" * len(header))

    started = time.time()
    for label, question, factory, overrides in runs:
        params = {**base, **overrides}
        result = walk_forward(
            bars,
            factory,
            grid={"fast": FAST_GRID, "slow": SLOW_GRID},
            train_years=3.0,
            test_years=1.0,
            **params,
        ).stitched
        excess = result.total_return - result.benchmark_return
        print(
            f"{label:<26}{result.total_return:>+8.1%}{result.benchmark_return:>+9.1%}"
            f"{excess:>+9.1%}{result.sharpe:>8.2f}{result.beta:>+7.2f}"
            f"{result.alpha:>+8.1%}{result.max_drawdown:>8.1%}"
            + (f"   <- {question}" if question else "")
        )

    print(f"\n({time.time() - started:.0f}s)")
    print("\nNine configs against one test period is multiple testing: the best of nine")
    print("beats the baseline on luck alone. Read effect sizes and consistency, not the")
    print("winner. Anything promoted from here needs re-validating on untouched data.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
