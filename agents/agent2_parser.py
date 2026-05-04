"""LUCA L2 Parser agent.

Sprint 1 scope: parse a 10-K HTML payload (typically Inline XBRL — XML
with embedded XHTML and ``ix:*`` tags) into Items 1, 1A, 7 and 8 plus a
flat list of raw tables. Two practical realities of real EDGAR filings
shape the heuristics here:

1. The cosmetic ``XMLParsedAsHTMLWarning`` raised by ``BeautifulSoup``
   on iXBRL documents is silenced module-wide. ``lxml`` in HTML mode
   parses these documents correctly; the warning is a style hint.

2. Each item header appears multiple times in a 10-K: once in the
   table of contents (TOC), once at the head of the section's body,
   and possibly more times as cross-references (``"see Item 8 for…"``).
   The naive "first match wins" heuristic from Sprint 0 always picks
   the TOC entry, which yields ~20-character slices — see error log
   T1.7b. We therefore (a) detect and skip past the TOC, and (b) use
   title-aware regexes that demand the canonical SEC section title
   immediately after the item number, so body cross-references do not
   accidentally trigger.

Sprint 0's empty-html behaviour is preserved: an empty ``html_content``
returns empty strings for each item and an empty ``raw_tables`` list.
"""

from __future__ import annotations

import re
import warnings
from typing import Any

from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

from agents._logging import get_logger

# iXBRL filings start with an ``<?xml ... ?>`` preamble; ``lxml`` in
# HTML mode parses them fine, so the warning is purely cosmetic.
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

_LOGGER = get_logger(__name__)

# Whitespace runs that should collapse to a single space.
_WS_RE: re.Pattern[str] = re.compile(r"\s+")

# Generic item-header detector. Matches ``Item 1``, ``Item 1A``,
# ``Item 7``, etc. (case-insensitive). Used by :func:`_locate_toc_end`
# to find dense clusters of references.
_ITEM_HEADER_RE: re.Pattern[str] = re.compile(
    r"\bitem\s+\d+[a-z]?\b", flags=re.IGNORECASE,
)

# A real 10-K table of contents is rendered as a <table> whose cells
# enumerate every item from 1 through 15. We identify it as the first
# <table> whose plain text contains at least :data:`_TOC_MIN_ENTRIES`
# item-N references (e.g., ``"Item 1"``, ``"Item 1A"``). Cover-page
# tables that precede the TOC (registrant address, trading symbols,
# filer status) never reach that count. A pure plain-text heuristic
# was tried first but the cross-references that 10-Ks place in
# Item 1's "Forward-Looking Statements" paragraph (``"see Item 1A …
# refer to Item 7 … and Item 8"``) are tight enough to be
# indistinguishable from a TOC by gap alone — see error log T1.7b.
_TOC_MIN_ENTRIES: int = 5

# Title-aware item boundaries. Each value is ``(start_anchor,
# [end_anchors])``: the earliest matching end anchor closes the
# section. Patterns are case-insensitive and tolerate non-breaking
# spaces (already normalised to regular spaces by :func:`_html_to_text`)
# plus straight or curly apostrophes.
_ITEM_BOUNDARIES: dict[str, tuple[str, list[str]]] = {
    "item_1": (
        r"item\s+1[\.\s]+business\b",
        [r"item\s+1a[\.\s]+risk\s+factors"],
    ),
    "item_1a": (
        r"item\s+1a[\.\s]+risk\s+factors",
        [
            r"item\s+1b[\.\s]+unresolved",
            r"item\s+2[\.\s]+properties",
        ],
    ),
    "item_7": (
        r"item\s+7[\.\s]+management['’]?s?\s+discussion",
        [
            r"item\s+7a[\.\s]+quantitative",
            r"item\s+8[\.\s]+financial",
        ],
    ),
    "item_8": (
        r"item\s+8[\.\s]+financial\s+statements",
        [r"item\s+9[\.\s]+changes"],
    ),
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


def _locate_toc_end(html: str, plain_text: str) -> int:
    """Return the offset right after the table of contents in ``plain_text``.

    Walks ``<table>`` elements in document order and picks the first
    one whose text contains at least :data:`_TOC_MIN_ENTRIES` item-N
    references. The function then locates that table's text inside
    ``plain_text`` (anchored on its first 80 characters, which start
    with ``"Item 1. Business"`` in canonical 10-K layouts and are
    therefore unique) and returns the offset right after the table.

    Args:
        html: Raw HTML of the filing.
        plain_text: Output of :func:`_html_to_text` for the same HTML.
            Must be passed in (rather than recomputed) so that the
            table-text and the plain-text use the same whitespace
            normalisation.

    Returns:
        Offset right after the TOC table's last character in
        ``plain_text``. ``0`` when no TOC-shaped table is found
        (legacy first-match slicing then applies).
    """
    soup = BeautifulSoup(html, "lxml")
    for table in soup.find_all("table"):
        table_text_raw = table.get_text(separator=" ")
        if len(_ITEM_HEADER_RE.findall(table_text_raw)) < _TOC_MIN_ENTRIES:
            continue
        normalised = _WS_RE.sub(" ", table_text_raw).strip()
        if not normalised:
            return 0
        anchor = normalised[:80]
        idx = plain_text.find(anchor)
        if idx >= 0:
            return idx + len(normalised)
        # Fall through if the anchor is somehow not in plain_text;
        # better to leave toc_end=0 than to skip the wrong amount.
        return 0
    return 0


def _slice_item(text: str, start_pat: str, end_pats: list[str]) -> str:
    """Return the substring spanning a single 10-K item.

    Args:
        text: Plain text of the filing (typically ``text[toc_end:]``).
        start_pat: Regex matching the item header (case-insensitive).
        end_pats: Regex anchors that close the section; earliest hit
            wins.

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
        Dict with keys ``company``, ``ticker``, ``filing_date``,
        ``item_1``, ``item_1a``, ``item_7``, ``item_8`` and
        ``raw_tables``. See ``ARCHITECTURE.md`` (L2) for the full
        contract.
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
    toc_end = _locate_toc_end(html, text)
    if toc_end > 0:
        _LOGGER.info(
            "TOC detectado en %s: salta los primeros %d caracteres",
            ticker or "<unknown>", toc_end,
        )
    body_text = text[toc_end:]

    for key, (start, ends) in _ITEM_BOUNDARIES.items():
        base[key] = _slice_item(body_text, start, ends)
    base["raw_tables"] = _extract_tables(html)

    _LOGGER.info(
        "Parseado: item_1=%d caracteres, item_1a=%d caracteres, item_7=%d caracteres, item_8=%d caracteres",
        len(base["item_1"]), len(base["item_1a"]),
        len(base["item_7"]), len(base["item_8"]),
    )
    return base


__all__ = ["parse"]
