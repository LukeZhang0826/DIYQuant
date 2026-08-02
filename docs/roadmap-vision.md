# DIYQuant vision and research roadmap

A living plan for growing DIYQuant from a working paper-trading pipeline into a
serious, market-neutral, sentiment-informed research platform, and, if a real edge
survives testing, eventually a small real-money strategy. This is a 10-year arc, not
a sprint. Edit and check items off as they land.

Status when written: Phase 3 done, first unattended run verified 2026-07-22. The base
pipeline runs itself daily. Everything below is future work to plan, not build yet.

**Updated 2026-08-01.** Stage 1 is built and the strategy has been measured for the first
time. It loses to buy-and-hold: **+93.3% out-of-sample against +112.1% for the equal-weight
universe, at a 49% drawdown.** Full numbers and caveats in [`baseline.md`](baseline.md);
read it before planning anything below, because several stages were written assuming an
edge that has not been demonstrated. The ablations also re-ordered what comes next: Stage 5
now precedes Stage 2. See "What changed after measuring" at the end of the stage list.

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

### C. Validation harness (highest value, least glamorous) - SHIPPED 2026-08-01

The thing beginners skip and the thing that separates real edge from self-deception.
- [x] Walk-forward / strict out-of-sample: only trust a strategy on data it never saw.
      `backtest/walkforward.py`, parameters chosen per training slice.
- [x] Overfitting defense: testing 100 tweaks and keeping the best is luck, not edge.
      The grid is deliberately coarse and `ablate.py` warns about multiple testing.
- [x] Cost and capacity realism, partly: costs and slippage are modelled and priced
      (~21pp over the test period). Capacity and short borrow are not.
- [ ] Regime analysis: the per-window table shows the shape (wins in falling markets,
      bleeds in bull years) but there is no explicit regime breakdown yet.

Known gap it cannot close on its own: the universe is today's index membership, so every
backtest is survivorship-biased. Fixing that needs point-in-time constituent history.

### D. Portfolio construction (turn signals into money-shaped positions)

- **Selection: shipped 2026-07-28, measured 2026-08-01, and it works.** ~470 signals,
  five slots. `risk/selection.py` ranks on the SMA gap (`|fast - slow| / slow`) and funds
  the top `risk.max_positions`. The ablation shows alpha decaying monotonically as slots
  go 5 -> 10 -> 20 -> 50, so diluting the ranking dilutes the skill: the layer is doing
  real work, not just capping order count. One slot is *not* better than five, hitting a
  91.6% drawdown.
- **Hysteresis: measured and it is not paying.** The buffer costs ~70pp against ~21pp of
  total transaction costs, so it spends more in missed rotation than it saves in fees.
  Candidate for removal, but re-validate on data the ablation runs did not touch first.
- **The ranking metric shorts high-beta names by construction.** `|fast - slow| / slow`
  takes an absolute value, so it ranks on trend magnitude regardless of direction, and
  the largest downward gaps in a rising market belong to volatile names. Measured: median
  beta 1.84 for names shorted against 1.38 for names longed. This is the concrete failure
  mode a better conviction score has to fix, and it is now evidence rather than a hunch.
- **Shorting to long/short market-neutral.** The powerful version of shorting is not
  "also bet down"; it is holding longs and shorts so market moves cancel and only the
  stock-picking edge remains. The signal contract is already `{-1, 0, +1}`, so the
  signal layer speaks shorts already; the work is execution + risk handling a short.
  **This is now the highest-value track, on evidence.** The book carries persistent alpha
  (~33-36% across every ablation config) wrapped in an accidental **-0.66 beta** nobody
  chose: the long leg runs +0.47 beta on 0.61 gross weight, the short leg -1.18 on 0.36.
  Neutralising that exposure deliberately keeps the alpha. Going long-only instead trades
  it for market direction and abandons the thesis.
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

### Stage 1 - Measurement foundation (validation harness) [M] - DONE 2026-08-01
The instrument for everything after: the ability to know whether a change helped.
- Delivered: `scripts/validate.py` (walk-forward, out-of-sample), `backtest/portfolio.py`
  (replays the real selection pipeline, since the single-ticker `engine.py` measures a
  strategy the project does not run), `backtest/walkforward.py`, `scripts/ablate.py`, and
  a report card carrying return, drawdown, Sharpe, turnover, hit rate, alpha and beta.
- **Baseline: +93.3% out-of-sample vs +112.1% buy-and-hold, 49% drawdown.** The strategy
  loses to doing nothing. See [`baseline.md`](baseline.md).
- Not delivered: the sentiment gate is absent from the baseline because it cannot be
  backtested. yfinance serves recent news only and nothing reconstructs FinBERT's 2019
  opinion. `news_scores` began archiving headlines 2026-08-01; it needs months. (Track C)

### Stage 2 - Sentiment as a signal, not a veto [M] - BLOCKED, and no longer next
First real attempt to improve the edge, now that you can measure it.

> **Blocked on measurement, deliberately deferred behind Stage 5.** The gate cannot be
> evaluated at all today: there is no historical news, so "measured against the baseline"
> is not currently possible for anything sentiment-shaped. Building it now means adding an
> unverifiable component to a strategy that was just proven unmeasured, which is the exact
> trap Stage 1 exists to catch. Revisit once `news_scores` holds months of history.

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

### Stage 5 - Shorting and market-neutral [L] - DO THIS NEXT
The execution + risk work that unlocks the market-neutral thesis.

> **Promoted ahead of Stages 2-4 on evidence, 2026-08-01.** The ablations found persistent
> alpha (~33-36%) sitting inside an unmanaged **-0.66 beta**, so the book is net short a
> market that rose 112% while its stock-picking works. That is the single largest,
> best-evidenced defect in the strategy, it is a portfolio-construction problem rather
> than a signal problem, and it is measurable today with the harness that now exists.
> Add to the deliverables below: explicit beta targeting, so exposure is a choice rather
> than a by-product of which names the ranking happened to pick.

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

## What changed after measuring (2026-08-01)

The stage order above was written before anything had been measured. Stage 1 is now done
and it moved things:

| | Written order | Actual order now | Why |
| --- | --- | --- | --- |
| Next | Stage 2 (sentiment as signal) | **Stage 5 (market-neutral)** | Stage 2 is unmeasurable with no news history; Stage 5 fixes the largest measured defect |
| After | Stage 3 (LLM reads article) | Stage 4 (know your beta), partly done | `alpha_beta()` already ships in the report card |
| Deferred | - | Stages 2 and 3 | Until `news_scores` holds months of history |

Three things the measurement settled that reasoning had not:

1. **Selection earns its place.** Alpha decays monotonically as slots widen. Keep it.
2. **Hysteresis does not.** ~70pp cost against ~21pp of total transaction costs. Candidate
   for removal, pending validation on untouched data.
3. **The short leg spends the alpha rather than creating it.** Long-only returns +805.6%
   against the baseline's +93.3%, but alpha *falls* slightly (+35.9% to +32.5%) while beta
   swings -0.66 to +1.20. That gap is market exposure, not skill. Do not read it as
   "go long-only"; read it as "exposure is currently an accident".

Standing rule from here: **no config change ships on the strength of one test period.**
Nine ablation configs against one out-of-sample window is multiple testing, and the best of
nine beats the baseline on luck alone.

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
