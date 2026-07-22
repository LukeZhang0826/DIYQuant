# Verifying the first unattended run

Everything through 2026-07-21 was triggered by hand over SSH. Cron has never
fired on its own, so the pipeline is **configured** to be automated rather than
**proven** automated. This checklist closes that gap. Work through it once, then
delete it or keep it as the template for verifying any future cadence change.

Times are Toronto local, with UTC alongside, because cron on the box runs in UTC.

| Job | UTC | Toronto |
| --- | --- | --- |
| Refresh bars | 22:45 | 18:45 |
| Trading cycle | 23:00 | 19:00 |
| Publish dashboard | 23:10 | 19:10 |
| Backup to S3 | 23:30 | 19:30 |

Toronto is UTC-4 (EDT) from March to November, UTC-5 (EST) otherwise, so these
local times shift by an hour in winter while the UTC schedule stays fixed. That
is deliberate: a fixed UTC schedule never drifts relative to the market close.

## The morning after (about 10 minutes)

1. **A Discord heartbeat arrived** with nobody touching anything. This is the
   milestone; everything else is detail.
2. **The healthcheck is still green** at healthchecks.io.
3. **The dashboard shows a fresh timestamp.** The public URL is in the project
   notes, not committed here.
4. **The equity curve renders as a line.** Two snapshots is the minimum, so this
   is the first run where it stops saying "1 snapshot recorded".
5. **The sentiment panel has rows.** Expect roughly four, one per ticker. This is
   the first real data on the project's differentiator.
6. **Fills are still zero.** Expected, not a fault. The simulated broker fills at
   the *next* bar's open, so the loop needs a second cycle. Fills should appear
   the following day.

## If something looks wrong

```bash
ssh -i ~/.ssh/diyquant.pem ec2-user@<instance-ip>
tail -50 ~/diyquant-cron.log
systemctl is-active crond          # must print: active
crontab -l                         # confirm the four jobs are installed
```

Likely and benign:

- a `drawdown check skipped` note, which is the stale-baseline guard working
- a yfinance hiccup, since it scrapes rather than using a supported API
- `sentiment unavailable, trading ungated`, which degrades rather than skipping

Worth investigating:

- **Silence, but the healthcheck is green.** Means the cycle ran and pinged while
  Discord did not deliver. Check `DISCORD_WEBHOOK_URL` in the box's `.env` and run
  `./.venv/bin/python scripts/check_alerts.py`.
- **A halt.** Trading stops until a human clears it, by design. Read the reason in
  the Discord message before clearing anything.
- **Nothing at all, healthcheck red.** Start with `systemctl is-active crond`.
  A missing cron daemon fails silently, which is how it slipped through once
  already.

## Once, this week

7. **Test the dead-man's switch in the failing direction.** Let the grace window
   lapse without a ping and confirm the alert actually reaches you. The sending
   side is verified; the notifying side is not. An untested alarm is not an alarm,
   and this one only matters on the day everything else has already failed.
8. **Confirm the SSH key backup opens.** `diyquant.pem` exists in two places, this
   laptop and Google Drive. AWS keeps no copy, so losing both means rebuilding the
   instance.

## Then stop building for a week or two

Let the ledger accumulate. Watch for log growth, a yfinance breakage, and swap
usage, since that number decides the December 2026 instance sizing call.

Resist adding features on top until the pipeline has proven it runs unattended
across several days. Consumers built on an unproven producer mean debugging two
things at once.
