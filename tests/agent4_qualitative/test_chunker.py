"""Tests for the T2.2 Item 1A chunker.

Two layers:

* **Unit tests** exercise individual helpers (bold detection, cotas,
  anti-FP, summary heuristic, length fallback) on small synthetic
  HTML fragments so failures point at a single behaviour.
* **Integration tests** run the full :func:`chunk_item1a` over the
  cached AAPL / JPM / WMT 10-Ks in ``data/cache/``. They verify the
  closing criteria in ``docs/architecture/T2_2_chunker_spec.md``
  (no oversized chunks, JPM Summary, WMT body anchor count, full
  coverage, idempotency).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from agents.agent4_qualitative.chunker import (
    _find_anchor_in_div,
    _matches_anti_fp_pattern,
    _passes_cotas,
    chunk_item1a,
    find_item1a_range,
)
from agents.agent4_qualitative.models import Item1AChunkSet

_CACHE_DIR = Path(__file__).resolve().parents[2] / "data" / "cache"
_AAPL_CACHE = _CACHE_DIR / "AAPL_0000320193-25-000079.html"
_JPM_CACHE = _CACHE_DIR / "JPM_0001628280-26-008131.html"
_WMT_CACHE = _CACHE_DIR / "WMT_0000104169-26-000055.html"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_item1a_html(body_divs: list[str]) -> tuple[str, int, int]:
    """Build a minimal Item 1A document and return ``(html, start, end)``."""
    head = "<html><body>"
    intro = (
        '<div>Item 1A. Risk Factors The following discussion sets forth '
        "the risk factors that could materially adversely affect.</div>"
    )
    tail = "<div>Item 1B. Unresolved Staff Comments. None.</div></body></html>"
    html = head + intro + "".join(body_divs) + tail
    start, end = find_item1a_range(html)
    return html, start, end


def _bold_div(text: str, body: str = " body content", *, weight: str = "700") -> str:
    return f'<div><span style="font-weight:{weight}">{text}</span>{body}</div>'


def _div_from(html: str) -> object:
    return BeautifulSoup(html, "lxml").find("div")


# ---------------------------------------------------------------------------
# Unit: bold detection
# ---------------------------------------------------------------------------


def test_detect_bold_font_weight_700():
    div = _div_from(_bold_div("Heading text"))
    assert _find_anchor_in_div(div) == "Heading text"


def test_detect_bold_font_weight_bold():
    div = _div_from(_bold_div("Heading text", weight="bold"))
    assert _find_anchor_in_div(div) == "Heading text"


def test_detect_bold_font_weight_600():
    div = _div_from(_bold_div("Heading text", weight="600"))
    assert _find_anchor_in_div(div) == "Heading text"


def test_non_bold_returns_none():
    div = _div_from(_bold_div("Heading text", weight="400"))
    assert _find_anchor_in_div(div) is None


# ---------------------------------------------------------------------------
# Unit: cotas
# ---------------------------------------------------------------------------


def test_reject_short_anchor():
    assert _passes_cotas("One") is False
    assert _passes_cotas("Two Words") is True


def test_reject_long_anchor():
    long_text = " ".join(["word"] * 80)
    assert len(long_text) > 300
    assert _passes_cotas(long_text) is False


# ---------------------------------------------------------------------------
# Unit: anti-FP regex / repetition
# ---------------------------------------------------------------------------


def test_anti_fp_numeric():
    assert _matches_anti_fp_pattern("31") is True


def test_anti_fp_part_pattern():
    assert _matches_anti_fp_pattern("Parts I and II") is True
    assert _matches_anti_fp_pattern("Part IV") is True


def test_anti_fp_repetition():
    repeated = _bold_div("Repeated Anchor", " body content here.")
    unique = _bold_div("Unique Anchor Here", " distinct body content.")
    html, s, e = _build_item1a_html([repeated, repeated, repeated, repeated, unique])
    result = chunk_item1a(html, s, e, "TEST", 2024)
    body_anchors = {c.anchor_text for c in result.body_chunks if c.anchor_text}
    assert "Repeated Anchor" not in body_anchors
    assert "Unique Anchor Here" in body_anchors


# ---------------------------------------------------------------------------
# Unit: summary detection
# ---------------------------------------------------------------------------


_LEVEL_2_ANCHOR = _bold_div(
    "This is a level two header phrase with more than four words",
    " body text that follows.",
)


def test_summary_detection_with_bullets():
    body_divs = [
        _bold_div("Summary", " The principal risks include:"),
        "<div>&#8226; Political risks, including the potential negative effects from "
        "political developments and their impact on the firm.</div>",
        "<div>&#8226; Market risks, including the effects on unfavorable economic "
        "conditions and market fluctuations affecting the firm.</div>",
        "<div>&#8226; Credit risks, including effects from adverse changes in "
        "the financial condition of counterparties.</div>",
        _LEVEL_2_ANCHOR,
    ]
    html, s, e = _build_item1a_html(body_divs)
    result = chunk_item1a(html, s, e, "TEST", 2024)
    assert result.summary_present is True
    assert len(result.summary_chunks) >= 3
    for chunk in result.summary_chunks:
        assert chunk.in_summary is True
        assert chunk.anchor_level == 1


def test_summary_not_detected_without_bullets():
    body_divs = [
        _bold_div("Summary", " Plain text follows without any bullets here."),
        _LEVEL_2_ANCHOR,
    ]
    html, s, e = _build_item1a_html(body_divs)
    result = chunk_item1a(html, s, e, "TEST", 2024)
    assert result.summary_present is False
    assert result.summary_chunks == []


# ---------------------------------------------------------------------------
# Unit: length fallback
# ---------------------------------------------------------------------------


def test_length_fallback():
    big_body = "".join(
        f"<div>Paragraph {i}: " + "filler text " * 30 + "end.</div>"
        for i in range(120)
    )
    body_divs = [
        _bold_div(
            "Big anchor that introduces a long discussion section needing fallback",
            " ",
        ),
        big_body,
    ]
    html, s, e = _build_item1a_html(body_divs)
    result = chunk_item1a(html, s, e, "TEST", 2024)

    for chunk in result.body_chunks:
        assert chunk.token_estimate <= 4000
        assert len(chunk.text) <= 16_000

    # Length fallback shows up as overlap between consecutive sibling chunks
    # (the parent chunk is split at div boundaries with ~500 chars overlap).
    chunks_sorted = sorted(result.body_chunks, key=lambda c: c.char_start)
    has_overlap = any(
        chunks_sorted[i + 1].char_start < chunks_sorted[i].char_end
        for i in range(len(chunks_sorted) - 1)
    )
    assert has_overlap, (
        "Length fallback should have produced overlapping sub-chunks for an oversized parent"
    )


# ---------------------------------------------------------------------------
# Integration: real fixtures
# ---------------------------------------------------------------------------


def _require_cache(path: Path) -> Path:
    if not path.exists():
        pytest.skip(f"cache file not present: {path.name}")
    return path


@pytest.fixture(scope="module")
def aapl_chunkset() -> tuple[Item1AChunkSet, int, int]:
    html = _require_cache(_AAPL_CACHE).read_text(encoding="utf-8")
    s, e = find_item1a_range(html)
    return chunk_item1a(html, s, e, "AAPL", 2025), s, e


@pytest.fixture(scope="module")
def jpm_chunkset() -> tuple[Item1AChunkSet, int, int]:
    html = _require_cache(_JPM_CACHE).read_text(encoding="utf-8")
    s, e = find_item1a_range(html)
    return chunk_item1a(html, s, e, "JPM", 2025), s, e


@pytest.fixture(scope="module")
def wmt_chunkset() -> tuple[Item1AChunkSet, int, int]:
    html = _require_cache(_WMT_CACHE).read_text(encoding="utf-8")
    s, e = find_item1a_range(html)
    return chunk_item1a(html, s, e, "WMT", 2026), s, e


def _assert_no_oversized(result: Item1AChunkSet) -> None:
    for c in result.summary_chunks + result.body_chunks:
        assert c.token_estimate <= 4000, f"{c.chunk_id}: {c.token_estimate} > 4000"


def _assert_full_coverage(
    result: Item1AChunkSet, item1a_start: int, item1a_end: int,
) -> None:
    chunks = sorted(result.summary_chunks + result.body_chunks, key=lambda c: c.char_start)
    assert chunks, "Expected at least one chunk"
    assert chunks[0].char_start == item1a_start
    assert chunks[-1].char_end == item1a_end
    prev_end = item1a_start
    for c in chunks:
        assert c.char_start <= prev_end, (
            f"Gap before {c.chunk_id}: prev_end={prev_end} char_start={c.char_start}"
        )
        prev_end = max(prev_end, c.char_end)


def test_chunker_aapl(aapl_chunkset):
    result, s, e = aapl_chunkset
    assert isinstance(result, Item1AChunkSet)
    assert result.summary_present is False
    assert result.summary_chunks == []
    _assert_no_oversized(result)
    _assert_full_coverage(result, s, e)


def test_chunker_jpm(jpm_chunkset):
    result, s, e = jpm_chunkset
    assert isinstance(result, Item1AChunkSet)
    assert result.summary_present is True
    assert len(result.summary_chunks) >= 8
    for c in result.summary_chunks:
        assert c.in_summary is True
    _assert_no_oversized(result)
    _assert_full_coverage(result, s, e)


def test_chunker_wmt(wmt_chunkset):
    result, s, e = wmt_chunkset
    assert isinstance(result, Item1AChunkSet)
    assert result.summary_present is False
    assert result.summary_chunks == []
    assert len(result.body_chunks) >= 10
    _assert_no_oversized(result)
    _assert_full_coverage(result, s, e)


# ---------------------------------------------------------------------------
# Integration: idempotency
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ticker", "filename", "fy"),
    [
        ("AAPL", _AAPL_CACHE.name, 2025),
        ("JPM", _JPM_CACHE.name, 2025),
        ("WMT", _WMT_CACHE.name, 2026),
    ],
)
def test_idempotency(ticker: str, filename: str, fy: int) -> None:
    path = _require_cache(_CACHE_DIR / filename)
    html = path.read_text(encoding="utf-8")
    s, e = find_item1a_range(html)
    r1 = chunk_item1a(html, s, e, ticker, fy)
    r2 = chunk_item1a(html, s, e, ticker, fy)
    assert r1.model_dump_json() == r2.model_dump_json()
