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

> **Updated 2026-08-09, and the numbers above are the ones to stop quoting.** Every figure
> in that paragraph comes from **five** test windows. Re-run on 2005-2026, eighteen windows,
> the conclusions move so far that three of them invert. Momentum's +226pp edge became
> -23pp; the flat-cap baseline's +93.3% became **-1.6% with a -94.7% drawdown**; hysteresis
> went from "candidate for removal" to clearly paying. **Five windows cannot tell a strategy
> from a good year**, and that is the single most useful thing this project has measured.
>
> Two consequences for everything below. **Stage 5's beta-targeting half is cancelled**, not
> deferred: it was promoted on an accidental -0.66 beta that volatility sizing had already
> removed, and the hedge built for it lost on every measure including drawdown. What remains
> of Stage 5 is the broker. And any number in this file without a window count behind it
> should be treated as a hypothesis. `baseline.md` is authoritative; this file is the plan.

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
- [x] Cost and capacity realism, mostly: costs, slippage **and short borrow** are modelled
      and priced. Costs are ~10pp over 21 years (the ~21pp figure came from the 5-window
      sample). Borrow ships at 200bp/yr since 2026-08-09 and costs ~0.44%/yr at the book's
      0.223 average short exposure. Capacity and availability are still unmodelled: a name
      that cannot be borrowed at any price is shorted here regardless.
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
- **Hysteresis: it pays. Re-validated 2026-08-09 and the earlier verdict was wrong.** On
  five windows the buffer looked like a ~70pp cost and was flagged for removal. On eighteen,
  removing it costs 65pp and widening it to 20 gains 49pp with the best Sharpe and alpha of
  any flat-cap row. Keep it. Worth remembering as the cheapest lesson in the file: that was
  a confident, mechanism-backed argument from a real measurement, and it was wrong only
  because the measurement had five windows under it.
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

  > **The beta half of that is finished and the answer was no, 2026-08-09.** The -0.66 was
  > a property of the flat cap. Volatility sizing (shipped 2026-08-08) already took the
  > 21-year beta to **+0.09** as a side effect nobody designed, so by the time an index
  > hedge existed there was almost nothing left to neutralise. Measured, it cost 610pp of
  > return, cut Sharpe 0.66 -> 0.41, more than doubled gross exposure 0.65 -> 1.45, **made
  > drawdown worse (-46.1% -> -58.5%)** and won 6 of 18 windows. `risk/hedge.py` stays in
  > the repo, tested and disabled. Do not re-propose it without first showing the beta is
  > back. Table in [`baseline.md`](baseline.md).
  >
  > The **long/short execution** half of this bullet still stands and is now the whole of
  > Stage 5: the simulated broker models shorting as free, with no borrow accrual, no margin
  > and no cash check, so it cannot honestly settle the shorts this track depends on.
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

### Stage 5 - Shorting: settle it honestly [L] - DO THIS NEXT (half of it)
The execution + risk work that unlocks the market-neutral thesis.

> **Promoted ahead of Stages 2-4 on evidence, 2026-08-01.** The ablations found persistent
> alpha (~33-36%) sitting inside an unmanaged **-0.66 beta**, so the book is net short a
> market that rose 112% while its stock-picking works. That is the single largest,
> best-evidenced defect in the strategy, it is a portfolio-construction problem rather
> than a signal problem, and it is measurable today with the harness that now exists.
> Add to the deliverables below: explicit beta targeting, so exposure is a choice rather
> than a by-product of which names the ranking happened to pick.

> **Half cancelled, half sharpened, 2026-08-09.** The beta-targeting deliverable added
> above is **done and rejected**: the -0.66 belonged to the flat cap, volatility sizing had
> already taken the 21-year beta to +0.09, and the hedge built for it lost on return,
> Sharpe, alpha and drawdown while winning 6 of 18 windows. See the Track D note above and
> [`baseline.md`](baseline.md). `risk/hedge.py` stays disabled in the repo so it can be
> re-measured in twenty minutes if the beta ever comes back.
>
> **What remains is the part that was always the real work**, and it is a measurement
> defect rather than a portfolio one: `SimulatedBroker` models shorting as **free**. No
> borrow accrual, no margin requirement, no cash check. Backtest and paper now disagree
> about what a short costs, since the backtest started charging borrow on 2026-08-09 and
> the broker did not. Everything downstream, Stage 6 pairs especially, is built on shorts
> being settled honestly, so this is the load-bearing piece.

- Deliverables: simulated broker and risk module correctly open, hold, and settle short
  positions, **including borrow accrued daily, a margin model and a cash check**; kill-switch
  and sizing handle shorts; a long/short variant runs end-to-end in backtest and paper.
- Design already sketched: the broker has no concept of a day passing (it only acts inside
  `get_order_fill`), so borrow needs an explicit accrual step in `run_once` **between
  reconciling fills and snapshotting equity**, with a persisted last-accrued date so a
  re-run cannot double-charge. It feeds equity and therefore the daily kill-switch, though
  the magnitude is small: 200bp/yr on 0.223 short exposure is ~0.02%/day against a 3% limit.
- Done when: a short is opened, marked, carried at a cost, and closed correctly in paper;
  the broker refuses what the account cannot fund; and the kill-switch behaves with shorts
  on the book. (Track D)

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

## What changed after measuring again (2026-08-09)

The table and the three findings above rest on **five** test windows. Re-run on 2005-2026,
eighteen windows, only one of the three survives. This section supersedes it.

| | Order after 2026-08-01 | Order now | Why |
| --- | --- | --- | --- |
| Next | Stage 5 (market-neutral) | **Stage 5, broker half only** | Beta targeting was built, measured and rejected; honest short settlement is what is left |
| After | Stage 4 (know your beta) | Stage 4, mostly done | `alpha_beta()` ships, and beta is now measured routinely in every ablation |
| Deferred | Stages 2 and 3 | Unchanged | Still waiting on `news_scores` history |

1. **Selection still earns its place.** Alpha decays monotonically 5 -> 10 -> 20 -> 50 in
   *both* samples. The only finding that held twice, and so the only one to trust.
2. **Hysteresis reversed.** It pays, and more of it pays more. Finding 2 above is wrong.
3. **The long-only row is survivorship bias, not a finding.** At 21 years it returns
   **+65,725%**, roughly 37%/yr, with the *highest* alpha in the table. It went from +805%
   (8y) to +65,725% (21y) because the bias compounds with sample length and lands entirely
   on the long side: the universe is today's S&P 500 projected back, so a concentrated
   five-name long book is handed the survivors by construction. Finding 3's arithmetic no
   longer holds, but its conclusion does, for a better reason: **still do not go long-only.**
4. **Volatility sizing is the strongest result in the project**, and the only major one that
   got *stronger* on a bigger sample. The flat cap loses 94.7% over 21 years; sizing by
   volatility returns +571% to +953% at a third of the drawdown. `target_risk_pct` is a
   leverage knob, not a performance one: alpha per unit of gross exposure is flat at ~20%
   across 0.3 / 0.4 / 0.5, so no setting on it buys edge. Live stays at 0.4 for kill-switch
   headroom, and that choice now gives up nothing measurable.

Standing rule, strengthened: **no config change ships on the strength of one test period,
and no strategy claim survives on five windows.** The clearest demonstration is momentum,
which beat the equal-weight universe by +226pp on five windows and trailed it by 23pp on
eighteen, with nothing changed but the number of independent periods.

Corollary found the same day: **a walk-forward that re-tunes annually will make almost any
new cost look survivable**, because it optimises around it. A 1000bp borrow costs the
walk-forward 7% of terminal equity and a fixed-parameter run 62%. The live pipeline runs a
fixed 20/50 and re-tunes never, so measure every future cost both ways.

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
