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

from diyquant.risk.hedge import plan_hedge
from diyquant.risk.selection import select_positions
from diyquant.risk.sizing import DEFAULT_VOL_LOOKBACK, realized_vol_pct, volatility_budget_pct
from diyquant.signals.base import conviction_series

TRADING_DAYS = 252
DEFAULT_BETA_LOOKBACK = 120


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
    alpha: float = 0.0  # annualised excess over what beta alone explains
    beta: float = 0.0  # exposure to the equal-weight universe
    # Mean sum of absolute weights: 1.0 is fully invested, 0.5 is half in cash.
    # Equal weighting pins this at 1.0, so it only says anything once sizing can
    # choose to hold less. Without it a volatility-scaled config looks simply
    # worse than the baseline, when part of the gap is it being less invested.
    avg_gross_exposure: float = float("nan")
    gross_exposure: pd.Series = field(default_factory=pd.Series)
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
            f"Beta to universe: {self.beta:+.2f}\n"
            f"Alpha (ann.)    : {self.alpha:+.1%}\n"
            f"Gross exposure  : {self.avg_gross_exposure:.2f}x\n"
            f"Turnover (ann.) : {turnover}\n"
            f"Hit rate        : {hit}"
        )


def _aligned(
    bars_by_symbol: dict[str, pd.DataFrame], strategy: object, vol_lookback: int
) -> tuple[list[str], pd.DatetimeIndex, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Signals, convictions, volatilities, simple returns and a validity mask on one date grid.

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
    signals, strengths, returns, vols = {}, {}, {}, {}
    for symbol, bars in bars_by_symbol.items():
        signals[symbol] = strategy.generate(bars)
        strengths[symbol] = conviction_series(strategy, bars)
        returns[symbol] = bars["close"].pct_change()
        # Skipped entirely when sizing will not consult it. A walk-forward fits
        # 16 parameter combinations per window and every one of them would
        # otherwise pay for a rolling standard deviation across ~500 symbols
        # that the equal-weight path never reads.
        if vol_lookback is not None:
            vols[symbol] = realized_vol_pct(bars["close"], vol_lookback)

    sig = pd.DataFrame(signals).sort_index()
    dates = sig.index
    raw_ret = pd.DataFrame(returns).reindex(dates)
    valid = raw_ret.notna()

    # A symbol with no bar on a date is not tradable there: signal 0 keeps it out
    # of the candidate set, and a 0 return means holding it contributes nothing.
    sig = sig.fillna(0.0)
    stg = pd.DataFrame(strengths).reindex(dates).fillna(0.0)
    ret = raw_ret.fillna(0.0)
    # Volatility keeps its NaNs on purpose, unlike every other frame here. NaN
    # means too little history to size the name, and filling it with 0 would
    # read as "perfectly calm" and hand it the largest allowed position.
    vol = pd.DataFrame(vols).reindex(dates)

    symbols = list(sig.columns)
    return (
        symbols,
        dates,
        sig.to_numpy(dtype=float),
        stg[symbols].to_numpy(dtype=float),
        vol[symbols].to_numpy(dtype=float),
        ret[symbols].to_numpy(dtype=float),
        valid[symbols].to_numpy(dtype=bool),
    )


def alpha_beta(strategy: pd.Series, benchmark: pd.Series) -> tuple[float, float]:
    """Split daily returns into market exposure and what beta does not explain.

    Beta is the slope of the strategy against the equal-weight universe; alpha
    is the intercept, annualised. The distinction decides what a shortfall
    means. A strategy that trails the index at beta 1.0 is losing to it on the
    same risk and is simply worse. One that trails at beta 0.2 is barely
    invested in the thing it is being compared to, and the honest read is that
    it is under-exposed rather than wrong, which points at position sizing or a
    market-neutral framing instead of at the signal.

    Zero variance in the benchmark leaves beta undefined; return 0.0 rather
    than a divide-by-zero, which only happens on degenerate inputs anyway.
    """
    paired = pd.concat([strategy, benchmark], axis=1).dropna()
    if len(paired) < 2:
        return 0.0, 0.0
    strat, bench = paired.iloc[:, 0], paired.iloc[:, 1]
    variance = float(bench.var())
    if variance == 0:
        return 0.0, 0.0
    beta = float(bench.cov(strat) / variance)
    daily_alpha = float(strat.mean() - beta * bench.mean())
    return daily_alpha * TRADING_DAYS, beta


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
    max_position_pct: float = 20.0,
    target_risk_pct: float = 0.0,
    vol_lookback: int = DEFAULT_VOL_LOOKBACK,
    hedge_symbol: str = "",
    target_beta: float = 0.0,
    beta_lookback: int = DEFAULT_BETA_LOOKBACK,
    borrow_bps: float = 0.0,
) -> PortfolioResult:
    """Replay the selection pipeline over history and score what it would have done.

    With `target_risk_pct` at 0 every funded name gets an equal share of the
    book, which is what the pipeline did before 2026-08-08 and what the ablation
    compares against. Above 0, each name instead gets the notional from
    `risk.sizing.volatility_budget_pct`, so the weights no longer sum to 1: a
    book of jumpy names is deliberately less invested than a book of calm ones,
    and the difference sits in cash earning nothing. That drag is the cost being
    measured, and it has to be paid out of the same equity curve as the benefit.

    `hedge_symbol` turns on Stage 5 beta targeting. The named instrument is
    excluded from candidacy and from the benchmark, since it is neither a pick
    nor a member of the universe being beaten, and instead carries whatever
    weight brings the book's beta to `target_beta`. Its cost, its turnover and
    its contribution to gross exposure are all charged normally: a hedge that
    looked free would be the same self-deception as a short leg that never paid
    borrow.

    `borrow_bps` is that borrow, as an **annual** rate charged daily on the
    notional held short. Until 2026-08-09 it did not exist and every short in
    this project was free, which flattered every result with a short leg in it,
    including the negative beta that the Stage 5 hedge was built to correct.
    It defaults to 0 so that older numbers stay reproducible; the shipped value
    lives in `backtest.borrow_bps`.

    Two deliberate omissions, both erring the same way. Cash earns no interest
    here and short proceeds earn none either, so a book holding half its equity
    in cash is charged the opportunity cost in full and credited nothing. And
    the rate is flat across names, where reality charges a few basis points for
    a mega-cap and hundreds for something hard to borrow. The first makes the
    result pessimistic, the second makes it optimistic for exactly the jumpy
    small names this strategy's ranking metric likes to short. Neither is
    modelled honestly enough to net off, which is why the shipped rate is chosen
    from a measured sensitivity range rather than from a single guess.
    """
    if not bars_by_symbol:
        raise ValueError("no bars given")
    if hedge_symbol and hedge_symbol not in bars_by_symbol:
        raise ValueError(f"hedge symbol {hedge_symbol!r} has no bars; backfill it first")

    symbols, dates, sig, stg, vol, ret, valid = _aligned(bars_by_symbol, strategy, vol_lookback)
    idx_of = {s: j for j, s in enumerate(symbols)}
    n_dates, n_symbols = sig.shape
    weights = np.zeros((n_dates, n_symbols))

    hedge_idx = idx_of[hedge_symbol] if hedge_symbol else None
    betas = np.empty((0, 0))
    if hedge_idx is not None:
        # Never a candidate: a zero signal keeps it out of `candidates` without
        # special-casing selection, and dropping it from `valid` keeps it out of
        # the equal-weight benchmark, which measures the universe rather than the
        # tools used to trade it. Copied because _aligned hands back pandas-backed
        # views, which are read-only.
        sig, valid = sig.copy(), valid.copy()
        sig[:, hedge_idx] = 0
        valid[:, hedge_idx] = False
        returns_frame = pd.DataFrame(ret, index=dates, columns=symbols)
        market = returns_frame[hedge_symbol]
        betas = (
            returns_frame.rolling(beta_lookback)
            .cov(market)
            .div(market.rolling(beta_lookback).var().replace(0.0, np.nan), axis=0)
            .to_numpy(dtype=float)
        )

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
                j = idx_of[s]
                if target_risk_pct > 0:
                    share = (
                        volatility_budget_pct(vol[i, j], target_risk_pct, max_position_pct) / 100
                    )
                weights[i, j] = row_sig[j] * share
        # Keyed off the weight, not off `funded`: a name whose volatility budget
        # came out 0 was selected but is not held, and the pipeline reads
        # incumbency from the broker's position, which would be 0 too.
        direction = {s: int(row_sig[idx_of[s]]) for s in funded if weights[i, idx_of[s]] != 0}

        if hedge_idx is not None:
            # Sized from the picks as they now stand, so the risk budgets above
            # are never overridden to hit a portfolio-level target.
            held_now = {s: weights[i, idx_of[s]] for s in direction}
            weights[i, hedge_idx] = plan_hedge(
                held_now,
                {s: betas[i, idx_of[s]] for s in direction},
                target_beta,
            ).weight

    # Position held DURING date i is the one selected at i-1: no look-ahead.
    held_w = np.vstack([np.zeros((1, n_symbols)), weights[:-1]])
    gross = (held_w * ret).sum(axis=1)
    turnover = np.abs(np.diff(held_w, axis=0, prepend=np.zeros((1, n_symbols)))).sum(axis=1)
    costs = turnover * (cost_bps + slippage_bps) / 10_000
    # Charged on the notional held short, every day it is held, unlike commission
    # and slippage which are charged once on the change. A short that never moves
    # costs nothing to trade and still accrues borrow for as long as it is open,
    # which is precisely the cost this book was not paying.
    short_notional = -np.minimum(held_w, 0.0).sum(axis=1)
    borrow = short_notional * (borrow_bps / 10_000) / TRADING_DAYS
    port_ret = gross - costs - borrow

    # The hedge is excluded from the hit rate: it is a risk instrument, not a
    # view on a company, and counting it as a won or lost position would measure
    # market direction under the heading of stock-picking skill.
    picks_w = held_w
    if hedge_idx is not None:
        picks_w = held_w.copy()
        picks_w[:, hedge_idx] = 0.0
    closed = _position_returns(picks_w, ret)

    gross_exp = pd.Series(np.abs(held_w).sum(axis=1), index=dates)
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
    ann_alpha, beta = alpha_beta(returns_s, bench_ret)

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
        alpha=ann_alpha,
        beta=beta,
        avg_gross_exposure=float(gross_exp.mean()),
        gross_exposure=gross_exp,
        trade_returns=closed,
    )
