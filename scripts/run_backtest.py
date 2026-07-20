"""Run the configured strategy over stored bars for one ticker.

Usage: python scripts/run_backtest.py [TICKER]   (default: first ticker in universe)
"""

import sys

from diyquant.backtest.engine import run_backtest
from diyquant.config import get_settings
from diyquant.data.store import load_bars
from diyquant.signals.technical.sma_crossover import SmaCrossover


def main() -> None:
    settings = get_settings()
    ticker = sys.argv[1].upper() if len(sys.argv) > 1 else settings.universe["tickers"][0]

    bars = load_bars(ticker)
    strategy = SmaCrossover(**settings.strategy.params)
    signal = strategy.generate(bars)
    result = run_backtest(
        bars,
        signal,
        cost_bps=settings.backtest.cost_bps,
        slippage_bps=settings.backtest.slippage_bps,
    )

    print(f"=== {ticker} | {settings.strategy.name} {settings.strategy.params} ===")
    print(result.summary())


if __name__ == "__main__":
    main()
