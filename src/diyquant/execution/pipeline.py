"""One live trading cycle: signal -> risk -> execution, with everything recorded.

Order of operations each cycle:
  1. Reconcile fills for orders submitted in earlier cycles.
  2. Snapshot account equity.
  3. If a halt is active, stop here (a human must clear it).
  4. Kill-switch: if equity dropped past the daily limit since the previous
     snapshot, halt, flatten every position, and stop. Skipped when that
     snapshot is too stale to stand in for the start of the trading day.
  5. Per symbol: compute the signal, size it, cap-check it, submit the delta.

The broker is the source of truth for current positions; the ledger's derived
position exists to reconcile against it (Phase 3 alerting).
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pandas as pd

from diyquant.config import Settings
from diyquant.execution.base import Broker
from diyquant.execution.ledger import Ledger
from diyquant.risk.limits import check_daily_drawdown, check_position_cap
from diyquant.risk.sizing import target_shares
from diyquant.signals.base import Signal
from diyquant.signals.sentiment.filter import apply_sentiment_gate


@dataclass
class CycleReport:
    halted: bool = False
    fills_reconciled: int = 0
    orders_submitted: int = 0
    orders_blocked: int = 0
    notes: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"halted           : {self.halted}",
            f"fills reconciled : {self.fills_reconciled}",
            f"orders submitted : {self.orders_submitted}",
            f"orders blocked   : {self.orders_blocked}",
        ]
        lines += self.notes
        return "\n".join(lines)


def _hours_since(ts: str) -> float:
    return (datetime.now(timezone.utc) - datetime.fromisoformat(ts)).total_seconds() / 3600


def _reconcile_fills(broker: Broker, ledger: Ledger, report: CycleReport) -> None:
    for order in ledger.pending_orders():
        fill = broker.get_order_fill(order["broker_order_id"])
        if fill.status == "filled":
            ledger.record_fill(
                order_id=order["id"],
                symbol=order["symbol"],
                side=order["side"],
                qty=fill.filled_qty,
                price=fill.avg_price,
            )
            ledger.update_order_status(order["id"], "filled")
            report.fills_reconciled += 1
        elif fill.status in ("canceled", "expired", "rejected"):
            ledger.update_order_status(order["id"], "canceled")
            report.notes.append(f"order {order['id']} {order['symbol']}: {fill.status}")


def _flatten_all(
    broker: Broker, ledger: Ledger, symbols: list[str], reason: str, report: CycleReport
) -> None:
    for symbol in symbols:
        held = broker.get_position(symbol)
        if held == 0:
            continue
        result = broker.submit_market_order(symbol, -held)
        ledger.record_order(
            symbol=symbol,
            side="sell" if held > 0 else "buy",
            qty=abs(held),
            signal_name="kill_switch",
            signal_value=0,
            status="submitted",
            risk_reason=reason,
            broker_order_id=result.broker_order_id,
        )
        report.orders_submitted += 1


def run_once(
    broker: Broker,
    ledger: Ledger,
    bars_by_symbol: dict[str, pd.DataFrame],
    strategy: Signal,
    strategy_name: str,
    settings: Settings,
    sentiment_scores: dict[str, float | None] | None = None,
) -> CycleReport:
    report = CycleReport()
    risk_cfg = settings.risk

    _reconcile_fills(broker, ledger, report)

    account = broker.get_account()
    baseline = ledger.last_equity_snapshot()
    ledger.record_equity_snapshot(cash=account.cash, equity=account.equity)

    halt = ledger.active_halt()
    if halt is not None:
        report.halted = True
        report.notes.append(f"halted since {halt['triggered_at']}: {halt['reason']}")
        return report

    if baseline is not None:
        age_hours = _hours_since(baseline["ts"])
        if age_hours > risk_cfg.max_baseline_age_hours:
            # A stale baseline turns the daily check into a multi-day one, which
            # would flatten the book on ordinary drift after any outage.
            report.notes.append(
                f"drawdown check skipped: baseline is {age_hours:.1f}h old, "
                f"limit {risk_cfg.max_baseline_age_hours:.0f}h"
            )
        else:
            decision = check_daily_drawdown(
                day_start_equity=float(baseline["equity"]),
                current_equity=account.equity,
                max_daily_drawdown_pct=risk_cfg.max_daily_drawdown_pct,
            )
            if not decision.allowed:
                ledger.trigger_halt(decision.reason)
                _flatten_all(broker, ledger, list(bars_by_symbol), decision.reason, report)
                report.halted = True
                report.notes.append(f"KILL SWITCH: {decision.reason}")
                return report

    for symbol, bars in bars_by_symbol.items():
        signal = strategy.generate(bars)
        target = int(signal.iloc[-1])
        if sentiment_scores is not None:
            target, gate_reason = apply_sentiment_gate(
                target,
                sentiment_scores.get(symbol),
                settings.sentiment.gate_threshold,
            )
            if gate_reason:
                report.notes.append(f"{symbol}: {gate_reason}")
        price = float(bars["close"].iloc[-1])
        shares = target_shares(
            target=target,
            equity=account.equity,
            price=price,
            max_position_pct=risk_cfg.max_position_pct,
        )
        delta = shares - broker.get_position(symbol)
        if delta == 0:
            continue

        side = "buy" if delta > 0 else "sell"
        cap = check_position_cap(
            position_value=shares * price,
            equity=account.equity,
            max_position_pct=risk_cfg.max_position_pct,
        )
        if not cap.allowed:
            ledger.record_order(
                symbol=symbol,
                side=side,
                qty=abs(delta),
                signal_name=strategy_name,
                signal_value=target,
                status="blocked",
                risk_reason=cap.reason,
            )
            report.orders_blocked += 1
            continue

        result = broker.submit_market_order(symbol, delta)
        ledger.record_order(
            symbol=symbol,
            side=side,
            qty=abs(delta),
            signal_name=strategy_name,
            signal_value=target,
            status="submitted",
            broker_order_id=result.broker_order_id,
        )
        report.orders_submitted += 1

    return report
