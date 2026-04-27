"""LUCA L1 Ingestion agent.

Scope (T1.7): download companyfacts + submissions for a ticker, resolve the
most recent 10-K, and fetch its primary HTML document. The HTML is cached
on disk under ``data/cache/`` keyed by ``<ticker>_<accession>.html`` so that
repeated runs (typical during development and evaluation) do not hammer
EDGAR.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from agents._config import PROJECT_ROOT
from agents._edgar_client import (
    fetch_10k_html,
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

#: Where downloaded 10-K HTML files are cached. Created on demand.
_CACHE_DIR: Path = PROJECT_ROOT / "data" / "cache"


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


def _cache_path_for(ticker: str, accession: str) -> Path:
    """Return the on-disk cache path for ``(ticker, accession)``.

    Args:
        ticker: Uppercased ticker symbol.
        accession: Accession number with dashes.

    Returns:
        Absolute path under ``data/cache/`` of the form
        ``<TICKER>_<accession>.html``.
    """
    safe_ticker = ticker.strip().upper() or "UNKNOWN"
    safe_accession = accession.strip()
    return _CACHE_DIR / f"{safe_ticker}_{safe_accession}.html"


def _load_or_download_10k_html(
    ticker: str, cik: str, accession: str
) -> str:
    """Return the 10-K HTML for ``accession``, using the on-disk cache.

    If ``data/cache/<ticker>_<accession>.html`` already exists, it is read
    and returned without contacting EDGAR. Otherwise, the document is
    downloaded via :func:`fetch_10k_html`, written to the cache atomically,
    and returned. Cache directory is created on demand.

    Args:
        ticker: Uppercased ticker symbol (used only as a cache key prefix).
        cik: 10-digit zero-padded CIK.
        accession: Accession number with dashes.

    Returns:
        The HTML body as a string. Empty string is never returned: if the
        download fails, the underlying exception is propagated.
    """
    cache_path = _cache_path_for(ticker, accession)
    if cache_path.is_file():
        _LOGGER.info("HTML 10-K en cache: %s", cache_path)
        return cache_path.read_text(encoding="utf-8")

    _LOGGER.info(
        "Descargando HTML 10-K (cache miss) ticker=%s accession=%s",
        ticker,
        accession,
    )
    html = fetch_10k_html(cik, accession)

    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    # Write atomically: dump to a sibling temp file, then rename. This avoids
    # leaving a half-written file in the cache if the process is interrupted.
    tmp_path = cache_path.with_suffix(cache_path.suffix + ".tmp")
    tmp_path.write_text(html, encoding="utf-8")
    tmp_path.replace(cache_path)
    _LOGGER.info("HTML 10-K cacheado en %s (%d caracteres)", cache_path, len(html))
    return html


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

    if accession_number:
        html_content = _load_or_download_10k_html(
            ticker_upper, cik, accession_number
        )
    else:
        _LOGGER.warning(
            "No se encontró 10-K para %s; html_content quedará vacío.",
            ticker_upper,
        )
        html_content = ""

    result: dict[str, Any] = {
        "company": company_name,
        "ticker": ticker_upper,
        "cik": cik,
        "filing_date": filing_date,
        "accession_number": accession_number,
        "html_content": html_content,
        "xbrl_data": companyfacts,
        "source_urls": source_urls,
    }

    _LOGGER.info(
        "Ingesta completada: %s, filing %s (%d chars HTML)",
        ticker_upper,
        filing_date or "n/a",
        len(html_content),
    )
    return result


__all__ = ["ingest"]
