"""Evaluation script for the T2.2 Item 1A chunker.

Reads a manually-curated gold standard of anchors per ticker, runs
``chunk_item1a`` over the cached 10-Ks for those tickers, and reports
precision / recall / F1 for anchor detection plus chunk-size and
coverage statistics.

Gold standard format
--------------------
``data/gold_chunker_anchors.json``::

    {
      "AAPL": {
        "fiscal_year": 2024,
        "anchors": [
          {"text": "Macroeconomic and Industry Risks", "level": 1},
          {"text": "The Company's future performance depends in part on support from third-party software developers.", "level": 2}
        ]
      },
      "JPM":  {"fiscal_year": 2024, "anchors": [...]},
      "WMT":  {"fiscal_year": 2025, "anchors": [...]}
    }

Anchor matching is text-normalised: lowercase, ``strip``, collapse
internal whitespace runs to a single space. ``level`` is reported but
not enforced for matching (precision / recall are over anchor text
only); the spec keeps the level distinction informative for future
work.

Cached 10-Ks are discovered by glob ``data/cache/{TICKER}_*.html``
(the same naming the rest of the project uses).

Behaviour when the gold standard is absent
------------------------------------------
If ``data/gold_chunker_anchors.json`` does not exist the script
appends an entry to ``docs/blockers/T2_2_blockers.md`` and exits with
status 0. The gold is expected to be annotated manually (1-2 h
according to the spec); the absence is a known, planned blocker, not
an evaluation failure.

Outputs
-------
* Markdown summary written to ``docs/eval/T2_2_chunker_eval.md``.
* The same table printed to ``stdout`` for convenience.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# When invoked as a script the project root is not on ``sys.path``;
# add it so ``from agents...`` resolves regardless of cwd.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agents.agent4_qualitative.chunker import chunk_item1a, find_item1a_range  # noqa: E402
from agents.agent4_qualitative.models import Chunk, Item1AChunkSet  # noqa: E402

_REPO_ROOT = Path(__file__).resolve().parents[1]
_GOLD_PATH = _REPO_ROOT / "data" / "gold_chunker_anchors.json"
_CACHE_DIR = _REPO_ROOT / "data" / "cache"
_BLOCKERS_PATH = _REPO_ROOT / "docs" / "blockers" / "T2_2_blockers.md"
_EVAL_REPORT_PATH = _REPO_ROOT / "docs" / "eval" / "T2_2_chunker_eval.md"

_WS_RE: re.Pattern[str] = re.compile(r"\s+")


def _normalize(text: str) -> str:
    return _WS_RE.sub(" ", text).strip().lower()


def _resolve_cache_file(ticker: str) -> Path | None:
    matches = sorted(_CACHE_DIR.glob(f"{ticker}_*.html"))
    return matches[0] if matches else None


def _detected_anchors(chunkset: Item1AChunkSet) -> list[str]:
    """Body anchors detected by the chunker (excludes None and sub-chunks)."""
    anchors: list[str] = []
    for chunk in chunkset.body_chunks:
        if chunk.anchor_text is None or chunk.anchor_level == 3:
            continue
        anchors.append(chunk.anchor_text)
    return anchors


def _coverage_pct(chunkset: Item1AChunkSet, item1a_start: int, item1a_end: int) -> float:
    if item1a_end == item1a_start:
        return 100.0
    covered: list[tuple[int, int]] = sorted(
        (c.char_start, c.char_end)
        for c in chunkset.summary_chunks + chunkset.body_chunks
    )
    if not covered:
        return 0.0
    union_total = 0
    cur_start, cur_end = covered[0]
    for start, end in covered[1:]:
        if start <= cur_end:
            cur_end = max(cur_end, end)
        else:
            union_total += cur_end - cur_start
            cur_start, cur_end = start, end
    union_total += cur_end - cur_start
    capped = min(union_total, item1a_end - item1a_start)
    return 100.0 * capped / (item1a_end - item1a_start)


def _max_chunk_stats(chunkset: Item1AChunkSet) -> tuple[int, int]:
    all_chunks: list[Chunk] = chunkset.summary_chunks + chunkset.body_chunks
    if not all_chunks:
        return 0, 0
    max_tok = max(c.token_estimate for c in all_chunks)
    max_chars = max(len(c.text) for c in all_chunks)
    return max_tok, max_chars


def _score(
    detected: list[str],
    gold: list[str],
) -> tuple[float, float, float, int, int, int]:
    detected_norm = {_normalize(t) for t in detected if t}
    gold_norm = {_normalize(t) for t in gold if t}
    tp = len(detected_norm & gold_norm)
    fp = len(detected_norm - gold_norm)
    fn = len(gold_norm - detected_norm)
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return precision, recall, f1, tp, fp, fn


def _write_blocker_for_missing_gold() -> None:
    _BLOCKERS_PATH.parent.mkdir(parents=True, exist_ok=True)
    entry = (
        "\n## Blocker — gold de anchors pendiente de anotación manual\n"
        f"**Detected at:** {datetime.now(timezone.utc).isoformat(timespec='seconds')} "
        "(scripts/eval_chunker.py run).\n"
        f"**Symptom:** `{_GOLD_PATH.relative_to(_REPO_ROOT)}` does not exist.\n"
        "**Needs human decision on:** the gold of anchors is pending manual "
        "annotation (1–2 h per spec). Format is documented in the docstring "
        "of `scripts/eval_chunker.py`.\n"
    )
    existing = _BLOCKERS_PATH.read_text(encoding="utf-8") if _BLOCKERS_PATH.exists() else ""
    if "gold de anchors pendiente" in existing:
        return
    if not existing:
        existing = "# T2.2 — Blockers\n"
    _BLOCKERS_PATH.write_text(existing + entry, encoding="utf-8")


def _format_report(rows: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    lines.append("# T2.2 — Chunker evaluation\n")
    lines.append(
        f"Run: {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n"
    )
    lines.append("## Per-ticker metrics\n")
    lines.append(
        "| ticker | FY | gold | detected | TP | FP | FN | "
        "precision | recall | F1 | max tok | max chars | coverage % |"
    )
    lines.append(
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
    )
    for r in rows:
        lines.append(
            f"| {r['ticker']} | {r['fiscal_year']} | {r['gold']} | "
            f"{r['detected']} | {r['tp']} | {r['fp']} | {r['fn']} | "
            f"{r['precision']:.3f} | {r['recall']:.3f} | {r['f1']:.3f} | "
            f"{r['max_tok']} | {r['max_chars']} | {r['coverage']:.2f} |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    if not _GOLD_PATH.exists():
        _write_blocker_for_missing_gold()
        print(
            f"[eval_chunker] gold standard not found at "
            f"{_GOLD_PATH.relative_to(_REPO_ROOT)}; blocker appended. "
            f"This is the expected pre-annotation state — no error."
        )
        return 0

    with _GOLD_PATH.open("r", encoding="utf-8") as fh:
        gold: dict[str, Any] = json.load(fh)

    rows: list[dict[str, Any]] = []
    for ticker, payload in gold.items():
        fiscal_year = int(payload["fiscal_year"])
        gold_anchors = [a["text"] for a in payload["anchors"]]
        cache_file = _resolve_cache_file(ticker)
        if cache_file is None:
            print(f"[eval_chunker] no cached HTML for {ticker} — skipping", file=sys.stderr)
            continue
        html = cache_file.read_text(encoding="utf-8")
        item1a_start, item1a_end = find_item1a_range(html)
        result = chunk_item1a(html, item1a_start, item1a_end, ticker, fiscal_year)
        detected = _detected_anchors(result)
        precision, recall, f1, tp, fp, fn = _score(detected, gold_anchors)
        max_tok, max_chars = _max_chunk_stats(result)
        coverage = _coverage_pct(result, item1a_start, item1a_end)
        rows.append(
            {
                "ticker": ticker,
                "fiscal_year": fiscal_year,
                "gold": len(gold_anchors),
                "detected": len(detected),
                "tp": tp,
                "fp": fp,
                "fn": fn,
                "precision": precision,
                "recall": recall,
                "f1": f1,
                "max_tok": max_tok,
                "max_chars": max_chars,
                "coverage": coverage,
            }
        )

    report = _format_report(rows)
    _EVAL_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _EVAL_REPORT_PATH.write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())
