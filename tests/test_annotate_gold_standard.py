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

        # Exactly GOLD_ROW_COUNT data rows after the header. The literal
        # equals ``len(GOLD_TICKERS) * len(GOLD_METRICS)`` so the test
        # tracks the schema automatically as new metrics are added (T2.0c
        # extended GOLD_METRICS from 6 to 8, raising the row count from
        # 60 to 80).
        data_rows = sheet.max_row - 1
        assert data_rows == GOLD_ROW_COUNT
        assert GOLD_ROW_COUNT == len(GOLD_TICKERS) * len(GOLD_METRICS)

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
        """A workbook with all rows correctly annotated is reported clean.

        The unit convention is enforced: the five monetary metrics use
        ``unit == "USD"`` and ``eps_diluted`` uses ``unit == "USD/share"``
        (see ``EXPECTED_UNITS`` in ``agents/_gold_schema.py``).
        """
        from agents._gold_schema import EXPECTED_UNITS

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
                unit=EXPECTED_UNITS[row["metric"]],
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
# Unit-consistency check (added after T1.5 review)
#
# The gold-standard convention (see ``EXPECTED_UNITS`` in
# ``agents/_gold_schema.py``):
#   * the five monetary metrics → ``unit == "USD"``
#   * ``eps_diluted`` → ``unit == "USD/share"``
# Anything else is flagged as invalid with an explicit reason.
# ---------------------------------------------------------------------------


class TestValidateUnits:
    def _seed_skeleton(
        self,
        tmp_path: Path,
        annotate_module: ModuleType,
    ) -> Path:
        """Initialise a fresh skeleton workbook for each unit test."""
        path = tmp_path / "gold.xlsx"
        annotate_module.init_workbook(path)
        return path

    def _annotate_row(
        self,
        path: Path,
        annotate_module: ModuleType,
        excel_row: int,
        *,
        ticker: str,
        metric: str,
        unit: str,
    ) -> None:
        """Overwrite a row with a fully-filled annotation using ``unit``."""
        wb = load_workbook(path)
        sheet = wb[annotate_module.SHEET_NAME]
        _write_row(
            sheet,
            excel_row,
            ticker=ticker,
            metric=metric,
            fiscal_year=2024,
            value=1234.5,
            unit=unit,
            source_page=42,
            notes="anotado a mano",
        )
        wb.save(path)

    def test_monetary_metric_with_usd_is_valid(
        self, tmp_path: Path, annotate_module: ModuleType
    ) -> None:
        """Monetary metric (revenue) with ``unit == "USD"`` must validate."""
        path = self._seed_skeleton(tmp_path, annotate_module)
        self._annotate_row(
            path, annotate_module, excel_row=2,
            ticker="AAPL", metric="revenue", unit="USD",
        )

        report = annotate_module.validate_workbook(path)

        # Row 2 is the only annotated row; it should have no issues.
        row2_issues = [i for i in report.issues if i.excel_row == 2]
        assert row2_issues == []
        assert report.invalid_rows == 0

    def test_monetary_metric_with_thousands_is_invalid(
        self, tmp_path: Path, annotate_module: ModuleType
    ) -> None:
        """Monetary metric with ``unit == "thousands"`` is rejected with a
        reason that names both the expected and the offending unit.
        """
        path = self._seed_skeleton(tmp_path, annotate_module)
        self._annotate_row(
            path, annotate_module, excel_row=2,
            ticker="AAPL", metric="revenue", unit="thousands",
        )

        report = annotate_module.validate_workbook(path)

        row2_issues = [i for i in report.issues if i.excel_row == 2]
        assert len(row2_issues) == 1
        reason = row2_issues[0].reason
        assert "unit incorrecta" in reason
        assert "'USD'" in reason
        assert "'thousands'" in reason
        assert report.invalid_rows == 1

    def test_eps_diluted_with_usd_per_share_is_valid(
        self, tmp_path: Path, annotate_module: ModuleType
    ) -> None:
        """``eps_diluted`` with ``unit == "USD/share"`` must validate."""
        path = self._seed_skeleton(tmp_path, annotate_module)
        self._annotate_row(
            path, annotate_module, excel_row=2,
            ticker="AAPL", metric="eps_diluted", unit="USD/share",
        )

        report = annotate_module.validate_workbook(path)

        row2_issues = [i for i in report.issues if i.excel_row == 2]
        assert row2_issues == []
        assert report.invalid_rows == 0

    def test_eps_diluted_with_plain_usd_is_invalid(
        self, tmp_path: Path, annotate_module: ModuleType
    ) -> None:
        """``eps_diluted`` annotated as plain ``"USD"`` (instead of
        ``"USD/share"``) is rejected with an explicit reason.
        """
        path = self._seed_skeleton(tmp_path, annotate_module)
        self._annotate_row(
            path, annotate_module, excel_row=2,
            ticker="AAPL", metric="eps_diluted", unit="USD",
        )

        report = annotate_module.validate_workbook(path)

        row2_issues = [i for i in report.issues if i.excel_row == 2]
        assert len(row2_issues) == 1
        reason = row2_issues[0].reason
        assert "unit incorrecta" in reason
        assert "'USD/share'" in reason
        assert "'USD'" in reason
        assert report.invalid_rows == 1


# ---------------------------------------------------------------------------
# Encoding conventions surfaced during T1.2 (annotation of the 10 tickers)
#
# Two real-world annotation conventions adopted by the user:
#   * ``source_page`` as a statement-name string (e.g. "CONSOLIDATED
#     STATEMENTS OF OPERATIONS") instead of a PDF page number.
#   * ``value == "null"`` (NULL_SENTINEL) for metrics that are
#     **structurally** absent for a filer (JPM operating_income because
#     SIC 6022 lacks ``OperatingIncomeLoss``; JNJ operating_income
#     because the company chooses not to publish that subtotal).
# ---------------------------------------------------------------------------


class TestEncodingConventions:
    def _seed_skeleton(
        self,
        tmp_path: Path,
        annotate_module: ModuleType,
    ) -> Path:
        path = tmp_path / "gold.xlsx"
        annotate_module.init_workbook(path)
        return path

    def test_validate_accepts_source_page_as_statement_name(
        self, tmp_path: Path, annotate_module: ModuleType
    ) -> None:
        """A statement-name string in ``source_page`` is a valid
        annotation (more useful than PDF page numbers, which shift
        across filings).
        """
        path = self._seed_skeleton(tmp_path, annotate_module)

        wb = load_workbook(path)
        sheet = wb[annotate_module.SHEET_NAME]
        _write_row(
            sheet,
            2,
            ticker="AAPL",
            metric="revenue",
            fiscal_year=2025,
            value=391_035_000_000,
            unit="USD",
            source_page="CONSOLIDATED STATEMENTS OF OPERATIONS",
            notes="anotado a mano",
        )
        wb.save(path)

        report = annotate_module.validate_workbook(path)

        row2_issues = [i for i in report.issues if i.excel_row == 2]
        assert row2_issues == [], (
            f"source_page como nombre de statement debe validar, fue {row2_issues!r}"
        )
        assert report.invalid_rows == 0

    def test_validate_accepts_null_sentinel_for_structurally_absent_metric(
        self, tmp_path: Path, annotate_module: ModuleType
    ) -> None:
        """``value == "null"`` is the sentinel for structurally absent
        metrics (JPM operating_income, JNJ operating_income). Validate
        must accept it as a complete annotation, distinct from a blank
        value cell.
        """
        path = self._seed_skeleton(tmp_path, annotate_module)

        wb = load_workbook(path)
        sheet = wb[annotate_module.SHEET_NAME]
        _write_row(
            sheet,
            2,
            ticker="JPM",
            metric="operating_income",
            fiscal_year=2025,
            value="null",
            unit="USD",
            source_page="CONSOLIDATED STATEMENTS OF INCOME",
            notes="JPM (SIC 6022) no publica OperatingIncomeLoss bajo US-GAAP",
        )
        wb.save(path)

        report = annotate_module.validate_workbook(path)

        row2_issues = [i for i in report.issues if i.excel_row == 2]
        assert row2_issues == [], (
            f"value='null' (sentinel) debe validar, fue {row2_issues!r}"
        )
        assert report.invalid_rows == 0

    def test_validate_null_sentinel_is_case_insensitive(
        self, tmp_path: Path, annotate_module: ModuleType
    ) -> None:
        """``"NULL"`` and ``"Null"`` are accepted equivalently to ``"null"``.
        Lenient with the user typing in different cases."""
        path = self._seed_skeleton(tmp_path, annotate_module)

        wb = load_workbook(path)
        sheet = wb[annotate_module.SHEET_NAME]
        _write_row(
            sheet, 2,
            ticker="JPM", metric="operating_income",
            fiscal_year=2025, value="NULL", unit="USD",
            source_page="CONSOLIDATED STATEMENTS OF INCOME",
            notes="caso límite de mayúsculas",
        )
        _write_row(
            sheet, 3,
            ticker="JNJ", metric="operating_income",
            fiscal_year=2024, value="Null", unit="USD",
            source_page="CONSOLIDATED STATEMENTS OF EARNINGS",
            notes="otra variante de mayúsculas",
        )
        wb.save(path)

        report = annotate_module.validate_workbook(path)

        for row in (2, 3):
            row_issues = [i for i in report.issues if i.excel_row == row]
            assert row_issues == [], f"fila {row} con sentinel debe validar"

    def test_coerce_gold_value_normalises_sentinel_to_none(self) -> None:
        """The helper ``coerce_gold_value`` returns ``None`` for the
        sentinel and a ``float`` for numeric inputs. This is the
        contract T1.8 / T1.9 evaluators must rely on when loading the
        gold standard.
        """
        from agents._gold_schema import coerce_gold_value

        assert coerce_gold_value("null") is None
        assert coerce_gold_value("NULL") is None
        assert coerce_gold_value("  Null  ") is None  # con espacios
        assert coerce_gold_value(391_035_000_000) == 391_035_000_000.0
        assert coerce_gold_value(6.13) == 6.13

        # Cualquier otro string debe romper en lugar de devolver None
        # silenciosamente (eso enmascararía un error de anotación).
        with pytest.raises(ValueError):
            coerce_gold_value("foo")
        with pytest.raises(ValueError):
            coerce_gold_value(None)
        with pytest.raises(ValueError):
            coerce_gold_value(True)


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
