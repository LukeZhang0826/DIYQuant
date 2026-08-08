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

Configs run in parallel, one process each, and print as they land. Use `-u` if
you redirect the output: a buffered twenty-minute run that shows nothing is
indistinguishable from a hung one.

Usage:
  python -u scripts/ablate.py                      # every config, ~4 min on 6 workers
  python -u scripts/ablate.py --only vol-scaled    # just those rows, against the baseline
  python -u scripts/ablate.py --limit 80           # quicker, noisier
  python -u scripts/ablate.py --jobs 1             # serial, for debugging a traceback
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

# Each worker holds its own copy of ~500 symbols' bars, so this is bounded by
# memory rather than by cores. Six is comfortable in about 1 GB.
DEFAULT_JOBS = min(6, os.cpu_count() or 1)


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
    p.add_argument(
        "--only",
        help="run only configs whose label contains this text, e.g. --only vol-scaled. "
        "The baseline always runs, since every row is read against it.",
    )
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


# Each worker loads the store once and reuses it for every config it is handed.
# Sending ~500 DataFrames through the pickle boundary per job instead would cost
# more than the backtests being parallelised.
_WORKER_BARS: dict[str, pd.DataFrame] = {}


def _init_worker(tickers: list[str]) -> None:
    warnings.filterwarnings("ignore")
    global _WORKER_BARS
    _WORKER_BARS = _load(tickers)


def _run_config(job: tuple) -> tuple:
    label, factory, params = job
    started = time.time()
    result = walk_forward(
        _WORKER_BARS,
        factory,
        grid={"fast": FAST_GRID, "slow": SLOW_GRID},
        train_years=3.0,
        test_years=1.0,
        **params,
    ).stitched
    return label, result, time.time() - started


def _format(label: str, result, question: str) -> str:
    excess = result.total_return - result.benchmark_return
    return (
        f"{label:<26}{result.total_return:>+8.1%}{result.benchmark_return:>+9.1%}"
        f"{excess:>+9.1%}{result.sharpe:>8.2f}{result.beta:>+7.2f}"
        f"{result.alpha:>+8.1%}{result.max_drawdown:>8.1%}"
        f"{result.avg_gross_exposure:>7.2f}" + (f"   <- {question}" if question else "")
    )


def main() -> int:
    warnings.filterwarnings("ignore")
    args = parse_args()
    settings = get_settings()
    risk = settings.risk

    tickers = (
        settings.universe["tickers"][: args.limit] if args.limit else settings.universe["tickers"]
    )

    base = dict(
        max_positions=risk.max_positions,
        hysteresis_rank=risk.hysteresis_rank,
        cost_bps=settings.backtest.cost_bps,
        slippage_bps=settings.backtest.slippage_bps,
        max_position_pct=risk.max_position_pct,
        target_risk_pct=0.0,  # baseline is the flat cap, whatever config now ships
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
            "  vol-scaled 0.3%",
            "does risk sizing pay?",
            SmaCrossover,
            {"target_risk_pct": 0.3},
        ),
        ("  vol-scaled 0.5%", "", SmaCrossover, {"target_risk_pct": 0.5}),
        ("  vol-scaled 0.8%", "", SmaCrossover, {"target_risk_pct": 0.8}),
        (
            "  zero costs",
            "how much do costs eat?",
            SmaCrossover,
            {"cost_bps": 0, "slippage_bps": 0},
        ),
    ]

    if args.only:
        runs = [r for r in runs if args.only in r[0] or r[0].startswith("baseline")]
        if len(runs) <= 1:
            raise SystemExit(f"--only {args.only!r} matched no config")

    questions = {label: question for label, question, _, _ in runs}
    jobs = [(label, factory, {**base, **overrides}) for label, _, factory, overrides in runs]
    workers = max(1, min(args.jobs, len(jobs)))

    print("walk-forward 3y train / 1y test, out-of-sample only")
    print(f"{len(runs)} configs on {workers} worker(s)\n", flush=True)

    started = time.time()
    results = {}
    if workers == 1:
        _init_worker(tickers)
        if not _WORKER_BARS:
            raise SystemExit("no bars in the local store: run scripts/backfill.py first")
        for job in jobs:
            label, result, secs = _run_config(job)
            results[label] = result
            print(f"  done {label.strip():<20} {secs:>5.0f}s", flush=True)
    else:
        # Progress is printed as each config lands rather than at the end. A
        # twenty-minute run that prints nothing is indistinguishable from a hung
        # one, which is exactly how the first attempt at this was wasted.
        with ProcessPoolExecutor(
            max_workers=workers, initializer=_init_worker, initargs=(tickers,)
        ) as pool:
            futures = {pool.submit(_run_config, job): job[0] for job in jobs}
            for future in as_completed(futures):
                label, result, secs = future.result()
                results[label] = result
                print(f"  done {label.strip():<20} {secs:>5.0f}s", flush=True)

    header = (
        f"{'config':<26}{'return':>9}{'bench':>9}{'excess':>9}"
        f"{'sharpe':>8}{'beta':>7}{'alpha':>8}{'maxDD':>8}{'gross':>7}"
    )
    print(f"\n{header}")
    print("-" * len(header))
    for label, *_ in runs:
        print(_format(label, results[label], questions[label]))

    print(f"\n({time.time() - started:.0f}s)")
    print("\nTwelve configs against one test period is multiple testing: the best of twelve")
    print("beats the baseline on luck alone. Read effect sizes and consistency, not the")
    print("winner. Anything promoted from here needs re-validating on untouched data.")
    print("\n'gross' is the mean sum of absolute weights: 1.00 is fully invested. The")
    print("volatility-scaled rows hold less than that by design, so compare them on")
    print("sharpe, alpha and maxDD. Their raw return is lower partly because less of")
    print("the account is at work, which is the trade being offered, not a defect.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
