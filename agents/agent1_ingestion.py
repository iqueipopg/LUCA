"""LUCA L1 Ingestion agent.

Sprint 0 scope: download companyfacts + submissions for a ticker. The HTML
content of the 10-K is left as a placeholder and will land in Sprint 1.
"""

from __future__ import annotations

from typing import Any

from agents._edgar_client import (
    fetch_companyfacts,
    fetch_submissions,
    latest_10k_accession,
    ticker_to_cik,
)
from agents._logging import get_logger

_LOGGER = get_logger(__name__)

_COMPANYFACTS_URL_TMPL: str = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
_SUBMISSIONS_URL_TMPL: str = "https://data.sec.gov/submissions/CIK{cik}.json"
_FILING_INDEX_URL_TMPL: str = (
    "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_nodash}/{accession}-index.htm"
)


def _filing_date_for(submissions: dict[str, Any], accession: str | None) -> str | None:
    """Return the ``filingDate`` paired with ``accession``, or ``None``.

    Args:
        submissions: Decoded submissions JSON returned by EDGAR.
        accession: Accession number to look up.

    Returns:
        The ISO ``YYYY-MM-DD`` filing date, or ``None`` if not found.
    """
    if accession is None or not isinstance(submissions, dict):
        return None
    recent = submissions.get("filings", {}).get("recent", {})
    accessions = recent.get("accessionNumber") or []
    dates = recent.get("filingDate") or []
    if not isinstance(accessions, list) or not isinstance(dates, list):
        return None
    for idx, acc in enumerate(accessions):
        if acc == accession and idx < len(dates) and isinstance(dates[idx], str):
            return dates[idx]
    return None


def _build_filing_index_url(cik_padded: str, accession: str | None) -> str | None:
    """Return the EDGAR filing-index URL for ``accession``, or ``None``.

    Args:
        cik_padded: 10-digit zero-padded CIK.
        accession: Accession number with dashes (e.g. ``"0000320193-23-000106"``).

    Returns:
        Absolute URL string, or ``None`` if ``accession`` is ``None``.
    """
    if not accession:
        return None
    return _FILING_INDEX_URL_TMPL.format(
        cik_int=str(int(cik_padded)),
        accession_nodash=accession.replace("-", ""),
        accession=accession,
    )


def ingest(ticker: str) -> dict[str, Any]:
    """Run L1 Ingestion for a single ticker.

    Args:
        ticker: Stock ticker symbol (case-insensitive).

    Returns:
        Dict with keys ``company``, ``ticker``, ``cik``, ``filing_date``,
        ``accession_number``, ``html_content``, ``xbrl_data`` and
        ``source_urls``. See ``ARCHITECTURE.md`` (L1) for the full contract.

    Raises:
        ValueError: If ``ticker`` cannot be resolved to a CIK.
    """
    ticker_upper = ticker.strip().upper() if isinstance(ticker, str) else ""
    _LOGGER.info("Iniciando ingesta para ticker %s", ticker_upper or ticker)

    cik = ticker_to_cik(ticker)
    companyfacts = fetch_companyfacts(cik)
    submissions = fetch_submissions(cik)

    accession_number = latest_10k_accession(submissions)
    filing_date = _filing_date_for(submissions, accession_number)

    company_name = companyfacts.get("entityName")
    if not isinstance(company_name, str) or not company_name:
        company_name = submissions.get("name", "") if isinstance(submissions, dict) else ""

    source_urls: dict[str, str | None] = {
        "companyfacts": _COMPANYFACTS_URL_TMPL.format(cik=cik),
        "submissions": _SUBMISSIONS_URL_TMPL.format(cik=cik),
        "filing_index": _build_filing_index_url(cik, accession_number),
    }

    result: dict[str, Any] = {
        "company": company_name,
        "ticker": ticker_upper,
        "cik": cik,
        "filing_date": filing_date,
        "accession_number": accession_number,
        "html_content": "",
        "xbrl_data": companyfacts,
        "source_urls": source_urls,
    }

    _LOGGER.info("Ingesta completada: %s, filing %s", ticker_upper, filing_date or "n/a")
    return result


__all__ = ["ingest"]
