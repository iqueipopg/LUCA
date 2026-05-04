"""experiments/regold_baselines.py — re-evaluate baseline CSVs against an updated gold.

When the gold standard changes (e.g. T1.10 sub-incidencia 1: WMT/net_income
re-anotado de consolidated a Walmart-attributable), las predicciones del LLM
no cambian — solo cambia la comparación contra gold. Este script lee un CSV
de baseline ya escrito por ``eval_baseline_llm.py``, recomputa las columnas
``gold_value`` / ``gold_fiscal_year`` / ``match`` / ``abs_error`` /
``rel_error`` / ``notes_gold`` contra el gold actual, y escribe un nuevo CSV
con un nuevo timestamp.

**No invoca al LLM. No toca EDGAR. No re-extrae nada.** El campo
``raw_llm_response`` se conserva tal cual del CSV original.

Uso típico
----------
::

    /home/<user>/luca-ai-lab/venv/bin/python experiments/regold_baselines.py \\
        --input experiments/output/eval_baseline_structured_20260504_180953.csv

El CSV original se mantiene como referencia histórica; el nuevo se guarda
con el mismo prefijo y un timestamp nuevo, así ``error_analysis.py``
autodetecta el más reciente sin cambios.
"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path
from typing import Final

_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agents._logging import get_logger  # noqa: E402
from experiments._eval_common import compare_values, load_gold_standard  # noqa: E402

_LOGGER = get_logger(__name__)

DEFAULT_GOLD_PATH: Path = _PROJECT_ROOT / "data" / "gold_standard.xlsx"

#: Prefijos válidos de input. El output reusa el prefijo + timestamp nuevo.
RECOGNISED_PREFIXES: Final[tuple[str, ...]] = (
    "eval_baseline_structured_",
    "eval_baseline_naive_",
)


def _fmt_float(value: float | None) -> str:
    if value is None:
        return ""
    return repr(value)


def _fmt_int(value: int | None) -> str:
    if value is None:
        return ""
    return str(value)


def _parse_float(raw: object) -> float | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    return float(text)


def regold_csv(
    input_path: Path,
    output_path: Path,
    *,
    gold_path: Path,
) -> tuple[int, int, int]:
    """Re-evaluate ``input_path`` against ``gold_path`` and write to ``output_path``.

    Returns:
        Tuple ``(rows_written, flips_to_hit, flips_to_miss)``.
    """
    if not input_path.is_file():
        raise FileNotFoundError(f"No existe el CSV de input: {input_path}")

    gold = load_gold_standard(gold_path)
    _LOGGER.info("Gold cargado desde %s (%d filas)", gold_path, len(gold))

    with input_path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = list(reader.fieldnames or ())
        in_rows = list(reader)

    required = {"ticker", "metric", "predicted_value", "match"}
    missing = required - set(fieldnames)
    if missing:
        raise ValueError(
            f"CSV {input_path} carece de columnas {sorted(missing)}; "
            f"encontradas: {fieldnames}"
        )

    out_rows: list[dict[str, str]] = []
    flips_to_hit = 0
    flips_to_miss = 0

    for r in in_rows:
        ticker = r["ticker"].strip()
        metric = r["metric"].strip()
        old_match = r.get("match", "").strip() == "True"

        gold_entry = gold.get((ticker, metric))
        if gold_entry is None:
            _LOGGER.warning(
                "No hay gold para (%s, %s); fila excluida del output", ticker, metric
            )
            continue

        predicted = _parse_float(r.get("predicted_value"))
        new_match, abs_err, rel_err = compare_values(gold_entry.value, predicted)

        if not old_match and new_match:
            flips_to_hit += 1
            _LOGGER.info("FLIP→HIT  : %s/%s", ticker, metric)
        elif old_match and not new_match:
            flips_to_miss += 1
            _LOGGER.info("FLIP→MISS : %s/%s", ticker, metric)

        new_row = dict(r)
        new_row["gold_value"] = _fmt_float(gold_entry.value)
        new_row["gold_fiscal_year"] = _fmt_int(gold_entry.fiscal_year)
        new_row["predicted_value"] = _fmt_float(predicted)
        new_row["match"] = "True" if new_match else "False"
        if "abs_error" in fieldnames:
            new_row["abs_error"] = _fmt_float(abs_err)
        if "rel_error" in fieldnames:
            new_row["rel_error"] = _fmt_float(rel_err)
        if "notes_gold" in fieldnames:
            new_row["notes_gold"] = gold_entry.notes
        out_rows.append(new_row)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)

    return len(out_rows), flips_to_hit, flips_to_miss


def _derive_output_path(input_path: Path) -> Path:
    """``eval_baseline_X_<TS_old>.csv`` → ``eval_baseline_X_<TS_new>.csv``."""
    stem = input_path.stem
    for prefix in RECOGNISED_PREFIXES:
        if stem.startswith(prefix):
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            return input_path.parent / f"{prefix}{stamp}.csv"
    raise ValueError(
        f"No reconozco el prefijo del input {stem!r}. "
        f"Esperaba uno de {RECOGNISED_PREFIXES}."
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="regold_baselines.py",
        description=(
            "Re-evalúa un CSV de baseline (structured o naive) contra el "
            "gold standard actual sin re-invocar al LLM. Escribe un nuevo "
            "CSV con timestamp nuevo."
        ),
    )
    parser.add_argument(
        "--input", type=Path, required=True,
        help="CSV de input (eval_baseline_structured_*.csv o eval_baseline_naive_*.csv).",
    )
    parser.add_argument(
        "--gold-path", type=Path, default=DEFAULT_GOLD_PATH,
        help=f"Gold standard (default: {DEFAULT_GOLD_PATH.relative_to(_PROJECT_ROOT)}).",
    )
    parser.add_argument(
        "--output", type=Path, default=None,
        help="Ruta de salida explícita (por defecto: mismo dir + timestamp nuevo).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    output = args.output or _derive_output_path(args.input)

    total, to_hit, to_miss = regold_csv(args.input, output, gold_path=args.gold_path)

    print()
    print(f"Re-evaluación contra {args.gold_path.name}:")
    print(f"  Input        : {args.input.name}")
    print(f"  Output       : {output.name}")
    print(f"  Filas escritas: {total}")
    print(f"  Flipped → HIT  : {to_hit}")
    print(f"  Flipped → MISS : {to_miss}")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_GOLD_PATH",
    "RECOGNISED_PREFIXES",
    "main",
    "regold_csv",
]
