"""LUCA L2 Parser agent.

Sprint 0 scope: segment the 10-K HTML into Items 1, 1A, 7 and 8 plus a list
of raw tables. In Sprint 0 ``html_content`` typically arrives empty from L1,
so the parser must accept that gracefully and return empty strings.
"""

from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

from agents._logging import get_logger

_LOGGER = get_logger(__name__)

# Whitespace runs that should collapse to a single space.
_WS_RE: re.Pattern[str] = re.compile(r"\s+")

# Item boundaries: each key maps to (start_anchor, [end_anchors]). The
# earliest matching end anchor closes the section. Patterns are
# case-insensitive.
_ITEM_BOUNDARIES: dict[str, tuple[str, list[str]]] = {
    "item_1": (r"item\s+1\b[\.\s]", [r"item\s+1a\b"]),
    "item_1a": (r"item\s+1a\b[\.\s]", [r"item\s+1b\b", r"item\s+2\b"]),
    "item_7": (r"item\s+7\b[\.\s]", [r"item\s+7a\b", r"item\s+8\b"]),
    "item_8": (r"item\s+8\b[\.\s]", [r"item\s+9\b"]),
}


def _html_to_text(html: str) -> str:
    """Extract plain text from HTML and collapse whitespace.

    Args:
        html: Raw HTML string.

    Returns:
        Plain text with single-space whitespace runs.
    """
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(separator=" ")
    return _WS_RE.sub(" ", text).strip()


def _extract_tables(html: str) -> list[str]:
    """Return inner text of each ``<table>`` in the HTML.

    Args:
        html: Raw HTML string.

    Returns:
        List of strings, one per table; rows separated by ``\\n``.
    """
    soup = BeautifulSoup(html, "lxml")
    tables: list[str] = []
    for table in soup.find_all("table"):
        rows: list[str] = []
        for row in table.find_all("tr"):
            cells = [_WS_RE.sub(" ", c.get_text(separator=" ")).strip()
                     for c in row.find_all(["td", "th"])]
            row_text = " | ".join(c for c in cells if c)
            if row_text:
                rows.append(row_text)
        if rows:
            tables.append("\n".join(rows))
    return tables


def _slice_item(text: str, start_pat: str, end_pats: list[str]) -> str:
    """Return the substring spanning a single 10-K item.

    Args:
        text: Full plain text of the filing.
        start_pat: Regex matching the item header (case-insensitive).
        end_pats: Regex anchors that close the section; earliest hit wins.

    Returns:
        Item text (header included), trimmed; ``""`` if not found.
    """
    start_match = re.search(start_pat, text, flags=re.IGNORECASE)
    if start_match is None:
        return ""
    start = start_match.start()
    end = len(text)
    for pat in end_pats:
        m = re.search(pat, text[start_match.end():], flags=re.IGNORECASE)
        if m is not None:
            candidate = start_match.end() + m.start()
            if candidate < end:
                end = candidate
    return text[start:end].strip()


def parse(ingest_output: dict[str, Any]) -> dict[str, Any]:
    """Segment a 10-K HTML payload into items and tables.

    Args:
        ingest_output: Output of L1 Ingestion with ``html_content`` and
            metadata keys ``company``, ``ticker``, ``filing_date``.

    Returns:
        Dict with keys ``company``, ``ticker``, ``filing_date``, ``item_1``,
        ``item_1a``, ``item_7``, ``item_8`` and ``raw_tables``. See
        ``ARCHITECTURE.md`` (L2) for the full contract.
    """
    ticker = ingest_output.get("ticker", "")
    _LOGGER.info("Parseando 10-K para %s", ticker or "<unknown>")

    base: dict[str, Any] = {
        "company": ingest_output.get("company", ""),
        "ticker": ticker,
        "filing_date": ingest_output.get("filing_date"),
        "item_1": "",
        "item_1a": "",
        "item_7": "",
        "item_8": "",
        "raw_tables": [],
    }

    html = ingest_output.get("html_content")
    if not html:
        _LOGGER.warning("L2 recibió html_content vacío, devolviendo items vacíos")
        return base

    text = _html_to_text(html)
    for key, (start, ends) in _ITEM_BOUNDARIES.items():
        base[key] = _slice_item(text, start, ends)
    base["raw_tables"] = _extract_tables(html)

    _LOGGER.info(
        "Parseado: item_1=%d caracteres, item_1a=%d caracteres, item_7=%d caracteres, item_8=%d caracteres",
        len(base["item_1"]), len(base["item_1a"]),
        len(base["item_7"]), len(base["item_8"]),
    )
    return base


__all__ = ["parse"]
