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
  signals/           # base protocol; technical/ (SMA crossover); sentiment/ (FinBERT + gate)
  backtest/          # vectorized engine with costs
  risk/              # limits.py (kill-switch), sizing.py
  execution/         # broker interface, simulated paper broker, ledger, pipeline
  alerts/            # discord.py: webhook heartbeat, never raises
scripts/             # refresh_universe, backfill, run_backtest, run_live, score_news, report, check_alerts
deploy/              # setup.sh, publish.sh, backup.sh, iam-policy.json (EC2 provisioning)
docs/deploy.md       # the AWS runbook: read this before touching the box
data/                # local parquet store + ledger.sqlite (gitignored)
```

The ledger is the system of record: `orders`, `fills`, `equity_snapshots`, `halts`,
`sentiment_gates`. It is append-only apart from order-status transitions and clearing
a halt. `sentiment_gates` stores **every** gate evaluation, not only the vetoes: a veto
count with no denominator cannot answer whether the gate earns its complexity. A NULL
score there means no whitelisted news was found, which is distinct from a neutral
reading and must not be collapsed to 0.0.

Anything reading a ledger must tolerate an older schema. `report.py` reads restored
backups as well as the live file, so a table that did not exist when the backup was
taken is a normal input, not a fault.

## Phase roadmap

- **Phase 1 — done.** Data layer + vectorized backtester + SMA crossover, end-to-end
  locally, with costs included.
- **Phase 2 — done.** FinBERT sentiment gate (article-age decay + source whitelist),
  risk module, paper execution via the built-in simulated broker (fills at real
  next-day opens). Owner is a Canadian resident: Alpaca accounts (even paper signup)
  are unavailable, so the Alpaca adapter exists but is unused; the real-money broker
  at the far-future live milestone will be IBKR Canada, in a non-registered account.
- **Phase 3 — done 2026-07-21.** Deployed on a single EC2 **t4g.small** (arm64,
  AL2023) in ca-central-1, cron-driven, with Discord alerts, an external dead-man's
  switch, append-only S3 backups, and a public CloudFront dashboard. Scoped IAM user,
  aws CLI only, no AWS MCP unless ops become frequent. Runbook: `docs/deploy.md`.
  Note t4g.small over t4g.micro: accounts created after 2025-07-15 get no 12-month
  free tier, while the t4g.small trial runs to **2026-12-31**, making the larger
  instance the free one. Revisit that in December 2026.
- **Universe expansion — done 2026-07-22.** From 4 hand-listed tickers to the full
  **self-updating S&P 500** (~503). `scripts/refresh_universe.py` scrapes the current
  constituents into `config/universe.txt` (gitignored, machine-generated; config falls
  back to the inline 4 if absent), run weekly by cron. `scripts/backfill.py` is now
  incremental so the daily run stays cheap at this scale. Adds `lxml` + `requests`. See
  the capital/selection constraint below.
- **Phase 4 — next, not started.** Intraday cadence. Three things must be settled
  first: a signal that defines "notable" (SMA crossover has no concept of magnitude),
  a data source that supports intraday backtesting (yfinance serves 1-minute bars for
  only 7 days), and a reworked drawdown baseline (see below). Open design tension: the
  news-sentiment edge has a multi-hour horizon, so trading faster may weaken the very
  thing that differentiates this project. Decide the thesis deliberately. The fuller
  sequenced plan is in `docs/roadmap-vision.md`, which re-sequences cadence to after
  sentiment, validation, and market-neutral work.

## Known constraint before any cadence change

`run_once()` anchors the daily drawdown kill-switch to the **previous equity
snapshot**, skipping the check when that snapshot exceeds `risk.max_baseline_age_hours`
(120h, chosen to clear a 72h weekend and a 96h holiday weekend). At one run per day the
previous snapshot is yesterday, which is correct. Running every few minutes would
silently turn a "3% daily drawdown" limit into "3% in 5 minutes", so a slow bleed across
a session would never trip it. The kill-switch would still pass its tests and no longer
protect anything. Anchor the baseline to the current trading day before changing cadence.

## Known constraint: universe vs capital

The universe is ~503 tickers but the account funds only about five positions
(`starting_cash` 100k at `risk.max_position_pct` 20%). The SMA crossover, having no
notion of magnitude, puts most of the universe into an active long/short state at once
(measured 2026-07-22: 335 long, 166 short, 2 flat of 503), far more signals than capital
can hold. There is no ranking/selection layer yet, so how `run_live.py` resolves "more
signals than capital" is the decisive, and largely unexercised, behaviour at this scale.
Understand it before trusting a large-universe cycle; a proper selection and sizing layer
is Stage 4/7 in `docs/roadmap-vision.md`.

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
- The universe lives in `config/universe.txt` (gitignored, generated by
  `scripts/refresh_universe.py`). Config resolves `universe.source` to that file and
  falls back to the inline `universe.tickers` (the original 4) when absent, so a fresh
  checkout still runs. Regenerate it rather than hand-editing.
- Keep diffs small and phase-scoped. Do not scaffold a later phase before the current
  one is verified end-to-end.
- Never place real trades. Paper trading only until the owner explicitly says otherwise.
- **The repo is public.** Never commit AWS account IDs, bucket names, instance IDs or
  webhook URLs; those live in `.env`, in the crontab on the box, or in placeholders.

## Lesson from the Phase 3 deployment

Seven bugs surfaced deploying to a real machine, none of which a passing test suite
could have caught, because each was a wrong assumption about the environment rather
than about the logic: a stale kill-switch baseline that only misbehaves under cron;
urllib's default User-Agent, which Discord's Cloudflare front rejects with a 403;
`git` absent on AL2023, making the bootstrap script unreachable inside the repo it
needed to clone; `/tmp` being a ~900 MB RAM-backed tmpfs, so pip failed with ENOSPC on
a box with 16 GB free; PyPI's default torch being a CUDA build, wasting 3.5 GB on a
GPU-less host; `tar` reading the directory it was writing its own archive into; and
**no cron daemon at all**, which fails silently — the crontab installs nowhere and the
box looks perfectly healthy while running nothing.

Two habits follow. Verify against the real environment before believing a component
works, especially anything touching the network, the filesystem, or a scheduler. And
read remote state back after writing it rather than trusting the write: an IAM policy
applied with a mangled resource name reported success and would have denied every
publish.
