"""T1.8 — Evaluate L3 Structured Extractor against the gold standard.

This is the first of the three legs of the Sprint 1 extraction
experiment (T1.8 + T1.9a + T1.9b). It runs the L1 → L3 stack on every
ticker covered by the gold standard, compares each extracted metric
against the human-annotated value, and emits two artefacts under
``experiments/output/``:

* a CSV with one row per ``(ticker, metric)`` pair, suitable for
  downstream pandas analysis;
* a Markdown report with three breakdowns (aggregate, per-metric,
  per-company) plus the distribution of ``tag_used`` across the
  resolved metrics. T1.10 reads this report directly to drive the
  error-analysis narrative.

Network policy
--------------
L1 fetches XBRL companyfacts and the 10-K HTML from EDGAR. The HTML is
cached on disk under ``data/cache/`` so re-runs are cheap; companyfacts
is always fresh, but EDGAR's API is rate-limited inside
``agents._edgar_client``. No LLM is invoked at any point — this
experiment is pure XBRL extraction. The LLM baseline is T1.9.

Usage
-----
::

    /home/<user>/luca-ai-lab/venv/bin/python \\
        experiments/eval_extraction.py \\
        [--gold-path PATH] \\
        [--output-dir PATH]

The defaults are sensible and match the project layout.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

# When invoked as a script, the project root is not on ``sys.path``.
_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agents._config import load_config  # noqa: E402
from agents._gold_schema import GOLD_METRICS, GOLD_TICKERS  # noqa: E402
from agents._logging import get_logger  # noqa: E402
from agents.agent1_ingestion import ingest  # noqa: E402
from agents.agent3_extractor import extract  # noqa: E402
from experiments._eval_common import (  # noqa: E402
    GoldEntry,
    compare_values,
    load_gold_standard,
)

_LOGGER = get_logger(__name__)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_GOLD_PATH: Path = _PROJECT_ROOT / "data" / "gold_standard.xlsx"
DEFAULT_OUTPUT_DIR: Path = _PROJECT_ROOT / "experiments" / "output"

CSV_FIELDNAMES: tuple[str, ...] = (
    "ticker",
    "metric",
    "gold_value",
    "gold_fiscal_year",
    "predicted_value",
    "predicted_fiscal_year",
    "predicted_period_end",
    "predicted_tag_used",
    "predicted_accession",
    "predicted_unit",
    "match",
    "abs_error",
    "rel_error",
    "notes_gold",
)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EvalRow:
    """A single (ticker, metric) row in the evaluation table."""

    ticker: str
    metric: str
    gold_value: float | None
    gold_fiscal_year: int | None
    predicted_value: float | None
    predicted_fiscal_year: int | None
    predicted_period_end: str | None
    predicted_tag_used: str | None
    predicted_accession: str | None
    predicted_unit: str | None
    match: bool
    abs_error: float | None
    rel_error: float | None
    notes_gold: str

    def as_csv_dict(self) -> dict[str, Any]:
        """Return a dict suitable for ``csv.DictWriter``."""
        return {
            "ticker": self.ticker,
            "metric": self.metric,
            "gold_value": _fmt_optional(self.gold_value),
            "gold_fiscal_year": _fmt_optional(self.gold_fiscal_year),
            "predicted_value": _fmt_optional(self.predicted_value),
            "predicted_fiscal_year": _fmt_optional(self.predicted_fiscal_year),
            "predicted_period_end": self.predicted_period_end or "",
            "predicted_tag_used": self.predicted_tag_used or "",
            "predicted_accession": self.predicted_accession or "",
            "predicted_unit": self.predicted_unit or "",
            "match": "True" if self.match else "False",
            "abs_error": _fmt_optional(self.abs_error),
            "rel_error": _fmt_optional(self.rel_error),
            "notes_gold": self.notes_gold or "",
        }


def _fmt_optional(value: object) -> str:
    """Render ``value`` for the CSV, treating ``None`` as empty string."""
    if value is None:
        return ""
    if isinstance(value, float):
        # Avoid scientific notation in CSV output.
        return repr(value)
    return str(value)


# ---------------------------------------------------------------------------
# Core evaluation
# ---------------------------------------------------------------------------


def _build_predicted_index(
    extract_output: dict[str, Any],
) -> dict[str, dict[str, Any] | None]:
    """Return ``metric → entry`` from L3's output dict, defensively typed."""
    metrics = extract_output.get("metrics") if isinstance(extract_output, dict) else None
    if not isinstance(metrics, dict):
        return {m: None for m in GOLD_METRICS}
    return {m: metrics.get(m) for m in GOLD_METRICS}


def evaluate_ticker(
    ticker: str,
    gold: dict[tuple[str, str], GoldEntry],
    *,
    ingest_fn: Any = ingest,
    extract_fn: Any = extract,
) -> list[EvalRow]:
    """Run L1 + L3 on ``ticker`` and produce one :class:`EvalRow` per metric.

    Args:
        ticker: Ticker symbol covered by the gold standard.
        gold: Output of :func:`load_gold_standard`.
        ingest_fn: Override for tests; defaults to the real L1 entry
            point.
        extract_fn: Override for tests; defaults to the real L3 entry
            point.

    Returns:
        One :class:`EvalRow` per metric in :data:`GOLD_METRICS`. Rows
        for ``(ticker, metric)`` pairs missing from ``gold`` are
        skipped.
    """
    _LOGGER.info("Evaluando %s (L1 + L3)", ticker)
    ingest_output = ingest_fn(ticker)
    extract_output = extract_fn(ingest_output)
    predicted_by_metric = _build_predicted_index(extract_output)

    rows: list[EvalRow] = []
    for metric in GOLD_METRICS:
        key = (ticker, metric)
        gold_entry = gold.get(key)
        if gold_entry is None:
            _LOGGER.warning(
                "No hay anotación gold para (%s, %s); fila omitida",
                ticker, metric,
            )
            continue

        predicted_entry = predicted_by_metric.get(metric)
        predicted_value: float | None = None
        predicted_fiscal_year: int | None = None
        predicted_period_end: str | None = None
        predicted_tag_used: str | None = None
        predicted_accession: str | None = None
        predicted_unit: str | None = None
        if isinstance(predicted_entry, dict):
            raw_value = predicted_entry.get("value")
            if isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool):
                predicted_value = float(raw_value)
            fy = predicted_entry.get("fiscal_year")
            if isinstance(fy, int) and not isinstance(fy, bool):
                predicted_fiscal_year = fy
            pe = predicted_entry.get("period_end")
            if isinstance(pe, str):
                predicted_period_end = pe
            tag = predicted_entry.get("tag_used")
            if isinstance(tag, str):
                predicted_tag_used = tag
            accn = predicted_entry.get("accession")
            if isinstance(accn, str):
                predicted_accession = accn
            unit = predicted_entry.get("unit")
            if isinstance(unit, str):
                predicted_unit = unit

        match, abs_error, rel_error = compare_values(
            gold_entry.value, predicted_value
        )

        rows.append(
            EvalRow(
                ticker=ticker,
                metric=metric,
                gold_value=gold_entry.value,
                gold_fiscal_year=gold_entry.fiscal_year,
                predicted_value=predicted_value,
                predicted_fiscal_year=predicted_fiscal_year,
                predicted_period_end=predicted_period_end,
                predicted_tag_used=predicted_tag_used,
                predicted_accession=predicted_accession,
                predicted_unit=predicted_unit,
                match=match,
                abs_error=abs_error,
                rel_error=rel_error,
                notes_gold=gold_entry.notes,
            )
        )

    return rows


def run_evaluation(
    gold_path: Path,
    *,
    ingest_fn: Any = ingest,
    extract_fn: Any = extract,
) -> list[EvalRow]:
    """Load the gold standard and evaluate every ticker in turn.

    Args:
        gold_path: Path to ``data/gold_standard.xlsx``.
        ingest_fn: Test override (defaults to real L1).
        extract_fn: Test override (defaults to real L3).

    Returns:
        Flattened list of :class:`EvalRow`, in
        ``GOLD_TICKERS × GOLD_METRICS`` order.
    """
    gold = load_gold_standard(gold_path)
    _LOGGER.info(
        "Gold standard cargado: %d filas, %d tickers",
        len(gold), len(GOLD_TICKERS),
    )

    all_rows: list[EvalRow] = []
    for idx, ticker in enumerate(GOLD_TICKERS, start=1):
        _LOGGER.info(
            "Progreso %d/%d → %s", idx, len(GOLD_TICKERS), ticker,
        )
        try:
            rows = evaluate_ticker(
                ticker, gold,
                ingest_fn=ingest_fn,
                extract_fn=extract_fn,
            )
        except Exception as exc:  # pragma: no cover  — logged + re-raised
            _LOGGER.error(
                "Fallo al evaluar ticker %s: %s", ticker, exc,
            )
            raise
        all_rows.extend(rows)

    return all_rows


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------


def write_csv(rows: list[EvalRow], path: Path) -> None:
    """Write the rows to ``path`` as UTF-8 CSV with the canonical header."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(CSV_FIELDNAMES))
        writer.writeheader()
        for row in rows:
            writer.writerow(row.as_csv_dict())


def _accuracy(matches: int, total: int) -> float:
    """Return ``matches / total`` with 0.0 fallback for empty buckets."""
    return (matches / total) if total else 0.0


def _fmt_value(value: float | None) -> str:
    """Render a numeric value for the Markdown tables."""
    if value is None:
        return "null"
    if abs(value) >= 1e6:
        return f"{value:,.0f}"
    return f"{value:,.4f}".rstrip("0").rstrip(".")


def _fmt_match(flag: bool) -> str:
    return "OK" if flag else "MISS"


def write_markdown_report(
    rows: list[EvalRow], path: Path, *, csv_path: Path
) -> None:
    """Write the human-readable Markdown report.

    The report contains:

    1. A header with run timestamp + path to the CSV companion.
    2. The aggregate accuracy.
    3. The per-metric breakdown (one section per metric, listing every
       ticker).
    4. The per-company breakdown (one section per ticker, listing every
       metric).
    5. The distribution of ``tag_used`` across all resolved metrics
       (this is the input T1.10 needs to argue about primary-vs-fallback
       coverage).
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    total = len(rows)
    matches = sum(1 for r in rows if r.match)
    accuracy = _accuracy(matches, total)

    lines: list[str] = []
    lines.append("# T1.8 — Evaluación L3 vs gold standard\n")
    lines.append(
        f"Generado: {datetime.now().isoformat(timespec='seconds')}\n"
    )
    lines.append(f"CSV detallado: `{csv_path.name}`\n")
    lines.append("")
    lines.append("## Resumen agregado\n")
    lines.append(
        f"- Pares evaluados: **{total}**"
    )
    lines.append(
        f"- Coincidencias: **{matches}**"
    )
    lines.append(
        f"- Accuracy global: **{accuracy:.1%}** ({matches}/{total})"
    )
    lines.append("")

    # --- Per-metric breakdown ----------------------------------------------
    lines.append("## Breakdown por métrica\n")
    rows_by_metric: dict[str, list[EvalRow]] = {m: [] for m in GOLD_METRICS}
    for row in rows:
        rows_by_metric.setdefault(row.metric, []).append(row)

    for metric in GOLD_METRICS:
        bucket = rows_by_metric.get(metric, [])
        m_total = len(bucket)
        m_matches = sum(1 for r in bucket if r.match)
        m_accuracy = _accuracy(m_matches, m_total)
        lines.append(
            f"### `{metric}` — accuracy {m_accuracy:.1%} "
            f"({m_matches}/{m_total})\n"
        )
        lines.append("| ticker | gold | predicted | match | rel_error |")
        lines.append("|---|---:|---:|:---:|---:|")
        for row in bucket:
            rel_err_str = (
                f"{row.rel_error:.4%}"
                if row.rel_error is not None else "—"
            )
            lines.append(
                f"| {row.ticker} | {_fmt_value(row.gold_value)} "
                f"| {_fmt_value(row.predicted_value)} "
                f"| {_fmt_match(row.match)} | {rel_err_str} |"
            )
        lines.append("")

    # --- Per-company breakdown ---------------------------------------------
    lines.append("## Breakdown por empresa\n")
    rows_by_ticker: dict[str, list[EvalRow]] = {t: [] for t in GOLD_TICKERS}
    for row in rows:
        rows_by_ticker.setdefault(row.ticker, []).append(row)

    for ticker in GOLD_TICKERS:
        bucket = rows_by_ticker.get(ticker, [])
        t_total = len(bucket)
        t_matches = sum(1 for r in bucket if r.match)
        t_accuracy = _accuracy(t_matches, t_total)
        lines.append(
            f"### {ticker} — accuracy {t_accuracy:.1%} "
            f"({t_matches}/{t_total})\n"
        )
        lines.append("| metric | gold | predicted | tag_used | match |")
        lines.append("|---|---:|---:|---|:---:|")
        for row in bucket:
            lines.append(
                f"| {row.metric} | {_fmt_value(row.gold_value)} "
                f"| {_fmt_value(row.predicted_value)} "
                f"| {row.predicted_tag_used or '—'} "
                f"| {_fmt_match(row.match)} |"
            )
        lines.append("")

    # --- Tag distribution --------------------------------------------------
    lines.append("## Distribución de `tag_used`\n")
    lines.append(
        "Solo se cuentan las extracciones donde L3 devolvió un valor "
        "(no ``None``). Por métrica:\n"
    )
    for metric in GOLD_METRICS:
        bucket = rows_by_metric.get(metric, [])
        tags_used = [r.predicted_tag_used for r in bucket if r.predicted_tag_used]
        if not tags_used:
            lines.append(f"### `{metric}`\n")
            lines.append("- Ninguna extracción produjo un tag (todas vacías).")
            lines.append("")
            continue
        counter = Counter(tags_used)
        lines.append(f"### `{metric}`\n")
        lines.append("| tag | empresas |")
        lines.append("|---|---:|")
        for tag, count in counter.most_common():
            lines.append(f"| `{tag}` | {count} |")
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Console summary
# ---------------------------------------------------------------------------


def _print_console_summary(rows: list[EvalRow]) -> None:
    """Print a compact summary suitable for terminal output."""
    total = len(rows)
    matches = sum(1 for r in rows if r.match)
    accuracy = _accuracy(matches, total)

    print()
    print("=" * 60)
    print("T1.8 — Evaluación L3 vs gold standard")
    print("=" * 60)
    print(f"Pares evaluados: {total}")
    print(f"Coincidencias:   {matches}")
    print(f"Accuracy global: {accuracy:.1%} ({matches}/{total})")
    print()
    print("Accuracy por métrica:")
    rows_by_metric: dict[str, list[EvalRow]] = {m: [] for m in GOLD_METRICS}
    for row in rows:
        rows_by_metric.setdefault(row.metric, []).append(row)
    for metric in GOLD_METRICS:
        bucket = rows_by_metric.get(metric, [])
        m_matches = sum(1 for r in bucket if r.match)
        m_total = len(bucket)
        m_accuracy = _accuracy(m_matches, m_total)
        print(
            f"  {metric:<20s} {m_accuracy:>6.1%}  ({m_matches}/{m_total})"
        )
    print("=" * 60)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_output_paths(output_dir: Path) -> tuple[Path, Path]:
    """Return ``(csv_path, md_path)`` with a shared timestamp."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = output_dir / f"eval_extraction_{stamp}.csv"
    md_path = output_dir / f"eval_extraction_{stamp}.md"
    return csv_path, md_path


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="eval_extraction.py",
        description=(
            "Evalúa el extractor estructurado L3 contra el gold standard "
            "y genera CSV + Markdown bajo experiments/output/."
        ),
    )
    parser.add_argument(
        "--gold-path",
        type=Path,
        default=DEFAULT_GOLD_PATH,
        help=(
            f"Ruta del Excel de gold standard "
            f"(por defecto: {DEFAULT_GOLD_PATH.relative_to(_PROJECT_ROOT)})."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=(
            f"Directorio de salida "
            f"(por defecto: {DEFAULT_OUTPUT_DIR.relative_to(_PROJECT_ROOT)})."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""
    args = _parse_args(argv)

    # Load global config + .env before touching EDGAR; the L1 client
    # reads ``SEC_USER_AGENT`` via ``agents._config.get_env``.
    load_config()

    gold_path: Path = args.gold_path
    output_dir: Path = args.output_dir

    rows = run_evaluation(gold_path)

    csv_path, md_path = _build_output_paths(output_dir)
    write_csv(rows, csv_path)
    write_markdown_report(rows, md_path, csv_path=csv_path)

    _LOGGER.info("CSV escrito en %s", csv_path)
    _LOGGER.info("Markdown escrito en %s", md_path)

    _print_console_summary(rows)
    print(f"\nCSV : {csv_path}")
    print(f"MD  : {md_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CSV_FIELDNAMES",
    "DEFAULT_GOLD_PATH",
    "DEFAULT_OUTPUT_DIR",
    "EvalRow",
    "evaluate_ticker",
    "main",
    "run_evaluation",
    "write_csv",
    "write_markdown_report",
]
