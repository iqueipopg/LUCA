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
