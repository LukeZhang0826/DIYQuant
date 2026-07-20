"""Alpaca paper-trading adapter for the Broker protocol.

Paper only: the constructor refuses live mode outright. Orders are
market-on-open (OPG) so a signal from bar T executes at bar T+1's open.
"""

from alpaca.common.exceptions import APIError
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from diyquant.execution.base import AccountState, FillInfo, OrderResult


class AlpacaBroker:
    def __init__(self, api_key: str, secret_key: str, paper: bool = True):
        if not paper:
            raise ValueError("Live trading is disabled: paper only until explicitly enabled.")
        if not api_key or not secret_key:
            raise ValueError("Alpaca keys missing: set ALPACA_API_KEY / ALPACA_SECRET_KEY in .env")
        self._client = TradingClient(api_key, secret_key, paper=True)

    def get_account(self) -> AccountState:
        acct = self._client.get_account()
        return AccountState(cash=float(acct.cash), equity=float(acct.equity))

    def get_position(self, symbol: str) -> int:
        try:
            pos = self._client.get_open_position(symbol)
        except APIError:
            return 0
        return int(float(pos.qty))

    def submit_market_order(self, symbol: str, qty: int) -> OrderResult:
        if qty == 0:
            raise ValueError("qty must be non-zero")
        order = self._client.submit_order(
            order_data=MarketOrderRequest(
                symbol=symbol,
                qty=abs(qty),
                side=OrderSide.BUY if qty > 0 else OrderSide.SELL,
                time_in_force=TimeInForce.OPG,
            )
        )
        return OrderResult(broker_order_id=str(order.id), status=str(order.status.value))

    def get_order_fill(self, broker_order_id: str) -> FillInfo:
        order = self._client.get_order_by_id(broker_order_id)
        return FillInfo(
            status=str(order.status.value),
            filled_qty=int(float(order.filled_qty or 0)),
            avg_price=float(order.filled_avg_price or 0.0),
        )
