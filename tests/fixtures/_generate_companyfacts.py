"""Script one-shot para regenerar tests/fixtures/companyfacts_AAPL.json.

Este archivo NO se ejecuta en pytest (prefijo _ lo excluye).
Ejecutar manualmente cuando sea necesario actualizar el fixture:

    ~/luca-ai-lab/venv/bin/python tests/fixtures/_generate_companyfacts.py

Requisitos:
    - SEC_USER_AGENT en .env (ej. "Nombre Apellido email@dominio.com").
    - Conexion a internet.
    - Respeta el rate limit de EDGAR (0.15s de sleep antes de la request).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# Asegurar que el project root esta en sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env", override=False)

import requests  # noqa: E402

from agents._config import get_env  # noqa: E402

# ---------------------------------------------------------------------------
# Tags que LUCA usa (del SKILL.md xbrl-parsing)
# ---------------------------------------------------------------------------
TAGS_TO_KEEP = {
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "Revenues",
    "SalesRevenueNet",
    "NetIncomeLoss",
    "ProfitLoss",
    "OperatingIncomeLoss",
    "Assets",
    "Liabilities",
    "StockholdersEquity",
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    "EarningsPerShareDiluted",
    "EarningsPerShareBasic",
    "CashAndCashEquivalentsAtCarryingValue",
    "Cash",
    "LongTermDebtNoncurrent",
    "LongTermDebt",
    "CommonStockSharesOutstanding",
    "WeightedAverageNumberOfSharesOutstandingBasic",
}

CIK_PADDED = "0000320193"
URL = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{CIK_PADDED}.json"
OUT_PATH = Path(__file__).resolve().parent / "companyfacts_AAPL.json"
DOWNLOAD_DATE = "2026-04-27"


def main() -> None:
    """Descarga y recorta el companyfacts de Apple Inc. (CIK 0000320193)."""
    user_agent = get_env("SEC_USER_AGENT")
    if not user_agent or not user_agent.strip():
        print(
            "ERROR: SEC_USER_AGENT no esta configurado. "
            "Añade SEC_USER_AGENT=... al archivo .env del proyecto."
        )
        sys.exit(1)

    print(f"User-Agent: {user_agent}")
    print(f"Descargando: {URL}")

    # Rate limit: SEC exige <= 10 req/s; 0.15s es conservador.
    time.sleep(0.15)

    response = requests.get(
        URL,
        headers={"User-Agent": user_agent.strip(), "Accept": "application/json"},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    print(
        f"Descargado: entityName={data.get('entityName')!r}, "
        f"cik={data.get('cik')!r}"
    )

    # Recortar: solo tags relevantes, solo FY + 10-K, max 5 records por tag.
    us_gaap_raw: dict = data.get("facts", {}).get("us-gaap", {})
    us_gaap_trimmed: dict = {}

    for tag in TAGS_TO_KEEP:
        if tag not in us_gaap_raw:
            continue
        tag_data = us_gaap_raw[tag]
        label = tag_data.get("label", tag)
        units_raw: dict = tag_data.get("units", {})
        units_trimmed: dict = {}

        for currency, records in units_raw.items():
            fy_records = [
                r for r in records
                if r.get("form") == "10-K" and r.get("fp") == "FY"
            ]
            # Los mas recientes primero (por fecha de presentacion).
            fy_records_sorted = sorted(
                fy_records, key=lambda r: r.get("filed", ""), reverse=True
            )[:5]
            if fy_records_sorted:
                units_trimmed[currency] = fy_records_sorted

        if units_trimmed:
            us_gaap_trimmed[tag] = {"label": label, "units": units_trimmed}

    result = {
        "_note": (
            f"Fixture recortado generado el {DOWNLOAD_DATE}. "
            "Solo contiene tags relevantes para LUCA (revenue, net_income, etc.) "
            "con max 5 records FY/10-K por tag. "
            "Regenerar con tests/fixtures/_generate_companyfacts.py."
        ),
        "cik": data.get("cik"),
        "entityName": data.get("entityName"),
        "facts": {
            "us-gaap": us_gaap_trimmed,
        },
    }

    with OUT_PATH.open("w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)

    size_kb = OUT_PATH.stat().st_size / 1024
    print(f"Guardado en: {OUT_PATH}")
    print(f"Tamano: {size_kb:.1f} KB")
    print(f"Tags incluidos ({len(us_gaap_trimmed)}): {sorted(us_gaap_trimmed.keys())}")


if __name__ == "__main__":
    main()
