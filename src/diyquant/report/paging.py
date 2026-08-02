"""Row capping and client-side pagination for the HTML dashboard.

The dashboard is a single static file with no backend, so a table cannot fetch
its next page: every row a reader can reach has to be in the document already.
That one constraint drives everything here.

It means the *embedded* row count is the real cost and the pager is only a
readability device, so capping and paging are two halves of one decision and
live in one module rather than drifting apart. It also means the markup, the
stylesheet and the script are a single contract: the script finds rows by the
class names and data attributes `paged_table` emits, so renaming one without
the others breaks paging silently, on a page that still looks fine. Keeping
them in one file is what makes that hard to do by accident.

The dashboard renders from an append-only ledger that only grows, so the cap is
the difference between a page that stays a fixed size forever and one that
grows without bound. At S&P 500 scale the sentiment gate alone writes ~503 rows
per cycle.
"""

from collections.abc import Sequence
from html import escape
from typing import TypeVar

TABLE_ROWS = 100  # ledger rows embedded per table
PAGE_SIZE = 25  # rows revealed at once within a paged table

T = TypeVar("T")


def esc(value: object) -> str:
    """HTML-escape any value, coercing to str first.

    Wraps the stdlib rather than hand-rolling the replacements: `html.escape`
    also escapes the apostrophe, and this codebase writes attributes in single
    quotes (`class='...'`), so a value containing one would otherwise close the
    attribute early.
    """
    return escape(str(value))


def newest_first(rows: Sequence[T], cap: int = TABLE_ROWS) -> list[T]:
    """The most recent `cap` rows, newest first.

    Ledger tables arrive oldest-first, so the recent end is the tail. Capping
    the head instead is the mistake to avoid: it yields the right number of
    rows and a page that looks entirely normal while showing the oldest history
    in the ledger.

    Slicing before reversing is a smaller point, and about cost rather than
    output: `reversed(rows)[:cap]` returns the same rows but materialises every
    one of a table that only ever grows.
    """
    return list(reversed(rows[-cap:] if cap > 0 else []))


def paged_table(head: str, rows: Sequence[str], total: int, *, search: str = "") -> str:
    """Wrap pre-rendered `<tr>` strings in a table that reveals PAGE_SIZE at a time.

    `total` is the full count in the ledger, which is normally larger than
    `len(rows)`. It is reported separately so the footer can admit how much
    history was left behind: 100 rows silently passing for a complete table is
    the failure this guards against, since a reader cannot tell a short ledger
    from a truncated view.

    Passing `search` adds a filter box. With JavaScript off the whole thing
    degrades to an ordinary table showing every embedded row.
    """
    filt = (
        f'<input class="filter" type="search" placeholder="{esc(search)}" '
        f'aria-label="{esc(search)}">'
        if search
        else ""
    )
    return f"""<div class="paged" data-page="{PAGE_SIZE}">
  {filt}
  <div class="scroll"><table>
    <thead>{head}</thead>
    <tbody>{"".join(rows)}</tbody>
  </table></div>
  <div class="pager">
    <button class="pg" data-nav="prev">&lsaquo; Prev</button>
    <span class="pager-pages"></span>
    <button class="pg" data-nav="next">Next &rsaquo;</button>
    <span class="pager-note" data-total="{total}">{len(rows)} rows</span>
  </div>
</div>"""


PAGER_CSS = """
/* Rows are hidden with the `hidden` attribute rather than a class so the table
   still reads correctly to assistive tech, and so a page with JavaScript off
   shows every embedded row instead of an empty tbody. */
[hidden] { display: none !important; }
.pager {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  margin-top: 10px; font-size: 12px;
}
.pg {
  font: inherit; font-variant-numeric: tabular-nums; color: var(--ink-2);
  background: var(--panel); border: 1px solid var(--line); border-radius: 8px;
  padding: 5px 10px; cursor: pointer;
}
.pg:hover:not(:disabled) { color: var(--ink); border-color: var(--muted); }
.pg:disabled { opacity: 0.35; cursor: default; }
.pg-on { color: var(--ink); background: var(--panel-2); border-color: var(--idle); }
.pager-pages { display: flex; gap: 4px; align-items: center; flex-wrap: wrap; }
.pager-gap { color: var(--muted); padding: 0 2px; }
.pager-note { color: var(--muted); margin-left: auto; font-variant-numeric: tabular-nums; }
.filter {
  font: inherit; width: 100%; max-width: 260px; margin-bottom: 10px;
  color: var(--ink); background: var(--panel); border: 1px solid var(--line);
  border-radius: 9px; padding: 7px 11px;
}
.filter::placeholder { color: var(--muted); }
.filter:focus { outline: none; border-color: var(--idle); }
"""

PAGER_SCRIPT = """
/* Client-side paging for every .paged table. There is no backend to ask for
   page 2, so all rows are already in the document and this only decides which
   of them are visible. */
document.querySelectorAll('.paged').forEach(function (root) {
  var size = Number(root.dataset.page) || 25;
  var rows = Array.prototype.slice.call(root.querySelectorAll('tbody tr'));
  var pages = root.querySelector('.pager-pages');
  var note = root.querySelector('.pager-note');
  var prev = root.querySelector('[data-nav=prev]');
  var next = root.querySelector('[data-nav=next]');
  var box = root.querySelector('.filter');
  var ledger = Number(note.dataset.total) || rows.length;
  var page = 0;
  var shown = rows;

  /* Page numbers, windowed around the current one. The universe table runs to
     20-odd pages, so listing them all would wrap the pager onto three lines. */
  function numbers(n) {
    if (n <= 7) {
      var all = [];
      for (var i = 0; i < n; i++) all.push(i);
      return all;
    }
    var out = [0];
    var lo = Math.max(1, page - 1);
    var hi = Math.min(n - 2, page + 1);
    if (lo > 1) out.push(null);
    for (var j = lo; j <= hi; j++) out.push(j);
    if (hi < n - 2) out.push(null);
    out.push(n - 1);
    return out;
  }

  function render() {
    var count = shown.length;
    var total = Math.max(Math.ceil(count / size), 1);
    if (page > total - 1) page = total - 1;

    rows.forEach(function (r) { r.hidden = true; });
    var start = page * size;
    shown.slice(start, start + size).forEach(function (r) { r.hidden = false; });

    pages.textContent = '';
    numbers(total).forEach(function (p) {
      if (p === null) {
        var gap = document.createElement('span');
        gap.className = 'pager-gap';
        gap.textContent = '\\u2026';
        pages.appendChild(gap);
        return;
      }
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'pg' + (p === page ? ' pg-on' : '');
      b.textContent = String(p + 1);
      b.addEventListener('click', function () { page = p; render(); });
      pages.appendChild(b);
    });

    var first = count ? start + 1 : 0;
    var last = Math.min(start + size, count);
    var range = 'showing ' + first + '-' + last + ' of ';
    if (count !== rows.length) {
      /* filtered: name the match count, and the loaded count it was drawn from */
      note.textContent = range + count + ' matching \\u00b7 ' +
        rows.length.toLocaleString() + ' loaded';
    } else if (ledger > rows.length) {
      /* capped: the ledger holds more than the page embeds, and must say so */
      note.textContent = range + rows.length.toLocaleString() + ' \\u00b7 ' +
        ledger.toLocaleString() + ' in ledger';
    } else {
      note.textContent = range + rows.length.toLocaleString();
    }

    prev.disabled = page === 0;
    next.disabled = page >= total - 1;
  }

  prev.addEventListener('click', function () {
    if (page > 0) { page--; render(); }
  });
  next.addEventListener('click', function () {
    if (page < Math.ceil(shown.length / size) - 1) { page++; render(); }
  });
  if (box) {
    box.addEventListener('input', function () {
      var q = box.value.trim().toLowerCase();
      shown = q ? rows.filter(function (r) {
        return r.textContent.toLowerCase().indexOf(q) !== -1;
      }) : rows;
      page = 0;
      render();
    });
  }

  render();
});
"""
