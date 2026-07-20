"""One daily paper-trading cycle. Schedule after market close (orders fill next open).

Usage: python scripts/run_live.py
Requires ALPACA_API_KEY / ALPACA_SECRET_KEY in .env (paper account).
"""

from diyquant.config import PROJECT_ROOT, get_secrets, get_settings
from diyquant.data.providers.yfinance_provider import YFinanceProvider
from diyquant.execution.alpaca_broker import AlpacaBroker
from diyquant.execution.ledger import Ledger
from diyquant.execution.pipeline import run_once
from diyquant.signals.technical.sma_crossover import SmaCrossover


def main() -> None:
    settings = get_settings()
    secrets = get_secrets()

    broker = AlpacaBroker(
        secrets.alpaca_api_key, secrets.alpaca_secret_key, paper=secrets.alpaca_paper
    )
    ledger = Ledger(PROJECT_ROOT / settings.execution.ledger_path)
    provider = YFinanceProvider()
    strategy = SmaCrossover(**settings.strategy.params)

    bars_by_symbol = {
        ticker: provider.fetch_daily_bars(ticker, settings.data.start)
        for ticker in settings.universe["tickers"]
    }

    report = run_once(
        broker=broker,
        ledger=ledger,
        bars_by_symbol=bars_by_symbol,
        strategy=strategy,
        strategy_name=settings.strategy.name,
        settings=settings,
    )
    ledger.close()
    print(report.summary())


if __name__ == "__main__":
    main()
