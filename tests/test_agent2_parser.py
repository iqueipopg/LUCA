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
