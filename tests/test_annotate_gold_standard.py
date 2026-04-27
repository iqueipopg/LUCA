"""Tests for ``scripts.annotate_gold_standard``.

The module is loaded by file path because ``scripts/`` is not a Python
package in this project (no ``__init__.py``); using ``importlib`` keeps
the import contract identical to running the file directly.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest
from openpyxl import load_workbook

from agents._gold_schema import (
    GOLD_COLUMNS,
    GOLD_METRICS,
    GOLD_ROW_COUNT,
    GOLD_TICKERS,
)


# ---------------------------------------------------------------------------
# Module loading
# ---------------------------------------------------------------------------


_SCRIPT_PATH: Path = (
    Path(__file__).resolve().parent.parent
    / "scripts"
    / "annotate_gold_standard.py"
)


def _load_module() -> ModuleType:
    """Import the script as a module without polluting ``sys.modules``."""
    spec = importlib.util.spec_from_file_location(
        "annotate_gold_standard_under_test", _SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def annotate_module() -> ModuleType:
    return _load_module()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_dict(sheet, excel_row: int) -> dict[str, object]:
    """Read a row by Excel row index and return a name→value dict."""
    return {
        name: sheet.cell(row=excel_row, column=idx + 1).value
        for idx, name in enumerate(GOLD_COLUMNS)
    }


def _write_row(sheet, excel_row: int, **values) -> None:
    """Overwrite a sheet row with the given column values."""
    for idx, name in enumerate(GOLD_COLUMNS):
        sheet.cell(row=excel_row, column=idx + 1).value = values.get(name)


# ---------------------------------------------------------------------------
# init
# ---------------------------------------------------------------------------


class TestInit:
    def test_init_creates_workbook_with_header_and_60_rows(
        self, tmp_path: Path, annotate_module: ModuleType
    ) -> None:
        """init() must create a workbook with one header + 60 skeleton rows."""
        path = tmp_path / "gold.xlsx"

        created = annotate_module.init_workbook(path)
        assert created is True
        assert path.exists()

        wb = load_workbook(path, data_only=True)
        assert annotate_module.SHEET_NAME in wb.sheetnames
        sheet = wb[annotate_module.SHEET_NAME]

        # Header row matches the canonical column order.
        header = tuple(
            sheet.cell(row=1, column=idx + 1).value
            for idx in range(len(GOLD_COLUMNS))
        )
        assert header == GOLD_COLUMNS

        # Exactly GOLD_ROW_COUNT data rows after the header.
        data_rows = sheet.max_row - 1
        assert data_rows == GOLD_ROW_COUNT == 60

        # Every (ticker, metric) pair appears exactly once and the rest of
        # the columns are empty (no pre-fill).
        seen: set[tuple[str, str]] = set()
        for excel_row in range(2, sheet.max_row + 1):
            row = _row_dict(sheet, excel_row)
            assert row["ticker"] in GOLD_TICKERS
            assert row["metric"] in GOLD_METRICS
            seen.add((row["ticker"], row["metric"]))

            for col in ("fiscal_year", "value", "unit", "source_page", "notes"):
                assert row[col] in (None, ""), (
                    f"La columna {col!r} debe quedar vacía en init "
                    f"(fila {excel_row}, valor {row[col]!r})"
                )

        expected = {(t, m) for t in GOLD_TICKERS for m in GOLD_METRICS}
        assert seen == expected

    def test_init_does_not_overwrite_existing_file(
        self, tmp_path: Path, annotate_module: ModuleType
    ) -> None:
        """A second init() call must leave the file untouched."""
        path = tmp_path / "gold.xlsx"

        assert annotate_module.init_workbook(path) is True

        # Pretend the user has started annotating: write a value into row 2.
        wb = load_workbook(path)
        sheet = wb[annotate_module.SHEET_NAME]
        sheet.cell(row=2, column=GOLD_COLUMNS.index("value") + 1).value = 123456789
        wb.save(path)

        # Second call: must return False AND must not clobber the value.
        created_again = annotate_module.init_workbook(path)
        assert created_again is False

        wb2 = load_workbook(path, data_only=True)
        sheet2 = wb2[annotate_module.SHEET_NAME]
        assert (
            sheet2.cell(row=2, column=GOLD_COLUMNS.index("value") + 1).value
            == 123456789
        )


# ---------------------------------------------------------------------------
# validate
# ---------------------------------------------------------------------------


class TestValidate:
    def test_validate_flags_skeleton_rows_as_empty(
        self, tmp_path: Path, annotate_module: ModuleType
    ) -> None:
        """Right after init(), every row is unannotated."""
        path = tmp_path / "gold.xlsx"
        annotate_module.init_workbook(path)

        report = annotate_module.validate_workbook(path)

        assert report.total_rows == GOLD_ROW_COUNT
        assert report.annotated_rows == 0
        assert report.empty_rows == GOLD_ROW_COUNT
        assert report.invalid_rows == 0
        assert not report.is_clean
        # One issue per empty row, all carrying the same reason.
        assert len(report.issues) == GOLD_ROW_COUNT
        assert all(issue.reason == "fila sin anotar" for issue in report.issues)

    def test_validate_accepts_well_formed_rows(
        self, tmp_path: Path, annotate_module: ModuleType
    ) -> None:
        """A workbook with all rows correctly annotated is reported clean."""
        path = tmp_path / "gold.xlsx"
        annotate_module.init_workbook(path)

        wb = load_workbook(path)
        sheet = wb[annotate_module.SHEET_NAME]
        for excel_row in range(2, sheet.max_row + 1):
            row = _row_dict(sheet, excel_row)
            _write_row(
                sheet,
                excel_row,
                ticker=row["ticker"],
                metric=row["metric"],
                fiscal_year=2024,
                value=1234.5,
                unit="USD millions",
                source_page=42,
                notes="anotado a mano",
            )
        wb.save(path)

        report = annotate_module.validate_workbook(path)

        assert report.is_clean
        assert report.annotated_rows == GOLD_ROW_COUNT
        assert report.empty_rows == 0
        assert report.invalid_rows == 0
        assert report.issues == ()

    def test_validate_flags_invalid_types(
        self, tmp_path: Path, annotate_module: ModuleType
    ) -> None:
        """Wrong types in a *partially* annotated row count as invalid."""
        path = tmp_path / "gold.xlsx"
        annotate_module.init_workbook(path)

        wb = load_workbook(path)
        sheet = wb[annotate_module.SHEET_NAME]

        # Row 2: value is a string, fiscal_year is malformed, source_page missing.
        _write_row(
            sheet,
            2,
            ticker="AAPL",
            metric="revenue",
            fiscal_year="dosmilveinticuatro",
            value="trescientos",
            unit="USD millions",
            source_page=None,
            notes="",
        )
        wb.save(path)

        report = annotate_module.validate_workbook(path)

        assert report.invalid_rows == 1
        # Skeleton-empty rows for the rest still contribute to empty_rows.
        assert report.empty_rows == GOLD_ROW_COUNT - 1

        row2_issues = [i for i in report.issues if i.excel_row == 2]
        reasons = " | ".join(i.reason for i in row2_issues)
        assert "fiscal_year" in reasons
        assert "value" in reasons
        assert "source_page" in reasons


# ---------------------------------------------------------------------------
# main() / CLI exit codes
# ---------------------------------------------------------------------------


class TestCli:
    def test_cli_init_then_validate_exits_nonzero_on_empty_skeleton(
        self,
        tmp_path: Path,
        annotate_module: ModuleType,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """``init`` exits 0; ``validate`` on an empty skeleton exits 1."""
        path = tmp_path / "gold.xlsx"

        rc_init = annotate_module.main(["--path", str(path), "init"])
        assert rc_init == 0
        assert path.exists()

        rc_validate = annotate_module.main(["--path", str(path), "validate"])
        assert rc_validate == 1  # invalid (empty rows)

        captured = capsys.readouterr().out
        assert "Filas detectadas" in captured

    def test_cli_validate_missing_file_exits_two(
        self,
        tmp_path: Path,
        annotate_module: ModuleType,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Validating a non-existent workbook is a hard error (rc=2)."""
        missing = tmp_path / "nope.xlsx"

        rc = annotate_module.main(["--path", str(missing), "validate"])
        assert rc == 2

        err = capsys.readouterr().err
        assert "Error" in err
