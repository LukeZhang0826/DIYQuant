# Verifying the first large-universe cycle

The universe went from 4 tickers to the full self-updating S&P 500 (~503) on
2026-07-22, live on the box the same night. This began as a checklist for the first
cycle at scale on 2026-07-23; it is kept as the record of what that cycle actually
did, because the answer was not among the options the checklist offered. Reuse the
shape of it for the next scale change, and read the section below before trusting any
prediction about how the pipeline behaves at a size it has not run at.

Times are Toronto local, UTC alongside; cron on the box runs in UTC.

| Job | UTC | Toronto |
| --- | --- | --- |
| Refresh bars (now incremental) | 22:45 | 18:45 |
| Trading cycle (503 tickers) | 23:00 | 19:00 |
| Publish dashboard | 23:10 | 19:10 |
| Backup to S3 | 23:30 | 19:30 |

## The evening of 2026-07-23 (about 10 minutes)

1. **The Discord heartbeat arrived.** Same milestone as before, now at scale.
2. **The cycle finished before 23:10.** The 23:00 job scores FinBERT sentiment for the
   tickers that have whitelisted news, then 23:10 publishes. `report.py` was measured
   at ~6s for 503 signals, so the long pole is the sentiment scoring, not the dashboard.
   If publish overlaps a still-running cycle, that is the thing to fix first.
3. **The 22:45 backfill stayed quick.** It is incremental now, fetching only the day's
   new bar per ticker. If the cron log shows it running long or bleeding into 23:00,
   that is a problem.
4. **The dashboard Universe panel reads 503** with a long/short/flat tally and up to 24
   active-name cards. Already true since 2026-07-22.

## The thing to actually watch: what it did with the signals

**Answered 2026-07-28. It attempted all of them.** The question this checklist posed,
whether `run_live.py` funds the first few, the largest, or errors, had a fourth answer
nobody listed: it sized *every* signal at the full 20% cap and submitted an order for
each. The cycle queued **466 orders against funding for five**, and which five you ended
up holding was decided by dict iteration order.

Two assumptions in the original checklist were wrong, both worth keeping written down:

- **"a handful funded, not 500 attempted"** treated over-submission as something the
  system would prevent. Nothing in it did.
- **Cash was assumed to be a backstop.** The simulated broker applies no cash check:
  `get_order_fill` fills unconditionally on the next bar and lets cash go negative. So
  the 466 orders were not going to fund five and expire, they were all going to fill.

Both are fixed: `risk/selection.py` ranks and funds `risk.max_positions`, and
`SimulatedBroker.cancel_order()` plus `scripts/cancel_pending_orders.py` can withdraw
resting orders. The same cycle re-run after the fix reported 467 live signals, 5 funded,
8 orders (5 entries and 3 wind-downs).

The general lesson, which outlives this checklist: a question phrased as "which of these
three sane things does it do" hides the possibility that it does none of them. Ask what
it actually did, against the ledger, before believing any of the options.

- **No unexpected halt.** A halt stops trading until a human clears it, by design.

## If something looks wrong

```bash
ssh -i ~/.ssh/diyquant.pem ec2-user@<instance-ip>
tail -80 ~/diyquant-cron.log
```

## Then stop again

If it runs clean, resist building. Let several 503-ticker days accumulate before
starting Stage 1 (the validation harness) in docs/roadmap-vision.md.
