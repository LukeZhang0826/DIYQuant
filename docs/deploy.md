# Phase 3 deployment: unattended daily runs on AWS

Goal: the pipeline runs itself every trading day, reports to Discord, and backs
itself up, with nobody watching. That last clause is the whole design
constraint. Everything below assumes failures happen when you are asleep.

Nothing here runs automatically. Work through it once, in order.

## What you are building

```
EC2 t4g.small (Amazon Linux 2023, arm64)
  cron 23:00 UTC Mon-Fri  ->  scripts/run_live.py   ->  Discord heartbeat
  cron 23:30 UTC Mon-Fri  ->  deploy/backup.sh      ->  S3 (append-only)
```

## Cost, honestly

| Item | Cost |
| --- | --- |
| t4g.small | **Free** until 2026-12-31 (750 hrs/month trial, all accounts), then ~$12/mo |
| Public IPv4 address | ~$3.60/mo |
| S3 storage | Cents. The data dir is a few MB. |
| **Now** | **~$3.60/mo**, covered by signup credits |
| **From Jan 2027** | **~$15/mo** |

Two things to know about your account:

- You are on the **Paid plan**, which is correct. The Free plan closes your
  account automatically at 6 months or when credits run out, taking your
  running resources with it. For a multi-year track record that would be fatal.
- Accounts created after 2025-07-15 get **no 12-month free tier**. You get
  credits instead ($100, up to $200 for completing onboarding tasks).

**Put a reminder in your calendar for December 2026.** The t4g.small trial ends
then. By that point you will have months of real memory data and can decide
whether to drop to t4g.micro, which is half the price and has 1 GiB.

## Prerequisites

- An AWS account on the Paid plan, with MFA on the root user, and a non-root
  IAM user for console work. If you are still using the root user for daily
  tasks, fix that before continuing.
- Your Discord webhook URL (the same one already working locally).
- An SSH key pair you control.

Pick one region and use it everywhere. `ca-central-1` (Montreal) is the
sensible default for you.

---

## Step 1: S3 bucket and a scoped IAM user

The instance needs to write backups and do nothing else. If its credentials
leak, the blast radius should be one folder in one bucket.

1. Create a bucket, e.g. `diyquant-backups-<something-unique>`, in your region.
   Keep **Block all public access** on, and enable **Versioning**.
2. Create an IAM user named `diyquant-backup`, **no console access**.
3. Attach an inline policy from `deploy/iam-policy.json`, replacing
   `BUCKET_NAME` with your bucket name.
4. Create an access key for it. You will paste it onto the instance in Step 4.

Why this policy is shaped the way it is: it grants `PutObject` and `GetObject`
under `backups/*` and `ListBucket` on that one bucket. It has **no
`DeleteObject`**, so a compromised instance cannot erase the backup history it
created. Combined with bucket versioning, your backups are append-only. A
backup an attacker can delete is not a backup.

## Step 2: Launch the instance

- **AMI:** Amazon Linux 2023, **arm64**. This must match the instance family;
  an x86 AMI will not boot on Graviton.
- **Type:** `t4g.small`.
- **Key pair:** yours.
- **Security group:** inbound **SSH (22) from your IP only**. Not `0.0.0.0/0`.
  Outbound: leave default (allow all). The box needs to reach yfinance,
  Hugging Face, Discord, and S3.
- **Storage:** 20 GiB gp3. The default 8 GiB is too tight once torch and the
  FinBERT weights land.

## Step 3: Bootstrap

SSH in and run:

```bash
sudo dnf install -y git      # AL2023 ships without git, and setup.sh lives in the repo
git clone https://github.com/LukeZhang0826/DIYQuant.git
./DIYQuant/deploy/setup.sh
```

That first line is not redundant. Amazon Linux 2023 has no `git` preinstalled,
and `setup.sh` cannot install it for you because `setup.sh` is inside the repo
you need `git` to fetch. Installing it by hand breaks the loop; `setup.sh`
installs it again harmlessly.

This installs packages, creates a 2 GB swapfile, sets up the virtualenv, and
pre-downloads FinBERT. Expect several minutes, mostly torch. Re-running it is
safe.

On the swapfile: FinBERT peaks near **786 MB** (measured) against this box's
2 GiB, so swap is insurance rather than a load-bearing part of the design. It
costs only disk, and converts a would-be out-of-memory kill into a merely slow
cycle. A once-daily batch job can afford slow. It cannot afford being killed.

The last bootstrap step scores a headline on the box. If that succeeds, the
instance can hold the model in memory, which is the main thing that could have
gone wrong.

## Step 4: Secrets

Never commit these. Create `~/DIYQuant/.env` on the instance:

```bash
cat > ~/DIYQuant/.env <<'ENV'
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
ENV
chmod 600 ~/DIYQuant/.env
```

Configure the backup credentials from Step 1:

```bash
aws configure   # paste the diyquant-backup key, set region, output = json
```

Now prove alerting works **from this box**:

```bash
cd ~/DIYQuant && ./.venv/bin/python scripts/check_alerts.py
```

It must print `OK: delivered`, and the Discord message must name the
instance's hostname (something like `ip-172-31-x-y`), **not** your laptop. That
hostname is the point: it is what distinguishes "the box is wired up" from "a
machine somewhere sharing the same webhook is wired up".

Then prove the backup path works:

```bash
export DIYQUANT_BACKUP_BUCKET=your-bucket-name
~/DIYQuant/deploy/backup.sh
```

Confirm the object appears in S3 before continuing. Do not schedule anything
you have not run by hand first.

## Step 5: Schedule it

`setup.sh` installs `cronie` and enables `crond`; AL2023 has neither by default.
Confirm before scheduling, because a missing cron daemon fails silently rather
than loudly:

```bash
systemctl is-active crond    # must print: active
```

Then `crontab -e`, and:

```cron
MAILTO=""
DIYQUANT_BACKUP_BUCKET=your-bucket-name
HEALTHCHECK_URL=https://hc-ping.com/your-uuid-here

# Trading cycle: 23:00 UTC = 19:00 ET, well after the 16:00 ET close.
# The && before curl is load-bearing: the ping fires only on exit 0, so a
# crashed cycle stays silent and trips the dead-man's switch. See Step 6.
0 23 * * 1-5 cd /home/ec2-user/DIYQuant && ./.venv/bin/python scripts/run_live.py >> /home/ec2-user/diyquant-cron.log 2>&1 && curl -fsS --retry 3 --max-time 20 "$HEALTHCHECK_URL" >> /home/ec2-user/diyquant-cron.log 2>&1

# Backup, 30 minutes later so it captures the cycle that just ran.
30 23 * * 1-5 /home/ec2-user/DIYQuant/deploy/backup.sh >> /home/ec2-user/diyquant-cron.log 2>&1
```

Notes on the schedule:

- **Mon-Fri only.** The longest normal gap is Friday to Monday, 72 hours.
- Cron on Amazon Linux runs in **UTC**. That is deliberate: a fixed UTC schedule
  does not shift under daylight saving, so the job never silently moves relative
  to the market close.
- Market holidays are harmless. yfinance returns the same last bar, the signal
  does not change, and no order goes out. A holiday adjacent to a weekend gives
  a 96-hour gap, which is why `risk.max_baseline_age_hours` is 120: it tolerates
  a long weekend but still treats a real multi-day outage as an outage rather
  than as one very bad trading day.

## Step 6: Dead-man's switch

Everything above alerts you when something **happens**. Nothing yet alerts you
when nothing happens. That gap is the important one: if the instance is stopped,
`crond` dies, the disk fills, or AWS retires the host, no code of ours runs, so
no code of ours can complain. The system fails by going quiet, and "a silent day
is the alarm" only works if a human reliably notices silence. People do not,
especially by week six.

A dead-man's switch inverts the logic. Something **outside** the box expects a
check-in on a schedule and shouts when one fails to arrive. It has to be
external: monitoring that runs on the machine it monitors cannot report that
machine's death.

[healthchecks.io](https://healthchecks.io) does this, and its free tier is
ample for one daily job.

1. Create a check named `diyquant-daily`.
2. Set **period** to 1 day and **grace** to 2 hours. The cycle runs at 23:00
   UTC, so a missed ping raises an alert around 01:00 UTC.
3. Set the schedule to weekdays only, matching cron: `0 23 * * 1-5`. Without
   this it will page you every Saturday.
4. Add a **Discord integration** pointing at the same webhook the pipeline uses,
   so failures and heartbeats land in one channel.
5. Copy the ping URL into `HEALTHCHECK_URL` in your crontab (Step 5).

Why the ping hangs off `&&` rather than living in `run_live.py`: the shell
already gives us exactly the semantics we want for free. `&&` fires the ping
only when the cycle exits 0, so a crash, an OOM kill, or a Python traceback all
result in no ping and therefore an alert. Putting it inside the Python would
mean the ping shares a process with the thing it is supposed to be reporting on,
which is precisely the arrangement to avoid.

Test it deliberately, in both directions:

```bash
curl -fsS "$HEALTHCHECK_URL"          # check goes green
```

Then leave it alone past the grace window and confirm the alert actually
arrives. **An untested alarm is not an alarm**, and this one has exactly one job
that only matters on the day everything else has already failed.

Note what this does *not* cover: a cycle that runs fine but makes bad decisions.
The switch proves the pipeline is alive, not that it is right. The Discord
heartbeat and the kill-switch cover that side.

## Verifying it actually works

The first Discord heartbeat after 23:00 UTC on the next trading day is the real
test. After that:

```bash
tail -50 ~/diyquant-cron.log
aws s3 ls s3://your-bucket-name/backups/
```

**A silent day is itself the alarm.** If no Discord message arrives, something
is wrong even though nothing reported an error. That is the failure mode this
whole phase exists to make visible, and once Step 6 is in place you are told
about it rather than having to notice it.

Watch memory on the first few real runs:

```bash
free -h        # after a cycle: how much swap actually got used
```

If swap usage stays near zero, the box is comfortable and t4g.micro becomes a
credible option come December 2026.

## Restoring from a backup

Worth doing once now, while nothing is at stake, so you are not learning it
during an incident.

```bash
aws s3 cp s3://your-bucket-name/backups/diyquant-YYYY-MM-DD.tar.gz .
mkdir restore && tar -xzf diyquant-YYYY-MM-DD.tar.gz -C restore
./.venv/bin/python -c "
import sqlite3
c = sqlite3.connect('restore/ledger.sqlite')
print('orders:', c.execute('SELECT COUNT(*) FROM orders').fetchone()[0])
print('fills :', c.execute('SELECT COUNT(*) FROM fills').fetchone()[0])
"
```

An untested backup is a guess. This turns it into a fact.

## Troubleshooting

| Symptom | Likely cause |
| --- | --- |
| No Discord message at all | cron did not run, or the box is down. Check `~/diyquant-cron.log` and that the instance is running. |
| `check_alerts.py` returns 403 | Missing or rejected User-Agent, or a webhook that was deleted in Discord. |
| Cycle killed with no traceback | Out of memory. Check `free -h` and `sudo dmesg | grep -i oom`. |
| `drawdown check skipped` in the report | Expected after an outage longer than 120h. It is the safety behaviour, not a bug. |
| Backup fails with `AccessDenied` | The IAM policy still says `BUCKET_NAME`, or the key belongs to a different user. |
| Log file growing without bound | Add logrotate, or truncate it periodically. Low priority at one run per day. |
| healthchecks.io alerts every Saturday | The check's schedule is daily; set it to `0 23 * * 1-5` to match cron. |
| Check stays green while the cycle fails | The ping is not hanging off `&&`, so it fires regardless of exit code. Re-read the Step 5 cron line. |
