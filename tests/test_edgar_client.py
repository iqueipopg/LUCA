"""Unit tests for agents._edgar_client.

All HTTP calls are mocked. The _TICKER_CACHE process-global is reset before
each test to prevent state leakage between tests.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def reset_edgar_state():
    """Reset process-level caches in _edgar_client and _config before each test."""
    import agents._config as cfg_mod
    import agents._edgar_client as edgar_mod

    cfg_mod._CACHE = None
    edgar_mod._TICKER_CACHE = None
    yield
    cfg_mod._CACHE = None
    edgar_mod._TICKER_CACHE = None


def _make_response(payload: dict, status: int = 200) -> MagicMock:
    """Build a mock requests.Response with the given JSON payload."""
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = payload
    resp.raise_for_status = MagicMock()
    return resp


def _load_fixture(name: str) -> dict:
    with (_FIXTURES_DIR / name).open("r", encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# ticker_to_cik
# ---------------------------------------------------------------------------


class TestTickerToCik:
    def test_ticker_to_cik_pads_to_10_digits(self):
        """ticker_to_cik('AAPL') must return '0000320193' (10-digit padded CIK)."""
        tickers_payload = _load_fixture("company_tickers.json")

        with patch("requests.get", return_value=_make_response(tickers_payload)), \
             patch("time.sleep"):
            from agents._edgar_client import ticker_to_cik

            result = ticker_to_cik("AAPL")

        assert result == "0000320193"
        assert len(result) == 10
        assert result.isdigit()

    def test_ticker_to_cik_unknown_raises(self):
        """ticker_to_cik with an unknown ticker must raise ValueError."""
        tickers_payload = _load_fixture("company_tickers.json")

        with patch("requests.get", return_value=_make_response(tickers_payload)), \
             patch("time.sleep"):
            from agents._edgar_client import ticker_to_cik

            with pytest.raises(ValueError, match="UNKNOWNTICKER"):
                ticker_to_cik("UNKNOWNTICKER")


# ---------------------------------------------------------------------------
# fetch_companyfacts
# ---------------------------------------------------------------------------


class TestFetchCompanyfacts:
    def test_fetch_companyfacts_normalizes_cik(self):
        """fetch_companyfacts must accept both '320193' and '0000320193'."""
        companyfacts_payload = _load_fixture("companyfacts_AAPL.json")

        with patch("requests.get", return_value=_make_response(companyfacts_payload)), \
             patch("time.sleep"):
            from agents._edgar_client import fetch_companyfacts

            result_short = fetch_companyfacts("320193")
            result_padded = fetch_companyfacts("0000320193")

        assert result_short["entityName"] == "Apple Inc."
        assert result_padded["entityName"] == "Apple Inc."


# ---------------------------------------------------------------------------
# fetch_submissions — User-Agent header check
# ---------------------------------------------------------------------------


class TestFetchSubmissionsHeaders:
    def test_fetch_submissions_uses_user_agent(self, monkeypatch):
        """fetch_submissions must pass User-Agent header to requests.get."""
        submissions_payload = _load_fixture("submissions_AAPL.json")

        monkeypatch.setenv("SEC_USER_AGENT", "Test User test@example.com")

        captured_headers: dict[str, Any] = {}

        def _mock_get(url, headers=None, **kwargs):
            if headers:
                captured_headers.update(headers)
            return _make_response(submissions_payload)

        with patch("requests.get", side_effect=_mock_get), patch("time.sleep"):
            from agents._edgar_client import fetch_submissions

            fetch_submissions("0000320193")

        assert "User-Agent" in captured_headers, (
            "User-Agent header was not sent to EDGAR"
        )
        assert "Test User" in captured_headers["User-Agent"]


# ---------------------------------------------------------------------------
# 429 retry
# ---------------------------------------------------------------------------


class TestRateLimitRetry:
    def test_429_triggers_retry_with_delay(self, monkeypatch):
        """A 429 response must trigger a sleep+retry; second attempt should succeed."""
        submissions_payload = _load_fixture("submissions_AAPL.json")

        monkeypatch.setenv("SEC_USER_AGENT", "Test User test@example.com")

        call_count = 0

        def _mock_get(url, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                resp = MagicMock()
                resp.status_code = 429
                # raise_for_status only when we exhaust retries; on first 429 the
                # code checks status_code == 429 and sleeps.
                resp.raise_for_status = MagicMock(
                    side_effect=Exception("429 Too Many Requests")
                )
                return resp
            return _make_response(submissions_payload)

        sleep_calls: list[float] = []

        def _mock_sleep(secs: float):
            sleep_calls.append(secs)

        with patch("requests.get", side_effect=_mock_get), \
             patch("time.sleep", side_effect=_mock_sleep):
            from agents._edgar_client import fetch_submissions

            result = fetch_submissions("0000320193")

        assert call_count == 2, f"Expected 2 GET calls (1 retry), got {call_count}"
        # At least one sleep should have been called for the 429 back-off.
        assert len(sleep_calls) >= 1, "time.sleep was never called despite 429"
        assert result["name"] == "Apple Inc."


# ---------------------------------------------------------------------------
# latest_10k_accession
# ---------------------------------------------------------------------------


class TestLatest10kAccession:
    def test_latest_10k_accession_picks_most_recent(self, submissions_aapl):
        """latest_10k_accession must return the accession of the newest 10-K."""
        from agents._edgar_client import latest_10k_accession

        result = latest_10k_accession(submissions_aapl)

        # Our fixture has 10-Ks filed on 2023-11-03 and 2022-10-28.
        # The most recent is 0000320193-23-000106.
        assert result == "0000320193-23-000106", (
            f"Expected the 2023 10-K accession, got {result!r}"
        )

    def test_latest_10k_accession_no_10k_returns_none(self):
        """latest_10k_accession must return None when there are no 10-K filings."""
        from agents._edgar_client import latest_10k_accession

        submissions = {
            "filings": {
                "recent": {
                    "form": ["10-Q", "8-K", "10-Q"],
                    "accessionNumber": ["acc-1", "acc-2", "acc-3"],
                    "filingDate": ["2023-08-04", "2023-09-01", "2023-05-05"],
                }
            }
        }
        result = latest_10k_accession(submissions)
        assert result is None


# ---------------------------------------------------------------------------
# Missing SEC_USER_AGENT
# ---------------------------------------------------------------------------


class TestFetch10kHtml:
    """Tests for ``fetch_10k_html`` (T1.7).

    The function makes two HTTP calls: one to ``index.json`` to discover the
    primary document, then one to download that document. We mock both with
    a URL-routing side effect.
    """

    @staticmethod
    def _make_text_response(text: str, status: int = 200) -> MagicMock:
        resp = MagicMock()
        resp.status_code = status
        resp.text = text
        # ``.json()`` should never be called on the text response, but make
        # it explode loudly if a future bug does call it.
        resp.json.side_effect = AssertionError(
            "fetch_10k_html should not call .json() on the document response"
        )
        resp.raise_for_status = MagicMock()
        return resp

    @staticmethod
    def _index_payload(items: list[dict[str, Any]]) -> dict[str, Any]:
        """Wrap ``items`` in the EDGAR index.json envelope."""
        return {
            "directory": {
                "name": "/Archives/edgar/data/320193/000032019323000106",
                "item": items,
            }
        }

    def test_picks_primary_document_by_type(self, monkeypatch):
        """fetch_10k_html prefers the .htm whose ``type`` field equals "10-K"."""
        monkeypatch.setenv("SEC_USER_AGENT", "Test User test@example.com")

        items = [
            {"name": "filing-index.htm", "type": "", "size": "5000"},
            {"name": "exhibit99.htm", "type": "EX-99.1", "size": "200000"},
            {"name": "aapl-20230930.htm", "type": "10-K", "size": "1500000"},
            {"name": "R1.htm", "type": "", "size": "8000"},
        ]
        index_payload = self._index_payload(items)
        html_body = "<html><body>10-K content of Apple</body></html>"

        captured_urls: list[str] = []

        def _mock_get(url, **kwargs):
            captured_urls.append(url)
            if url.endswith("index.json"):
                return _make_response(index_payload)
            if url.endswith("aapl-20230930.htm"):
                return self._make_text_response(html_body)
            return _make_response({"error": "not found"}, status=404)

        with patch("requests.get", side_effect=_mock_get), patch("time.sleep"):
            from agents._edgar_client import fetch_10k_html

            result = fetch_10k_html("0000320193", "0000320193-23-000106")

        assert result == html_body
        # Two GETs: index.json then primary document.
        assert len(captured_urls) == 2
        assert captured_urls[0].endswith(
            "/Archives/edgar/data/320193/000032019323000106/index.json"
        )
        assert captured_urls[1].endswith(
            "/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm"
        )

    def test_fallback_to_largest_htm(self, monkeypatch):
        """If no item has ``type=='10-K'``, pick the largest non-index .htm."""
        monkeypatch.setenv("SEC_USER_AGENT", "Test User test@example.com")

        items = [
            # No item has the 10-K type — exercise the size fallback.
            {"name": "filing-index.htm", "type": "", "size": "5000"},
            {"name": "small-exhibit.htm", "type": "", "size": "10000"},
            {"name": "primary-doc.htm", "type": "", "size": "1200000"},
            {"name": "R5.htm", "type": "", "size": "9999999"},  # excluded
        ]
        index_payload = self._index_payload(items)
        html_body = "<html><body>fallback primary</body></html>"

        def _mock_get(url, **kwargs):
            if url.endswith("index.json"):
                return _make_response(index_payload)
            if url.endswith("primary-doc.htm"):
                return self._make_text_response(html_body)
            return _make_response({"error": "not found"}, status=404)

        with patch("requests.get", side_effect=_mock_get), patch("time.sleep"):
            from agents._edgar_client import fetch_10k_html

            result = fetch_10k_html("320193", "0000320193-23-000106")

        assert result == html_body

    def test_no_primary_document_raises(self, monkeypatch):
        """If the index has no usable .htm at all, fetch_10k_html raises."""
        monkeypatch.setenv("SEC_USER_AGENT", "Test User test@example.com")

        # Only PDFs and XML — no HTML primary document.
        items = [
            {"name": "filing.pdf", "type": "", "size": "100000"},
            {"name": "data.xml", "type": "", "size": "50000"},
        ]
        index_payload = self._index_payload(items)

        def _mock_get(url, **kwargs):
            if url.endswith("index.json"):
                return _make_response(index_payload)
            return _make_response({"error": "not found"}, status=404)

        with patch("requests.get", side_effect=_mock_get), patch("time.sleep"):
            from agents._edgar_client import fetch_10k_html

            with pytest.raises(RuntimeError, match="primary HTML document"):
                fetch_10k_html("0000320193", "0000320193-23-000106")

    def test_rate_limit_sleep_is_respected(self, monkeypatch):
        """fetch_10k_html sleeps the configured rate-limit before each GET."""
        monkeypatch.setenv("SEC_USER_AGENT", "Test User test@example.com")

        items = [{"name": "primary.htm", "type": "10-K", "size": "1000"}]
        index_payload = self._index_payload(items)
        html_body = "<html>x</html>"

        def _mock_get(url, **kwargs):
            if url.endswith("index.json"):
                return _make_response(index_payload)
            return self._make_text_response(html_body)

        sleep_calls: list[float] = []

        def _mock_sleep(secs: float):
            sleep_calls.append(secs)

        with patch("requests.get", side_effect=_mock_get), \
             patch("time.sleep", side_effect=_mock_sleep):
            from agents._edgar_client import fetch_10k_html

            fetch_10k_html("0000320193", "0000320193-23-000106")

        # At least two 0.15s sleeps (one per GET). Other test fixtures may
        # introduce extra sleeps but the rate-limit value should appear.
        rate_limit_sleeps = [s for s in sleep_calls if abs(s - 0.15) < 1e-9]
        assert len(rate_limit_sleeps) >= 2, (
            f"Expected at least two 0.15s sleeps (one per GET), got {sleep_calls!r}"
        )

    def test_empty_accession_raises(self):
        """fetch_10k_html('0000320193', '') must reject empty accession."""
        from agents._edgar_client import fetch_10k_html

        with pytest.raises(ValueError, match="accession"):
            fetch_10k_html("0000320193", "")


class TestMissingUserAgent:
    def test_missing_user_agent_raises(self, monkeypatch):
        """fetch_submissions must raise RuntimeError when SEC_USER_AGENT is unset."""
        # Remove the env var entirely
        monkeypatch.delenv("SEC_USER_AGENT", raising=False)
        # Also ensure it's not in the config cache
        import agents._config as cfg_mod
        cfg_mod._CACHE = None

        # Patch load_config to return empty env so get_env also finds nothing
        fake_config = {
            "global": {"llm": {}, "sources": {"sec_edgar": {"rate_limit_s": 0.15}}},
            "agents": {
                "L1_ingestion": {"timeout_s": 30, "max_retries": 1}
            },
            "env": {},
        }
        with patch("agents._edgar_client.load_config", return_value=fake_config), \
             patch("agents._edgar_client.get_agent_config", return_value={"timeout_s": 30, "max_retries": 1}), \
             patch("agents._edgar_client.get_env", return_value=None), \
             patch("time.sleep"):
            from agents._edgar_client import fetch_submissions

            with pytest.raises(RuntimeError, match="SEC_USER_AGENT"):
                fetch_submissions("0000320193")
