"""Make market exposure a decision instead of a by-product.

The book has never chosen its beta. It measured **-0.66** before volatility
sizing, -0.17 after, and +0.09 across the 21-year sample: three different
answers, none of them intended, all of them just whatever fell out of which
names the ranking happened to pick that day. `docs/baseline.md` traced the
original -0.66 to the ranking metric preferring large moves, which belong to
high-beta names, and the short leg then carrying -1.18 beta on 0.36 of the
gross weight.

The fix chosen for Stage 5 is an **index hedge**, not rescaling the two legs.
Rescaling would hit the target by overriding the volatility risk budgets shipped
on 2026-08-08, undoing per-name risk control to fix a portfolio-level problem,
and it cannot neutralise a book at all when every pick points the same way, which
happens whenever the trend is one-directional. A hedge leaves the five picks at
exactly the sizes the risk budget gave them and puts the entire exposure decision
into one explicitly sized, explicitly logged position.

Because the hedge instrument *is* the market proxy the betas are measured
against, its own beta is 1.0 by construction and the arithmetic collapses to a
subtraction. That is a deliberate simplification: measuring symbol betas against
one index and hedging with a different one would introduce a basis nobody is
tracking.
"""

from dataclasses import dataclass

import pandas as pd

# A name whose beta cannot be estimated is assumed to behave like the market
# rather than like cash. Zero would quietly claim a position carries no market
# exposure, which is the least likely value for an equity and would leave the
# book under-hedged in exactly the situation where least is known.
DEFAULT_BETA = 1.0


@dataclass(frozen=True)
class HedgePlan:
    weight: float  # signed weight of the hedge instrument, as a fraction of equity
    book_beta: float  # beta of the five picks before hedging
    assumed: tuple[str, ...] = ()  # symbols whose beta had to be assumed


def rolling_beta(symbol_returns: pd.Series, market_returns: pd.Series, lookback: int) -> pd.Series:
    """Rolling OLS beta of one symbol against the market proxy.

    Plain covariance over variance on simple returns, matching how
    `backtest.portfolio.alpha_beta` computes the book-level figure, so a
    per-symbol beta and the reported portfolio beta mean the same thing.

    NaN until the lookback fills, and NaN wherever the market has no variance.
    Callers must treat that as unknown, never as zero: see DEFAULT_BETA.
    """
    if lookback < 2:
        raise ValueError(f"lookback must be at least 2, got {lookback}")
    covariance = symbol_returns.rolling(lookback).cov(market_returns)
    variance = market_returns.rolling(lookback).var()
    return covariance / variance.replace(0.0, float("nan"))


def plan_hedge(
    weights: dict[str, float],
    betas: dict[str, float],
    target_beta: float,
) -> HedgePlan:
    """Size the hedge that moves the book's beta to `target_beta`.

    `weights` are signed fractions of equity, negative for shorts. `betas` maps
    each held symbol to its estimated beta; a missing or NaN entry falls back to
    DEFAULT_BETA and is reported in `assumed` so the caller can surface how much
    of the hedge rests on a guess.

    The hedge instrument has beta 1.0 against itself, so the required weight is
    just the shortfall. A book already at target gets a zero-weight hedge, which
    costs nothing and trades nothing.
    """
    book_beta = 0.0
    assumed: list[str] = []
    for symbol, weight in weights.items():
        if weight == 0:
            continue
        beta = betas.get(symbol)
        if beta is None or beta != beta:  # NaN != NaN
            beta = DEFAULT_BETA
            assumed.append(symbol)
        book_beta += weight * beta
    return HedgePlan(
        weight=target_beta - book_beta,
        book_beta=book_beta,
        assumed=tuple(sorted(assumed)),
    )
