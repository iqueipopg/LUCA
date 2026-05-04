"""Unit tests for agents.agent2_parser.parse.

No mocks needed — the parser is a pure function of string inputs. We use
the sample_10k.html fixture loaded via conftest.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_ingest(html_content: str = "") -> dict:
    """Build a minimal ingest_output dict for parse()."""
    return {
        "company": "Apple Inc.",
        "ticker": "AAPL",
        "filing_date": "2023-11-03",
        "html_content": html_content,
        "xbrl_data": {},
        "accession_number": None,
        "cik": "0000320193",
        "source_urls": {},
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestParseEmptyHtml:
    def test_parse_empty_html_returns_empty_items(self):
        """parse() with empty html_content must return empty strings for all items
        and an empty raw_tables list."""
        from agents.agent2_parser import parse

        result = parse(_make_ingest(html_content=""))

        assert result["item_1"] == ""
        assert result["item_1a"] == ""
        assert result["item_7"] == ""
        assert result["item_8"] == ""
        assert result["raw_tables"] == []

    def test_parse_empty_html_preserves_metadata(self):
        """parse() with empty html must still carry company/ticker/filing_date."""
        from agents.agent2_parser import parse

        result = parse(_make_ingest(html_content=""))

        assert result["company"] == "Apple Inc."
        assert result["ticker"] == "AAPL"
        assert result["filing_date"] == "2023-11-03"


class TestParseExtractsItem1A:
    def test_parse_extracts_item_1a(self, sample_10k_html):
        """parse() must extract a non-empty item_1a from the sample fixture."""
        from agents.agent2_parser import parse

        result = parse(_make_ingest(html_content=sample_10k_html))

        assert result["item_1a"] != "", (
            "item_1a should not be empty with the sample fixture"
        )
        # Spot check: the sample 1A mentions Risk Factors
        assert "Risk" in result["item_1a"] or "risk" in result["item_1a"]


class TestParseExtractsAllFourItems:
    def test_parse_extracts_all_four_items(self, sample_10k_html):
        """All four items must have content > 0 chars with the sample fixture."""
        from agents.agent2_parser import parse

        result = parse(_make_ingest(html_content=sample_10k_html))

        for item_key in ("item_1", "item_1a", "item_7", "item_8"):
            assert len(result[item_key]) > 0, (
                f"{item_key} is empty but should have content from the sample fixture"
            )


class TestParseExtractsTable:
    def test_parse_extracts_table(self, sample_10k_html):
        """parse() must populate raw_tables with at least one entry from the fixture.

        The sample_10k.html contains a financial statements table in Item 8.
        """
        from agents.agent2_parser import parse

        result = parse(_make_ingest(html_content=sample_10k_html))

        assert len(result["raw_tables"]) >= 1, (
            "raw_tables should have at least one table from the sample fixture"
        )
        # Each table entry must be a non-empty string
        for table_text in result["raw_tables"]:
            assert isinstance(table_text, str)
            assert len(table_text) > 0


class TestParseSkipsTableOfContents:
    """T1.7b — body headers, not TOC entries.

    The original Sprint 0 implementation always picked the *first*
    occurrence of each item header, which on real 10-Ks falls inside
    the table of contents (e.g., ``Item 1. Business 1`` — title plus
    page number, ~20 chars). After T1.7b the parser detects the TOC
    cluster, skips past it, and applies title-aware regexes to the
    body text.
    """

    def test_item_1_picks_body_not_toc_entry(self, sample_10k_with_toc_html):
        """item_1 must contain Item 1 body text, not the TOC line."""
        from agents.agent2_parser import parse

        result = parse(_make_ingest(html_content=sample_10k_with_toc_html))

        assert len(result["item_1"]) > 1000, (
            f"item_1 should pick the body, not the TOC line; got "
            f"{len(result['item_1'])} chars: {result['item_1'][:200]!r}"
        )
        assert result["item_1"].lower().startswith("item 1. business"), (
            "item_1 must start with the body header, not midway through"
        )
        assert "Forward-Looking Statements" in result["item_1"]
        # Sanity: we must NOT have leaked into the Item 1A body. The
        # cross-reference "See Item 1A … under the heading "Risk
        # Factors"" lives inside Item 1, so the substring "Risk
        # Factors" can legitimately appear; what cannot appear is the
        # body header sentence "Item 1A. Risk Factors The Company's
        # business" that opens Item 1A in the fixture.
        assert "Macroeconomic" not in result["item_1"]
        assert "The Company’s business, reputation" not in result["item_1"]

    def test_item_1a_picks_body_not_toc_entry(self, sample_10k_with_toc_html):
        """item_1a must contain Item 1A body text, not the TOC line."""
        from agents.agent2_parser import parse

        result = parse(_make_ingest(html_content=sample_10k_with_toc_html))

        assert len(result["item_1a"]) > 100, (
            f"item_1a should pick the body, not the TOC line; got "
            f"{len(result['item_1a'])} chars: {result['item_1a'][:200]!r}"
        )
        assert "Macroeconomic" in result["item_1a"]

    def test_item_7_picks_body_with_md_and_a_content(
        self, sample_10k_with_toc_html,
    ):
        """item_7 must contain MD&A body, not the TOC line."""
        from agents.agent2_parser import parse

        result = parse(_make_ingest(html_content=sample_10k_with_toc_html))

        assert len(result["item_7"]) > 100
        assert "$416.2 billion" in result["item_7"]

    def test_item_8_picks_body_and_includes_table_text(
        self, sample_10k_with_toc_html,
    ):
        """item_8 must contain the financial statements body."""
        from agents.agent2_parser import parse

        result = parse(_make_ingest(html_content=sample_10k_with_toc_html))

        assert len(result["item_8"]) > 100
        # Body header verbatim, then the consolidated statements table.
        assert "Financial Statements" in result["item_8"]
        assert "Net income" in result["item_8"]

    def test_raw_tables_still_includes_toc_table(
        self, sample_10k_with_toc_html,
    ):
        """T1.7b must NOT alter raw_tables — full set still flows downstream."""
        from agents.agent2_parser import parse

        result = parse(_make_ingest(html_content=sample_10k_with_toc_html))

        # Fixture has two tables: the TOC and the financial statements.
        assert len(result["raw_tables"]) >= 2
        joined = "\n".join(result["raw_tables"])
        assert "Risk Factors" in joined  # TOC entry survives
        assert "$416,161" in joined      # financial statements survive


class TestLocateTocEnd:
    """Direct unit tests for :func:`agents.agent2_parser._locate_toc_end`.

    The new heuristic is DOM-based: it walks ``<table>`` elements and
    picks the first one with ≥_TOC_MIN_ENTRIES item-N references in
    its cell text.
    """

    def test_returns_zero_when_no_tables_present(self):
        """Plain-text-only HTML with no <table> means no TOC to skip."""
        from agents.agent2_parser import _html_to_text, _locate_toc_end

        html = (
            "<html><body>"
            "<p>Item 1. Business body.</p>"
            "<p>Item 1A. Risk Factors body.</p>"
            "</body></html>"
        )
        plain = _html_to_text(html)
        assert _locate_toc_end(html, plain) == 0

    def test_returns_zero_when_table_is_not_a_toc(self):
        """A small table with < _TOC_MIN_ENTRIES item refs is not a TOC."""
        from agents.agent2_parser import _html_to_text, _locate_toc_end

        html = (
            "<html><body>"
            "<table>"
            "<tr><td>Filer</td><td>Item 1 only here</td></tr>"
            "</table>"
            "<p>Item 1. Business body content.</p>"
            "<p>Item 1A. Risk Factors body.</p>"
            "</body></html>"
        )
        plain = _html_to_text(html)
        assert _locate_toc_end(html, plain) == 0

    def test_skips_cover_page_tables_and_finds_real_toc(self):
        """Cover-page tables (≤2 cells) come before the TOC; the heuristic
        must skip them and land on the first table with many item refs."""
        from agents.agent2_parser import _html_to_text, _locate_toc_end

        html = (
            "<html><body>"
            "<table><tr><td>California</td><td>94-2404110</td></tr></table>"
            "<table><tr><td>Common Stock</td><td>AAPL</td></tr></table>"
            "<table>"
            "<tr><td>Item 1.</td><td>Business</td><td>1</td></tr>"
            "<tr><td>Item 1A.</td><td>Risk Factors</td><td>5</td></tr>"
            "<tr><td>Item 7.</td><td>MD&amp;A</td><td>23</td></tr>"
            "<tr><td>Item 8.</td><td>Financial Statements</td><td>28</td></tr>"
            "<tr><td>Item 9.</td><td>Changes</td><td>52</td></tr>"
            "</table>"
            "<p>BODY_MARKER</p>"
            "<p>Item 1. Business The Company designs ...</p>"
            "</body></html>"
        )
        plain = _html_to_text(html)
        end = _locate_toc_end(html, plain)
        assert end > 0
        tail = plain[end:]
        # The TOC text must NOT survive past the offset, but the body
        # marker must.
        assert "BODY_MARKER" in tail
        assert "Risk Factors 5" not in tail
