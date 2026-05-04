"""Tests for ``experiments.eval_extraction``.

The L1 ingest and the L3 extract functions are mocked; no test ever
touches EDGAR. We exercise the full flow end-to-end against a tiny
synthetic gold standard and inspect the produced CSV + Markdown
artefacts.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from openpyxl import Workbook

from agents._gold_schema import GOLD_COLUMNS, GOLD_METRICS, GOLD_TICKERS
from experiments._eval_common import GOLD_SHEET_NAME
from experiments.eval_extraction import (
    CSV_FIELDNAMES,
    EvalRow,
    evaluate_ticker,
    run_evaluation,
    write_csv,
    write_markdown_report,
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


def _full_gold_workbook(path: Path, value_overrides: dict | None = None) -> None:
    """Write a complete 60-row gold-standard workbook for testing.

    Default value strategy: every (ticker, metric) gets a unique
    deterministic value derived from the indices, so we can detect
    cross-talk in row matching. ``value_overrides`` lets a test pin
    specific cells.
    """
    overrides = value_overrides or {}
    wb = Workbook()
    sheet = wb.active
    sheet.title = GOLD_SHEET_NAME
    sheet.append(list(GOLD_COLUMNS))
    for t_idx, ticker in enumerate(GOLD_TICKERS, start=1):
        for m_idx, metric in enumerate(GOLD_METRICS, start=1):
            key = (ticker, metric)
            if key in overrides:
                value = overrides[key]
            else:
                # Deterministic fake value, large enough to look real.
                value = (t_idx * 1_000_000_000) + (m_idx * 1_000_000)
            unit = "USD/share" if metric == "eps_diluted" else "USD"
            sheet.append([
                ticker,
                2025,
                metric,
                value,
                unit,
                "STATEMENT",
                f"note-{ticker}-{metric}",
            ])
    wb.save(path)


def _make_extract_output(
    ticker: str,
    *,
    metric_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a fake L3 extract output mirroring the real shape."""
    overrides = metric_overrides or {}
    metrics: dict[str, Any] = {}
    for metric in GOLD_METRICS:
        if metric in overrides:
            metrics[metric] = overrides[metric]
            continue
        # Build a "perfect" extraction matching the deterministic gold value.
        t_idx = GOLD_TICKERS.index(ticker) + 1
        m_idx = GOLD_METRICS.index(metric) + 1
        value = (t_idx * 1_000_000_000) + (m_idx * 1_000_000)
        metrics[metric] = {
            "value": float(value),
            "fiscal_year": 2025,
            "period_end": "2025-12-31",
            "tag_used": f"FakeTag_{metric}",
            "unit": "USD/shares" if metric == "eps_diluted" else "USD",
            "accession": f"0000000000-25-{t_idx:06d}",
        }
    return {
        "company": f"{ticker} Inc.",
        "ticker": ticker,
        "fiscal_year": 2025,
        "metrics": metrics,
    }


def _fake_ingest(ticker: str) -> dict[str, Any]:
    """Stand-in for L1 ingest. Only returns what L3 needs (xbrl_data)."""
    return {
        "company": f"{ticker} Inc.",
        "ticker": ticker,
        "filing_date": "2025-12-31",
        "accession_number": "0000000000-25-000001",
        "html_content": "",
        "xbrl_data": {},
        "cik": "0000000000",
        "source_urls": {},
    }


# ---------------------------------------------------------------------------
# Per-ticker evaluation
# ---------------------------------------------------------------------------


class TestEvaluateTickerHappyPath:
    def test_perfect_match_yields_match_true_and_zero_error(self, tmp_path: Path):
        gold_path = tmp_path / "gold.xlsx"
        _full_gold_workbook(gold_path)
        from experiments._eval_common import load_gold_standard

        gold = load_gold_standard(gold_path)

        rows = evaluate_ticker(
            "AAPL",
            gold,
            ingest_fn=lambda t: _fake_ingest(t),
            extract_fn=lambda ingest_out: _make_extract_output(ingest_out["ticker"]),
        )

        assert len(rows) == len(GOLD_METRICS)
        for row in rows:
            assert row.ticker == "AAPL"
            assert row.match is True
            assert row.predicted_tag_used == f"FakeTag_{row.metric}"
            assert row.predicted_fiscal_year == 2025


class TestEvaluateTickerNullCases:
    def test_gold_null_predicted_null_is_match(self, tmp_path: Path):
        gold_path = tmp_path / "gold.xlsx"
        # Override AAPL operating_income to "null" sentinel.
        _full_gold_workbook(
            gold_path,
            value_overrides={("AAPL", "operating_income"): "null"},
        )
        from experiments._eval_common import load_gold_standard

        gold = load_gold_standard(gold_path)

        # Extractor returns None for operating_income.
        def fake_extract(ingest_out: dict[str, Any]) -> dict[str, Any]:
            base = _make_extract_output(ingest_out["ticker"])
            base["metrics"]["operating_income"] = None
            return base

        rows = evaluate_ticker(
            "AAPL",
            gold,
            ingest_fn=lambda t: _fake_ingest(t),
            extract_fn=fake_extract,
        )

        oi_row = next(r for r in rows if r.metric == "operating_income")
        assert oi_row.gold_value is None
        assert oi_row.predicted_value is None
        assert oi_row.match is True
        assert oi_row.abs_error is None
        assert oi_row.rel_error is None

    def test_gold_null_predicted_numeric_is_mismatch(self, tmp_path: Path):
        gold_path = tmp_path / "gold.xlsx"
        _full_gold_workbook(
            gold_path,
            value_overrides={("AAPL", "operating_income"): "null"},
        )
        from experiments._eval_common import load_gold_standard

        gold = load_gold_standard(gold_path)

        # Extractor hallucinates a value for the absent metric.
        def fake_extract(ingest_out: dict[str, Any]) -> dict[str, Any]:
            base = _make_extract_output(ingest_out["ticker"])
            base["metrics"]["operating_income"] = {
                "value": 12_345_678.0,
                "fiscal_year": 2025,
                "period_end": "2025-12-31",
                "tag_used": "OperatingIncomeLoss",
                "unit": "USD",
                "accession": "0000000000-25-000001",
            }
            return base

        rows = evaluate_ticker(
            "AAPL",
            gold,
            ingest_fn=lambda t: _fake_ingest(t),
            extract_fn=fake_extract,
        )

        oi_row = next(r for r in rows if r.metric == "operating_income")
        assert oi_row.gold_value is None
        assert oi_row.predicted_value == 12_345_678.0
        assert oi_row.match is False
        # Reason: hallucinated value → no abs/rel error.
        assert oi_row.abs_error is None
        assert oi_row.rel_error is None

    def test_gold_numeric_predicted_null_is_mismatch_with_abs_error(
        self, tmp_path: Path
    ):
        gold_path = tmp_path / "gold.xlsx"
        _full_gold_workbook(gold_path)
        from experiments._eval_common import load_gold_standard

        gold = load_gold_standard(gold_path)

        def fake_extract(ingest_out: dict[str, Any]) -> dict[str, Any]:
            base = _make_extract_output(ingest_out["ticker"])
            base["metrics"]["revenue"] = None
            return base

        rows = evaluate_ticker(
            "AAPL",
            gold,
            ingest_fn=lambda t: _fake_ingest(t),
            extract_fn=fake_extract,
        )

        rev_row = next(r for r in rows if r.metric == "revenue")
        assert rev_row.predicted_value is None
        assert rev_row.match is False
        assert rev_row.abs_error == abs(rev_row.gold_value)


class TestEvaluateTickerTolerance:
    def test_within_tolerance_is_match(self, tmp_path: Path):
        gold_path = tmp_path / "gold.xlsx"
        _full_gold_workbook(
            gold_path,
            value_overrides={("AAPL", "revenue"): 391_035_000_000},
        )
        from experiments._eval_common import load_gold_standard

        gold = load_gold_standard(gold_path)

        def fake_extract(ingest_out: dict[str, Any]) -> dict[str, Any]:
            base = _make_extract_output(ingest_out["ticker"])
            base["metrics"]["revenue"] = {
                "value": 391_034_900_000.0,  # 0.0003% off
                "fiscal_year": 2025,
                "period_end": "2025-12-31",
                "tag_used": "Revenues",
                "unit": "USD",
                "accession": "x",
            }
            return base

        rows = evaluate_ticker(
            "AAPL",
            gold,
            ingest_fn=lambda t: _fake_ingest(t),
            extract_fn=fake_extract,
        )

        rev_row = next(r for r in rows if r.metric == "revenue")
        assert rev_row.match is True
        assert rev_row.rel_error is not None and rev_row.rel_error < 0.005

    def test_outside_tolerance_is_mismatch(self, tmp_path: Path):
        gold_path = tmp_path / "gold.xlsx"
        _full_gold_workbook(
            gold_path,
            value_overrides={("AAPL", "revenue"): 391_035_000_000},
        )
        from experiments._eval_common import load_gold_standard

        gold = load_gold_standard(gold_path)

        def fake_extract(ingest_out: dict[str, Any]) -> dict[str, Any]:
            base = _make_extract_output(ingest_out["ticker"])
            base["metrics"]["revenue"] = {
                "value": 400_000_000_000.0,  # ~2.3% off
                "fiscal_year": 2025,
                "period_end": "2025-12-31",
                "tag_used": "Revenues",
                "unit": "USD",
                "accession": "x",
            }
            return base

        rows = evaluate_ticker(
            "AAPL",
            gold,
            ingest_fn=lambda t: _fake_ingest(t),
            extract_fn=fake_extract,
        )

        rev_row = next(r for r in rows if r.metric == "revenue")
        assert rev_row.match is False
        assert rev_row.rel_error is not None and rev_row.rel_error > 0.005


# ---------------------------------------------------------------------------
# Full pipeline: run_evaluation + write_csv + write_markdown_report
# ---------------------------------------------------------------------------


class TestRunEvaluationFullFlow:
    def test_perfect_run_produces_csv_and_md_with_full_accuracy(
        self, tmp_path: Path
    ):
        gold_path = tmp_path / "gold.xlsx"
        _full_gold_workbook(gold_path)

        rows = run_evaluation(
            gold_path,
            ingest_fn=_fake_ingest,
            extract_fn=lambda ingest_out: _make_extract_output(
                ingest_out["ticker"]
            ),
        )

        assert len(rows) == len(GOLD_TICKERS) * len(GOLD_METRICS)
        assert all(r.match for r in rows)

        csv_path = tmp_path / "out.csv"
        md_path = tmp_path / "out.md"
        write_csv(rows, csv_path)
        write_markdown_report(rows, md_path, csv_path=csv_path)

        # --- CSV --------------------------------------------------------
        with csv_path.open("r", encoding="utf-8", newline="") as fh:
            reader = csv.DictReader(fh)
            assert reader.fieldnames is not None
            assert tuple(reader.fieldnames) == CSV_FIELDNAMES
            csv_rows = list(reader)
        assert len(csv_rows) == len(rows)
        assert all(row["match"] == "True" for row in csv_rows)

        # --- Markdown ---------------------------------------------------
        md = md_path.read_text(encoding="utf-8")
        assert "Accuracy global" in md
        assert "100.0%" in md
        # Each metric and ticker appears as a section header.
        for metric in GOLD_METRICS:
            assert f"`{metric}`" in md
        for ticker in GOLD_TICKERS:
            assert f"### {ticker} —" in md
        # Tag distribution section is present.
        assert "Distribución de `tag_used`" in md

    def test_imperfect_run_reflects_mixed_accuracy_in_outputs(
        self, tmp_path: Path
    ):
        gold_path = tmp_path / "gold.xlsx"
        _full_gold_workbook(gold_path)

        # Make every revenue extraction a mismatch (off by 50%).
        def fake_extract(ingest_out: dict[str, Any]) -> dict[str, Any]:
            base = _make_extract_output(ingest_out["ticker"])
            rev = base["metrics"]["revenue"]
            rev["value"] = rev["value"] * 0.5
            return base

        rows = run_evaluation(
            gold_path,
            ingest_fn=_fake_ingest,
            extract_fn=fake_extract,
        )

        misses = [r for r in rows if not r.match]
        assert len(misses) == len(GOLD_TICKERS)  # one revenue miss per ticker
        assert all(r.metric == "revenue" for r in misses)

        csv_path = tmp_path / "out.csv"
        md_path = tmp_path / "out.md"
        write_csv(rows, csv_path)
        write_markdown_report(rows, md_path, csv_path=csv_path)

        md = md_path.read_text(encoding="utf-8")
        # Aggregate accuracy is not 100% anymore.
        assert "100.0%" not in md.split("Resumen agregado")[1].split("##")[0]
        # The revenue section reflects the lower accuracy.
        assert "MISS" in md


class TestEvalRowCsvSerialisation:
    def test_eval_row_serialises_none_as_empty_string(self):
        row = EvalRow(
            ticker="JPM",
            metric="operating_income",
            gold_value=None,
            gold_fiscal_year=2025,
            predicted_value=None,
            predicted_fiscal_year=None,
            predicted_period_end=None,
            predicted_tag_used=None,
            predicted_accession=None,
            predicted_unit=None,
            match=True,
            abs_error=None,
            rel_error=None,
            notes_gold="",
        )
        out = row.as_csv_dict()
        assert out["gold_value"] == ""
        assert out["predicted_value"] == ""
        assert out["predicted_tag_used"] == ""
        assert out["match"] == "True"
        assert out["abs_error"] == ""
        assert out["rel_error"] == ""


# ---------------------------------------------------------------------------
# Sanity: skipped row when gold lacks an entry for one (ticker, metric)
# ---------------------------------------------------------------------------


class TestEvaluateTickerSkipsMissingGoldEntries:
    def test_missing_pair_is_logged_and_skipped(self, tmp_path: Path, caplog):
        # Gold workbook only has one row for AAPL revenue. The other
        # five AAPL metrics are absent from the gold map; evaluate_ticker
        # must skip them rather than raise.
        path = tmp_path / "gold.xlsx"
        wb = Workbook()
        sheet = wb.active
        sheet.title = GOLD_SHEET_NAME
        sheet.append(list(GOLD_COLUMNS))
        sheet.append(["AAPL", 2025, "revenue", 416_161_000_000, "USD",
                      "STATEMENT", "only-row"])
        wb.save(path)

        from experiments._eval_common import load_gold_standard

        gold = load_gold_standard(path)
        assert len(gold) == 1

        # Stub extract returns the matching value for revenue.
        def fake_extract(ingest_out: dict[str, Any]) -> dict[str, Any]:
            return {
                "company": "Apple Inc.",
                "ticker": "AAPL",
                "fiscal_year": 2025,
                "metrics": {
                    "revenue": {
                        "value": 416_161_000_000.0,
                        "fiscal_year": 2025,
                        "period_end": "2025-09-27",
                        "tag_used": "Revenues",
                        "unit": "USD",
                        "accession": "x",
                    },
                    "net_income": None,
                    "operating_income": None,
                    "total_assets": None,
                    "total_equity": None,
                    "eps_diluted": None,
                },
            }

        rows = evaluate_ticker(
            "AAPL",
            gold,
            ingest_fn=lambda t: _fake_ingest(t),
            extract_fn=fake_extract,
        )
        # Only one row produced — for the only annotated pair.
        assert len(rows) == 1
        assert rows[0].metric == "revenue"
        assert rows[0].match is True
