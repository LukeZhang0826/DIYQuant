"""Does the Stage 5 index hedge earn its cost? Measured out-of-sample.

`risk/hedge.py` shipped disabled and unmeasured. The claim it rests on is that
the book's beta is an accident: -0.66 before volatility sizing, -0.17 after,
+0.09 over the 21-year sample, three different answers nobody chose. Sizing an
index position to cancel that exposure should keep the stock-picking and drop
the market direction. Should. This is the run that decides.

Rows are **paired**: each hedged config sits directly beneath the identical
unhedged one, because the only defensible reading is hedged-minus-its-own-pair.
Both sizing regimes are included, since the hedge and the volatility budget both
change exposure and their interaction is not obvious from either alone.

Two things to hold in mind while reading the table:

  * The `beta` column is measured against the **equal-weight universe**, which
    is the benchmark this project is trying to beat. The hedge neutralises beta
    against **SPY**, the instrument it trades. Those two are highly correlated
    and not identical, so a perfectly executed hedge lands near zero in this
    column, not exactly on it. A residual of a few hundredths is basis, not a bug.
  * Each row picks its own parameters in each window, so a per-window difference
    is the difference between two complete configurations, not the isolated
    effect of the hedge leg. That is the honest comparison (it is what you would
    actually deploy) but it does add noise to the window count below.

The window count is the point of this script, not the totals. A 226pp edge over
five windows evaporated to -23pp over eighteen on 2026-08-08; anything that
cannot win most windows has not been shown to work at all.

Usage:
  python -u scripts/measure_hedge.py             # full universe, 21y store
  python -u scripts/measure_hedge.py --limit 80  # quicker, noisier
  python -u scripts/measure_hedge.py --jobs 1    # serial, for a traceback
"""

import argparse
import os
import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from diyquant.backtest.walkforward import walk_forward  # noqa: E402
from diyquant.config import get_settings  # noqa: E402
from diyquant.data.store import load_bars  # noqa: E402
from diyquant.signals.technical.sma_crossover import SmaCrossover  # noqa: E402

FAST_GRID = [5, 10, 20, 30]
SLOW_GRID = [50, 100, 150, 200]

HEDGE_SYMBOL = "SPY"

DEFAULT_JOBS = min(6, os.cpu_count() or 1)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--limit", type=int, help="use only the first N tickers")
    p.add_argument(
        "--jobs",
        type=int,
        default=DEFAULT_JOBS,
        help=f"configs to run in parallel (default {DEFAULT_JOBS}); 1 runs in-process",
    )
    return p.parse_args()


def _load(tickers: list[str]) -> dict[str, pd.DataFrame]:
    bars = {}
    for ticker in tickers:
        try:
            bars[ticker] = load_bars(ticker)
        except Exception:
            pass
    return bars


_WORKER_BARS: dict[str, pd.DataFrame] = {}


def _init_worker(tickers: list[str]) -> None:
    warnings.filterwarnings("ignore")
    global _WORKER_BARS
    _WORKER_BARS = _load(tickers)


def _run_config(job: tuple) -> tuple:
    label, params = job
    started = time.time()
    # SPY is not an index constituent, and an unhedged row must not see it at
    # all: run_portfolio_backtest only excludes the hedge instrument from
    # candidacy and from the benchmark when hedging is switched on, so leaving
    # it in the dict would let the unhedged control both trade the hedge and be
    # scored against a benchmark containing it. Two different baselines wearing
    # one label is exactly the confusion this run exists to avoid.
    bars = _WORKER_BARS
    if not params.get("hedge_symbol"):
        bars = {s: b for s, b in bars.items() if s != HEDGE_SYMBOL}
    result = walk_forward(
        bars,
        SmaCrossover,
        grid={"fast": FAST_GRID, "slow": SLOW_GRID},
        train_years=3.0,
        test_years=1.0,
        **params,
    )
    return label, result, time.time() - started


def _format(label: str, result) -> str:
    s = result.stitched
    excess = s.total_return - s.benchmark_return
    return (
        f"{label:<28}{s.total_return:>+9.1%}{s.benchmark_return:>+9.1%}"
        f"{excess:>+9.1%}{s.sharpe:>8.2f}{s.beta:>+7.2f}"
        f"{s.alpha:>+8.1%}{s.max_drawdown:>8.1%}{s.avg_gross_exposure:>7.2f}"
    )


def main() -> int:
    warnings.filterwarnings("ignore")
    args = parse_args()
    settings = get_settings()
    risk = settings.risk

    tickers = (
        settings.universe["tickers"][: args.limit] if args.limit else settings.universe["tickers"]
    )
    if HEDGE_SYMBOL not in tickers:
        tickers = [*tickers, HEDGE_SYMBOL]

    base = dict(
        max_positions=risk.max_positions,
        hysteresis_rank=risk.hysteresis_rank,
        cost_bps=settings.backtest.cost_bps,
        slippage_bps=settings.backtest.slippage_bps,
        max_position_pct=risk.max_position_pct,
    )
    live_risk = risk.target_risk_pct

    # (label, pair it is compared against, overrides)
    runs = [
        ("flat cap, unhedged", None, {"target_risk_pct": 0.0}),
        (
            "  + hedge to 0.0",
            "flat cap, unhedged",
            {"target_risk_pct": 0.0, "hedge_symbol": HEDGE_SYMBOL, "target_beta": 0.0},
        ),
        (f"vol {live_risk}%, unhedged (live)", None, {"target_risk_pct": live_risk}),
        (
            "  + hedge to 0.0",
            f"vol {live_risk}%, unhedged (live)",
            {"target_risk_pct": live_risk, "hedge_symbol": HEDGE_SYMBOL, "target_beta": 0.0},
        ),
        (
            "  + hedge to +0.3",
            f"vol {live_risk}%, unhedged (live)",
            {"target_risk_pct": live_risk, "hedge_symbol": HEDGE_SYMBOL, "target_beta": 0.3},
        ),
    ]

    # Labels repeat by design (two rows read "+ hedge to 0.0"), so jobs are keyed
    # by position instead. Losing one row into another's dict slot would be
    # invisible in the output and would silently invert the conclusion.
    jobs = [(f"{i}", {**base, **overrides}) for i, (_, _, overrides) in enumerate(runs)]
    workers = max(1, min(args.jobs, len(jobs)))

    print(f"walk-forward 3y train / 1y test, out-of-sample only, hedging with {HEDGE_SYMBOL}")
    print(f"{len(runs)} configs on {workers} worker(s)\n", flush=True)

    started = time.time()
    results = {}
    if workers == 1:
        _init_worker(tickers)
        if not _WORKER_BARS:
            raise SystemExit("no bars in the local store: run scripts/backfill.py first")
        if HEDGE_SYMBOL not in _WORKER_BARS:
            raise SystemExit(f"no bars for {HEDGE_SYMBOL}: run scripts/backfill.py first")
        for job in jobs:
            key, result, secs = _run_config(job)
            results[key] = result
            print(f"  done {runs[int(key)][0].strip():<24} {secs:>5.0f}s", flush=True)
    else:
        with ProcessPoolExecutor(
            max_workers=workers, initializer=_init_worker, initargs=(tickers,)
        ) as pool:
            futures = {pool.submit(_run_config, job): job[0] for job in jobs}
            for future in as_completed(futures):
                key, result, secs = future.result()
                results[key] = result
                print(f"  done {runs[int(key)][0].strip():<24} {secs:>5.0f}s", flush=True)

    header = (
        f"{'config':<28}{'return':>9}{'bench':>9}{'excess':>9}"
        f"{'sharpe':>8}{'beta':>7}{'alpha':>8}{'maxDD':>8}{'gross':>7}"
    )
    print(f"\n{header}")
    print("-" * len(header))
    for i, (label, _, _) in enumerate(runs):
        print(_format(label, results[str(i)]))

    by_label = {label: results[str(i)] for i, (label, _, _) in enumerate(runs) if label}
    print("\nPer-window, hedged against its own unhedged pair:")
    print(f"  {'config':<46}{'won':>9}{'median diff':>14}{'worst':>9}{'best':>9}")
    for i, (label, pair, _) in enumerate(runs):
        if pair is None:
            continue
        hedged = results[str(i)].windows
        plain = by_label[pair].windows
        diffs = [h.test_return - p.test_return for h, p in zip(hedged, plain)]
        won = sum(1 for d in diffs if d > 0)
        median = pd.Series(diffs).median()
        print(
            f"  {label.strip() + ' vs ' + pair:<46}{f'{won}/{len(diffs)}':>9}"
            f"{median:>+14.1%}{min(diffs):>+9.1%}{max(diffs):>+9.1%}"
        )

    print(f"\n({time.time() - started:.0f}s)")
    print("\nRead the window count first. A hedge that lifts the total while winning")
    print("half the windows has been carried by one period and has not been shown to")
    print("work. 'beta' is measured against the equal-weight universe while the hedge")
    print("neutralises against SPY, so a residual of a few hundredths is basis, not a")
    print("failure. 'gross' rises by the hedge's own weight: that capital is at work")
    print("and is charged costs, which is the price being weighed here.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
