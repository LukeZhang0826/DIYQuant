# DIYQuant

A retail-scale, end-to-end quantitative trading pipeline in Python:
**data → signal → risk → execution**, with an NLP news-sentiment filter as the
alternative-data layer.

Runs unattended on AWS every trading day and publishes what it did:

**Live dashboard → <https://d1d65vxvyvrbmn.cloudfront.net>**

> Paper trading only, against a simulated broker. This is a systems-engineering
> project, not financial advice and not a track record of profitability — see
> [What this does and does not show](#what-this-does-and-does-not-show).

## Architecture

```
[yfinance] → [Parquet store] → [Signal (pure fn)] → [Risk limits] → [Broker] → [Ledger]
                                       ↑                                          ↓
                        [FinBERT news sentiment gate]              [Dashboard · Backup · Alerts]
```

Design rules, all load-bearing:

- **Signals are pure functions.** Bars in, target position in `{-1, 0, +1}` out. No
  I/O, no state. This is what makes backtest/live parity provable.
- **Risk sits between signal and execution, non-optionally.** Drawdown kill-switch
  and position caps are properties of the pipeline, not features of a strategy.
- **Providers and brokers are interfaces.** Swapping data sources, or paper → live,
  is a config change rather than a code change.
- **No look-ahead.** A signal computed on bar T executes at bar T+1's open at the
  earliest. Every backtest includes transaction costs and slippage.
- **Zero secrets in code.** Keys come from `.env`, which is gitignored;
  `.env.example` documents what is needed.

## How a day runs

All times UTC, weekdays only. The US market closes at 21:00 UTC (16:00 ET).

| Time | Step | Failure behaviour |
| --- | --- | --- |
| 22:45 | Refresh the parquet bar store | dashboard sparklines go stale |
| 23:00 | Signal → sentiment gate → risk → orders | no healthcheck ping fires an alert |
| 23:10 | Regenerate and publish the dashboard | page goes stale, trading unaffected |
| 23:30 | Snapshot the ledger to S3 | backup gap, trading unaffected |

Each step degrades independently. Sentiment failures fall back to trading ungated
rather than skipping the cycle; alert failures never abort a trade.

## Operations

Deployed on a single `t4g.small` (arm64, Amazon Linux 2023) in `ca-central-1`.
Full runbook: [`docs/deploy.md`](docs/deploy.md).

- **Observability.** A Discord heartbeat after every cycle, leading with `HALTED`
  if the kill-switch fired.
- **A silent day is the alarm.** Because people do not reliably notice absence, an
  external dead-man's switch alerts when a scheduled run fails to check in.
  Monitoring hosted on the machine it monitors cannot report that machine's death.
- **Backups are append-only.** SQLite is snapshotted via `.backup` rather than
  copied, since copying a live database can capture a half-written transaction and
  restore as a corrupt file. Dated keys plus an IAM user with no `DeleteObject`
  mean a compromised host cannot erase its own backup history.
- **The box is push-only.** It writes outward to S3 and nothing reaches in, which
  is what lets the trading host keep an SSH-from-one-IP security group. The public
  dashboard is served by CloudFront from a private bucket.

## Quickstart

```bash
python -m venv .venv
.venv\Scripts\activate           # Windows
pip install -e ".[dev]"

python scripts/backfill.py       # pull daily bars for the configured universe
python scripts/run_backtest.py   # SMA crossover backtest, costs included
python scripts/report.py         # render the dashboard from the local ledger
pytest
```

Parameters live in `config/settings.yaml`; secrets in `.env` (copy `.env.example`).
Phase 1 needs no keys.

| Script | Purpose |
| --- | --- |
| `backfill.py` | Fetch daily bars into the parquet store |
| `run_backtest.py` | Vectorised backtest with costs and slippage |
| `run_live.py` | One trading cycle: signal → risk → execution |
| `score_news.py` | Score headlines through FinBERT |
| `report.py` | Render `index.html` and `state.json` from the ledger |
| `check_alerts.py` | Prove the alerting path end to end; exits non-zero on failure |

## What this does and does not show

The strategy is an SMA(20/50) crossover, which trades roughly **five times a year
per ticker**. Across four tickers that is about **20 trades a year**.

No statistically meaningful conclusion about profitability can be drawn from 20
trades, or 40, or probably 100. Treat the equity curve as evidence the machinery
works, not as evidence the strategy makes money. That distinction is the point.

What the track record *can* support, honestly:

- the pipeline runs unattended without losing days
- risk limits fire when they should
- backtest and live execution agree
- the sentiment gate fires at a defensible rate (~1,000 evaluations a year, so
  this becomes answerable within months rather than years)

## Roadmap

- [x] **Phase 1** — data layer, parquet store, vectorised backtester, SMA baseline
- [x] **Phase 2** — FinBERT sentiment gate (age decay + source whitelist), risk
      module, paper execution against a simulated broker filling at real next-day opens
- [x] **Phase 3** — AWS deployment, cron scheduling, Discord alerts, dead-man's
      switch, S3 backups, public dashboard
- [ ] **Phase 4** — intraday cadence, a signal that defines "notable", reworked
      drawdown baseline, and a data source that supports intraday backtesting

Phase 4 note: the daily drawdown kill-switch currently compares against the previous
cycle's equity snapshot. At daily cadence that is the previous day, which is correct.
Running every few minutes would silently turn it into a "3% in 5 minutes" check, so
the baseline must be anchored to the trading day before cadence changes.

## Licence

Personal project. No warranty. Never trade real money on this without
understanding every line of it.
