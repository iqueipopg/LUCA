"""LUCA pipeline CLI orchestrator.

Runs the (currently L1 -> L2) pipeline for a single ticker and prints the
parser output to stdout. Intended as the user-facing entry point during
Sprint 0; later sprints will append further stages (L3 onwards).
"""

from __future__ import annotations

import argparse
import json
import os
import pprint
import sys
from typing import Any

_TRUNCATE_THRESHOLD: int = 500
_TRUNCATE_PREVIEW: int = 200


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Optional argument vector for testing; ``None`` uses ``sys.argv``.

    Returns:
        The populated :class:`argparse.Namespace`.
    """
    parser = argparse.ArgumentParser(
        prog="run_pipeline.py",
        description="Run the LUCA pipeline (L1 ingest -> L2 parse) for a ticker.",
    )
    parser.add_argument("--ticker", required=True, help="Stock ticker (e.g. AAPL).")
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable DEBUG logging.",
    )
    parser.add_argument(
        "--output", choices=("pretty", "json"), default="pretty",
        help="Output format for the parser result (default: pretty).",
    )
    parser.add_argument(
        "--memo", action="store_true",
        help="Run the full E2E pipeline (L1->L2->L3->L4->L5->L7) and write the "
             "investment memo to outputs/memos/ instead of printing L2.",
    )
    return parser.parse_args(argv)


def _truncate_for_pretty(value: Any) -> Any:
    """Shorten long string fields for the ``pretty`` output mode.

    Strings longer than :data:`_TRUNCATE_THRESHOLD` characters are replaced by
    a ``"<N chars> first200..."`` placeholder. Lists and dicts are walked
    recursively. JSON output is left untouched.
    """
    if isinstance(value, str) and len(value) > _TRUNCATE_THRESHOLD:
        return f"<{len(value)} caracteres> {value[:_TRUNCATE_PREVIEW]}..."
    if isinstance(value, list):
        return [_truncate_for_pretty(v) for v in value]
    if isinstance(value, dict):
        return {k: _truncate_for_pretty(v) for k, v in value.items()}
    return value


def _emit(result: dict[str, Any], fmt: str) -> None:
    """Print ``result`` to stdout in the requested format."""
    if fmt == "json":
        sys.stdout.write(
            json.dumps(result, indent=2, default=str, ensure_ascii=False) + "\n"
        )
    else:
        pprint.pprint(_truncate_for_pretty(result), sort_dicts=False)


def main(argv: list[str] | None = None) -> None:
    """CLI entry point. See module docstring for behaviour."""
    args = _parse_args(argv)

    if args.verbose:
        os.environ["LUCA_LOG_LEVEL"] = "DEBUG"

    # Imports happen *after* the env var is set so the logger picks it up.
    from agents._config import load_config
    from agents._logging import get_logger
    from agents.agent1_ingestion import ingest
    from agents.agent2_parser import parse

    # Load .env into os.environ so SEC_USER_AGENT (required by L1) is available,
    # mirroring the eval scripts' entry points.
    load_config()

    logger = get_logger(__name__)
    ticker = args.ticker.strip().upper()
    logger.info("Ejecutando pipeline para %s", ticker)

    try:
        l1 = ingest(ticker)
    except ValueError as exc:
        logger.error("L1 ingestion falló para %s: %s", ticker, exc)
        sys.exit(2)

    logger.info(
        "L1 completado: %s, accession=%s",
        l1.get("company") or "<unknown>",
        l1.get("accession_number"),
    )

    l2 = parse(l1)
    logger.info("L2 completado: item_1a=%d caracteres", len(l2.get("item_1a") or ""))

    if not args.memo:
        _emit(l2, args.output)
        return

    # Full E2E: L3 (structured) -> L4 (qualitative risks) -> L5 (analyst) -> L7 (memo).
    from agents.agent3_extractor import extract
    from agents.agent4_qualitative import extract_qualitative
    from agents.agent5_analyst import analyze
    from agents.agent7_writer import write_memo

    l3 = extract(l1)
    logger.info("L3 completado: %d métricas", len(l3.get("metrics") or {}))

    l4: dict[str, Any] | None = None
    try:
        l4 = extract_qualitative(l1)
        logger.info("L4 completado: %d riesgos", len(l4.get("risks") or []))
    except Exception as exc:  # noqa: BLE001 — L4 is best-effort for the demo
        logger.warning("L4 falló (%s); el memo seguirá sin riesgos", exc)

    l5 = analyze(l3, l4 or {"risks": []}, ingest_output=l1)
    logger.info("L5 completado: %d riesgos clasificados", l5["meta"]["n_risks"])

    memo = write_memo(l3, l5, l4_output=l4, l2_output=l2)
    logger.info("L7 completado: memo de %d caracteres", len(memo))
    sys.stdout.write(memo)


if __name__ == "__main__":
    main()
