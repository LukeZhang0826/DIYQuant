"""Render the trade ledger as a self-contained HTML dashboard.

Read-only by design. This shows what the system did; changing what it does
stays in config/settings.yaml under version control, so a bad afternoon cannot
turn into an untracked strategy change.

Reads a ledger directly, so it can point at the live file or at a restored S3
backup. Pointing it at a backup has a useful side effect: every report you
generate re-proves the backup is real and restorable.

Ticker sparklines are drawn from the local parquet bar store when it is
present, and skipped when it is not, so the report still works on a box that
streams bars straight from yfinance without persisting them.

Usage:
  python scripts/report.py                        # live ledger from settings
  python scripts/report.py path/to/ledger.sqlite  # e.g. a restored backup
  python scripts/report.py --out report.html
"""

import argparse
import random
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

STALE_AFTER_HOURS = 30.0  # a weekday cycle runs every 24h; 30 allows for lateness
SPARK_BARS = 90  # trading days of price history per ticker card


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("ledger", nargs="?", help="path to ledger.sqlite (default: from settings)")
    p.add_argument("--out", default="report.html", help="output HTML path")
    return p.parse_args()


def default_ledger_path() -> Path:
    from diyquant.config import PROJECT_ROOT, get_settings

    return PROJECT_ROOT / get_settings().execution.ledger_path


def glow(name: str, tint: str | None = None) -> str:
    """Inline CSS vars giving one panel its own glow placement.

    Seeded off the panel's name rather than left to chance: a report that
    reshuffles its own lighting on every regeneration reads as unstable, and
    you would not be able to tell a redesign from a re-render. Same panel,
    same glow, forever; different panels, different glows.

    tint overrides the first hue, letting a card's wash follow its data
    (gain teal, loss coral) while position stays decorative.
    """
    rng = random.Random(name)
    c1 = tint or ("var(--glow-a)" if rng.random() < 0.6 else "var(--glow-b)")
    c2 = "var(--glow-b)" if "glow-a" in c1 else "var(--glow-a)"
    return (
        f"--gx1:{rng.randint(-10, 55)}%; --gy1:{rng.randint(-25, 35)}%;"
        f"--gr1:{rng.randint(45, 85)}%; --go1:{rng.uniform(0.10, 0.24):.2f}; --gc1:{c1};"
        f"--gx2:{rng.randint(55, 115)}%; --gy2:{rng.randint(-15, 60)}%;"
        f"--gr2:{rng.randint(40, 75)}%; --go2:{rng.uniform(0.07, 0.18):.2f}; --gc2:{c2};"
        f"--gtilt:{rng.randint(120, 205)}deg;"
    )


def hours_since(ts: str) -> float:
    return (datetime.now(timezone.utc) - datetime.fromisoformat(ts)).total_seconds() / 3600


def money(v: float) -> str:
    return f"${v:,.2f}"


def esc(s: object) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def short_ts(ts: str) -> str:
    try:
        return datetime.fromisoformat(ts).strftime("%d %b %H:%M")
    except ValueError:
        return str(ts)


# -- charts ----------------------------------------------------------------


def polyline(values: list[float], w: float, h: float, pad: float = 3.0) -> tuple[str, float, float]:
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    step = (w - 2 * pad) / max(len(values) - 1, 1)
    pts = []
    for i, v in enumerate(values):
        x = pad + i * step
        y = h - pad - (v - lo) / span * (h - 2 * pad)
        pts.append(f"{x:.1f},{y:.1f}")
    last_x, last_y = pts[-1].split(",")
    return " ".join(pts), float(last_x), float(last_y)


def sparkline(values: list[float], tone: str, uid: str) -> str:
    """Mini area+line chart. The endpoint is emphasised: it is the value read."""
    w, h = 240.0, 68.0
    line, lx, ly = polyline(values, w, h)
    area = f"3,{h - 3} {line} {lx:.1f},{h - 3}"
    return f"""<svg class="spark" viewBox="0 0 {w:.0f} {h:.0f}" preserveAspectRatio="none"
     role="img" aria-label="price history">
  <defs><linearGradient id="g{uid}" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0%" stop-color="var(--{tone})" stop-opacity="0.28"/>
    <stop offset="100%" stop-color="var(--{tone})" stop-opacity="0"/>
  </linearGradient></defs>
  <polygon points="{area}" fill="url(#g{uid})"/>
  <polyline points="{line}" fill="none" stroke="var(--{tone})" stroke-width="2"
            vector-effect="non-scaling-stroke" stroke-linejoin="round"/>
  <circle cx="{lx:.1f}" cy="{ly:.1f}" r="3.5" fill="var(--{tone})"/>
</svg>"""


def equity_panel(snapshots: list[sqlite3.Row]) -> str:
    if len(snapshots) < 2:
        n = len(snapshots)
        current = money(float(snapshots[-1]["equity"])) if snapshots else "--"
        return f"""<div class="panel" style="{glow("equity")}">
  <div class="panel-head"><h2>Equity</h2></div>
  <div class="hero-num">{esc(current)}</div>
  <div class="empty">
    <strong>{n} snapshot{"" if n == 1 else "s"} recorded.</strong>
    A curve needs at least two, one per completed cycle. This fills in from the
    next scheduled run onward.
  </div>
</div>"""

    values = [float(r["equity"]) for r in snapshots]
    w, h = 900.0, 240.0
    line, lx, ly = polyline(values, w, h, pad=12)
    area = f"12,{h - 12} {line} {lx:.1f},{h - 12}"
    delta = values[-1] - values[0]
    tone = "pos" if delta >= 0 else "neg"
    sign = "+" if delta >= 0 else ""
    pct = delta / values[0] * 100 if values[0] else 0.0

    dots = "".join(
        f'<circle class="dot" cx="{p.split(",")[0]}" cy="{p.split(",")[1]}" r="3">'
        f"<title>{esc(short_ts(r['ts']))} — {esc(money(float(r['equity'])))}</title></circle>"
        for p, r in zip(line.split(" "), snapshots)
    )

    return f"""<div class="panel" style="{glow("equity")}">
  <div class="panel-head">
    <h2>Equity</h2>
    <span class="chip chip-{tone}">{sign}{esc(money(delta))} · {sign}{pct:.2f}%</span>
  </div>
  <div class="hero-num">{esc(money(values[-1]))}</div>
  <svg class="equity" viewBox="0 0 {w:.0f} {h:.0f}" preserveAspectRatio="none"
       role="img" aria-label="Account equity over time">
    <defs><linearGradient id="ge" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="var(--{tone})" stop-opacity="0.30"/>
      <stop offset="100%" stop-color="var(--{tone})" stop-opacity="0"/>
    </linearGradient></defs>
    <polygon points="{area}" fill="url(#ge)"/>
    <polyline points="{line}" fill="none" stroke="var(--{tone})" stroke-width="2.5"
              vector-effect="non-scaling-stroke" stroke-linejoin="round"/>
    {dots}
  </svg>
  <div class="axis">
    <span>{esc(short_ts(snapshots[0]["ts"]))}</span>
    <span>{esc(short_ts(snapshots[-1]["ts"]))}</span>
  </div>
</div>"""


# -- ticker cards ----------------------------------------------------------


def ticker_cards() -> str:
    """One card per universe ticker: price history and the live signal.

    Skipped entirely when the parquet store is absent, rather than faked.
    """
    try:
        from diyquant.config import get_settings
        from diyquant.data.store import load_bars
        from diyquant.signals.technical.sma_crossover import SmaCrossover

        settings = get_settings()
        strategy = SmaCrossover(**settings.strategy.params)
        tickers = settings.universe["tickers"]
    except Exception:
        return ""

    cards = []
    for i, ticker in enumerate(tickers):
        try:
            bars = load_bars(ticker)
            closes = [float(v) for v in bars["close"].tail(SPARK_BARS)]
            signal = int(strategy.generate(bars).iloc[-1])
        except Exception:
            continue
        if len(closes) < 2:
            continue

        change = (closes[-1] - closes[0]) / closes[0] * 100
        tone = "pos" if change >= 0 else "neg"
        sign = "+" if change >= 0 else ""
        label = {1: "long", -1: "short", 0: "flat"}.get(signal, "flat")
        stance = {1: "pos", -1: "neg", 0: "idle"}.get(signal, "idle")

        wash = "var(--pos)" if tone == "pos" else "var(--neg)"
        cards.append(f"""<div class="card" style="{glow(ticker, wash)}">
  <div class="card-head">
    <span class="ticker">{esc(ticker)}</span>
    <span class="chip chip-{stance}">{esc(label)}</span>
  </div>
  {sparkline(closes, tone, str(i))}
  <div class="card-foot">
    <span class="card-price">{esc(money(closes[-1]))}</span>
    <span class="card-delta {tone}">{sign}{change:.2f}%</span>
  </div>
  <div class="card-note">{SPARK_BARS} sessions · SMA
    {esc(settings.strategy.params.get("fast"))}/{esc(settings.strategy.params.get("slow"))}</div>
</div>""")

    if not cards:
        return ""
    return f"""<div class="panel" style="{glow("universe")}">
  <div class="panel-head"><h2>Universe</h2>
    <span class="panel-note">signal state per ticker</span></div>
  <div class="cards">{"".join(cards)}</div>
</div>"""


# -- tables ----------------------------------------------------------------


def orders_table(orders: list[sqlite3.Row]) -> str:
    if not orders:
        return '<div class="empty">No orders recorded.</div>'
    rows = "".join(
        f"<tr><td class='mono muted'>{esc(short_ts(o['ts']))}</td>"
        f"<td class='sym'>{esc(o['symbol'])}</td>"
        f"<td class='{'pos' if o['side'] == 'buy' else 'neg'}'>{esc(o['side'])}</td>"
        f"<td class='num'>{o['qty']}</td>"
        f"<td><span class='pill pill-{esc(o['status'])}'>{esc(o['status'])}</span></td>"
        f"<td class='muted'>{esc(o['signal_name'])} ({o['signal_value']:+d})</td>"
        f"<td class='muted'>{esc(o['risk_reason'] or '')}</td></tr>"
        for o in reversed(orders)
    )
    return f"""<div class="scroll"><table>
  <thead><tr><th>Time (UTC)</th><th>Symbol</th><th>Side</th><th class="num">Qty</th>
  <th>Status</th><th>Signal</th><th>Risk note</th></tr></thead>
  <tbody>{rows}</tbody></table></div>"""


def fills_table(fills: list[sqlite3.Row]) -> str:
    if not fills:
        return (
            '<div class="empty">No fills yet. The simulated broker fills at the '
            "<em>next</em> bar's open, so orders stay open until a later cycle "
            "reconciles them. Closing the loop takes two runs.</div>"
        )
    rows = "".join(
        f"<tr><td class='mono muted'>{esc(short_ts(f['ts']))}</td>"
        f"<td class='sym'>{esc(f['symbol'])}</td>"
        f"<td class='{'pos' if f['side'] == 'buy' else 'neg'}'>{esc(f['side'])}</td>"
        f"<td class='num'>{f['qty']}</td>"
        f"<td class='num'>{esc(money(float(f['price'])))}</td>"
        f"<td class='num muted'>{esc(money(float(f['fees'])))}</td></tr>"
        for f in reversed(fills)
    )
    return f"""<div class="scroll"><table>
  <thead><tr><th>Time (UTC)</th><th>Symbol</th><th>Side</th><th class="num">Qty</th>
  <th class="num">Price</th><th class="num">Fees</th></tr></thead>
  <tbody>{rows}</tbody></table></div>"""


def positions_block(positions: dict[str, int]) -> str:
    held = {s: q for s, q in positions.items() if q}
    if not held:
        return '<div class="empty">Flat. No fills have settled into a position yet.</div>'
    chips = "".join(
        f'<div class="pos-chip"><span class="sym">{esc(s)}</span>'
        f'<span class="{"pos" if q > 0 else "neg"} num">{q:+d}</span>'
        f'<span class="muted">{"long" if q > 0 else "short"}</span></div>'
        for s, q in sorted(held.items())
    )
    return f'<div class="pos-grid">{chips}</div>'


CSS = """
/* Committed to a single dark treatment on purpose: this is a trading terminal,
   and the reference direction is emphatically dark. Tokens stay fixed so the
   viewer's light toggle cannot half-invert it into something unreadable. */
:root {
  --bg: #080b14; --panel: #111827; --panel-2: #131a2b; --line: #1f2a3d;
  --ink: #e8edf5; --ink-2: #b3c0d4; --muted: #7a879e;
  --pos: #19a67c; --neg: #e45a43; --idle: #5b7cfa; --glow-a: #3b4fd8; --glow-b: #6d3bd8;
}
* { box-sizing: border-box; }
body {
  margin: 0; color: var(--ink); min-height: 100vh;
  font: 14px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  -webkit-font-smoothing: antialiased;
  /* Layered glows over a vertical wash. background-attachment keeps them
     anchored to the viewport, so the ground stays lit while content scrolls
     rather than dragging a gradient down the page with it. */
  background:
    radial-gradient(90ch 60ch at 12% -8%, rgba(59,79,216,0.22), transparent 65%),
    radial-gradient(80ch 55ch at 88% 4%, rgba(109,59,216,0.16), transparent 62%),
    radial-gradient(70ch 50ch at 50% 108%, rgba(25,166,124,0.10), transparent 60%),
    linear-gradient(178deg, #0a0f1c 0%, var(--bg) 42%, #060911 100%);
  background-attachment: fixed;
}
.mono, .num, .hero-num, .card-price, .ticker { font-variant-numeric: tabular-nums; }
.mono, .num { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
.shell { max-width: 1120px; margin: 0 auto; padding: 22px 18px 72px; }

/* top bar */
.topbar {
  display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
  background: var(--panel); border: 1px solid var(--line); border-radius: 14px;
  padding: 12px 16px; margin-bottom: 18px;
}
.mark {
  width: 32px; height: 32px; border-radius: 9px; display: grid; place-items: center;
  background: linear-gradient(145deg, var(--pos), #0f7d5d); color: #04120d;
  font-weight: 800; font-size: 15px; flex: none;
}
.brand { font-size: 17px; font-weight: 650; letter-spacing: -0.01em; }
.navs { display: flex; gap: 4px; margin-left: 6px; flex-wrap: wrap; }
.nav { padding: 6px 13px; border-radius: 999px; font-size: 13px; color: var(--muted); }
.nav-on { background: var(--panel-2); color: var(--ink); border: 1px solid var(--line); }
.spacer { flex: 1 1 auto; }
.status {
  display: inline-flex; align-items: center; gap: 7px; padding: 6px 14px;
  border-radius: 999px; font-size: 12.5px; font-weight: 600;
  border: 1px solid currentColor;
}
.status .led { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
.status-ok { color: var(--pos); } .status-warn { color: #d9a441; } .status-halt { color: var(--neg); }

/* Panels. Each instance overrides the --g* variables inline with its own
   seeded values, so no two panels carry the same glow. Defaults here keep a
   panel sane if it is rendered without them. */
.panel {
  position: relative; overflow: hidden;
  --gx1: 18%; --gy1: 6%; --gr1: 62%; --go1: 0.17; --gc1: var(--glow-a);
  --gx2: 82%; --gy2: 22%; --gr2: 55%; --go2: 0.13; --gc2: var(--glow-b);
  --gtilt: 160deg;
  background: linear-gradient(var(--gtilt), var(--panel-2), var(--panel) 62%);
  border: 1px solid var(--line); border-radius: 16px; padding: 18px 20px; margin-bottom: 16px;
}
.panel::before {
  content: ""; position: absolute; inset: 0; pointer-events: none;
  background: radial-gradient(var(--gr1) var(--gr1) at var(--gx1) var(--gy1),
              var(--gc1), transparent 70%);
  opacity: var(--go1);
}
.panel::after {
  content: ""; position: absolute; inset: 0; pointer-events: none;
  background: radial-gradient(var(--gr2) var(--gr2) at var(--gx2) var(--gy2),
              var(--gc2), transparent 70%);
  opacity: var(--go2);
}
.panel > * { position: relative; }
.panel-head { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 10px; }
h2 {
  margin: 0; font-size: 11px; text-transform: uppercase; letter-spacing: 0.1em;
  color: var(--muted); font-weight: 650;
}
.panel-note { font-size: 11.5px; color: var(--muted); }
.hero-num { font-size: 34px; font-weight: 680; letter-spacing: -0.02em; margin-bottom: 6px; }
.equity { width: 100%; height: 240px; display: block; }
.axis { display: flex; justify-content: space-between; font-size: 11px; color: var(--muted); margin-top: 4px; }

/* banner */
.banner {
  display: flex; gap: 10px; align-items: baseline; flex-wrap: wrap;
  border-radius: 12px; padding: 12px 16px; margin-bottom: 16px; font-size: 13.5px;
  background: var(--panel); border: 1px solid var(--line); border-left: 3px solid var(--pos);
  color: var(--ink-2);
}
.banner-warn { border-left-color: #d9a441; } .banner-halt { border-left-color: var(--neg); }
.banner b { color: var(--ink); }

/* tiles */
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 16px; }
.tile { background: var(--panel); border: 1px solid var(--line); border-radius: 14px; padding: 14px 16px; }
.tile-label { display: block; font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--muted); }
.tile-value { display: block; font-size: 23px; font-weight: 650; margin-top: 3px; font-variant-numeric: tabular-nums; }
.tile-note { display: block; font-size: 11px; color: var(--muted); min-height: 1em; }

/* ticker cards */
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 12px; }
.card {
  position: relative; overflow: hidden;
  --gx1: 20%; --gy1: 10%; --gr1: 60%; --go1: 0.16; --gc1: var(--glow-a);
  --gx2: 80%; --gy2: 30%; --gr2: 55%; --go2: 0.10; --gc2: var(--glow-b);
  --gtilt: 155deg;
  background: linear-gradient(var(--gtilt), var(--panel-2), var(--panel) 70%);
  border: 1px solid var(--line); border-radius: 14px; padding: 14px;
}
/* Same glow machinery as .panel. The card's first hue is its direction
   (teal for a gain, coral for a loss), so the wash carries meaning while its
   placement stays decorative. */
.card::before {
  content: ""; position: absolute; inset: 0; pointer-events: none;
  background: radial-gradient(var(--gr1) var(--gr1) at var(--gx1) var(--gy1),
              var(--gc1), transparent 70%);
  opacity: var(--go1);
}
.card::after {
  content: ""; position: absolute; inset: 0; pointer-events: none;
  background: radial-gradient(var(--gr2) var(--gr2) at var(--gx2) var(--gy2),
              var(--gc2), transparent 70%);
  opacity: var(--go2);
}
.card > * { position: relative; }
.card-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.ticker { font-size: 14.5px; font-weight: 680; letter-spacing: 0.02em; }
.spark { width: 100%; height: 68px; display: block; margin: 8px 0 6px; }
.card-foot { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
.card-price { font-size: 17px; font-weight: 620; }
.card-delta { font-size: 13px; font-weight: 600; font-variant-numeric: tabular-nums; }
.card-note { font-size: 10.5px; color: var(--muted); margin-top: 5px; }

/* chips & pills */
.chip {
  font-size: 11px; font-weight: 650; padding: 3px 10px; border-radius: 999px;
  border: 1px solid currentColor; text-transform: lowercase;
}
.chip-pos { color: var(--pos); } .chip-neg { color: var(--neg); } .chip-idle { color: var(--muted); }
.pill {
  display: inline-block; font-size: 10.5px; font-weight: 650; padding: 3px 9px;
  border-radius: 999px; border: 1px solid var(--line); color: var(--ink-2);
  text-transform: uppercase; letter-spacing: 0.05em;
}
.pill-submitted { color: var(--idle); border-color: var(--idle); }
.pill-filled { color: var(--pos); border-color: var(--pos); }
.pill-blocked { color: var(--neg); border-color: var(--neg); }

/* positions */
.pos-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 10px; }
.pos-chip {
  display: flex; align-items: baseline; gap: 8px; background: var(--panel);
  border: 1px solid var(--line); border-radius: 12px; padding: 10px 13px; font-size: 13px;
}

/* tables */
.scroll { overflow-x: auto; border: 1px solid var(--line); border-radius: 12px; background: var(--panel); }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th {
  text-align: left; font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em;
  color: var(--muted); font-weight: 650; padding: 10px 13px;
  border-bottom: 1px solid var(--line); white-space: nowrap;
}
td { padding: 10px 13px; border-bottom: 1px solid var(--line); white-space: nowrap; color: var(--ink-2); }
tr:last-child td { border-bottom: none; }
.num { text-align: right; }
.sym { color: var(--ink); font-weight: 620; }
.pos { color: var(--pos); } .neg { color: var(--neg); } .muted { color: var(--muted); }
.empty {
  background: rgba(255,255,255,0.02); border: 1px dashed var(--line); border-radius: 12px;
  padding: 15px; color: var(--ink-2); font-size: 13px;
}
.empty strong { color: var(--ink); }
footer { color: var(--muted); font-size: 11.5px; margin-top: 22px; text-align: center; }
code { font-family: ui-monospace, Menlo, Consolas, monospace; color: var(--ink-2); }
@media (max-width: 560px) { .hero-num { font-size: 27px; } .navs { display: none; } }
"""


def status_bits(halt, snapshots) -> tuple[str, str, str]:
    if halt is not None:
        return ("halt", "Halted", f"{halt['reason']} — triggered {short_ts(halt['triggered_at'])}.")
    if not snapshots:
        return ("warn", "No runs", "No cycle has completed yet.")
    age = hours_since(snapshots[-1]["ts"])
    if age > STALE_AFTER_HOURS:
        return (
            "warn",
            "Stale",
            f"Last cycle {age:.0f}h ago, past the {STALE_AFTER_HOURS:.0f}h gap.",
        )
    return ("ok", "Running", f"Last cycle {short_ts(snapshots[-1]['ts'])}, {age:.1f}h ago.")


def build_html(conn: sqlite3.Connection, source: Path) -> str:
    orders = conn.execute("SELECT * FROM orders ORDER BY id").fetchall()
    fills = conn.execute("SELECT * FROM fills ORDER BY id").fetchall()
    snapshots = conn.execute("SELECT * FROM equity_snapshots ORDER BY id").fetchall()
    halts = conn.execute("SELECT * FROM halts ORDER BY id").fetchall()
    active = next((h for h in halts if h["cleared_at"] is None), None)

    positions: dict[str, int] = {}
    for f in fills:
        positions[f["symbol"]] = positions.get(f["symbol"], 0) + (
            f["qty"] if f["side"] == "buy" else -f["qty"]
        )

    tone, label, detail = status_bits(active, snapshots)
    equity = float(snapshots[-1]["equity"]) if snapshots else 0.0
    cash = float(snapshots[-1]["cash"]) if snapshots else 0.0
    pending = sum(1 for o in orders if o["status"] == "submitted")
    blocked = sum(1 for o in orders if o["status"] == "blocked")

    tiles = [
        ("Equity", money(equity), "mark to market"),
        ("Cash", money(cash), ""),
        ("Open positions", str(len([p for p in positions.values() if p])), ""),
        ("Orders", str(len(orders)), f"{pending} awaiting fill"),
        ("Fills", str(len(fills)), "settled trades"),
        ("Blocked by risk", str(blocked), "rejected pre-submit"),
    ]
    tile_html = "".join(
        f'<div class="tile"><span class="tile-label">{esc(la)}</span>'
        f'<span class="tile-value">{esc(v)}</span>'
        f'<span class="tile-note">{esc(n)}</span></div>'
        for la, v, n in tiles
    )

    generated = datetime.now(timezone.utc).strftime("%d %b %Y %H:%M UTC")
    return f"""<title>DIYQuant — dashboard</title>
<style>{CSS}</style>
<div class="shell">
  <div class="topbar">
    <span class="mark">Q</span>
    <span class="brand">DIYQuant</span>
    <nav class="navs">
      <span class="nav nav-on">Dashboard</span>
      <span class="nav">Paper</span>
      <span class="nav">SMA + FinBERT</span>
    </nav>
    <span class="spacer"></span>
    <span class="status status-{tone}"><span class="led"></span>{esc(label)}</span>
  </div>

  <div class="banner banner-{tone}"><b>{esc(label)}.</b> <span>{esc(detail)}</span></div>

  <div class="tiles">{tile_html}</div>

  {equity_panel(snapshots)}
  {ticker_cards()}

  <div class="panel" style="{glow("positions")}">
    <div class="panel-head"><h2>Positions</h2></div>
    {positions_block(positions)}
  </div>

  <div class="panel" style="{glow("orders")}">
    <div class="panel-head"><h2>Orders</h2>
      <span class="panel-note">most recent first</span></div>
    {orders_table(orders)}
  </div>

  <div class="panel" style="{glow("fills")}">
    <div class="panel-head"><h2>Fills</h2></div>
    {fills_table(fills)}
  </div>

  <footer>
    Read-only · generated {esc(generated)} from <code>{esc(source.name)}</code><br>
    Strategy changes live in <code>config/settings.yaml</code> under version control.
  </footer>
</div>"""


def main() -> int:
    args = parse_args()
    path = Path(args.ledger) if args.ledger else default_ledger_path()
    if not path.exists():
        print(f"no ledger at {path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    html = build_html(conn, path)
    conn.close()

    out = Path(args.out)
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out} ({len(html):,} bytes) from {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
