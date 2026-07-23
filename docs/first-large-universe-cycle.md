# Verifying the first large-universe cycle

The universe went from 4 tickers to the full self-updating S&P 500 (~503) on
2026-07-22, live on the box the same night. The pipeline has run one unattended day
at 4 tickers and none at 503. This checklist covers the first cycle at scale on
2026-07-23. Delete it once it passes, or keep it as the template for the next scale
change.

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

The SMA crossover put ~500 of 503 tickers into an active long/short state, but the
account funds only about **5 positions** (100k at 20% max each). This is the first cycle
that meets "far more signals than capital." Before it runs, or right after, read how
`run_live.py` sizes and selects among many simultaneous signals: does it fund the first
few, the largest, or error? That behaviour is currently unknown and undocumented. See
the capital/selection constraint in CLAUDE.md.

- **Orders look sane:** a handful funded, not 500 attempted, no crash.
- **No unexpected halt.** A halt stops trading until a human clears it, by design.

## If something looks wrong

```bash
ssh -i ~/.ssh/diyquant.pem ec2-user@<instance-ip>
tail -80 ~/diyquant-cron.log
```

## Then stop again

If it runs clean, resist building. Let several 503-ticker days accumulate before
starting Stage 1 (the validation harness) in docs/roadmap-vision.md.
