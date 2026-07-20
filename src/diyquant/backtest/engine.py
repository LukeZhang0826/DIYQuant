"""Vectorized daily backtester with transaction costs and slippage.

Signal at bar T is executed at bar T+1 (shift(1)) — no look-ahead.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class BacktestResult:
    equity_curve: pd.Series          # strategy cumulative growth (1.0 = start)
    benchmark_curve: pd.Series       # buy-and-hold cumulative growth
    total_return: float
    benchmark_return: float
    cagr: float
    sharpe: float
    max_drawdown: float
    n_trades: int

    def summary(self) -> str:
        return (
            f"Strategy return : {self.total_return:+.1%}\n"
            f"Buy-hold return : {self.benchmark_return:+.1%}\n"
            f"CAGR            : {self.cagr:+.1%}\n"
            f"Sharpe (ann.)   : {self.sharpe:.2f}\n"
            f"Max drawdown    : {self.max_drawdown:.1%}\n"
            f"Trades          : {self.n_trades}"
        )


def run_backtest(
    bars: pd.DataFrame,
    signal: pd.Series,
    cost_bps: float = 5.0,
    slippage_bps: float = 2.0,
) -> BacktestResult:
    close = bars["close"]
    market_ret = np.log(close / close.shift(1))

    # Position held DURING bar T is the signal computed at T-1
    position = signal.shift(1).fillna(0)

    # Cost charged whenever position changes, proportional to size of the change
    turnover = position.diff().abs().fillna(0)
    cost_per_unit = (cost_bps + slippage_bps) / 10_000
    costs = turnover * cost_per_unit

    strat_ret = market_ret * position - costs

    equity = np.exp(strat_ret.cumsum())
    benchmark = np.exp(market_ret.cumsum())

    n_days = len(strat_ret.dropna())
    years = n_days / 252
    total_return = float(equity.iloc[-1] - 1)
    cagr = float(equity.iloc[-1] ** (1 / years) - 1) if years > 0 else 0.0
    daily = strat_ret.dropna()
    sharpe = float(daily.mean() / daily.std() * np.sqrt(252)) if daily.std() > 0 else 0.0
    drawdown = equity / equity.cummax() - 1

    return BacktestResult(
        equity_curve=equity,
        benchmark_curve=benchmark,
        total_return=total_return,
        benchmark_return=float(benchmark.iloc[-1] - 1),
        cagr=cagr,
        sharpe=sharpe,
        max_drawdown=float(drawdown.min()),
        n_trades=int((turnover > 0).sum()),
    )
