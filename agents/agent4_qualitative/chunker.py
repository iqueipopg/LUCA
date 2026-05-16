"""Bold-leading Item 1A chunker for iXBRL 10-Ks (T2.2).

Implements the contract documented in
``docs/architecture/T2_2_chunker_spec.md``. The chunker is purely
structural: it slices the Item 1A range of an iXBRL 10-K into chunks
consumable by L4 and emits per-chunk metadata; it does **not** extract
risks or any other qualitative content.

Coordinate system
-----------------
``char_start`` / ``char_end`` are offsets into the *plain text* of the
10-K, where the plain text is the output of
``BeautifulSoup(html, "lxml").get_text(separator=" ")`` followed by a
whitespace-collapse pass. This matches ``agents/agent2_parser.py`` and
keeps offsets stable across re-parses. The same convention applies to
the ``item1a_start`` and ``item1a_end`` inputs.

Detection
---------
A sub-header is a "leaf" ``<div>`` (a ``<div>`` with no descendant
``<div>``) whose first non-whitespace, non-bullet (``•``) text leaf has
an ancestor ``<span>`` with ``font-weight`` ≥ 600 (numeric ``600``..``900``,
or the literals ``bold`` / ``bolder``). The anchor text is the inner
text of that bold span.

Cotas y anti-FP
---------------
Body anchors must pass ``len(words) >= 2`` and ``len(text) <= 300``
chars. Three anti-FP filters then reject (a) numeric / page / part
patterns, (b) anchors that recur ≥ 3 times in the full document, and
(c) 1-word bolds (already excluded by the ≥ 2 word lower bound but
kept explicit). Summary header detection uses a different ≤ 2 word
rule because category-labels like "Summary" are short by design.

Length fallback
---------------
A chunk whose ``text`` exceeds 16 000 chars (4 000 tokens) is split
at div boundaries closest to multiples of 12 000 chars with a 500-char
overlap between consecutive sub-chunks. Sub-chunks are ``anchor_level
= 3`` and have ``anchor_text = None``. A hard cut to 16 000 chars is
applied if any sub-chunk still exceeds the budget after div
segmentation; a warning is appended to the ``Item1AChunkSet`` when
this hard cut fires.
"""

from __future__ import annotations

import re
import warnings

from bs4 import BeautifulSoup, NavigableString, Tag, XMLParsedAsHTMLWarning

from agents._logging import get_logger
from agents.agent4_qualitative.models import Chunk, Item1AChunkSet

# iXBRL files emit a cosmetic warning when parsed in HTML mode.
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

_LOGGER = get_logger(__name__)

# ---------------------------------------------------------------------------
# Spec-driven tunables. Names are documented in T2_2_chunker_spec.md.
# ---------------------------------------------------------------------------

_MIN_ANCHOR_WORDS: int = 2
_MAX_ANCHOR_CHARS: int = 300
_ANCHOR_LEVEL_1_MAX_WORDS: int = 4

_SUMMARY_SEARCH_RANGE_CHARS: int = 5000
_SUMMARY_HEADER_MAX_WORDS: int = 2
_SUMMARY_MIN_BULLETS: int = 3
# Defensive upper bound when no level-2 anchor follows the short header.
_SUMMARY_DEFENSIVE_BOUND_CHARS: int = 10_000
_BULLET_CHAR: str = "•"  # '•'

_MAX_CHUNK_CHARS: int = 16_000   # 4 000 tokens
_SUBCHUNK_TARGET_CHARS: int = 12_000
_SUBCHUNK_OVERLAP_CHARS: int = 500
_HARD_CUT_CHARS: int = 16_000

_REPETITION_MAX: int = 3

_ANTI_FP_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"^\d+$"),
    re.compile(r"^Page\s+\d+$", re.IGNORECASE),
    re.compile(r"^Parts?\s+[IVX]+(\s+and\s+[IVX]+)?$", re.IGNORECASE),
]

_WS_RE: re.Pattern[str] = re.compile(r"\s+")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _html_to_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(separator=" ")
    return _WS_RE.sub(" ", text).strip()


def _parse_font_weight(style: str | None) -> int | None:
    """Extract ``font-weight`` from an inline ``style`` attribute.

    Returns ``700`` for the literals ``bold`` / ``bolder``, an int for
    numeric weights, or ``None`` if no ``font-weight`` declaration is
    present or it is malformed.
    """
    if not style:
        return None
    for prop in style.split(";"):
        if ":" not in prop:
            continue
        key, value = prop.split(":", 1)
        if key.strip().lower() != "font-weight":
            continue
        v = value.strip().lower()
        if v in ("bold", "bolder"):
            return 700
        try:
            return int(v)
        except ValueError:
            return None
    return None


def _is_bold_span(node: object) -> bool:
    if not isinstance(node, Tag) or node.name != "span":
        return False
    weight = _parse_font_weight(node.get("style"))
    return weight is not None and weight >= 600


def _normalize_text(text: str) -> str:
    return _WS_RE.sub(" ", text).strip()


def _first_meaningful_text(div: Tag) -> NavigableString | None:
    """First descendant text node that is neither whitespace nor a sole bullet."""
    for descendant in div.descendants:
        if not isinstance(descendant, NavigableString):
            continue
        stripped = str(descendant).strip()
        if not stripped or stripped == _BULLET_CHAR:
            continue
        return descendant
    return None


def _find_anchor_in_div(div: Tag) -> str | None:
    """Return the anchor text if ``div`` is bold-leading, else ``None``.

    The check operates on the first non-whitespace, non-bullet text
    leaf of ``div``: if that leaf has a ``<span>`` ancestor (within
    ``div``) whose ``font-weight`` is ≥ 600, the div is bold-leading
    and the anchor text is the inner text of that bold span.
    """
    leaf = _first_meaningful_text(div)
    if leaf is None:
        return None
    bold_ancestor: Tag | None = None
    for ancestor in leaf.parents:
        if ancestor is div:
            break
        if _is_bold_span(ancestor):
            bold_ancestor = ancestor
            break
    if bold_ancestor is None:
        return None
    anchor_text = _normalize_text(bold_ancestor.get_text(separator=" "))
    return anchor_text or None


def _word_count(text: str) -> int:
    return len(text.split())


def _passes_cotas(anchor_text: str) -> bool:
    return _MIN_ANCHOR_WORDS <= _word_count(anchor_text) and len(anchor_text) <= _MAX_ANCHOR_CHARS


def _matches_anti_fp_pattern(anchor_text: str) -> bool:
    return any(p.match(anchor_text) for p in _ANTI_FP_PATTERNS)


def _anchor_level_for(anchor_text: str) -> int:
    return 1 if _word_count(anchor_text) <= _ANCHOR_LEVEL_1_MAX_WORDS else 2


def _div_first_text_fragment(div: Tag) -> str | None:
    """Short stable fragment we can search for in plain_text to locate the div."""
    leaf = _first_meaningful_text(div)
    if leaf is None:
        return None
    fragment = _normalize_text(str(leaf))
    return fragment[:80] if fragment else None


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def _walk_leaf_divs(
    html: str,
    plain_text: str,
) -> tuple[list[int], list[tuple[int, str]]]:
    """Walk leaf ``<div>`` elements in document order.

    Returns two parallel structures keyed on positions in ``plain_text``:

    * ``all_div_positions`` — start offset of every leaf-div we managed
      to locate in ``plain_text`` (used by the length fallback to cut
      at div boundaries).
    * ``raw_anchors`` — ``(pos, anchor_text)`` for each leaf-div whose
      first meaningful text is bold-leading. Cotas and anti-FP filters
      are **not** applied here; callers handle them.

    A monotonic ``cursor`` enforces document order when searching
    ``plain_text``. If the first ``find`` from ``cursor`` misses we
    retry from offset 0 to absorb whitespace-normalisation drift, then
    skip the div if still not found.
    """
    soup = BeautifulSoup(html, "lxml")
    all_div_positions: list[int] = []
    raw_anchors: list[tuple[int, str]] = []
    cursor = 0
    for div in soup.find_all("div"):
        if div.find("div") is not None:
            # Not a leaf-div; the inner div(s) will be visited separately.
            continue
        fragment = _div_first_text_fragment(div)
        if not fragment:
            continue
        pos = plain_text.find(fragment, cursor)
        if pos < 0:
            pos = plain_text.find(fragment)
            if pos < 0:
                continue
        all_div_positions.append(pos)
        if pos >= cursor:
            cursor = pos + len(fragment)
        anchor_text = _find_anchor_in_div(div)
        if anchor_text:
            raw_anchors.append((pos, anchor_text))
    return all_div_positions, raw_anchors


def _detect_summary(
    plain_text: str,
    item1a_start: int,
    item1a_end: int,
    raw_anchors: list[tuple[int, str]],
) -> tuple[int | None, int | None, str | None]:
    """Return ``(summary_start, summary_end)`` or ``(None, None)``.

    A Summary is detected when a short (≤ 2 words) bold-leading anchor
    sits within ``[item1a_start, item1a_start + 5000]`` and the range
    from that short header to the next level-2 anchor (> 4 words)
    contains ≥ 3 ``•`` bullets. If no level-2 anchor follows, the
    defensive bound ``item1a_start + 10000`` is used.

    ``summary_end`` is the position of the first level-2 bold-leading
    anchor that appears after the last ``•`` in
    ``plain_text[summary_start:item1a_end]``.

    The bullet window was widened from the prior ~500 char fixed
    window after JPM (bullet length 300-1000 chars) revealed the old
    rule under-counted dense filings. See
    ``docs/architecture/T2_2_chunker_spec.md`` § Detección note.
    """
    window_end = min(item1a_end, item1a_start + _SUMMARY_SEARCH_RANGE_CHARS)
    for pos, anchor_text in raw_anchors:
        if pos < item1a_start:
            continue
        if pos >= window_end:
            break
        if _word_count(anchor_text) > _SUMMARY_HEADER_MAX_WORDS:
            continue
        short_header_end = pos + len(anchor_text)
        next_l2_pos: int | None = None
        for q_pos, q_text in raw_anchors:
            if q_pos <= pos:
                continue
            if q_pos >= item1a_end:
                break
            if _word_count(q_text) > _ANCHOR_LEVEL_1_MAX_WORDS:
                next_l2_pos = q_pos
                break
        bullet_range_end = (
            next_l2_pos
            if next_l2_pos is not None
            else min(item1a_end, item1a_start + _SUMMARY_DEFENSIVE_BOUND_CHARS)
        )
        bullets = plain_text[short_header_end:bullet_range_end].count(_BULLET_CHAR)
        if bullets >= _SUMMARY_MIN_BULLETS:
            # summary_end is the end of the bullet range. Per spec, the first
            # level-2 anchor after the last bullet IS next_l2_pos when present
            # (no level-2 anchors live inside the candidate range by
            # construction), so reuse it directly.
            return pos, bullet_range_end, anchor_text
    return None, None, None


def _extract_summary_chunks(
    plain_text: str,
    summary_start: int,
    summary_end: int,
    short_header_text: str,
) -> list[Chunk]:
    """Build :class:`Chunk` objects covering ``[summary_start, summary_end]``.

    The first chunk covers the summary header + intro line (everything
    before the first ``•``); subsequent chunks are one per bullet. All
    chunks have ``in_summary=True`` and ``anchor_level=1``. ``chunk_id``
    is left as the placeholder ``"__pending__"`` — final IDs are
    assigned by :func:`chunk_item1a` once gaps are filled.
    """
    summary_text = plain_text[summary_start:summary_end]
    bullet_positions: list[int] = []
    cursor = 0
    while True:
        p = summary_text.find(_BULLET_CHAR, cursor)
        if p < 0:
            break
        bullet_positions.append(p)
        cursor = p + 1
    if not bullet_positions:
        return []

    chunks: list[Chunk] = []

    intro_end_local = bullet_positions[0]
    if intro_end_local > 0:
        intro_text = summary_text[:intro_end_local].strip()
        if intro_text:
            chunks.append(
                Chunk(
                    chunk_id="__pending__",
                    text=summary_text[:intro_end_local],
                    char_start=summary_start,
                    char_end=summary_start + intro_end_local,
                    anchor_text=short_header_text,
                    anchor_level=1,
                    in_summary=True,
                    token_estimate=intro_end_local // 4,
                )
            )

    for i, local_start in enumerate(bullet_positions):
        local_end = (
            bullet_positions[i + 1]
            if i + 1 < len(bullet_positions)
            else (summary_end - summary_start)
        )
        abs_start = summary_start + local_start
        abs_end = summary_start + local_end
        text = plain_text[abs_start:abs_end]
        if not text.strip():
            continue
        stripped = text.lstrip(_BULLET_CHAR).strip()
        label = _summary_bullet_label(stripped)
        chunks.append(
            Chunk(
                chunk_id="__pending__",
                text=text,
                char_start=abs_start,
                char_end=abs_end,
                anchor_text=label,
                anchor_level=1,
                in_summary=True,
                token_estimate=len(text) // 4,
            )
        )
    return chunks


def _summary_bullet_label(stripped_bullet: str) -> str:
    """Extract a category-label from a bullet's stripped body text."""
    m = re.match(r"^([A-Z][A-Za-z/&\- ]{0,60}?)\s+risks?\b", stripped_bullet, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    head = stripped_bullet.split(",", 1)[0]
    head = head.split(".", 1)[0]
    return head.strip()[:60] or "bullet"


def _build_chunk_id(ticker: str, fiscal_year: int, idx: int) -> str:
    return f"{ticker}_{fiscal_year}_item1a_{idx:03d}"


def _filter_body_anchors(
    raw_anchors: list[tuple[int, str]],
    plain_text: str,
    body_start: int,
    item1a_end: int,
) -> list[tuple[int, str]]:
    """Apply cotas and anti-FP filters to raw anchors inside the body range."""
    full_doc_repeats: dict[str, int] = {}
    seen_texts = {at for _, at in raw_anchors}
    for at in seen_texts:
        full_doc_repeats[at] = plain_text.count(at)

    body_anchors: list[tuple[int, str]] = []
    for pos, anchor_text in raw_anchors:
        if pos < body_start or pos >= item1a_end:
            continue
        if not _passes_cotas(anchor_text):
            continue
        if _matches_anti_fp_pattern(anchor_text):
            continue
        if full_doc_repeats.get(anchor_text, 0) >= _REPETITION_MAX:
            continue
        body_anchors.append((pos, anchor_text))
    return body_anchors


def _build_body_chunks(
    plain_text: str,
    body_anchors: list[tuple[int, str]],
    body_start: int,
    item1a_end: int,
) -> list[Chunk]:
    """Cut ``[body_start, item1a_end]`` into anchor-bounded chunks.

    Pre-anchor content (intro before the first body anchor) becomes
    an orphan chunk with ``anchor_text=None`` and ``anchor_level=3``.
    ``chunk_id`` is left as ``"__pending__"`` — final IDs are
    assigned by :func:`chunk_item1a` once gaps are filled.
    """
    chunks: list[Chunk] = []

    if not body_anchors:
        text = plain_text[body_start:item1a_end]
        if text.strip():
            chunks.append(
                Chunk(
                    chunk_id="__pending__",
                    text=text,
                    char_start=body_start,
                    char_end=item1a_end,
                    anchor_text=None,
                    anchor_level=3,
                    in_summary=False,
                    token_estimate=len(text) // 4,
                )
            )
        return chunks

    first_pos = body_anchors[0][0]
    if first_pos > body_start:
        intro_text = plain_text[body_start:first_pos]
        if intro_text.strip():
            chunks.append(
                Chunk(
                    chunk_id="__pending__",
                    text=intro_text,
                    char_start=body_start,
                    char_end=first_pos,
                    anchor_text=None,
                    anchor_level=3,
                    in_summary=False,
                    token_estimate=len(intro_text) // 4,
                )
            )

    for i, (pos, anchor_text) in enumerate(body_anchors):
        next_pos = body_anchors[i + 1][0] if i + 1 < len(body_anchors) else item1a_end
        text = plain_text[pos:next_pos]
        if not text.strip():
            continue
        chunks.append(
            Chunk(
                chunk_id="__pending__",
                text=text,
                char_start=pos,
                char_end=next_pos,
                anchor_text=anchor_text,
                anchor_level=_anchor_level_for(anchor_text),
                in_summary=False,
                token_estimate=len(text) // 4,
            )
        )
    return chunks


def _split_oversized(
    chunk: Chunk,
    div_positions: list[int],
    warnings_list: list[str],
) -> list[Chunk]:
    """Sub-chunk ``chunk`` if its text exceeds ``_MAX_CHUNK_CHARS``.

    Cuts at div boundaries closest to multiples of
    ``_SUBCHUNK_TARGET_CHARS`` within the chunk, with
    ``_SUBCHUNK_OVERLAP_CHARS`` of text overlap between consecutive
    sub-chunks. A hard cut to ``_HARD_CUT_CHARS`` is applied if a
    sub-chunk is still oversized; a warning is appended. Sub-chunks
    keep ``chunk_id="__pending__"`` because :func:`chunk_item1a`
    renumbers everything sequentially in a single final pass.
    """
    if len(chunk.text) <= _MAX_CHUNK_CHARS:
        return [chunk]

    interior_divs = [p for p in div_positions if chunk.char_start < p < chunk.char_end]
    boundaries: list[int] = [chunk.char_start]
    target = chunk.char_start + _SUBCHUNK_TARGET_CHARS
    while target < chunk.char_end:
        if interior_divs:
            closest = min(interior_divs, key=lambda p: abs(p - target))
            if not boundaries or closest > boundaries[-1]:
                boundaries.append(closest)
                target = closest + _SUBCHUNK_TARGET_CHARS
                continue
        if not boundaries or target > boundaries[-1]:
            boundaries.append(target)
        target += _SUBCHUNK_TARGET_CHARS
    boundaries.append(chunk.char_end)

    sub_chunks: list[Chunk] = []
    for i in range(len(boundaries) - 1):
        start = boundaries[i]
        end = boundaries[i + 1]
        if i > 0:
            start = max(boundaries[0], start - _SUBCHUNK_OVERLAP_CHARS)
        text = chunk.text[(start - chunk.char_start):(end - chunk.char_start)]
        if len(text) > _HARD_CUT_CHARS:
            text = text[:_HARD_CUT_CHARS]
            end = start + _HARD_CUT_CHARS
            warnings_list.append(
                f"Hard cut to {_HARD_CUT_CHARS} chars while sub-chunking an oversized chunk"
            )
        sub_chunks.append(
            Chunk(
                chunk_id="__pending__",
                text=text,
                char_start=start,
                char_end=end,
                anchor_text=None,
                anchor_level=3,
                in_summary=chunk.in_summary,
                token_estimate=len(text) // 4,
            )
        )
    return sub_chunks


def chunk_item1a(
    html: str,
    item1a_start: int,
    item1a_end: int,
    ticker: str,
    fiscal_year: int,
) -> Item1AChunkSet:
    """Slice the Item 1A range of an iXBRL 10-K into chunks.

    Args:
        html: Raw HTML of the 10-K (iXBRL).
        item1a_start: Plain-text offset where Item 1A begins.
        item1a_end: Plain-text offset where Item 1A ends (exclusive).
        ticker: Filer ticker (used in ``chunk_id``).
        fiscal_year: Filing fiscal year (used in ``chunk_id``).

    Returns:
        :class:`Item1AChunkSet` with summary and body chunks. The hard
        guarantee is that no chunk has ``token_estimate > 4000``.
    """
    if item1a_end < item1a_start:
        raise ValueError(
            f"item1a_end ({item1a_end}) must be >= item1a_start ({item1a_start})"
        )

    _LOGGER.info(
        "chunk_item1a: ticker=%s FY=%d range=[%d,%d]",
        ticker, fiscal_year, item1a_start, item1a_end,
    )

    plain_text = _html_to_text(html)
    item1a_text = plain_text[item1a_start:item1a_end]
    div_positions, raw_anchors = _walk_leaf_divs(html, plain_text)

    warnings_list: list[str] = []

    summary_start, summary_end, short_header_text = _detect_summary(
        plain_text, item1a_start, item1a_end, raw_anchors,
    )

    summary_chunks_raw: list[Chunk] = []
    body_start = item1a_start
    if summary_start is not None and summary_end is not None:
        summary_chunks_raw = _extract_summary_chunks(
            plain_text, summary_start, summary_end, short_header_text or "Summary",
        )
        if summary_chunks_raw:
            body_start = summary_end
        else:
            warnings_list.append(
                "Summary header detected but no bullets resolved into chunks; "
                "treating range as body."
            )
            summary_start = None

    pre_summary_chunk: Chunk | None = None
    if summary_start is not None and summary_start > item1a_start:
        pre_text = plain_text[item1a_start:summary_start]
        if pre_text.strip():
            pre_summary_chunk = Chunk(
                chunk_id="__pending__",
                text=pre_text,
                char_start=item1a_start,
                char_end=summary_start,
                anchor_text=None,
                anchor_level=3,
                in_summary=False,
                token_estimate=len(pre_text) // 4,
            )

    body_anchors = _filter_body_anchors(
        raw_anchors, plain_text, body_start, item1a_end,
    )
    if not body_anchors:
        warnings_list.append(
            "No body sub-headers passed cotas/anti-FP filters; "
            "falling back to length-only chunking."
        )
    body_chunks_raw = _build_body_chunks(
        plain_text, body_anchors, body_start, item1a_end,
    )
    if pre_summary_chunk is not None:
        body_chunks_raw.insert(0, pre_summary_chunk)

    # Length fallback per chunk. Each parent chunk either stays as one
    # chunk (singleton) or fans out into a sibling group of sub-chunks.
    Item = Chunk | list[Chunk]
    items: list[Item] = []
    for ch in summary_chunks_raw + body_chunks_raw:
        splits = _split_oversized(ch, div_positions, warnings_list)
        items.append(splits[0] if len(splits) == 1 else splits)

    def _item_start(item: Item) -> int:
        return item[0].char_start if isinstance(item, list) else item.char_start

    def _item_end(item: Item) -> int:
        return item[-1].char_end if isinstance(item, list) else item.char_end

    items.sort(key=_item_start)

    # Gap-filling pass: ensure the union of chunk ranges covers
    # [item1a_start, item1a_end] exactly.
    filled: list[Item] = []
    cursor = item1a_start
    for item in items:
        start = _item_start(item)
        if start > cursor:
            gap_text = plain_text[cursor:start]
            if gap_text.strip():
                filled.append(
                    Chunk(
                        chunk_id="__pending__",
                        text=gap_text,
                        char_start=cursor,
                        char_end=start,
                        anchor_text=None,
                        anchor_level=3,
                        in_summary=False,
                        token_estimate=len(gap_text) // 4,
                    )
                )
        filled.append(item)
        cursor = max(cursor, _item_end(item))
    if cursor < item1a_end:
        tail_text = plain_text[cursor:item1a_end]
        if tail_text.strip():
            filled.append(
                Chunk(
                    chunk_id="__pending__",
                    text=tail_text,
                    char_start=cursor,
                    char_end=item1a_end,
                    anchor_text=None,
                    anchor_level=3,
                    in_summary=False,
                    token_estimate=len(tail_text) // 4,
                )
            )

    # Assign sequential chunk_ids. Sub-chunk groups share a parent number
    # and use lowercase suffixes per spec example (`_001a`, `_001b`, ...).
    summary_chunks_final: list[Chunk] = []
    body_chunks_final: list[Chunk] = []
    for idx, item in enumerate(filled, start=1):
        base_id = _build_chunk_id(ticker, fiscal_year, idx)
        if isinstance(item, list):
            for j, sub in enumerate(item):
                suffix = chr(ord("a") + j)
                renamed = sub.model_copy(update={"chunk_id": f"{base_id}{suffix}"})
                (summary_chunks_final if renamed.in_summary else body_chunks_final).append(renamed)
        else:
            renamed = item.model_copy(update={"chunk_id": base_id})
            (summary_chunks_final if renamed.in_summary else body_chunks_final).append(renamed)

    for ch in summary_chunks_final + body_chunks_final:
        if ch.token_estimate > _MAX_CHUNK_CHARS // 4:
            warnings_list.append(
                f"Chunk {ch.chunk_id} still exceeds 4000 tokens after sub-chunking"
            )

    return Item1AChunkSet(
        ticker=ticker,
        fiscal_year=fiscal_year,
        item1a_token_estimate=len(item1a_text) // 4,
        summary_present=summary_start is not None and len(summary_chunks_final) > 0,
        summary_chunks=summary_chunks_final,
        body_chunks=body_chunks_final,
        warnings=warnings_list,
    )


_ITEM1A_BODY_RE: re.Pattern[str] = re.compile(
    r"item\s+1a[\.\s:]+risk\s+factors", re.IGNORECASE,
)
_ITEM_1B_OR_2_RE: re.Pattern[str] = re.compile(
    r"item\s+1b\b|item\s+2\b", re.IGNORECASE,
)
_TOC_LIKE_TAIL_RE: re.Pattern[str] = re.compile(r"^\s*[.\s]*\d")
_QUOTE_CHARS: str = "\"'“”‘’"


def _find_section_header(
    plain_text: str,
    pattern: re.Pattern[str],
    start: int = 0,
) -> int | None:
    """Return the first occurrence that looks like a section body header.

    Two filters reject the common confounders:

    * **Cross-references** (``" Item 1A. Risk Factors "`` in another
      section) — rejected when any quotation-mark character sits
      within five chars before the match.
    * **TOC entries** — rejected when the match is followed by a page
      number pattern within the next ~15 chars.
    """
    for m in pattern.finditer(plain_text, start):
        pos = m.start()
        prev = plain_text[max(0, pos - 5):pos]
        nxt = plain_text[m.end():m.end() + 15]
        if any(c in prev for c in _QUOTE_CHARS):
            continue
        if _TOC_LIKE_TAIL_RE.match(nxt):
            continue
        return pos
    return None


def find_item1a_range(html: str) -> tuple[int, int]:
    """Locate the plain-text offsets of the Item 1A body.

    Uses text-pattern matching with cross-reference and TOC filters
    rather than the chunker's bold-leading detector because some
    filers (notably JPM) inline the Item 1A header into the first
    paragraph rather than rendering it as a bold ``<div>``.

    Returns:
        ``(item1a_start, item1a_end)`` plain-text offsets.

    Raises:
        RuntimeError: if no canonical header pair can be found.
    """
    plain_text = _html_to_text(html)
    item1a_start = _find_section_header(plain_text, _ITEM1A_BODY_RE, start=0)
    if item1a_start is None:
        raise RuntimeError("Could not locate Item 1A body header")
    item1a_end = _find_section_header(
        plain_text, _ITEM_1B_OR_2_RE, start=item1a_start + 200,
    )
    if item1a_end is None:
        raise RuntimeError("Could not locate Item 1B / Item 2 closing anchor")
    return item1a_start, item1a_end


__all__ = ["chunk_item1a", "find_item1a_range"]
