"""Score alternative signals against the shipped SMA crossover, out-of-sample.

`ablate.py` asks whether each piece of the *pipeline* earns its place, holding
the signal fixed. This asks the other question: is the signal itself the best
one available. Same walk-forward, same universe, same costs, same selection and
sizing, so the only thing that differs between rows is the rule that decides what
to hold.

**The candidates were fixed before anything was run, and chosen from published
prior evidence rather than by searching this data.** That constraint is the whole
point. With a 500-name universe and eight years of history it is easy to find a
rule that beat the baseline here, and almost as easy to find one that keeps
beating it for exactly as long as it takes to deploy. Four rows tested once is a
weak enough multiple-testing burden to reason about; forty rows would not be.

  momentum      Jegadeesh & Titman 1993, the most replicated equity anomaly.
  reversal      Lehmann 1990 / Jegadeesh 1990, and deliberately the opposite
                thesis, so that a clean sweep by trend followers can be told
                apart from a harness that simply flatters trend following.
  sma risk-adj  Not a new signal at all: identical entries to the baseline, only
                the ranking metric changed, isolating the defect docs/baseline.md
                already measured.

Each strategy gets its own parameter grid, fitted on each training slice and
scored only on the test slice that follows. Grids are kept deliberately small:
a wider grid does not find a better strategy, it finds a better fit to the
training slice and spends the harness's credibility doing it.

Usage:
  python -u scripts/compare_signals.py             # full universe
  python -u scripts/compare_signals.py --limit 80  # quicker, noisier
  python -u scripts/compare_signals.py --jobs 1    # serial, for a traceback
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
from diyquant.signals.technical.momentum import Momentum  # noqa: E402
from diyquant.signals.technical.reversal import Reversal  # noqa: E402
from diyquant.signals.technical.sma_crossover import SmaCrossover  # noqa: E402

DEFAULT_JOBS = min(6, os.cpu_count() or 1)

# (label, factory, grid, question)
CANDIDATES = [
    (
        "baseline SMA 20/50",
        SmaCrossover,
        {"fast": [5, 10, 20, 30], "slow": [50, 100, 150, 200]},
        "the shipped signal",
    ),
    (
        "  SMA risk-adj rank",
        SmaCrossover,
        {
            "fast": [5, 10, 20, 30],
            "slow": [50, 100, 150, 200],
            "rank_by": ["risk_adjusted"],
        },
        "is the ranking metric the defect?",
    ),
    (
        "  momentum 12-1",
        Momentum,
        {"lookback": [126, 252], "skip": [21], "vol_lookback": [60]},
        "does a real anomaly beat a moving average?",
    ),
    (
        "  reversal 5d",
        Reversal,
        {"lookback": [5, 10], "vol_lookback": [60]},
        "or does the opposite thesis win?",
    ),
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--limit", type=int, help="use only the first N tickers")
    p.add_argument(
        "--jobs", type=int, default=DEFAULT_JOBS, help=f"parallel (default {DEFAULT_JOBS})"
    )
    return p.parse_args()


_WORKER_BARS: dict[str, pd.DataFrame] = {}


def _init_worker(tickers: list[str]) -> None:
    warnings.filterwarnings("ignore")
    global _WORKER_BARS
    for ticker in tickers:
        try:
            _WORKER_BARS[ticker] = load_bars(ticker)
        except Exception:
            pass


def _run(job: tuple) -> tuple:
    label, factory, grid, params = job
    started = time.time()
    result = walk_forward(
        _WORKER_BARS, factory, grid=grid, train_years=3.0, test_years=1.0, **params
    ).stitched
    return label, result, time.time() - started


def main() -> int:
    warnings.filterwarnings("ignore")
    args = parse_args()
    settings = get_settings()
    risk = settings.risk

    tickers = (
        settings.universe["tickers"][: args.limit] if args.limit else settings.universe["tickers"]
    )
    # Every row runs the pipeline exactly as configured, volatility sizing
    # included: a signal that only looks good at the old flat cap is not a
    # finding about the signal.
    params = dict(
        max_positions=risk.max_positions,
        hysteresis_rank=risk.hysteresis_rank,
        cost_bps=settings.backtest.cost_bps,
        slippage_bps=settings.backtest.slippage_bps,
        max_position_pct=risk.max_position_pct,
        target_risk_pct=risk.target_risk_pct,
    )

    jobs = [(label, factory, grid, params) for label, factory, grid, _ in CANDIDATES]
    questions = {label: q for label, _, _, q in CANDIDATES}
    workers = max(1, min(args.jobs, len(jobs)))

    print("walk-forward 3y train / 1y test, out-of-sample only")
    print(f"sizing: {risk.target_risk_pct}% risk/position, cap {risk.max_position_pct}%")
    print(f"{len(jobs)} signals on {workers} worker(s)\n", flush=True)

    started = time.time()
    results = {}
    if workers == 1:
        _init_worker(tickers)
        for job in jobs:
            label, result, secs = _run(job)
            results[label] = result
            print(f"  done {label.strip():<20} {secs:>5.0f}s", flush=True)
    else:
        with ProcessPoolExecutor(
            max_workers=workers, initializer=_init_worker, initargs=(tickers,)
        ) as pool:
            futures = [pool.submit(_run, job) for job in jobs]
            for future in as_completed(futures):
                label, result, secs = future.result()
                results[label] = result
                print(f"  done {label.strip():<20} {secs:>5.0f}s", flush=True)

    header = (
        f"{'signal':<22}{'return':>9}{'bench':>9}{'excess':>9}"
        f"{'sharpe':>8}{'beta':>7}{'alpha':>8}{'maxDD':>8}{'gross':>7}"
    )
    print(f"\n{header}")
    print("-" * len(header))
    for label, *_ in CANDIDATES:
        r = results[label]
        excess = r.total_return - r.benchmark_return
        question = questions[label]
        print(
            f"{label:<22}{r.total_return:>+8.1%}{r.benchmark_return:>+9.1%}{excess:>+9.1%}"
            f"{r.sharpe:>8.2f}{r.beta:>+7.2f}{r.alpha:>+8.1%}{r.max_drawdown:>8.1%}"
            f"{r.avg_gross_exposure:>7.2f}" + (f"   <- {question}" if question else "")
        )

    print(f"\n({time.time() - started:.0f}s)")
    print("\nFour signals against one test period is still multiple testing. A winner")
    print("here has not earned deployment; it has earned a re-validation on data these")
    print("runs did not touch. Compare sharpe and alpha per unit of gross exposure, not")
    print("raw return: rows hold different amounts of the account.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
