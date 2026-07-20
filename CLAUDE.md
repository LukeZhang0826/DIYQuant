# DIYQuant

Retail-scale quantitative trading pipeline built as a long-horizon (10-year) personal project
and portfolio piece. Owner: Luke Zhang. Pipeline shape: **data -> signal -> risk -> execution**,
with an NLP news-sentiment filter as the Phase 2 differentiator.

## Inspiration & precedent

Origin: a viral LinkedIn/X post (Jan 2026, urn:li:activity:7480578720085385216) about a trader
combining Claude for market context, an OSINT headline parser, and MiroFish simulation to trade
oil. The P&L claims are unverifiable — the *architecture* (news signal -> simulation -> decision
filter) is the inspiration, not the numbers.

Reference repos (study, don't fork — this codebase is built from scratch on purpose):

- [MiroFish](https://github.com/666ghj/MiroFish) — swarm-simulation prediction engine from the
  original post. GraphRAG over news, agent-based event simulation. Reference for ideas only;
  too heavyweight to be a dependency here.
- [TradingAgents](https://github.com/tauricresearch/tradingagents) — multi-agent LLM trading
  framework (analyst/sentiment/technical agents). Best reference for LLM-as-analyst prompt
  structure.
- [FinGPT](https://github.com/AI4Finance-Foundation/FinGPT) — open financial LLMs; alternative
  to FinBERT for sentiment extraction.
- [LLM-Enhanced-Trading](https://github.com/Ronitt272/LLM-Enhanced-Trading) — closest precedent
  to this project's core thesis: FinGPT sentiment layered over an SMA strategy.
- FinBERT model: `ProsusAI/finbert` on Hugging Face — local, fast headline sentiment (Phase 2).

Why from scratch: the reference repos are research demos with weak risk management and
execution discipline. The resume value here is the end-to-end pipeline engineering.

## Architecture rules (non-negotiable)

1. **Signals are pure functions.** A signal takes market data and returns a position target
   in {-1, 0, +1}. No API calls, no state, no side effects. This is what makes backtest/live
   parity provable.
2. **Risk sits between signal and execution, non-optionally.** Every order routes through
   `risk/`. Kill-switches (max drawdown, position caps) are properties of the pipeline, not
   features of a strategy.
3. **Providers and brokers are interfaces.** Swapping data providers or paper -> live is a
   config change in `config/settings.yaml`, never a code change.
4. **No look-ahead bias.** Signals computed on bar T execute on bar T+1 at the earliest.
   Every backtest includes transaction costs and slippage.
5. **Zero secrets in code.** All keys come from `.env` via `diyquant.config`. `.env` is
   gitignored; `.env.example` documents required keys.

## Layout

```
src/diyquant/
  config.py          # pydantic-settings: .env + config/settings.yaml
  data/              # models (Bar, NewsItem), providers/ (yfinance, alpaca), store.py (parquet)
  signals/           # base protocol; technical/ (SMA crossover); sentiment/ (Phase 2)
  backtest/          # vectorized engine with costs
  risk/              # limits.py (kill-switch), sizing.py        [Phase 2]
  execution/         # broker interface, alpaca paper adapter    [Phase 2]
  alerts/            # discord webhook heartbeat                 [Phase 3]
scripts/             # backfill.py, run_backtest.py
data/                # local parquet store (gitignored)
```

## Phase roadmap

- **Phase 1 (current):** data layer + vectorized backtester + SMA crossover, end-to-end
  locally. Success = backtest runs with costs included, zero unhandled exceptions.
- **Phase 2:** FinBERT sentiment filter (with article-age decay + source whitelist),
  risk module, Alpaca paper-trading execution.
- **Phase 3:** AWS deployment (single EC2 t4g.micro, cron-driven; S3 nightly backup of
  data dir; scoped IAM user, aws CLI only, no AWS MCP unless ops become frequent),
  Discord heartbeat/alerts, live paper track record.

## Communication

The owner is new to quantitative finance and git. When reporting results or explaining
decisions, define jargon in plain English on first use (bar, bps, backtest, drawdown,
buy-hold, commit, etc.) and explain *why* a step matters, not just what happened.
Assume no prior trading knowledge; do not assume familiarity with git workflows.

## Conventions

- Python >= 3.11, src layout, hatchling build. Install: `pip install -e ".[dev]"`
- Lint: `ruff check .`  Test: `pytest`
- yfinance note: `auto_adjust=True` is the default — adjusted prices are in `Close`;
  there is no `Adj Close` column.
- Keep diffs small and phase-scoped. Do not scaffold Phase 2/3 modules before Phase 1
  is verified end-to-end.
- Never place real trades. Paper trading only until the owner explicitly says otherwise.
