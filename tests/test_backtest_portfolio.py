import numpy as np
import pandas as pd
import pytest

from diyquant.backtest.portfolio import run_portfolio_backtest


class Scripted:
    """Signal and conviction read from per-symbol scripts, so ranking is exact."""

    def __init__(self, signals: dict[str, list[int]], scores: dict[str, float]):
        self.signals = signals
        self.scores = scores

    def generate(self, bars: pd.DataFrame) -> pd.Series:
        return pd.Series(self.signals[bars.attrs["sym"]], index=bars.index, dtype=int)

    def strength_series(self, bars: pd.DataFrame) -> pd.Series:
        return pd.Series(self.scores[bars.attrs["sym"]], index=bars.index, dtype=float)


def bars_from(sym: str, daily_returns: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2024-01-01", periods=len(daily_returns) + 1, freq="B")
    close = np.concatenate([[100.0], 100 * np.cumprod(1 + np.array(daily_returns))])
    frame = pd.DataFrame({"close": close}, index=idx)
    frame.attrs["sym"] = sym
    return frame


def build(rets: dict[str, list[float]], scores: dict[str, float], signal: int = 1):
    bars = {s: bars_from(s, r) for s, r in rets.items()}
    n = len(next(iter(bars.values())))
    strategy = Scripted({s: [signal] * n for s in rets}, scores)
    return bars, strategy


def test_only_max_positions_are_funded():
    """The reason this engine exists: live holds five of five hundred, not all of them."""
    bars, strategy = build(
        {"A": [0.01] * 4, "B": [0.01] * 4, "C": [0.01] * 4, "D": [0.01] * 4},
        {"A": 4.0, "B": 3.0, "C": 2.0, "D": 1.0},
    )
    result = run_portfolio_backtest(bars, strategy, max_positions=2, hysteresis_rank=2)

    funded = (result.weights != 0).sum(axis=1)
    assert funded.max() == 2
    # Ranked on conviction, so the two weakest never get a slot.
    assert (result.weights["C"] == 0).all()
    assert (result.weights["D"] == 0).all()


def test_funded_names_are_equally_weighted():
    bars, strategy = build(
        {"A": [0.01] * 4, "B": [0.01] * 4, "C": [0.01] * 4},
        {"A": 3.0, "B": 2.0, "C": 1.0},
    )
    result = run_portfolio_backtest(bars, strategy, max_positions=2, hysteresis_rank=2)
    row = result.weights.iloc[-1]
    assert row["A"] == row["B"] == 0.5
    assert row.abs().sum() == 1.0


def test_a_signal_cannot_earn_the_return_of_the_bar_that_produced_it():
    """No look-ahead, and the single most damaging thing that could break here.

    The signal turns on at bar 1, so the position is only held from bar 2. The
    entry bar's own +10% must not be collected. Deliberately tested with a signal
    that *changes*: with a constant signal the first bar has no prior close, so
    its return is zero either way and a missing shift would go unnoticed.
    """
    bars = {"A": bars_from("A", [0.10, 0.10, 0.10])}
    strategy = Scripted({"A": [0, 1, 1, 1]}, {"A": 1.0})
    result = run_portfolio_backtest(
        bars, strategy, max_positions=1, hysteresis_rank=1, cost_bps=0, slippage_bps=0
    )

    # Two bars of return collected, not three. Unshifted this would be 1.10**3.
    assert result.equity_curve.iloc[-1] == pytest.approx(1.10**2)


def test_a_short_position_profits_when_the_price_falls():
    bars, strategy = build({"A": [-0.10, -0.10]}, {"A": 1.0}, signal=-1)
    result = run_portfolio_backtest(bars, strategy, max_positions=1, hysteresis_rank=1)
    assert result.total_return > 0
    assert result.trade_returns[0] > 0


def test_costs_scale_with_the_number_of_positions_opened():
    """Opening five costs five times opening one, which single-ticker costing misses."""
    one, s1 = build({"A": [0.0] * 4}, {"A": 1.0})
    five = {chr(65 + i): [0.0] * 4 for i in range(5)}
    many, s5 = build(five, {chr(65 + i): float(i) for i in range(5)})

    cheap = run_portfolio_backtest(one, s1, max_positions=1, hysteresis_rank=1, cost_bps=10)
    dear = run_portfolio_backtest(many, s5, max_positions=5, hysteresis_rank=5, cost_bps=10)

    # Flat prices, so all of the loss is cost. Equal weights mean the total
    # traded notional is the same, hence the same drag, not five times it.
    assert cheap.total_return < 0
    assert dear.total_return == pytest.approx(cheap.total_return)


def test_cagr_is_withheld_on_a_sub_year_sample():
    """Annualising four days yields billions of percent. Refusing to print it is the point."""
    bars, strategy = build({"A": [0.10] * 4}, {"A": 1.0})
    result = run_portfolio_backtest(bars, strategy, max_positions=1, hysteresis_rank=1)
    assert np.isnan(result.cagr)
    assert "n/a" in result.summary()


def test_hit_rate_counts_positions_not_days():
    """One position held over many days is one outcome, not many."""
    bars, strategy = build({"A": [0.05] * 6}, {"A": 1.0})
    result = run_portfolio_backtest(bars, strategy, max_positions=1, hysteresis_rank=1)
    assert result.n_positions == 1
    assert result.hit_rate == 1.0


def test_a_flip_from_long_to_short_is_two_positions():
    """A reversal never passes through flat, so it must still close one and open another."""
    n = 6
    signals = {"A": [1, 1, 1, -1, -1, -1, -1]}
    bars = {"A": bars_from("A", [0.01] * n)}
    strategy = Scripted(signals, {"A": 1.0})
    result = run_portfolio_backtest(bars, strategy, max_positions=1, hysteresis_rank=1)
    assert result.n_positions == 2


def test_benchmark_is_the_whole_universe_not_the_funded_names():
    """Beating five names you picked is meaningless; the comparison must be the universe."""
    bars, strategy = build(
        {"WINNER": [0.10] * 4, "LOSER": [-0.10] * 4},
        {"WINNER": 2.0, "LOSER": 1.0},
    )
    result = run_portfolio_backtest(bars, strategy, max_positions=1, hysteresis_rank=1)

    # Strategy holds only WINNER; benchmark carries both, so it lands between them.
    assert result.total_return > result.benchmark_return
    assert result.benchmark_return == pytest.approx(0.0, abs=0.02)


def test_a_symbol_with_no_bars_on_a_date_is_not_funded():
    """Universe turnover means symbols start and stop mid-history."""
    long_bars = bars_from("OLD", [0.01] * 6)
    short_bars = bars_from("NEW", [0.05] * 6).iloc[4:]  # listed late
    strategy = Scripted({"OLD": [1] * 7, "NEW": [1] * 3}, {"OLD": 1.0, "NEW": 99.0})

    result = run_portfolio_backtest(
        {"OLD": long_bars, "NEW": short_bars}, strategy, max_positions=1, hysteresis_rank=1
    )
    # NEW outranks OLD but cannot be held before it existed.
    assert (result.weights["NEW"].iloc[:4] == 0).all()


def test_benchmark_ignores_symbols_that_have_no_data_yet():
    """Regression: an unlisted symbol must not count as a 0% return.

    Averaging across every column ever seen drags the equal-weight universe
    toward zero for every date before a late-listing symbol exists. On the real
    503-name store that understated the benchmark by ~9 percentage points over
    eight years, which is more than enough to make a losing strategy look like a
    winning one. Nothing else in the suite would have shown it.
    """
    early = bars_from("EARLY", [0.10] * 4)
    late = bars_from("LATE", [0.10] * 4).iloc[4:]  # exists only at the very end
    strategy = Scripted({"EARLY": [1] * 5, "LATE": [1]}, {"EARLY": 1.0, "LATE": 1.0})

    result = run_portfolio_backtest(
        {"EARLY": early, "LATE": late}, strategy, max_positions=2, hysteresis_rank=2
    )
    # Every live symbol returned 10% a day, so the universe did too. If LATE's
    # absent dates counted as 0%, this would come out near half that.
    assert result.benchmark_return == pytest.approx(1.10**4 - 1, abs=0.01)


def test_funding_every_name_long_reproduces_the_benchmark():
    """The engine's own plumbing check, and how the bug above was found.

    Holding all names equally, always long, with no costs, is the equal-weight
    universe by definition. Any gap is the machinery disagreeing with itself.
    """
    rets = {"A": [0.03, -0.01, 0.02], "B": [-0.02, 0.04, 0.01], "C": [0.01, 0.01, -0.03]}
    bars, strategy = build(rets, {"A": 1.0, "B": 1.0, "C": 1.0})

    result = run_portfolio_backtest(
        bars, strategy, max_positions=3, hysteresis_rank=3, cost_bps=0, slippage_bps=0
    )
    # The strategy sits out its first bar, so compare from the second onward.
    strat = (1 + result.daily_returns.iloc[1:]).prod()
    bench = (1 + pd.Series(result.benchmark_curve).pct_change().iloc[1:]).prod()
    assert strat == pytest.approx(bench)
