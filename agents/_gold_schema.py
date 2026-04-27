"""Schema constants for the LUCA gold standard.

This module holds the canonical lists of tickers and metrics used by the
gold-standard annotation workflow. Centralising them here lets every
downstream consumer (the annotation script in :mod:`scripts`, the L3
extractor evaluation in :mod:`experiments.eval_extraction`, and the
LLM-baseline experiment in :mod:`experiments.eval_baseline_llm`) agree on
the exact same set of (ticker, metric) pairs.

Do not mutate these constants at runtime; they are treated as
immutable contracts across the project.
"""

from __future__ import annotations

from typing import Final

#: Tickers covered by the gold standard. Order is intentional: AAPL first
#: because it is the calibration company for CHECKPOINT 1.
GOLD_TICKERS: Final[tuple[str, ...]] = (
    "AAPL",
    "MSFT",
    "GOOGL",
    "META",
    "AMZN",
    "NVDA",
    "JPM",
    "KO",
    "JNJ",
    "WMT",
)

#: Metrics annotated for every ticker. Names match the canonical keys used
#: by L3's US-GAAP mapping table (see T1.3).
GOLD_METRICS: Final[tuple[str, ...]] = (
    "revenue",
    "net_income",
    "operating_income",
    "total_assets",
    "total_equity",
    "eps_diluted",
)

#: Column order in the annotation Excel sheet. Single source of truth so the
#: writer (init) and the reader (validate) cannot drift apart.
GOLD_COLUMNS: Final[tuple[str, ...]] = (
    "ticker",
    "fiscal_year",
    "metric",
    "value",
    "unit",
    "source_page",
    "notes",
)

#: Total number of rows the initialised workbook should contain (one per
#: (ticker, metric) pair).
GOLD_ROW_COUNT: Final[int] = len(GOLD_TICKERS) * len(GOLD_METRICS)

#: Canonical ``unit`` string expected in the gold-standard workbook for each
#: metric. The convention (set by the user, 2026-04-27) is:
#:
#: * The five monetary metrics (``revenue``, ``net_income``,
#:   ``operating_income``, ``total_assets``, ``total_equity``) are
#:   recorded as **absolute USD** values (no thousands/millions scaling)
#:   with ``unit == "USD"``.
#: * ``eps_diluted`` is recorded as the per-share ratio as published in
#:   the 10-K (e.g. ``6.13``) with ``unit == "USD/share"``.
#:
#: This dict is the single source of truth for unit consistency: the
#: ``annotate_gold_standard.py validate`` subcommand reads it, and the
#: T1.8/T1.9 evaluation scripts will reuse the same constant when
#: comparing gold values against L3 / LLM extractions. Do not duplicate
#: these strings elsewhere — import from here instead.
EXPECTED_UNITS: Final[dict[str, str]] = {
    "revenue": "USD",
    "net_income": "USD",
    "operating_income": "USD",
    "total_assets": "USD",
    "total_equity": "USD",
    "eps_diluted": "USD/share",
}

#: Sentinel string written into the ``value`` cell when a metric is
#: **structurally** unavailable for a filer (e.g. JPM does not report
#: ``OperatingIncomeLoss`` because the SIC 6022 banking taxonomy has no
#: standard tag for it; JNJ chooses not to publish an operating-profit
#: subtotal). This is **not** the same as "forgot to annotate" — that
#: case yields a blank cell and is caught by ``validate``. Recognised
#: case-insensitively. Evaluators must coerce this sentinel to Python
#: ``None`` before comparing against extractor outputs.
NULL_SENTINEL: Final[str] = "null"


def coerce_gold_value(raw: object) -> float | None:
    """Normalise a raw cell from the gold-standard ``value`` column.

    Args:
        raw: The cell value as returned by openpyxl.

    Returns:
        ``None`` if the cell holds the :data:`NULL_SENTINEL` (e.g. for a
        metric that is structurally absent for that filer); otherwise a
        ``float`` for any numeric value.

    Raises:
        ValueError: When ``raw`` is neither numeric nor the recognised
            sentinel — that signals a gold-standard cell that the
            evaluator should not silently interpret as "missing".
    """
    if isinstance(raw, str) and raw.strip().lower() == NULL_SENTINEL:
        return None
    if isinstance(raw, bool):
        # bool is a subclass of int — explicitly reject.
        raise ValueError(f"Valor de gold standard no esperado: {raw!r}")
    if isinstance(raw, (int, float)):
        return float(raw)
    raise ValueError(f"Valor de gold standard no esperado: {raw!r}")


__all__ = [
    "GOLD_TICKERS",
    "GOLD_METRICS",
    "GOLD_COLUMNS",
    "GOLD_ROW_COUNT",
    "EXPECTED_UNITS",
    "NULL_SENTINEL",
    "coerce_gold_value",
]
