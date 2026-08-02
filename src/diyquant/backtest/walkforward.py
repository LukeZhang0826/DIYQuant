"""Walk-forward evaluation: score a strategy only on data its parameters never saw.

A single backtest over all history with one hand-picked parameter pair answers a
question nobody asked. The configured 20/50 was a default, not a finding, and if
you search for a better pair over the whole history and report that pair's
result, you are reporting the best of many tries as though it were one try. That
number is luck wearing a lab coat.

So the history is cut into successive windows. In each, parameters are chosen on
the training slice alone, then applied unchanged to the test slice that follows,
and only test slices are scored. The parameters are always older than the data
they are judged on, which is the one property that makes an out-of-sample claim
mean anything.

What this still cannot fix: the universe is today's index membership, so every
window is survivorship-biased (see portfolio.py). Walk-forward defends against
overfitting, not against a biased sample.
"""

from dataclasses import dataclass
from itertools import product

import numpy as np
import pandas as pd

from diyquant.backtest.portfolio import TRADING_DAYS, PortfolioResult, run_portfolio_backtest


@dataclass
class Window:
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    chosen: dict
    test_return: float
    benchmark_return: float


@dataclass
class WalkForwardResult:
    windows: list[Window]
    stitched: PortfolioResult  # the concatenated out-of-sample record
    grid_size: int

    def summary(self) -> str:
        lines = [
            "=== Walk-forward (out-of-sample only) ===",
            f"Windows        : {len(self.windows)}",
            f"Grid per window: {self.grid_size} parameter pairs",
            "",
            f"{'train':<24}{'test':<24}{'chosen':<14}{'strat':>9}{'bench':>9}",
        ]
        for w in self.windows:
            chosen = ",".join(str(v) for v in w.chosen.values())
            lines.append(
                f"{w.train_start.date()}..{w.train_end.date():%Y-%m-%d}  "
                f"{w.test_start.date()}..{w.test_end.date():%Y-%m-%d}  "
                f"{chosen:<14}{w.test_return:>+8.1%}{w.benchmark_return:>+9.1%}"
            )
        lines += ["", self.stitched.summary()]
        return "\n".join(lines)


def _slice(bars_by_symbol: dict, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    """Bars up to `end`, keeping history before `start` so rolling windows warm up.

    Only the scored range is cut at `start`; the leading history stays because a
    50-day average on the first test day has to come from somewhere. Truncating
    it would hand every window a warmup period of flat, position-free days and
    quietly understate turnover and exposure alike.
    """
    out = {}
    for symbol, bars in bars_by_symbol.items():
        window = bars[bars.index <= end]
        if len(window[window.index >= start]) > 0:
            out[symbol] = window
    return out


def make_windows(
    dates: pd.DatetimeIndex, train_years: float, test_years: float
) -> list[tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp, pd.Timestamp]]:
    """Successive (train_start, train_end, test_start, test_end) spans.

    Anchored on trading-day counts rather than calendar dates so every window
    carries the same amount of evidence: a calendar year holds a different number
    of sessions depending on holidays and halts.
    """
    train_n = int(train_years * TRADING_DAYS)
    test_n = int(test_years * TRADING_DAYS)
    if train_n < 1 or test_n < 1:
        raise ValueError("train and test spans must each cover at least one session")

    spans = []
    start = 0
    while start + train_n + test_n <= len(dates):
        spans.append(
            (
                dates[start],
                dates[start + train_n - 1],
                dates[start + train_n],
                dates[min(start + train_n + test_n - 1, len(dates) - 1)],
            )
        )
        start += test_n  # roll forward by one test span, so tests never overlap
    return spans


def walk_forward(
    bars_by_symbol: dict[str, pd.DataFrame],
    strategy_factory,
    grid: dict[str, list],
    max_positions: int = 5,
    hysteresis_rank: int = 10,
    cost_bps: float = 5.0,
    slippage_bps: float = 2.0,
    train_years: float = 3.0,
    test_years: float = 1.0,
    objective=lambda r: r.sharpe,
) -> WalkForwardResult:
    """Choose parameters on each training slice, score only the test slice that follows.

    `strategy_factory(**params)` builds the strategy; `grid` maps each parameter
    to the values to try. `objective` ranks candidates on the training slice and
    defaults to Sharpe rather than raw return, since return alone will happily
    pick the pair that made one enormous leveraged-looking bet and survived.
    """
    all_dates = pd.DatetimeIndex(sorted({d for b in bars_by_symbol.values() for d in b.index}))
    spans = make_windows(all_dates, train_years, test_years)
    if not spans:
        raise ValueError(
            f"history covers {len(all_dates)} sessions, too few for "
            f"{train_years}y train + {test_years}y test"
        )

    keys = list(grid)
    combos = [dict(zip(keys, values)) for values in product(*(grid[k] for k in keys))]
    if not combos:
        raise ValueError("empty parameter grid")

    windows: list[Window] = []
    oos_returns: list[pd.Series] = []
    oos_bench: list[pd.Series] = []

    for train_start, train_end, test_start, test_end in spans:
        train_bars = _slice(bars_by_symbol, train_start, train_end)

        best, best_score = None, -np.inf
        for params in combos:
            try:
                scored = run_portfolio_backtest(
                    train_bars,
                    strategy_factory(**params),
                    max_positions=max_positions,
                    hysteresis_rank=hysteresis_rank,
                    cost_bps=cost_bps,
                    slippage_bps=slippage_bps,
                )
            except ValueError:
                continue  # an invalid combination, e.g. fast >= slow
            score = objective(scored)
            # Ties break on the earlier combo so the choice is reproducible.
            if score > best_score:
                best, best_score = params, score

        if best is None:
            continue

        test_bars = _slice(bars_by_symbol, test_start, test_end)
        tested = run_portfolio_backtest(
            test_bars,
            strategy_factory(**best),
            max_positions=max_positions,
            hysteresis_rank=hysteresis_rank,
            cost_bps=cost_bps,
            slippage_bps=slippage_bps,
        )
        # Score only the test span. The warmup history kept by _slice would
        # otherwise be counted again in every later window.
        scored_days = tested.daily_returns[tested.daily_returns.index >= test_start]
        bench_days = tested.benchmark_curve.pct_change().fillna(0.0)
        bench_days = bench_days[bench_days.index >= test_start]

        windows.append(
            Window(
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
                chosen=best,
                test_return=float((1 + scored_days).prod() - 1),
                benchmark_return=float((1 + bench_days).prod() - 1),
            )
        )
        oos_returns.append(scored_days)
        oos_bench.append(bench_days)

    stitched = _stitch(oos_returns, oos_bench)
    return WalkForwardResult(windows=windows, stitched=stitched, grid_size=len(combos))


def _stitch(returns: list[pd.Series], bench: list[pd.Series]) -> PortfolioResult:
    """Join the test slices into one continuous out-of-sample record.

    This is the number to quote. Each window's parameters were fixed before its
    slice began, so the joined curve is what the strategy would have returned had
    it been re-tuned annually and never once peeked forward.
    """
    joined = pd.concat(returns).sort_index()
    joined_bench = pd.concat(bench).sort_index()
    equity = (1 + joined).cumprod()
    benchmark = (1 + joined_bench).cumprod()

    years = len(joined) / TRADING_DAYS
    drawdown = equity / equity.cummax() - 1
    return PortfolioResult(
        equity_curve=equity,
        benchmark_curve=benchmark,
        daily_returns=joined,
        weights=pd.DataFrame(),  # per-window books are not comparable once joined
        total_return=float(equity.iloc[-1] - 1),
        benchmark_return=float(benchmark.iloc[-1] - 1),
        cagr=float(equity.iloc[-1] ** (1 / years) - 1) if years >= 1 else float("nan"),
        sharpe=float(joined.mean() / joined.std() * np.sqrt(TRADING_DAYS))
        if joined.std() > 0
        else 0.0,
        max_drawdown=float(drawdown.min()),
        annual_turnover=float("nan"),  # windows are stitched, so turnover is per-window
        hit_rate=float("nan"),
        n_positions=0,
    )
