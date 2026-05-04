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


# ---------------------------------------------------------------------------
# extend (T2.0d): grow the workbook schema in-place without touching
# already-annotated rows. Used when GOLD_TICKERS or GOLD_METRICS expands.
# ---------------------------------------------------------------------------


class TestExtend:
    """Contract tests for the ``extend`` subcommand.

    Strategy: ``annotate_gold_standard.py`` imports ``GOLD_TICKERS`` and
    ``GOLD_METRICS`` directly into its namespace, so monkeypatching the
    loaded module's attributes lets us simulate "schema grew" without
    needing to mutate the canonical constants in ``agents._gold_schema``
    or touching the real workbook on disk.
    """

    def _seed_with_schema(
        self,
        tmp_path: Path,
        annotate_module: ModuleType,
        monkeypatch: pytest.MonkeyPatch,
        tickers: tuple[str, ...],
        metrics: tuple[str, ...],
    ) -> Path:
        """Create a fresh workbook using a *reduced* schema.

        Patches the module-level ``GOLD_TICKERS`` and ``GOLD_METRICS``
        before calling ``init_workbook`` so the resulting skeleton
        reflects ``tickers × metrics`` only.
        """
        path = tmp_path / "gold.xlsx"
        monkeypatch.setattr(annotate_module, "GOLD_TICKERS", tickers)
        monkeypatch.setattr(annotate_module, "GOLD_METRICS", metrics)
        annotate_module.init_workbook(path)
        return path

    def test_extend_appends_missing_rows(
        self,
        tmp_path: Path,
        annotate_module: ModuleType,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Growing GOLD_METRICS adds one row per existing ticker × new metric.

        The fake metric ``"test_metric"`` is appended to the schema after
        ``init`` writes the smaller skeleton; ``extend_workbook`` must
        detect the gap and append exactly ``len(tickers)`` new rows.
        """
        tickers = ("AAPL", "MSFT", "GOOGL")
        initial_metrics = ("revenue", "net_income")
        path = self._seed_with_schema(
            tmp_path, annotate_module, monkeypatch, tickers, initial_metrics
        )

        # Sanity: the skeleton has 3 × 2 = 6 data rows before extend.
        wb = load_workbook(path, data_only=True)
        sheet = wb[annotate_module.SHEET_NAME]
        assert sheet.max_row - 1 == len(tickers) * len(initial_metrics)

        # Schema grows: add a new metric.
        extended_metrics = initial_metrics + ("test_metric",)
        monkeypatch.setattr(annotate_module, "GOLD_METRICS", extended_metrics)

        added = annotate_module.extend_workbook(path)

        expected_added = tuple((t, "test_metric") for t in tickers)
        assert added == expected_added

        wb2 = load_workbook(path, data_only=True)
        sheet2 = wb2[annotate_module.SHEET_NAME]
        assert sheet2.max_row - 1 == len(tickers) * len(extended_metrics)

        # Header is preserved.
        header = tuple(
            sheet2.cell(row=1, column=idx + 1).value
            for idx in range(len(GOLD_COLUMNS))
        )
        assert header == GOLD_COLUMNS

        # Each new row is a skeleton: only ticker + metric filled.
        new_rows_start = len(tickers) * len(initial_metrics) + 2  # +1 header, +1 first new
        for offset, (ticker, metric) in enumerate(expected_added):
            excel_row = new_rows_start + offset
            row = _row_dict(sheet2, excel_row)
            assert row["ticker"] == ticker
            assert row["metric"] == metric
            for col in ("fiscal_year", "value", "unit", "source_page", "notes"):
                assert row[col] in (None, ""), (
                    f"La columna {col!r} debe quedar vacía en extend "
                    f"(fila {excel_row}, valor {row[col]!r})"
                )

    def test_extend_is_idempotent(
        self,
        tmp_path: Path,
        annotate_module: ModuleType,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Two consecutive ``extend`` calls leave the workbook stable.

        Contract: the second call must return an empty tuple and must
        not change the row count nor the header. Re-opening the
        workbook after both calls must still succeed (structurally
        intact).
        """
        tickers = ("AAPL", "MSFT")
        initial_metrics = ("revenue",)
        path = self._seed_with_schema(
            tmp_path, annotate_module, monkeypatch, tickers, initial_metrics
        )

        # Grow schema by one metric.
        extended_metrics = initial_metrics + ("net_income",)
        monkeypatch.setattr(annotate_module, "GOLD_METRICS", extended_metrics)

        first = annotate_module.extend_workbook(path)
        assert len(first) == len(tickers)  # one row per ticker for the new metric

        wb_after_first = load_workbook(path, data_only=True)
        sheet_after_first = wb_after_first[annotate_module.SHEET_NAME]
        rows_after_first = sheet_after_first.max_row

        # Second call: schema unchanged, nothing new to append.
        second = annotate_module.extend_workbook(path)
        assert second == ()

        wb_after_second = load_workbook(path, data_only=True)
        sheet_after_second = wb_after_second[annotate_module.SHEET_NAME]
        assert sheet_after_second.max_row == rows_after_first, (
            "extend no debe añadir filas en una segunda ejecución"
        )

        # Header still intact (workbook structurally usable).
        header = tuple(
            sheet_after_second.cell(row=1, column=idx + 1).value
            for idx in range(len(GOLD_COLUMNS))
        )
        assert header == GOLD_COLUMNS

    def test_extend_does_not_modify_annotated_rows(
        self,
        tmp_path: Path,
        annotate_module: ModuleType,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Pre-annotated rows must survive ``extend`` byte-for-byte.

        After init we hand-fill row 2 with realistic annotation values,
        grow the schema, run ``extend``, and re-read row 2 to confirm
        every column matches the original input.
        """
        tickers = ("AAPL", "MSFT")
        initial_metrics = ("revenue",)
        path = self._seed_with_schema(
            tmp_path, annotate_module, monkeypatch, tickers, initial_metrics
        )

        # Pre-annotate row 2 (AAPL/revenue) with a complete record.
        wb = load_workbook(path)
        sheet = wb[annotate_module.SHEET_NAME]
        original = {
            "ticker": "AAPL",
            "metric": "revenue",
            "fiscal_year": 2025,
            "value": 391_035_000_000,
            "unit": "USD",
            "source_page": "CONSOLIDATED STATEMENTS OF OPERATIONS",
            "notes": "anotado a mano antes del extend",
        }
        _write_row(sheet, 2, **original)
        wb.save(path)

        # Grow the schema and extend.
        extended_metrics = initial_metrics + ("net_income",)
        monkeypatch.setattr(annotate_module, "GOLD_METRICS", extended_metrics)
        added = annotate_module.extend_workbook(path)
        assert len(added) == len(tickers)

        # Re-open and verify row 2 is byte-for-byte identical.
        wb2 = load_workbook(path, data_only=True)
        sheet2 = wb2[annotate_module.SHEET_NAME]
        row2 = _row_dict(sheet2, 2)
        for col, expected_val in original.items():
            assert row2[col] == expected_val, (
                f"extend modificó la columna {col!r} de la fila anotada "
                f"(esperado {expected_val!r}, encontrado {row2[col]!r})"
            )

    def test_extend_returns_empty_when_nothing_missing(
        self,
        tmp_path: Path,
        annotate_module: ModuleType,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """A workbook already covering the full schema yields no-op extend.

        ``extend_workbook`` must return an empty tuple, and the CLI
        printer must surface the "nada que extender" message.
        """
        tickers = ("AAPL", "MSFT")
        metrics = ("revenue", "net_income")
        path = self._seed_with_schema(
            tmp_path, annotate_module, monkeypatch, tickers, metrics
        )

        added = annotate_module.extend_workbook(path)
        assert added == ()

        # User-facing print must say "nada que extender".
        annotate_module._print_extend(added)
        captured = capsys.readouterr().out
        assert "nada que extender" in captured


# ---------------------------------------------------------------------------
# extend (T2.0d) — additional edge-case tests
# ---------------------------------------------------------------------------


class TestExtendEdgeCases:
    """Edge-case and defensive tests for ``extend_workbook``."""

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _seed_with_schema(
        self,
        tmp_path: Path,
        annotate_module: ModuleType,
        monkeypatch: pytest.MonkeyPatch,
        tickers: tuple[str, ...],
        metrics: tuple[str, ...],
    ) -> Path:
        path = tmp_path / "gold.xlsx"
        monkeypatch.setattr(annotate_module, "GOLD_TICKERS", tickers)
        monkeypatch.setattr(annotate_module, "GOLD_METRICS", metrics)
        annotate_module.init_workbook(path)
        return path

    # ------------------------------------------------------------------
    # test 1 — NULL_SENTINEL in value column counts as "present"
    # ------------------------------------------------------------------

    def test_extend_treats_null_sentinel_value_as_present(
        self,
        tmp_path: Path,
        annotate_module: ModuleType,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A row whose ``value`` cell holds NULL_SENTINEL is already present.

        ``extend_workbook`` must NOT treat it as a missing pair and must not
        append a duplicate skeleton row for that (ticker, metric) combination.
        The function's presence check is based solely on whether ticker and
        metric columns are non-empty strings — value content is irrelevant.
        """
        from agents._gold_schema import NULL_SENTINEL

        tickers = ("AAPL", "MSFT")
        metrics = ("revenue", "operating_income")
        path = self._seed_with_schema(
            tmp_path, annotate_module, monkeypatch, tickers, metrics
        )

        # Annotate row 2 (AAPL/revenue) with NULL_SENTINEL as value — the
        # sentinel indicates the metric is structurally absent for this filer.
        wb = load_workbook(path)
        sheet = wb[annotate_module.SHEET_NAME]
        _write_row(
            sheet,
            2,
            ticker="AAPL",
            metric="revenue",
            fiscal_year=2025,
            value=NULL_SENTINEL,
            unit="USD",
            source_page="CONSOLIDATED STATEMENTS OF OPERATIONS",
            notes="structurally absent",
        )
        wb.save(path)

        # Schema is unchanged: extend should find nothing missing.
        added = annotate_module.extend_workbook(path)

        # The sentinel row must not appear in the added tuple.
        assert ("AAPL", "revenue") not in added, (
            "extend añadió AAPL/revenue a pesar de que ya existía con sentinel"
        )
        # Nothing should be added at all (full schema already covered).
        assert added == (), (
            f"extend debería devolver () pero devolvió {added!r}"
        )

        # Row count must be unchanged (header + initial 4 data rows).
        wb2 = load_workbook(path, data_only=True)
        sheet2 = wb2[annotate_module.SHEET_NAME]
        assert sheet2.max_row == 1 + len(tickers) * len(metrics)

    # ------------------------------------------------------------------
    # test 2 — FileNotFoundError when workbook is missing
    # ------------------------------------------------------------------

    def test_extend_fails_gracefully_when_workbook_missing(
        self,
        tmp_path: Path,
        annotate_module: ModuleType,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """``extend_workbook`` raises ``FileNotFoundError`` for a missing file.

        The error message must reference the path so the user can diagnose
        what to fix. The CLI handler must catch the exception, print to
        stderr, and return exit code 2.
        """
        missing = tmp_path / "no_existe.xlsx"

        # Direct API: must raise FileNotFoundError with a clear message.
        with pytest.raises(FileNotFoundError, match="No se encuentra"):
            annotate_module.extend_workbook(missing)

        # CLI handler: must catch and return rc=2.
        rc = annotate_module.main(["--path", str(missing), "extend"])
        assert rc == 2, f"extend sobre archivo ausente debe devolver rc=2, fue {rc}"

        err = capsys.readouterr().err
        assert "Error" in err, (
            f"El handler de extend debe escribir 'Error' en stderr, fue {err!r}"
        )

    # ------------------------------------------------------------------
    # test 3 — ValueError on corrupted/wrong header
    # ------------------------------------------------------------------

    def test_extend_fails_gracefully_on_wrong_header(
        self,
        tmp_path: Path,
        annotate_module: ModuleType,
    ) -> None:
        """``extend_workbook`` raises ``ValueError`` when the header row differs.

        Build a workbook directly with openpyxl using a header whose first
        column name is changed, simulating a workbook that was manually edited
        or comes from a different version of the schema.
        """
        from openpyxl import Workbook as _Workbook

        path = tmp_path / "bad_header.xlsx"
        wb = _Workbook()
        sheet = wb.active
        sheet.title = annotate_module.SHEET_NAME

        # Write a corrupted header: replace the first column name with
        # something unknown.
        bad_header = ("simbolo",) + GOLD_COLUMNS[1:]  # "simbolo" instead of "ticker"
        sheet.append(list(bad_header))
        sheet.append(["AAPL", 2025, "revenue", 100.0, "USD", 42, ""])
        wb.save(path)

        with pytest.raises(ValueError, match="Cabecera inesperada"):
            annotate_module.extend_workbook(path)

    # ------------------------------------------------------------------
    # test 4 — row with metric but no ticker is treated as NOT present
    # ------------------------------------------------------------------

    def test_extend_handles_row_with_metric_but_no_ticker(
        self,
        tmp_path: Path,
        annotate_module: ModuleType,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A row with an empty ticker and a filled metric is an anomaly.

        Per the ``extend_workbook`` docstring, a row missing either ticker
        or metric does not represent any concrete (ticker, metric) pair and
        is therefore treated as NOT present. ``extend`` must still append
        the canonical skeleton row for that combination and must leave the
        anomalous row untouched.
        """
        tickers = ("AAPL",)
        metrics = ("revenue",)
        path = self._seed_with_schema(
            tmp_path, annotate_module, monkeypatch, tickers, metrics
        )

        # Overwrite the only data row to leave ticker empty (anomaly).
        wb = load_workbook(path)
        sheet = wb[annotate_module.SHEET_NAME]
        # Clear the ticker column; keep metric filled.
        sheet.cell(row=2, column=GOLD_COLUMNS.index("ticker") + 1).value = None
        sheet.cell(row=2, column=GOLD_COLUMNS.index("metric") + 1).value = "revenue"
        wb.save(path)

        # Verify anomaly is in place: there is 1 data row, ticker is None.
        wb_check = load_workbook(path, data_only=True)
        sheet_check = wb_check[annotate_module.SHEET_NAME]
        assert sheet_check.max_row == 2  # header + 1 anomalous row

        # extend should detect AAPL/revenue as missing (anomalous row doesn't
        # count) and append the correct skeleton row.
        added = annotate_module.extend_workbook(path)
        assert ("AAPL", "revenue") in added, (
            "extend debe considerar la fila anómala (ticker vacío) como ausente "
            "y añadir la combinación correcta"
        )

        wb2 = load_workbook(path, data_only=True)
        sheet2 = wb2[annotate_module.SHEET_NAME]

        # Workbook now has header + anomalous row + new skeleton row = 3 rows.
        assert sheet2.max_row == 3, (
            f"Se esperaban 3 filas (header + anomalía + nueva), "
            f"hay {sheet2.max_row}"
        )

        # The anomalous row (row 2) must still have no ticker.
        anomaly_ticker = sheet2.cell(
            row=2, column=GOLD_COLUMNS.index("ticker") + 1
        ).value
        assert anomaly_ticker is None, (
            f"extend no debe tocar la fila anómala, "
            f"pero el ticker de la fila 2 es {anomaly_ticker!r}"
        )

        # The new row (row 3) must have the correct ticker and metric.
        new_row = _row_dict(sheet2, 3)
        assert new_row["ticker"] == "AAPL"
        assert new_row["metric"] == "revenue"

    # ------------------------------------------------------------------
    # test 5 — workbook structure is intact after extend + save
    # ------------------------------------------------------------------

    def test_extend_preserves_workbook_structure_after_save(
        self,
        tmp_path: Path,
        annotate_module: ModuleType,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """After ``extend``, re-opening the workbook reveals a healthy file.

        Smoke test that ``wb.save`` did not corrupt the file:
        * The sheet ``gold_standard`` must exist.
        * The header row must exactly equal ``GOLD_COLUMNS``.
        * Total row count (header + data) must equal 1 + pre_existing + added.
        """
        tickers = ("AAPL", "MSFT", "GOOGL")
        initial_metrics = ("revenue", "net_income")
        path = self._seed_with_schema(
            tmp_path, annotate_module, monkeypatch, tickers, initial_metrics
        )

        pre_existing = len(tickers) * len(initial_metrics)

        # Grow the schema by one new metric.
        extended_metrics = initial_metrics + ("operating_income",)
        monkeypatch.setattr(annotate_module, "GOLD_METRICS", extended_metrics)

        added = annotate_module.extend_workbook(path)
        n_added = len(added)
        assert n_added == len(tickers), (
            f"Se esperaban {len(tickers)} filas añadidas, se añadieron {n_added}"
        )

        # Re-open with openpyxl independently (not via the module) to avoid
        # any caching effect.
        wb = load_workbook(path, data_only=True)

        # Sheet must exist.
        assert annotate_module.SHEET_NAME in wb.sheetnames, (
            f"La hoja '{annotate_module.SHEET_NAME}' desapareció tras el save"
        )

        sheet = wb[annotate_module.SHEET_NAME]

        # Header must be exactly GOLD_COLUMNS.
        header = tuple(
            sheet.cell(row=1, column=idx + 1).value
            for idx in range(len(GOLD_COLUMNS))
        )
        assert header == GOLD_COLUMNS, (
            f"La cabecera cambió tras el save: {header!r}"
        )

        # Total rows = 1 header + pre-existing data rows + newly added rows.
        expected_total_rows = 1 + pre_existing + n_added
        assert sheet.max_row == expected_total_rows, (
            f"Se esperaban {expected_total_rows} filas totales "
            f"(1 header + {pre_existing} previas + {n_added} nuevas), "
            f"hay {sheet.max_row}"
        )


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
