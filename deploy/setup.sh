#!/usr/bin/env bash
# One-time bootstrap for a fresh Amazon Linux 2023 arm64 instance (t4g.small).
# Run it once, as ec2-user, after SSHing in. Safe to re-run: every step checks
# before acting.
#
# It deliberately does NOT create .env or install cron entries. Those are the
# two steps that need your secrets and your judgement, so docs/deploy.md walks
# them through by hand.
set -euo pipefail

REPO="${DIYQUANT_REPO:-https://github.com/LukeZhang0826/DIYQuant.git}"
PROJECT_DIR="${DIYQUANT_DIR:-$HOME/DIYQuant}"
SWAP_GB=2

echo "=== 1/5 system packages ==="
sudo dnf install -y git python3.11 python3.11-pip sqlite awscli-2

echo "=== 2/5 ${SWAP_GB}GB swapfile ==="
# Insurance, not load-bearing: FinBERT peaks near 786 MB against this box's
# 2 GiB. It costs only disk, and turns a would-be OOM kill into a slow cycle.
# A once-daily batch job can afford slow; it cannot afford being killed.
if [ -f /swapfile ]; then
  echo "swapfile already present, skipping"
else
  sudo dd if=/dev/zero of=/swapfile bs=1M count=$((SWAP_GB * 1024)) status=progress
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
  echo "swap enabled and persisted across reboots"
fi
free -h

echo "=== 3/5 clone repo ==="
if [ -d "$PROJECT_DIR/.git" ]; then
  git -C "$PROJECT_DIR" pull --ff-only
else
  git clone "$REPO" "$PROJECT_DIR"
fi

echo "=== 4/5 virtualenv + dependencies ==="
cd "$PROJECT_DIR"
[ -d .venv ] || python3.11 -m venv .venv

# pip stages downloads and unpacks wheels under TMPDIR. On AL2023 /tmp is a
# ~900 MB tmpfs, which torch overruns, and because tmpfs is RAM-backed filling
# it also consumes the memory FinBERT needs. Stage on disk instead: / has room.
export TMPDIR="$HOME/.cache/diyquant-pip-tmp"
mkdir -p "$TMPDIR"
trap 'rm -rf "$TMPDIR"' EXIT

./.venv/bin/pip install --upgrade pip

# Install the CPU build of torch first. PyPI's default is a CUDA build
# (torch==X+cuNNN) that drags in ~3.5 GB of nvidia and triton packages, none of
# which can run on a GPU-less Graviton box. Doing this before the editable
# install means pip sees the torch requirement already satisfied and leaves it
# alone. Expect several minutes even so: torch is the bulk of the download.
./.venv/bin/pip install --index-url https://download.pytorch.org/whl/cpu torch

./.venv/bin/pip install -e ".[dev]"

echo "=== 5/5 pre-download FinBERT ==="
# Fetch the model now rather than during the first cron run: a slow download
# inside a scheduled job looks identical to a hang, and you would not be
# watching. This also proves the box has the memory to load it at all.
./.venv/bin/python -c "
from diyquant.signals.sentiment.finbert import FinbertScorer
print('score:', FinbertScorer().score_headlines(['Company beats earnings expectations'])[0])
"

echo
echo "Bootstrap complete. Next, per docs/deploy.md:"
echo "  1. create $PROJECT_DIR/.env  (DISCORD_WEBHOOK_URL)"
echo "  2. ./.venv/bin/python scripts/check_alerts.py"
echo "  3. install the cron entries"
