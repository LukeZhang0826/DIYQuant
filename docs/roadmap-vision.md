# DIYQuant vision and research roadmap

A living plan for growing DIYQuant from a working paper-trading pipeline into a
serious, market-neutral, sentiment-informed research platform, and, if a real edge
survives testing, eventually a small real-money strategy. This is a 10-year arc, not
a sprint. Edit and check items off as they land.

Status when written: Phase 3 done, first unattended run verified 2026-07-22. The base
pipeline runs itself daily. Everything below is future work to plan, not build yet.

## The honest framing (read before dreaming)

The gap between an *impressive* trading system and one that *makes money* is enormous.
Making money requires a real **edge**: a repeatable reason your trades beat simply
buying and holding, after costs. Most retail quant strategies do not have one. The SMA
crossover certainly does not; it is textbook scaffolding, arbitraged away decades ago.

So the money question reduces to two hard problems:
1. Find an edge that survives brutal out-of-sample testing.
2. Do not lose it to transaction costs, or to overfitting (fooling yourself that a
   lucky backtest is a real edge). Problem 2 kills more retail quants than problem 1.

Reframe that keeps this worth doing regardless of P&L: even if it never beats
buy-and-hold, an end-to-end system with sentiment ML, rigorous validation, market-
neutral portfolio construction, live cloud deployment, and an LLM analyst desk is a
stronger portfolio piece than most working quants can show. The money is the moonshot;
the skills and the artifact are the guaranteed payout.

## The through-line

One coherent thesis, not a pile of features: **a market-neutral, sentiment-informed,
statistically-validated equity strategy.** Sentiment supplies the edge; quant math
supplies portfolio construction and validation; frequency is the last lever, applied
only to an edge already proven.

## Research tracks

### A. Deepen the sentiment signal (the differentiator)

- Turn the gate from a **veto** into a **signal**: sentiment *strength* sizes trades
  (bet bigger on conviction); sentiment *acceleration* (news improving fast) often
  predicts better than the level.
- **Entity and event resolution.** "Apple sued" and "Apple wins suit" both mention
  Apple; FinBERT alone is shallow. Bring an LLM in to read the actual article and
  reason about what it means for the stock. This is a current, hard-to-replicate edge
  and the natural use of the TradingAgents / FinGPT references.
- Add signal *diversity* (momentum, mean-reversion, volatility) so any edge is not one
  lucky indicator.

### B. Quant math toolkit, aimed at what is actually useful

High-value here and now:
- **Cointegration / pairs trading (statistical arbitrage).** The sweet spot: real math,
  market-neutral, retail-accessible, and it unifies with the shorting ambition. Two
  stocks that historically move together but temporarily diverge: short the rich one,
  long the cheap one, profit when they reconverge. Ornstein-Uhlenbeck / z-score entries.
- **Volatility modeling (GARCH)** for position sizing: bet less on wild names.
- **Factor models (Fama-French)** to understand and neutralize market beta.
- **Rigorous cross-validation** (purged / embargoed, per Lopez de Prado) so leakage
  does not manufacture a fake edge.

Famous but premature (do not start here):
- Black-Scholes and stochastic calculus: that is *options* pricing, parked for now.
- Market-microstructure / optimal-execution math: for size and speed we do not have.

### C. Validation harness (highest value, least glamorous)

The thing beginners skip and the thing that separates real edge from self-deception.
- Walk-forward / strict out-of-sample: only trust a strategy on data it never saw.
- Overfitting defense: testing 100 tweaks and keeping the best is luck, not edge.
- Regime analysis: does it work in bull, crash, and sideways markets, or one lucky slice?
- Cost and capacity realism: an edge that dies under real costs is not an edge.

If only one track gets built first, build this alongside A.

### D. Portfolio construction (turn signals into money-shaped positions)

- **Shorting to long/short market-neutral.** The powerful version of shorting is not
  "also bet down"; it is holding longs and shorts so market moves cancel and only the
  stock-picking edge remains. The signal contract is already `{-1, 0, +1}`, so the
  signal layer speaks shorts already; the work is execution + risk handling a short.
- Volatility targeting and correlation-aware sizing (do not hold 8 tech longs that are
  really one bet).
- Dynamic risk: the kill-switch is a floor; scale leverage down in drawdowns.
- Sizing math: Kelly criterion, risk parity.

### E. Cadence / faster execution (with hard prerequisites)

"Execute more rapidly" splits into two very different things:
- **Fixed high frequency (every N minutes): a trap for this project.** The news edge is
  multi-hour, so faster fights the edge. It also silently breaks the kill-switch and
  cannot be backtested on yfinance (7-day minute-bar limit).
- **Event-driven reaction (act when a material headline drops, not at the daily cron):**
  aligns with the edge and is the natural evolution. A once-a-day system reacts to the
  morning's news at the close.

Hard prerequisites before ANY cadence change (from CLAUDE.md, non-negotiable):
1. Re-anchor the drawdown kill-switch to the current trading day, not the previous
   snapshot, or a slow intraday bleed never trips it.
2. Solve intraday data (yfinance serves 1-minute bars for only 7 days).
3. Settle the horizon thesis: does reacting faster help, given a multi-hour edge?

### F. The "insane" engineering layer (portfolio gold, money-neutral)

- Multi-agent LLM analyst desk (sentiment / technical / risk agents that debate a
  decision), TradingAgents-style. A genuine resume centerpiece.
- A research platform: experiment tracking, a strategy leaderboard, automated backtest
  reports. Makes the A-C work fast, which is what compounds.

## Sequenced delivery plan (each stage feasible on its own)

The tracks above are a capability catalog, not an order. Here they are sequenced into
stages small enough to finish and verify one at a time. Rules that keep it feasible:

- **One stage at a time, verified end-to-end before the next** (the repo's standing rule:
  do not scaffold a later phase before the current one works).
- **Every stage is independently valuable and shippable.** Stop after any stage and what
  you have still runs, and is still a stronger system than before.
- **Validation comes first, because it is the instrument that tells you whether every
  later stage actually helped.** Without it you are guessing.
- Effort is a rough t-shirt size (S / M / L), not a promise.

This re-sequences CLAUDE.md's tentative "Phase 4 = intraday cadence." Cadence moves to
Stage 8, after there is an edge worth running faster and after the kill-switch is fixed.
Update CLAUDE.md's phase roadmap when you commit to this ordering.

### Stage 1 - Measurement foundation (validation harness) [M]
The instrument for everything after: the ability to know whether a change helped.
- Deliverables: walk-forward / out-of-sample backtest; an honest report card (return,
  drawdown, Sharpe, turnover, hit rate) for any strategy config; strict cost + slippage
  realism; a documented baseline for today's SMA + sentiment-gate strategy vs buy-and-hold.
- Done when: one command produces an out-of-sample report for any config, and you have a
  written baseline number to beat. (Track C)

### Stage 2 - Sentiment as a signal, not a veto [M]
First real attempt to improve the edge, now that you can measure it.
- Deliverables: gate upgraded so sentiment *strength* sizes trades and *acceleration*
  contributes direction; run through Stage 1 against the baseline.
- Done when: measured out-of-sample vs baseline, and kept only if it genuinely beats the
  veto-only version. Discarding it is a valid, honest outcome. (Track A)

### Stage 3 - LLM reads the article [L]
Where real, hard-to-copy differentiation lives.
- Deliverables: an LLM reads full articles (not just headlines) and reasons about impact
  per stock, augmenting or replacing FinBERT; measured against Stage 2.
- Done when: measured vs Stage 2 and kept if it helps. (Track A)

### Stage 4 - Know your beta [M]
Understand how much of the "edge" is just the market rising.
- Deliverables: factor / market-beta measurement in the report card; one or two genuinely
  different signal types (momentum, mean-reversion) for diversity.
- Done when: you can state what fraction of return is market beta vs real alpha. (Tracks A/B)

### Stage 5 - Shorting and market-neutral [L]
The execution + risk work that unlocks the market-neutral thesis.
- Deliverables: simulated broker and risk module correctly open, hold, and settle short
  positions; kill-switch and sizing handle shorts; a long/short market-neutral variant runs
  end-to-end in backtest and paper.
- Done when: a short is opened, marked, and closed correctly in paper, and the kill-switch
  behaves with shorts on the book. (Track D)

### Stage 6 - Cointegration / pairs (first real quant-math strategy) [L]
Built on Stage 5's shorting. Your first statistical-arbitrage strategy.
- Deliverables: a cointegration test to find pairs; an Ornstein-Uhlenbeck / z-score
  entry-exit pairs strategy running through the Stage 1 harness and the live pipeline.
- Done when: a pairs strategy backtests and paper-trades through the existing machinery.
  (Track B)

### Stage 7 - Risk-aware sizing [M]
Stop betting fixed percentages.
- Deliverables: volatility targeting, correlation-aware sizing, and a Kelly or risk-parity
  sizing option.
- Done when: position size responds to volatility and correlation, verified in backtest.
  (Track D)

### Stage 8 - Cadence, done safely [L]
Only now, and only if an edge is worth running faster. This is the re-sequenced Phase 4.
- Prerequisites (hard, from CLAUDE.md): re-anchor the drawdown kill-switch to the current
  trading day; solve intraday data; settle the horizon thesis.
- Deliverables: event-driven reaction to material headlines (not fixed N-minute trading),
  with the kill-switch correct under the new cadence.
- Done when: prerequisites are met and event-driven reaction runs without weakening the
  kill-switch. (Track E)

### Stage 9 - Analyst desk + research platform [ongoing]
The "insane" engineering layer: valuable throughout, not a finish line.
- Deliverables: multi-agent LLM analyst desk; experiment tracking and a strategy leaderboard
  that make Stages 1-8 faster. (Track F)

## Path to real money (the actual sequence)

1. Find a candidate edge (Track A/B).
2. Prove it survives out-of-sample and cost-realistic testing (Track C). Most candidates
   die here; that is the process working, not failure.
3. Paper trade it live for months, unattended, confirming backtest matches reality (the
   pipeline is already built for exactly this).
4. Only then risk small real capital via IBKR Canada, and scale slowly.

## Reference reading

- Ernie Chan, *Algorithmic Trading* and *Quantitative Trading*: retail-accessible pairs
  trading, cointegration, mean reversion.
- Marcos Lopez de Prado, *Advances in Financial Machine Learning*: purged cross-
  validation, meta-labeling, overfitting defense. The rigor bible.
- Grinold & Kahn, *Active Portfolio Management*: factor models, market-neutral theory.
