"""Tests for experiments/make_figures.py — numbers come from CSV, not hardcoded."""

from __future__ import annotations

import csv
import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "make_figures",
    Path(__file__).resolve().parents[1] / "experiments" / "make_figures.py",
)
make_figures = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(make_figures)


_FIELDS = ["ticker", "metric", "gold_value", "predicted_value", "match"]


def _write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def test_load_accuracy_by_metric_counts(tmp_path):
    csv_path = tmp_path / "eval_extraction_20260101_000000.csv"
    _write_csv(csv_path, [
        {"ticker": "AAPL", "metric": "revenue", "gold_value": "1", "predicted_value": "1", "match": "True"},
        {"ticker": "MSFT", "metric": "revenue", "gold_value": "2", "predicted_value": "9", "match": "False"},
        {"ticker": "AAPL", "metric": "net_income", "gold_value": "3", "predicted_value": "3", "match": "True"},
        # cash is not a core metric -> ignored
        {"ticker": "AAPL", "metric": "cash", "gold_value": "4", "predicted_value": "4", "match": "True"},
    ])
    by_metric = make_figures.load_accuracy_by_metric(csv_path)
    assert by_metric["revenue"] == (1, 2)
    assert by_metric["net_income"] == (1, 1)
    assert "cash" not in by_metric


def test_overall_accuracy(tmp_path):
    csv_path = tmp_path / "eval_extraction_20260101_000000.csv"
    _write_csv(csv_path, [
        {"ticker": "AAPL", "metric": "revenue", "gold_value": "1", "predicted_value": "1", "match": "True"},
        {"ticker": "MSFT", "metric": "revenue", "gold_value": "2", "predicted_value": "9", "match": "False"},
    ])
    assert make_figures.load_overall_accuracy(csv_path) == 0.5


def test_latest_csv_picks_most_recent(tmp_path):
    (tmp_path / "eval_extraction_20260101_000000.csv").write_text("x")
    newest = tmp_path / "eval_extraction_20260601_120000.csv"
    newest.write_text("y")
    assert make_figures._latest_csv("eval_extraction", output_dir=tmp_path) == newest


def test_write_results_tex_emits_table(tmp_path):
    rows = [{"ticker": "AAPL", "metric": "revenue", "gold_value": "1",
             "predicted_value": "1", "match": "True"}]
    p = tmp_path / "e.csv"
    _write_csv(p, rows)
    out = make_figures.write_results_tex(p, p, p, out_path=tmp_path / "results.tex")
    text = out.read_text()
    assert "\\begin{tabular}" in text
    assert "Global" in text
    assert "AUTO-GENERATED" in text
