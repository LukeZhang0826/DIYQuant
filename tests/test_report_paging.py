import re

from diyquant.report.paging import (
    PAGE_SIZE,
    PAGER_SCRIPT,
    TABLE_ROWS,
    esc,
    newest_first,
    paged_table,
)


def test_newest_first_reverses_ledger_order():
    """Ledger tables arrive oldest-first; the dashboard reads newest-first."""
    assert newest_first([1, 2, 3]) == [3, 2, 1]


def test_newest_first_caps_at_the_table_limit():
    rows = list(range(500))
    assert len(newest_first(rows)) == TABLE_ROWS


def test_newest_first_keeps_the_recent_tail_not_the_oldest_rows():
    """Capping the wrong end shows ancient history at the right row count.

    A dashboard filled with the oldest 100 orders looks entirely normal, so a
    length check alone would not catch it. Assert on identity instead: 499 is
    the newest row, 0 the oldest.
    """
    kept = newest_first(list(range(500)), cap=3)
    assert kept == [499, 498, 497]
    assert 0 not in kept


def test_newest_first_under_the_cap_returns_everything():
    assert newest_first([1, 2], cap=10) == [2, 1]


def test_newest_first_handles_an_empty_table():
    assert newest_first([]) == []


def test_newest_first_does_not_mutate_its_input():
    rows = [1, 2, 3]
    newest_first(rows)
    assert rows == [1, 2, 3]


def rows_in(html: str) -> int:
    body = re.search(r"<tbody>(.*?)</tbody>", html, re.S)
    return body.group(1).count("<tr>") if body else 0


def test_paged_table_embeds_every_row_it_is_given():
    """Paging is client-side, so a row not embedded is a row no reader can reach."""
    rows = [f"<tr><td>{i}</td></tr>" for i in range(40)]
    assert rows_in(paged_table("<tr><th>n</th></tr>", rows, 40)) == 40


def test_paged_table_reports_the_full_ledger_total_separately():
    """100 rows must not silently pass for a complete table.

    The reader cannot otherwise tell a short ledger from a truncated view, so
    the full count travels with the markup for the footer to declare.
    """
    html = paged_table("<tr><th>n</th></tr>", ["<tr><td>x</td></tr>"] * 100, 15090)
    assert 'data-total="15090"' in html


def test_paged_table_declares_the_page_size_the_script_reads():
    """The script takes its page size from this attribute; a mismatch breaks paging."""
    html = paged_table("<tr><th>n</th></tr>", [], 0)
    assert f'data-page="{PAGE_SIZE}"' in html
    assert "root.dataset.page" in PAGER_SCRIPT


def test_paged_table_omits_the_filter_box_unless_search_is_requested():
    plain = paged_table("<tr><th>n</th></tr>", [], 0)
    searchable = paged_table("<tr><th>n</th></tr>", [], 0, search="Filter by ticker...")
    assert 'class="filter"' not in plain
    assert 'class="filter"' in searchable
    assert "Filter by ticker..." in searchable


def test_paged_table_escapes_the_search_placeholder():
    html = paged_table("<tr><th>n</th></tr>", [], 0, search='" onfocus="x')
    assert 'onfocus="x' not in html
    assert "&quot;" in html


def test_paged_table_emits_the_hooks_the_script_binds_to():
    """Markup and script are one contract: renaming either silently breaks paging.

    A broken pager still renders a plausible-looking page, so nothing else in
    the suite would catch this.
    """
    html = paged_table("<tr><th>n</th></tr>", ["<tr><td>x</td></tr>"], 1, search="find")
    for hook in ('class="paged"', "pager-pages", "pager-note", "data-nav=", 'class="filter"'):
        assert hook in html
    for selector in (".paged", ".pager-pages", ".pager-note", "[data-nav=prev]", ".filter"):
        assert selector in PAGER_SCRIPT


def test_esc_neutralises_markup():
    assert esc("<script>&") == "&lt;script&gt;&amp;"


def test_esc_escapes_quotes_used_to_delimit_attributes():
    """Attributes here are written in single quotes, so both forms must escape."""
    assert '"' not in esc('a "b" c')
    assert "'" not in esc("a 'b' c")


def test_esc_coerces_non_strings():
    assert esc(3) == "3"
    assert esc(None) == "None"
