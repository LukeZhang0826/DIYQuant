# DIYQuant

A retail-scale, end-to-end quantitative trading pipeline in Python:
**data → signal → risk → execution**, with an NLP news-sentiment filter as the
alternative-data layer (Phase 2).

> Paper trading only. This is a systems-engineering project, not financial advice.

## Architecture

```
[Provider APIs] → [Parquet Store] → [Signal (pure fn)] → [Risk Limits] → [Broker (paper)]
                                          ↑
                              [FinBERT news sentiment filter]   (Phase 2)
```

Design rules:
- Signals are pure functions: bars in, target position out. No I/O, no state.
- Risk sits between signal and execution, non-optionally (drawdown kill-switch, position caps).
- Providers/brokers are interfaces — swapping data sources or paper→live is a config change.
- No look-ahead: signals at bar T execute at T+1; every backtest includes costs and slippage.

## Quickstart

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -e ".[dev]"

python scripts/backfill.py       # pull daily bars for the configured universe
python scripts/run_backtest.py   # run SMA crossover backtest with costs
pytest                           # run tests
```

Configuration lives in `config/settings.yaml` (parameters) and `.env` (secrets — copy
`.env.example`; Phase 1 needs no keys).

## Roadmap

- [x] Phase 1: data layer, parquet store, vectorized backtester, SMA crossover baseline
- [ ] Phase 2: FinBERT sentiment filter (age decay + source whitelist), risk module, Alpaca paper execution
- [ ] Phase 3: VPS deployment, Discord heartbeat/alerts, live paper track record
