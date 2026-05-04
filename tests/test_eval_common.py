"""Tests for ``experiments._eval_common``.

Covers the gold-standard reader (load_gold_standard) and the numeric
comparator (compare_values). The reader is exercised against a tiny
synthetic workbook built in a tmp dir; we never touch the real
``data/gold_standard.xlsx``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from openpyxl import Workbook

from agents._gold_schema import GOLD_COLUMNS
from experiments._eval_common import (
    GOLD_SHEET_NAME,
    GoldEntry,
    compare_values,
    load_gold_standard,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_workbook(path: Path, rows: list[tuple[Any, ...]]) -> None:
    """Create a minimal gold-standard workbook with the given rows."""
    wb = Workbook()
    sheet = wb.active
    sheet.title = GOLD_SHEET_NAME
    sheet.append(list(GOLD_COLUMNS))
    for row in rows:
        sheet.append(list(row))
    wb.save(path)


# ---------------------------------------------------------------------------
# compare_values
# ---------------------------------------------------------------------------


class TestCompareValuesBothNull:
    def test_both_null_is_match(self):
        match, abs_err, rel_err = compare_values(None, None)
        assert match is True
        assert abs_err is None
        assert rel_err is None


class TestCompareValuesOneSideNull:
    def test_gold_null_predicted_numeric_is_mismatch(self):
        # L3 hallucinated a value where the gold says it shouldn't exist.
        match, abs_err, rel_err = compare_values(None, 1_000_000.0)
        assert match is False
        # No abs/rel error is meaningful when gold is None.
        assert abs_err is None
        assert rel_err is None

    def test_gold_numeric_predicted_null_is_mismatch_with_abs_error(self):
        # L3 missed a value that the gold standard has.
        match, abs_err, rel_err = compare_values(391_035_000_000.0, None)
        assert match is False
        assert abs_err == 391_035_000_000.0
        assert rel_err is None


class TestCompareValuesNumericTolerance:
    def test_within_default_tolerance_is_match(self):
        # 391.035B vs 391.0349B → 0.0003% diff, well below 0.5%.
        match, abs_err, rel_err = compare_values(
            391_035_000_000.0, 391_034_900_000.0,
        )
        assert match is True
        assert abs_err is not None and abs_err == pytest.approx(100_000.0)
        assert rel_err is not None and rel_err < 0.005

    def test_outside_default_tolerance_is_mismatch(self):
        # 391.035B vs 400B → ~2.3% diff, well above 0.5%.
        match, abs_err, rel_err = compare_values(
            391_035_000_000.0, 400_000_000_000.0,
        )
        assert match is False
        assert abs_err is not None and abs_err > 0
        assert rel_err is not None and rel_err > 0.005

    def test_zero_gold_only_matches_exact_zero(self):
        # Pathological edge: gold is exactly zero. Only an exact-zero
        # prediction is a match (no relative tolerance possible).
        match, abs_err, rel_err = compare_values(0.0, 0.0)
        assert match is True
        assert abs_err == 0.0
        assert rel_err is None

        match2, _, _ = compare_values(0.0, 0.001)
        assert match2 is False

    def test_custom_tolerance_overrides_default(self):
        # 1% tolerance accepts a 0.6% difference that the default would reject.
        gold = 100.0
        predicted = 100.6
        match_default, _, _ = compare_values(gold, predicted)
        assert match_default is False
        match_loose, _, _ = compare_values(gold, predicted, rel_tol=0.01)
        assert match_loose is True


# ---------------------------------------------------------------------------
# load_gold_standard
# ---------------------------------------------------------------------------


class TestLoadGoldStandardHappyPath:
    def test_loads_numeric_and_null_rows_correctly(self, tmp_path: Path):
        path = tmp_path / "gold.xlsx"
        _write_workbook(
            path,
            [
                ("AAPL", 2025, "revenue", 416_161_000_000, "USD",
                 "CONSOLIDATED STATEMENTS OF OPERATIONS",
                 "Total net sales line"),
                ("JPM", 2025, "operating_income", "null", "USD",
                 "CONSOLIDATED STATEMENTS OF INCOME", "JPM no reporta"),
                ("AAPL", 2025, "eps_diluted", 7.46, "USD/share",
                 "CONSOLIDATED STATEMENTS OF OPERATIONS", "Diluted not Basic"),
            ],
        )

        entries = load_gold_standard(path)

        assert ("AAPL", "revenue") in entries
        assert ("JPM", "operating_income") in entries
        assert ("AAPL", "eps_diluted") in entries

        rev = entries[("AAPL", "revenue")]
        assert isinstance(rev, GoldEntry)
        assert rev.value == 416_161_000_000.0
        assert rev.fiscal_year == 2025
        assert rev.unit == "USD"
        assert rev.source_page == "CONSOLIDATED STATEMENTS OF OPERATIONS"
        assert rev.notes == "Total net sales line"

        nullish = entries[("JPM", "operating_income")]
        assert nullish.value is None  # sentinel coerced to None
        assert nullish.fiscal_year == 2025

        eps = entries[("AAPL", "eps_diluted")]
        assert eps.value == 7.46
        assert eps.unit == "USD/share"

    def test_skips_completely_empty_trailing_rows(self, tmp_path: Path):
        path = tmp_path / "gold.xlsx"
        _write_workbook(
            path,
            [
                ("AAPL", 2025, "revenue", 416_161_000_000, "USD", "p1", ""),
                (None, None, None, None, None, None, None),
            ],
        )

        entries = load_gold_standard(path)
        assert ("AAPL", "revenue") in entries
        assert len(entries) == 1


class TestLoadGoldStandardErrors:
    def test_missing_file_raises_filenotfounderror(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_gold_standard(tmp_path / "no-existe.xlsx")

    def test_unknown_ticker_raises_valueerror(self, tmp_path: Path):
        path = tmp_path / "gold.xlsx"
        _write_workbook(
            path,
            [
                ("ZZZZ", 2025, "revenue", 1_000_000, "USD", "p1", ""),
            ],
        )
        with pytest.raises(ValueError, match="ticker="):
            load_gold_standard(path)

    def test_unknown_metric_raises_valueerror(self, tmp_path: Path):
        path = tmp_path / "gold.xlsx"
        _write_workbook(
            path,
            [
                ("AAPL", 2025, "ebitda_super_secret", 1_000_000, "USD", "p1", ""),
            ],
        )
        with pytest.raises(ValueError, match="metric="):
            load_gold_standard(path)

    def test_invalid_value_raises_valueerror_with_row_context(self, tmp_path: Path):
        path = tmp_path / "gold.xlsx"
        _write_workbook(
            path,
            [
                ("AAPL", 2025, "revenue", "not-a-number", "USD", "p1", ""),
            ],
        )
        # The error must mention the row + ticker + metric so the
        # annotator can locate it manually.
        with pytest.raises(ValueError, match="ticker=AAPL"):
            load_gold_standard(path)

    def test_wrong_header_raises_valueerror(self, tmp_path: Path):
        path = tmp_path / "gold.xlsx"
        wb = Workbook()
        sheet = wb.active
        sheet.title = GOLD_SHEET_NAME
        sheet.append(["wrong", "header", "row"])
        sheet.append(["AAPL", 2025, "revenue"])
        wb.save(path)
        with pytest.raises(ValueError, match="Cabecera"):
            load_gold_standard(path)
