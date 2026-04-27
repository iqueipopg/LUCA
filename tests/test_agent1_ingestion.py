"""Unit tests for agents.agent1_ingestion.ingest.

All EDGAR HTTP calls are mocked. Tests verify the output contract shape and
error handling.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _load_fixture(name: str) -> dict:
    with (_FIXTURES_DIR / name).open("r", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(autouse=True)
def reset_state():
    """Reset process-level caches before each test."""
    import agents._config as cfg_mod
    import agents._edgar_client as edgar_mod

    cfg_mod._CACHE = None
    edgar_mod._TICKER_CACHE = None
    yield
    cfg_mod._CACHE = None
    edgar_mod._TICKER_CACHE = None


# Expected top-level keys in the ingest() output contract.
_INGEST_REQUIRED_KEYS = {
    "company",
    "ticker",
    "cik",
    "filing_date",
    "accession_number",
    "html_content",
    "xbrl_data",
    "source_urls",
}


class TestIngestOutputShape:
    def test_ingest_returns_correct_shape(self):
        """ingest() must return a dict with all required contract keys.

        Patch targets use the agent's own module namespace (where the names
        were imported with ``from agents._edgar_client import ...``).
        """
        companyfacts = _load_fixture("companyfacts_AAPL.json")
        submissions = _load_fixture("submissions_AAPL.json")

        with patch("agents.agent1_ingestion.ticker_to_cik", return_value="0000320193"), \
             patch("agents.agent1_ingestion.fetch_companyfacts", return_value=companyfacts), \
             patch("agents.agent1_ingestion.fetch_submissions", return_value=submissions), \
             patch("time.sleep"):
            from agents.agent1_ingestion import ingest

            result = ingest("AAPL")

        missing = _INGEST_REQUIRED_KEYS - set(result.keys())
        assert not missing, f"ingest() output missing keys: {missing}"

    def test_ingest_populates_basic_fields(self):
        """ingest() must correctly populate ticker, company, cik from fixtures."""
        companyfacts = _load_fixture("companyfacts_AAPL.json")
        submissions = _load_fixture("submissions_AAPL.json")

        with patch("agents.agent1_ingestion.ticker_to_cik", return_value="0000320193"), \
             patch("agents.agent1_ingestion.fetch_companyfacts", return_value=companyfacts), \
             patch("agents.agent1_ingestion.fetch_submissions", return_value=submissions), \
             patch("time.sleep"):
            from agents.agent1_ingestion import ingest

            result = ingest("aapl")  # lowercase to test normalization

        assert result["ticker"] == "AAPL"
        assert result["company"] == "Apple Inc."
        assert result["cik"] == "0000320193"


class TestIngestNoTenK:
    def test_ingest_no_10k_returns_none_filing_date(self):
        """ingest() must set filing_date=None when no 10-K is present in submissions."""
        companyfacts = _load_fixture("companyfacts_AAPL.json")

        # Submissions with only 10-Q filings
        submissions_no_10k = {
            "name": "Apple Inc.",
            "filings": {
                "recent": {
                    "form": ["10-Q", "10-Q"],
                    "filingDate": ["2023-08-04", "2023-05-05"],
                    "accessionNumber": ["0000320193-23-000077", "0000320193-23-000064"],
                }
            },
        }

        with patch("agents.agent1_ingestion.ticker_to_cik", return_value="0000320193"), \
             patch("agents.agent1_ingestion.fetch_companyfacts", return_value=companyfacts), \
             patch("agents.agent1_ingestion.fetch_submissions", return_value=submissions_no_10k), \
             patch("time.sleep"):
            from agents.agent1_ingestion import ingest

            result = ingest("AAPL")

        assert result["filing_date"] is None, (
            f"Expected filing_date=None when no 10-K found, got {result['filing_date']!r}"
        )
        assert result["accession_number"] is None, (
            "Expected accession_number=None when no 10-K found"
        )


class TestIngestUnknownTicker:
    def test_ingest_unknown_ticker_raises(self):
        """ingest() must propagate ValueError for unresolvable tickers."""
        with patch(
            "agents.agent1_ingestion.ticker_to_cik",
            side_effect=ValueError("Ticker 'ZZZZ' not found in SEC EDGAR ticker map."),
        ), patch("time.sleep"):
            from agents.agent1_ingestion import ingest

            with pytest.raises(ValueError):
                ingest("ZZZZ")
