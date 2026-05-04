"""Unit tests for ``experiments.eval_baseline_llm``.

Focus on the deterministic helpers introduced or rewritten by T1.9
Bug #2 (``prepare_structured_content`` filtering) and Bug #3
(``prepare_naive_content`` head-plus-tail truncation). The LLM call
itself is not exercised here — the run-level integration is verified
end-to-end by ``--limit 1`` smoke runs against the real cache.
"""

from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))


# ---------------------------------------------------------------------------
# Bug #3 — prepare_naive_content: head + tail composition
# ---------------------------------------------------------------------------


class TestPrepareNaiveContent:
    """T1.9 Bug #3 — naive truncation must reach Item 8."""

    def test_short_html_returned_unchanged(self):
        """Documents below the budget should not be sliced at all."""
        from experiments.eval_baseline_llm import (
            NAIVE_MAX_CHARS,
            html_to_plain_text,
            prepare_naive_content,
        )

        html = "<html><body>" + ("Apple is a company. " * 50) + "</body></html>"
        plain = html_to_plain_text(html)
        assert len(plain) < NAIVE_MAX_CHARS

        out = prepare_naive_content(html, ticker="AAPL")
        assert out == plain

    def test_long_html_returns_head_plus_separator_plus_tail(self):
        """A document above the budget yields head + ``[...]`` + tail."""
        from experiments.eval_baseline_llm import (
            NAIVE_HEAD_CHARS,
            NAIVE_HEAD_TAIL_SEPARATOR,
            NAIVE_MAX_CHARS,
            NAIVE_TAIL_CHARS,
            html_to_plain_text,
            prepare_naive_content,
        )

        # Construct a deterministic plain text where head and tail
        # are unambiguously distinguishable.
        head_marker = "HEAD_MARKER_FYE_2025"
        tail_marker = "TAIL_MARKER_NET_INCOME_TABLE"
        body_filler = "x" * (NAIVE_MAX_CHARS * 2)
        plain_target = f"{head_marker} {body_filler} {tail_marker}"
        # Wrap in HTML so html_to_plain_text reproduces it verbatim.
        html = f"<html><body>{plain_target}</body></html>"

        # Sanity on construction.
        plain = html_to_plain_text(html)
        assert len(plain) > NAIVE_MAX_CHARS

        out = prepare_naive_content(html, ticker="AAPL")

        # Length is exactly HEAD + SEPARATOR + TAIL.
        assert len(out) == NAIVE_HEAD_CHARS + len(NAIVE_HEAD_TAIL_SEPARATOR) + NAIVE_TAIL_CHARS
        # The separator appears exactly once.
        assert out.count(NAIVE_HEAD_TAIL_SEPARATOR) == 1
        # Both markers are preserved (head and tail are taken verbatim).
        assert head_marker in out
        assert tail_marker in out
        # Composition: the separator splits head from tail.
        head_part, _, tail_part = out.partition(NAIVE_HEAD_TAIL_SEPARATOR)
        assert head_part == plain[:NAIVE_HEAD_CHARS]
        assert tail_part == plain[-NAIVE_TAIL_CHARS:]


# ---------------------------------------------------------------------------
# Bug #2 — prepare_structured_content: financial-table filter
# ---------------------------------------------------------------------------


class TestIsFinancialTable:
    """T1.9 Bug #2 — _is_financial_table heuristic."""

    def test_cover_page_address_table_is_rejected(self):
        from experiments.eval_baseline_llm import _is_financial_table

        text = (
            "California | 94-2404110\n"
            "(State or other jurisdiction of incorporation or organization)"
            " | (I.R.S. Employer Identification No.)\n"
            "One Apple Park Way\n"
            "Cupertino , California | 95014"
        )
        assert _is_financial_table(text) is False

    def test_consolidated_statement_table_is_accepted(self):
        """An income-statement excerpt with 'Net income' line passes both
        the dollar-amount and keyword filters."""
        from experiments.eval_baseline_llm import _is_financial_table

        text = (
            "Years ended\n"
            "September 27, 2025 | September 28, 2024 | September 30, 2023\n"
            "Net sales | $ | 416,161 | $ | 391,035 | $ | 365,817\n"
            "Operating income | 133,050 | 123,216 | 114,301\n"
            "Net income | $ | 112,010 | $ | 93,736 | $ | 96,995\n"
            "Earnings per share: Diluted | $ | 7.46 | $ | 6.08 | $ | 6.13"
        )
        assert _is_financial_table(text) is True

    def test_mda_segment_breakdown_is_rejected(self):
        """MD&A segment-revenue tables have $-amounts but lack canonical
        consolidated-statement keywords; they must be excluded."""
        from experiments.eval_baseline_llm import _is_financial_table

        text = (
            "2025 | Change | 2024 | Change | 2023\n"
            "Americas | $ | 178,353 | 7 | % | $ | 167,045 | 3 | % | $ | 162,560\n"
            "Europe | 111,032 | 10 | % | 101,328 | 7 | % | 94,294\n"
            "Greater China | 64,377 | (4) | % | 66,952 | (8) | % | 72,559\n"
            "Total net sales | $ | 416,161 | 6 | % | $ | 391,035 | 2 | % | $ | 383,285"
        )
        assert _is_financial_table(text) is False

    def test_non_string_input_is_rejected(self):
        from experiments.eval_baseline_llm import _is_financial_table

        assert _is_financial_table(None) is False
        assert _is_financial_table(123) is False
        assert _is_financial_table(["row1", "row2"]) is False


class TestPrepareStructuredContent:
    """T1.9 Bug #2 — selection of the first 5 financial-shaped tables."""

    @staticmethod
    def _make_parse_fn(raw_tables):
        """Return a stub parse function that yields fixed raw_tables."""
        def _fake_parse(_ingest):
            return {"raw_tables": raw_tables}
        return _fake_parse

    def test_skips_cover_page_and_picks_consolidated_statements(self):
        from experiments.eval_baseline_llm import prepare_structured_content

        # Three cover-page-style tables (no $ amounts) followed by
        # three financial tables. All three financial tables must
        # appear in the output, in order.
        cover_pages = [
            "California | 94-2404110",
            "Common Stock | AAPL | The Nasdaq Stock Market LLC",
            "Large accelerated filer | X",
        ]
        income = (
            "2025 | 2024 | 2023\n"
            "Net sales | $ | 416,161 | $ | 391,035 | $ | 365,817\n"
            "Operating income | $ | 133,050 | $ | 123,216 | $ | 114,301\n"
            "Net income | $ | 112,010 | $ | 93,736 | $ | 96,995"
        )
        balance = (
            "Sep 27, 2025 | Sep 28, 2024\n"
            "Total assets | $ | 359,241 | $ | 364,840\n"
            "Total liabilities | $ | 285,508 | $ | 308,030\n"
            "Total shareholders' equity | $ | 73,733 | $ | 56,810"
        )
        cash_flow = (
            "2025 | 2024 | 2023\n"
            "Operating activities:\n"
            "Net income | $ | 112,010 | $ | 93,736 | $ | 96,995\n"
            "Cash generated by operating activities | $ | 111,482 | $ | 118,254 | $ | 110,543"
        )
        raw_tables = cover_pages + [income, balance, cash_flow]

        out = prepare_structured_content(
            ingest_output={"html_content": "<html></html>"},
            ticker="AAPL",
            parse_fn=self._make_parse_fn(raw_tables),
        )

        # Cover page text is gone, all three financial tables remain in order.
        assert "California" not in out
        assert "Common Stock" not in out
        assert "Large accelerated filer" not in out
        # Each financial table is included with its TABLA marker.
        assert "--- TABLA 1 ---" in out
        assert "--- TABLA 2 ---" in out
        assert "--- TABLA 3 ---" in out
        # Order is preserved (income before balance before cash flow).
        idx_income = out.find("416,161")
        idx_balance = out.find("359,241")
        idx_cash = out.find("118,254")
        assert idx_income < idx_balance < idx_cash

    def test_returns_empty_when_no_financial_tables(self):
        from experiments.eval_baseline_llm import prepare_structured_content

        cover_only = [
            "California | 94-2404110",
            "Common Stock | AAPL | Nasdaq",
        ]
        out = prepare_structured_content(
            ingest_output={"html_content": "<html></html>"},
            ticker="AAPL",
            parse_fn=self._make_parse_fn(cover_only),
        )
        assert out == ""

    def test_caps_at_structured_table_count(self):
        from experiments.eval_baseline_llm import (
            STRUCTURED_TABLE_COUNT,
            prepare_structured_content,
        )

        # 7 financial-shaped tables; only STRUCTURED_TABLE_COUNT (=5)
        # should make it into the output. Each table satisfies both
        # filter conditions (≥3 dollar amounts and a canonical
        # consolidated-statement keyword).
        fin_table = (
            "2025 | 2024\n"
            "Net income | $ | 100,000 | $ | 95,000\n"
            "Total assets | $ | 50,000 | $ | 45,000\n"
            "Operating activities | $ | 10,000 | $ | 9,000"
        )
        raw_tables = [fin_table + f"\nMARKER_{i}" for i in range(7)]

        out = prepare_structured_content(
            ingest_output={"html_content": "<html></html>"},
            ticker="AAPL",
            parse_fn=self._make_parse_fn(raw_tables),
        )

        for i in range(STRUCTURED_TABLE_COUNT):
            assert f"MARKER_{i}" in out
        for i in range(STRUCTURED_TABLE_COUNT, 7):
            assert f"MARKER_{i}" not in out
