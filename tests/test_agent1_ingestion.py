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


@pytest.fixture
def patched_cache_dir(tmp_path, monkeypatch):
    """Redirect agent1_ingestion's cache to ``tmp_path`` for the test.

    Ensures that no test ever writes into the real ``data/cache/`` and that
    each test starts with an empty cache.
    """
    import agents.agent1_ingestion as ing_mod

    cache_dir = tmp_path / "cache"
    monkeypatch.setattr(ing_mod, "_CACHE_DIR", cache_dir)
    yield cache_dir


class TestIngestOutputShape:
    def test_ingest_returns_correct_shape(self, patched_cache_dir):
        """ingest() must return a dict with all required contract keys.

        Patch targets use the agent's own module namespace (where the names
        were imported with ``from agents._edgar_client import ...``).
        """
        companyfacts = _load_fixture("companyfacts_AAPL.json")
        submissions = _load_fixture("submissions_AAPL.json")

        with patch("agents.agent1_ingestion.ticker_to_cik", return_value="0000320193"), \
             patch("agents.agent1_ingestion.fetch_companyfacts", return_value=companyfacts), \
             patch("agents.agent1_ingestion.fetch_submissions", return_value=submissions), \
             patch("agents.agent1_ingestion.fetch_10k_html", return_value="<html>10-K</html>"), \
             patch("time.sleep"):
            from agents.agent1_ingestion import ingest

            result = ingest("AAPL")

        missing = _INGEST_REQUIRED_KEYS - set(result.keys())
        assert not missing, f"ingest() output missing keys: {missing}"
        # T1.7: html_content is no longer empty when a 10-K is found.
        assert result["html_content"] == "<html>10-K</html>"

    def test_ingest_populates_basic_fields(self, patched_cache_dir):
        """ingest() must correctly populate ticker, company, cik from fixtures."""
        companyfacts = _load_fixture("companyfacts_AAPL.json")
        submissions = _load_fixture("submissions_AAPL.json")

        with patch("agents.agent1_ingestion.ticker_to_cik", return_value="0000320193"), \
             patch("agents.agent1_ingestion.fetch_companyfacts", return_value=companyfacts), \
             patch("agents.agent1_ingestion.fetch_submissions", return_value=submissions), \
             patch("agents.agent1_ingestion.fetch_10k_html", return_value="<html>10-K</html>"), \
             patch("time.sleep"):
            from agents.agent1_ingestion import ingest

            result = ingest("aapl")  # lowercase to test normalization

        assert result["ticker"] == "AAPL"
        assert result["company"] == "Apple Inc."
        assert result["cik"] == "0000320193"


class TestIngestNoTenK:
    def test_ingest_no_10k_returns_none_filing_date(self, patched_cache_dir):
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

        # If accession_number is None, fetch_10k_html must NOT be called.
        # We fail loudly if it is.
        def _explode(*a, **kw):  # pragma: no cover - safety net
            raise AssertionError("fetch_10k_html should not be called when accession is None")

        with patch("agents.agent1_ingestion.ticker_to_cik", return_value="0000320193"), \
             patch("agents.agent1_ingestion.fetch_companyfacts", return_value=companyfacts), \
             patch("agents.agent1_ingestion.fetch_submissions", return_value=submissions_no_10k), \
             patch("agents.agent1_ingestion.fetch_10k_html", side_effect=_explode), \
             patch("time.sleep"):
            from agents.agent1_ingestion import ingest

            result = ingest("AAPL")

        assert result["filing_date"] is None, (
            f"Expected filing_date=None when no 10-K found, got {result['filing_date']!r}"
        )
        assert result["accession_number"] is None, (
            "Expected accession_number=None when no 10-K found"
        )
        assert result["html_content"] == "", (
            "Expected html_content='' when no 10-K is found, got "
            f"{result['html_content']!r}"
        )


class TestIngestHtmlCache:
    """T1.7 — verify the on-disk cache for 10-K HTML downloads."""

    def test_first_call_downloads_and_caches(self, patched_cache_dir):
        """On a cache miss, ingest() calls fetch_10k_html and writes the file."""
        companyfacts = _load_fixture("companyfacts_AAPL.json")
        submissions = _load_fixture("submissions_AAPL.json")

        html_body = "<html><body>Apple 10-K body</body></html>"

        with patch("agents.agent1_ingestion.ticker_to_cik", return_value="0000320193"), \
             patch("agents.agent1_ingestion.fetch_companyfacts", return_value=companyfacts), \
             patch("agents.agent1_ingestion.fetch_submissions", return_value=submissions), \
             patch(
                 "agents.agent1_ingestion.fetch_10k_html",
                 return_value=html_body,
             ) as mock_fetch, \
             patch("time.sleep"):
            from agents.agent1_ingestion import ingest

            result = ingest("AAPL")

        assert result["html_content"] == html_body
        assert mock_fetch.call_count == 1
        # The fixture submissions list 0000320193-23-000106 as latest 10-K.
        cache_file = patched_cache_dir / "AAPL_0000320193-23-000106.html"
        assert cache_file.is_file(), f"Expected cache file at {cache_file}"
        assert cache_file.read_text(encoding="utf-8") == html_body

    def test_second_call_reads_from_cache(self, patched_cache_dir):
        """On a cache hit, ingest() must NOT call fetch_10k_html."""
        companyfacts = _load_fixture("companyfacts_AAPL.json")
        submissions = _load_fixture("submissions_AAPL.json")

        # Pre-seed the cache.
        patched_cache_dir.mkdir(parents=True, exist_ok=True)
        cached_body = "<html><body>cached Apple 10-K</body></html>"
        cache_file = patched_cache_dir / "AAPL_0000320193-23-000106.html"
        cache_file.write_text(cached_body, encoding="utf-8")

        with patch("agents.agent1_ingestion.ticker_to_cik", return_value="0000320193"), \
             patch("agents.agent1_ingestion.fetch_companyfacts", return_value=companyfacts), \
             patch("agents.agent1_ingestion.fetch_submissions", return_value=submissions), \
             patch("agents.agent1_ingestion.fetch_10k_html") as mock_fetch, \
             patch("time.sleep"):
            from agents.agent1_ingestion import ingest

            result = ingest("AAPL")

        assert result["html_content"] == cached_body
        assert mock_fetch.call_count == 0, (
            "fetch_10k_html should not be called on a cache hit, but it was "
            f"called {mock_fetch.call_count} times."
        )

    def test_cache_dir_created_on_first_miss(self, patched_cache_dir):
        """ingest() must create ``data/cache/`` if it doesn't exist yet."""
        companyfacts = _load_fixture("companyfacts_AAPL.json")
        submissions = _load_fixture("submissions_AAPL.json")

        # Cache dir does not exist at start.
        assert not patched_cache_dir.exists()

        with patch("agents.agent1_ingestion.ticker_to_cik", return_value="0000320193"), \
             patch("agents.agent1_ingestion.fetch_companyfacts", return_value=companyfacts), \
             patch("agents.agent1_ingestion.fetch_submissions", return_value=submissions), \
             patch(
                 "agents.agent1_ingestion.fetch_10k_html",
                 return_value="<html>x</html>",
             ), \
             patch("time.sleep"):
            from agents.agent1_ingestion import ingest

            ingest("AAPL")

        assert patched_cache_dir.is_dir()


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
