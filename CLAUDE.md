# DIYQuant

Retail-scale quantitative trading pipeline built as a long-horizon (10-year) personal project
and portfolio piece. Owner: Luke Zhang. Pipeline shape: **data -> signal -> risk -> execution**,
with an NLP news-sentiment filter as the Phase 2 differentiator.

## Inspiration & precedent

Origin: a viral LinkedIn/X post (Jan 2026, urn:li:activity:7480578720085385216) about a trader
combining Claude for market context, an OSINT headline parser, and MiroFish simulation to trade
oil. The P&L claims are unverifiable: the *architecture* (news signal -> simulation -> decision
filter) is the inspiration, not the numbers.

Reference repos (study, don't fork, since this codebase is built from scratch on purpose):

- [MiroFish](https://github.com/666ghj/MiroFish): swarm-simulation prediction engine from the
  original post. GraphRAG over news, agent-based event simulation. Reference for ideas only;
  too heavyweight to be a dependency here.
- [TradingAgents](https://github.com/tauricresearch/tradingagents): multi-agent LLM trading
  framework (analyst/sentiment/technical agents). Best reference for LLM-as-analyst prompt
  structure.
- [FinGPT](https://github.com/AI4Finance-Foundation/FinGPT): open financial LLMs; alternative
  to FinBERT for sentiment extraction.
- [LLM-Enhanced-Trading](https://github.com/Ronitt272/LLM-Enhanced-Trading): the closest
  precedent to this project's core thesis, FinGPT sentiment layered over an SMA strategy.
- FinBERT model `ProsusAI/finbert` on Hugging Face: local, fast headline sentiment (Phase 2).

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
  signals/           # base protocol; technical/ (SMA crossover, momentum, reversal);
                     # sentiment/ (FinBERT + gate). Only SMA is deployed: see docs/baseline.md
  backtest/          # engine.py (single ticker), portfolio.py + walkforward.py (validation)
  risk/              # limits.py (kill-switch), sizing.py, selection.py (which signals get funded),
                     # intraday.py (mid-session mark; observes only, never trades)
  execution/         # broker interface, simulated paper broker, ledger, pipeline
  alerts/            # discord.py: webhook heartbeat, never raises
  report/            # paging.py: row caps + the dashboard's client-side pager
scripts/             # refresh_universe, backfill, run_backtest, run_live, score_news, report,
                     # validate, ablate, compare_signals (is SMA the best signal? not yet shown),
                     # check_alerts (smoke-test the webhook), check_pulse (alert when not trading),
                     # cancel_pending_orders (withdraw resting orders you no longer want),
                     # monitor_intraday (mid-session mark + warning), clear_halt (resume after one)
deploy/              # setup.sh, publish.sh, backup.sh, iam-policy.json (EC2 provisioning)
docs/deploy.md       # the AWS runbook: read this before touching the box
data/                # local parquet store + ledger.sqlite (gitignored)
```

The ledger is the system of record: `orders`, `fills`, `equity_snapshots`, `halts`,
`sentiment_gates`, `news_scores`, `intraday_marks`. It is append-only apart from order-status
transitions and clearing a halt.

`intraday_marks` is deliberately **not** `equity_snapshots`. A mid-session mark written into
the latter would become the baseline the next cycle measures its daily drawdown against,
which is precisely the "3% daily becomes 3% since the last mark" failure described under
*Known constraint* below. Separate table, so the monitor can run as often as it likes and
`last_equity_snapshot()` keeps meaning "yesterday's close". `sentiment_gates` stores **every** gate evaluation, not only the vetoes: a veto
count with no denominator cannot answer whether the gate earns its complexity. A NULL
score there means no whitelisted news was found, which is distinct from a neutral
reading and must not be collapsed to 0.0.

Anything reading a ledger must tolerate an older schema. `report.py` reads restored
backups as well as the live file, so a table that did not exist when the backup was
taken is a normal input, not a fault.

## Phase roadmap

- **Phase 1: done.** Data layer + vectorized backtester + SMA crossover, end-to-end
  locally, with costs included.
- **Phase 2: done.** FinBERT sentiment gate (article-age decay + source whitelist),
  risk module, paper execution via the built-in simulated broker (fills at real
  next-day opens). Owner is a Canadian resident: Alpaca accounts (even paper signup)
  are unavailable, so the Alpaca adapter exists but is unused; the real-money broker
  at the far-future live milestone will be IBKR Canada, in a non-registered account.
- **Phase 3: done 2026-07-21.** Deployed on a single EC2 **t4g.small** (arm64,
  AL2023) in ca-central-1, cron-driven, with Discord alerts, an external dead-man's
  switch, append-only S3 backups, and a public CloudFront dashboard. Scoped IAM user,
  aws CLI only, no AWS MCP unless ops become frequent. Runbook: `docs/deploy.md`.
  Note t4g.small over t4g.micro: accounts created after 2025-07-15 get no 12-month
  free tier, while the t4g.small trial runs to **2026-12-31**, making the larger
  instance the free one. Revisit that in December 2026.
- **Universe expansion: done 2026-07-22.** From 4 hand-listed tickers to the full
  **self-updating S&P 500** (~503). `scripts/refresh_universe.py` scrapes the current
  constituents into `config/universe.txt` (gitignored, machine-generated; config falls
  back to the inline 4 if absent), run weekly by cron. `scripts/backfill.py` is now
  incremental so the daily run stays cheap at this scale. Adds `lxml` + `requests`. See
  the capital/selection constraint below.
- **Stage 1 (validation harness): done 2026-08-01.** `scripts/validate.py` produces a
  walk-forward, out-of-sample report card for any config: parameters chosen on each
  training slice, scored only on the test slice that follows. `backtest/portfolio.py`
  replays the real pipeline (signals -> `select_positions` -> five equal-weight slots ->
  costs) because the single-ticker `engine.py` measures a strategy the project does not
  run. **The baseline is in `docs/baseline.md` and it is not flattering: +93.3%
  out-of-sample against +112.1% for equal-weight buy-and-hold, at a 49% drawdown.**
  Trend-following shape, earning its keep only when the market falls (2022: +35.8% vs
  -10.1%). Read that document before proposing any strategy change. `scripts/ablate.py`
  then measured the components: concentration earns its place (alpha decays monotonically
  as slots go 5 -> 10 -> 20 -> 50), hysteresis costs ~70pp against ~21pp of total
  transaction costs, and the short leg spends the alpha rather than creating it (alpha is
  flat at ~33-36% across configs while beta swings -0.66 to +1.20). The ranking metric
  takes an absolute value, so it shorts high-beta names by construction. `news_scores` now
  archives every scored headline, since the gate cannot be backtested without a news
  history that only accumulates from the day capture starts.
- **Stage 5 (market-neutral): next, not started.** Promoted ahead of Stage 2 on evidence
  2026-08-01. The book carries persistent alpha inside an accidental **-0.66 beta** nobody
  chose, so it is net short a market that rose 112% while its stock-picking works. That is
  a portfolio-construction defect, not a signal defect, and it is measurable today with the
  harness that now exists. Work: the simulated broker and risk module handling shorts
  properly, plus explicit beta targeting so exposure is a decision rather than a by-product
  of which names the ranking picked. Do **not** respond to the ablation by switching to
  long-only: that trades the alpha for market direction and abandons the market-neutral
  thesis. **Stage 2 (sentiment as a signal) is blocked**, not skipped: the gate cannot be
  evaluated until `news_scores` holds months of history, so building it now would add an
  unverifiable component to a strategy just proven unmeasured.
- **Phase 4 / Stage 8: not started.** Intraday cadence. Three things must be settled
  first: a signal that defines "notable" (SMA crossover has no concept of magnitude),
  a data source that supports intraday backtesting (yfinance serves 1-minute bars for
  only 7 days), and a reworked drawdown baseline (see below). Open design tension: the
  news-sentiment edge has a multi-hour horizon, so trading faster may weaken the very
  thing that differentiates this project. Decide the thesis deliberately. The fuller
  sequenced plan is in `docs/roadmap-vision.md`, which re-sequences cadence to after
  sentiment, validation, and market-neutral work.

## Intraday monitoring: observes only, 2026-08-08

`scripts/monitor_intraday.py` marks the book at live prices during the session, records it
to `intraday_marks`, and warns on Discord past `risk.intraday_warn_pct`. It exists because
the system was blind between daily cycles: on 2026-08-04 the account reached **-8.09%**
against day-start equity at 13:48 and closed at -6.95%, and the deeper excursion left no
trace anywhere, because a daily snapshot only ever sees the close.

**It does not and must not trade yet.** Two blockers, both real and both fixable:

- `SimulatedBroker.submit_market_order` stamps an order with the last daily bar's date and
  `get_order_fill` fills only when a *later* bar appears. An order placed at noon executes
  at tomorrow's open, the same price a 23:00 order gets, so an early stop would change the
  timing and not the price. Intraday execution needs a genuinely new order type.
- `run_once` returns early on an active halt **without flattening**. A monitor that merely
  set the halt flag would therefore stop the evening cycle from flattening the book at all,
  which is strictly worse than the current behaviour. Do not "just set the halt".

Measured before building, which is why it observes rather than acts: under the volatility
sizing shipped the same day, the 2026-08-04 book's worst intraday point was **-2.14%**,
inside the 3% limit, so a stop would not have fired at all. The flat-cap book would have
tripped in the first minute of the session, the gap alone being -4.85%, and stopping there
rather than holding to the close would have saved about $2,100. Whether that case recurs
often enough to justify the broker work is exactly what `intraday_marks` is accumulating
the evidence for. Do not build intraday execution until that table can answer it.

## Known constraint before any cadence change

`run_once()` anchors the daily drawdown kill-switch to the **previous equity
snapshot**, skipping the check when that snapshot exceeds `risk.max_baseline_age_hours`
(120h, chosen to clear a 72h weekend and a 96h holiday weekend). At one run per day the
previous snapshot is yesterday, which is correct. Running every few minutes would
silently turn a "3% daily drawdown" limit into "3% in 5 minutes", so a slow bleed across
a session would never trip it. The kill-switch would still pass its tests and no longer
protect anything. Anchor the baseline to the current trading day before changing cadence.

## Universe vs capital: resolved 2026-07-28 by the selection layer

The universe is ~503 tickers but the account funds only about five positions
(`starting_cash` 100k at `risk.max_position_pct` 20%). The SMA crossover, having no
notion of magnitude, puts most of the universe into an active long/short state at once
(measured 2026-07-22: 335 long, 166 short, 2 flat of 503), far more signals than capital
can hold. The pipeline used to size **every** one of those at the full 20% cap and submit
an order for each: the 2026-07-28 cycle queued 466 orders against funding for five, and
which five you ended up holding was decided by dict iteration order.

`risk/selection.py` now sits between the signal and sizing. It ranks the candidates that
survived the sentiment gate and funds `risk.max_positions` (5) of them; everything else
is targeted flat, which winds down a holding that lost its slot. Conviction comes from
`SmaCrossover.strength()`, the gap between the two moving averages over the slow one,
which is the magnitude the crossover already computes and used to throw away.
`risk.hysteresis_rank` (10) lets an incumbent keep its slot while it still ranks that
high, so a name slipping from 5th to 6th is not sold today and bought back tomorrow.

Two things this exposed, worth remembering:

- **The simulated broker applies no cash check.** `get_order_fill` fills unconditionally
  on the next bar and lets cash go negative. It never "funds the first few and stops", so
  over-submitting is not self-limiting. Selection is what bounds the book, not the broker.
- **Orders rest until the next open, so a stale one still fills.** Selection does not
  retract what is already at the broker. `SimulatedBroker.cancel_order()` and
  `scripts/cancel_pending_orders.py` exist for that.

## The cap was denominated in dollars, the limit in risk: fixed 2026-08-08

The live account halted on **2026-08-04** at a 6.93% daily drawdown against a 3.00%
limit, and the halt was correct: it flattened a book that would have lost far more by
2026-08-07. What was wrong is that the halt was reachable by a single name.

The book was five slots at `max_position_pct` 20% each: short COHR, SMCI, ALB and ON,
long TECH, netting **-$63k of exposure on $100k of equity**. COHR gapped **+13.1%
overnight** on 22% of equity. The account was already down 4.9% at the opening print.
Attribution: **71% of the day's loss was overnight gaps** realised at 09:30, 29% was
intraday drift.

The defect is that a flat 20% notional cap and a 3% daily drawdown limit are only
compatible for a name of average volatility. At 20% of equity, any name that can move
15% can trip the kill-switch by itself, so the switch stops being a circuit breaker for
"something is going wrong" and becomes a tripwire for "we own something jumpy".

`risk/sizing.py:volatility_budget_pct` now sizes each position so that a
one-standard-deviation day in it moves the account by about `risk.target_risk_pct`,
using 20-day realized volatility of daily simple returns. The flat cap stays on top as a
hard backstop, so scaling can only ever ask for **less**. Three things to keep in mind:

- **Unknown volatility means no position, never the maximum one.** Fewer bars than the
  lookback gives NaN, which returns a budget of 0. Defaulting the other way would hand
  the largest allowed position to the symbols the system knows least about. A genuinely
  *zero* volatility is a different case and does get the full cap.
- **Gross exposure is no longer pinned at 1.0.** A book of jumpy names is deliberately
  less invested, and the idle cash earns nothing. That drag is the price of the
  protection and it is charged to the same equity curve, which is why `PortfolioResult`
  reports `avg_gross_exposure`: without it a volatility-scaled config just looks worse.
- **Backtest and live share the function.** `backtest/portfolio.py` weights by the same
  `volatility_budget_pct` the pipeline calls, so this is measurable rather than assumed.
  `risk.target_risk_pct` of 0 restores the flat cap exactly, which is the ablation
  baseline.

Counterfactual on the actual 2026-08-04 book: mark-to-market loss **-5.39% -> -1.78%**,
gross exposure **1.03x -> 0.62x**. The kill-switch would not have fired.

This does not make the book market-neutral. Being 63% net short a rising market is still
**Stage 5**, and still next.

## Stale order cancellation: resolved 2026-08-01 in the pipeline

`run_once()` now withdraws resting orders itself, as step 2, and the ordering is the whole
design. It runs **after** reconciliation, never before: an order submitted last cycle is
*supposed* to be resting, since it fills at the next open and reconciliation is what records
that. Cancelling first would withdraw every order the cycle before it could ever execute, and
the pipeline would submit forever and trade never. What survives reconciliation is the
genuinely stale set, and on a healthy day that set is empty.

It cannot undo a fill that already happened at this morning's open. That trade is hours old by
the time the 23:00 cycle runs, and retracting it on the close would be look-ahead. Automatic
cancellation covers orders that rest *across* cycles; `scripts/cancel_pending_orders.py` is
still the tool for the same-evening case, before the next open.

One invariant bounds it: **never withdraw an order the cycle cannot replace.** Only symbols
that reach the sizing step get a fresh target, so cancelling outside that set removes intent
with nothing put back. A demoted ticker is the case that matters: its bars stay loaded so its
exit can fill, but it gets no new signal, so cancelling its resting sell would strand the
position with no order to close it. Those are reported in the cycle notes and still clear by
hand, as `run_live.py` documents.

Why it matters beyond tidiness: sizing computes `delta` from the broker's *position*, which
does not count resting orders. An unfilled buy left alone gets an identical buy stacked on it
the next cycle and both eventually fill, doubling the position past the cap meant to bound it.

A ranking layer that scores on something better than trend gap is still Stage 4/7 in
`docs/roadmap-vision.md`; this is the deliberately simple version of it.

## Communication

The owner is new to quantitative finance and git. When reporting results or explaining
decisions, define jargon in plain English on first use (bar, bps, backtest, drawdown,
buy-hold, commit, etc.) and explain *why* a step matters, not just what happened.
Assume no prior trading knowledge; do not assume familiarity with git workflows.

## Conventions

- Python >= 3.11, src layout, hatchling build. Install: `pip install -e ".[dev]"`
- Lint: `ruff check .`  Test: `pytest`
- yfinance note: `auto_adjust=True` is the default: adjusted prices are in `Close`;
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
**no cron daemon at all**, which fails silently: the crontab installs nowhere and the
box looks perfectly healthy while running nothing.

Two habits follow. Verify against the real environment before believing a component
works, especially anything touching the network, the filesystem, or a scheduler. And
read remote state back after writing it rather than trusting the write: an IAM policy
applied with a mangled resource name reported success and would have denied every
publish.
