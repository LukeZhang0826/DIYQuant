"""Portfolio backtester: the strategy as the live pipeline actually runs it.

`engine.py` answers "is this signal any good on one ticker", holding a single
name at full size forever. That is not what runs in production. Live picks about
five names out of five hundred through `risk.selection`, so a single-ticker
result cannot tell you whether the deployed system makes money: it measures a
different strategy.

This replays the real thing. Every date: signal and conviction for the whole
universe, `select_positions` to choose the funded few, equal weight across them,
returns on the next bar, costs on the turnover. The selection call is the same
function the pipeline calls, not a reimplementation, so a change to how names are
ranked shows up here without being ported.

Two deliberate departures from `engine.py`:

- **Simple returns, not log returns.** A daily-rebalanced portfolio's return is
  exactly the weighted sum of its holdings' *simple* returns. Weighting log
  returns and summing them is an approximation that only looks harmless with one
  position, and this book holds several.
- **Costs are charged on the change in held weight**, so opening five positions
  costs five times opening one. `engine.py` charges on a single position's
  change, which is the same rule applied to a book of one.

Known limitation, stated here because a validation harness that hides it is
worse than none: the universe is *today's* index membership. Backtesting current
S&P 500 constituents over past years is survivorship-biased, since it only ever
tests companies that made it in and stayed. Results are optimistic by an unknown
amount, and the fix is point-in-time constituent history, which the project does
not have. Treat absolute returns as untrustworthy and comparisons between two
configs over the same universe as meaningful.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from diyquant.risk.selection import select_positions
from diyquant.signals.base import conviction_series

TRADING_DAYS = 252


@dataclass
class PortfolioResult:
    equity_curve: pd.Series  # cumulative growth, 1.0 = start
    benchmark_curve: pd.Series  # equal-weight universe, same basis
    daily_returns: pd.Series
    weights: pd.DataFrame  # signed weight per symbol per date
    total_return: float
    benchmark_return: float
    cagr: float
    sharpe: float
    max_drawdown: float
    annual_turnover: float
    hit_rate: float
    n_positions: int  # closed position episodes
    trade_returns: list[float] = field(default_factory=list)

    def summary(self) -> str:
        excess = self.total_return - self.benchmark_return
        cagr = "n/a (under 1y)" if pd.isna(self.cagr) else f"{self.cagr:+.1%}"
        # Stitched walk-forward records leave these unset: they are per-window
        # quantities and averaging them across joined slices would invent a number.
        turnover = (
            "n/a (per window)" if pd.isna(self.annual_turnover) else f"{self.annual_turnover:.1f}x"
        )
        hit = (
            "n/a (per window)"
            if pd.isna(self.hit_rate)
            else f"{self.hit_rate:.1%} of {self.n_positions} positions"
        )
        return (
            f"Strategy return : {self.total_return:+.1%}\n"
            f"Equal-weight uni: {self.benchmark_return:+.1%}\n"
            f"Excess          : {excess:+.1%}\n"
            f"CAGR            : {cagr}\n"
            f"Sharpe (ann.)   : {self.sharpe:.2f}\n"
            f"Max drawdown    : {self.max_drawdown:.1%}\n"
            f"Turnover (ann.) : {turnover}\n"
            f"Hit rate        : {hit}"
        )


def _aligned(
    bars_by_symbol: dict[str, pd.DataFrame], strategy: object
) -> tuple[list[str], pd.DatetimeIndex, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Signals, convictions, simple returns and a validity mask on one date grid.

    Each series is computed over that symbol's own full history first, so a
    rolling window is never truncated by another symbol's start date, and only
    then reindexed onto the shared calendar.

    The validity mask is what keeps the benchmark honest. Symbols enter and leave
    the calendar at different dates, and treating a symbol that has not listed yet
    as a 0% return silently drags the equal-weight universe toward zero in every
    early period. Measured on the real store that understated the benchmark by
    about 9 percentage points over eight years, which is more than enough to turn
    a losing strategy into an apparently winning one.
    """
    signals, strengths, returns = {}, {}, {}
    for symbol, bars in bars_by_symbol.items():
        signals[symbol] = strategy.generate(bars)
        strengths[symbol] = conviction_series(strategy, bars)
        returns[symbol] = bars["close"].pct_change()

    sig = pd.DataFrame(signals).sort_index()
    dates = sig.index
    raw_ret = pd.DataFrame(returns).reindex(dates)
    valid = raw_ret.notna()

    # A symbol with no bar on a date is not tradable there: signal 0 keeps it out
    # of the candidate set, and a 0 return means holding it contributes nothing.
    sig = sig.fillna(0.0)
    stg = pd.DataFrame(strengths).reindex(dates).fillna(0.0)
    ret = raw_ret.fillna(0.0)

    symbols = list(sig.columns)
    return (
        symbols,
        dates,
        sig.to_numpy(dtype=float),
        stg[symbols].to_numpy(dtype=float),
        ret[symbols].to_numpy(dtype=float),
        valid[symbols].to_numpy(dtype=bool),
    )


def _position_returns(held_w: np.ndarray, ret: np.ndarray) -> list[float]:
    """Compounded return of each completed position, for a position-level hit rate.

    A hit rate over *days* mostly measures how often the market went up, since
    the book is long-biased and every held day counts. What a strategy should be
    judged on is how often a decision to hold a name worked out, so this walks
    each symbol's run of non-zero weight and compounds the return over it,
    signed by the direction held. A short that fell is a win.

    Positions still open at the end are included: excluding them would drop
    exactly the ones a losing strategy tends to be sitting on.
    """
    closed: list[float] = []
    # Only a handful of a 500-name universe is ever funded, so skip the columns
    # that were never held rather than walking every symbol's full history.
    for j in np.nonzero(np.any(held_w != 0, axis=0))[0]:
        sides = np.sign(held_w[:, j])
        growth = 1.0
        current = 0.0
        for i, side in enumerate(sides):
            # A flip straight from long to short closes one position and opens
            # another; it never passes through zero, so sign changes end an
            # episode just as going flat does.
            if side != current:
                if current != 0.0:
                    closed.append(growth - 1.0)
                growth = 1.0
                current = side
            if side != 0.0:
                growth *= 1.0 + side * ret[i, j]
        if current != 0.0:
            closed.append(growth - 1.0)
    return closed


def run_portfolio_backtest(
    bars_by_symbol: dict[str, pd.DataFrame],
    strategy: object,
    max_positions: int = 5,
    hysteresis_rank: int = 10,
    cost_bps: float = 5.0,
    slippage_bps: float = 2.0,
) -> PortfolioResult:
    """Replay the selection pipeline over history and score what it would have done."""
    if not bars_by_symbol:
        raise ValueError("no bars given")

    symbols, dates, sig, stg, ret, valid = _aligned(bars_by_symbol, strategy)
    idx_of = {s: j for j, s in enumerate(symbols)}
    n_dates, n_symbols = sig.shape
    weights = np.zeros((n_dates, n_symbols))

    # Sequential because hysteresis makes today's book depend on yesterday's:
    # an incumbent keeps its slot on a rank it would not win from outside.
    direction: dict[str, int] = {}  # symbol -> signed position currently funded

    for i in range(n_dates):
        row_sig, row_stg = sig[i], stg[i]
        candidates = {symbols[j]: float(row_stg[j]) for j in np.nonzero(row_sig)[0]}
        # An incumbent whose signal flipped is not an incumbent: it should be
        # closed or reversed on merit, not shielded by the buffer. Mirrors
        # execution/pipeline.py.
        held = {s for s, d in direction.items() if s in candidates and row_sig[idx_of[s]] == d}
        funded = select_positions(candidates, held, max_positions, hysteresis_rank)

        if funded:
            share = 1.0 / len(funded)
            for s in funded:
                weights[i, idx_of[s]] = row_sig[idx_of[s]] * share
        direction = {s: int(row_sig[idx_of[s]]) for s in funded}

    # Position held DURING date i is the one selected at i-1: no look-ahead.
    held_w = np.vstack([np.zeros((1, n_symbols)), weights[:-1]])
    gross = (held_w * ret).sum(axis=1)
    turnover = np.abs(np.diff(held_w, axis=0, prepend=np.zeros((1, n_symbols)))).sum(axis=1)
    costs = turnover * (cost_bps + slippage_bps) / 10_000
    port_ret = gross - costs

    closed = _position_returns(held_w, ret)

    returns_s = pd.Series(port_ret, index=dates)
    equity = (1 + returns_s).cumprod()
    # Equal weight across the symbols actually trading that day, not across every
    # column ever seen. Divide by the live count, never by the full universe.
    live = valid.sum(axis=1)
    bench_ret = pd.Series(
        np.divide((ret * valid).sum(axis=1), live, out=np.zeros(n_dates), where=live > 0),
        index=dates,
    )
    benchmark = (1 + bench_ret).cumprod()

    years = n_dates / TRADING_DAYS
    total_return = float(equity.iloc[-1] - 1)
    # Annualising a sub-year sample produces a headline number that is arithmetically
    # correct and wildly misleading: four good days compound to billions of percent.
    # A harness built to stop self-deception must not be the thing printing it.
    cagr = float(equity.iloc[-1] ** (1 / years) - 1) if years >= 1 else float("nan")
    sharpe = (
        float(returns_s.mean() / returns_s.std() * np.sqrt(TRADING_DAYS))
        if returns_s.std() > 0
        else 0.0
    )
    drawdown = equity / equity.cummax() - 1
    wins = [r for r in closed if r > 0]

    return PortfolioResult(
        equity_curve=equity,
        benchmark_curve=benchmark,
        daily_returns=returns_s,
        weights=pd.DataFrame(weights, index=dates, columns=symbols),
        total_return=total_return,
        benchmark_return=float(benchmark.iloc[-1] - 1),
        cagr=cagr,
        sharpe=sharpe,
        max_drawdown=float(drawdown.min()),
        annual_turnover=float(turnover.mean() * TRADING_DAYS / 2),
        hit_rate=len(wins) / len(closed) if closed else 0.0,
        n_positions=len(closed),
        trade_returns=closed,
    )
