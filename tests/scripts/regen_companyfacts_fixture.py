"""Script para regenerar tests/fixtures/companyfacts_<TICKER>.json.

Este archivo NO se ejecuta en pytest (vive en tests/scripts/, que pytest excluye
por defecto porque no hay test_*.py ni conftest.py en ese subdirectorio).

Uso:
    ~/luca-ai-lab/venv/bin/python tests/scripts/regen_companyfacts_fixture.py MSFT
    ~/luca-ai-lab/venv/bin/python tests/scripts/regen_companyfacts_fixture.py JPM

Requisitos:
    - SEC_USER_AGENT en .env (ej. "Nombre Apellido email@dominio.com").
    - Conexion a internet.
    - Respeta el rate limit de EDGAR (<= 10 req/s; sleep 0.15s antes del request).

Recorte:
    Solo los tags de _TAG_CANDIDATES de agent3_extractor, unidades USD y
    USD/shares. Max 5 hechos FY/10-K por tag, ordenados por filed desc.
    Objetivo: fixture < 30 KB.

Nota: este script es el unico punto del proyecto con permiso para tocar la
red de EDGAR. Los tests nunca llaman a este script ni a la red.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env", override=False)

import requests  # noqa: E402

from agents._config import get_env  # noqa: E402

# ---------------------------------------------------------------------------
# Tags que L3 usa — deben mantenerse sincronizados con _TAG_CANDIDATES
# en agents/agent3_extractor.py.
# ---------------------------------------------------------------------------
TAGS_TO_KEEP = {
    # revenue candidates
    "Revenues",
    "RevenueFromContractWithCustomerExcludingAssessedTax",
    "SalesRevenueNet",
    "InterestAndDividendIncomeOperating",
    # net_income candidates
    "NetIncomeLoss",
    "ProfitLoss",
    # operating_income candidates
    "OperatingIncomeLoss",
    # total_assets candidate
    "Assets",
    # total_equity candidates
    "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    "StockholdersEquity",
    # eps_diluted candidates
    "EarningsPerShareDiluted",
    "IncomeLossFromContinuingOperationsPerDilutedShare",
}

# Units to keep per tag. Everything else is dropped.
ALLOWED_UNITS = {"USD", "USD/shares"}

# Empresas conocidas — CIKs validados contra EDGAR company_tickers.json.
# Añadir mas según se necesiten.
KNOWN_CIKS: dict[str, str] = {
    "AAPL": "0000320193",
    "MSFT": "0000789019",
    "JPM": "0000019617",
    "META": "0001326801",
    "GOOGL": "0001652044",
    "AMZN": "0001018724",
    "JNJ": "0000200406",
    "XOM": "0000034088",
}

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
MAX_RECORDS_PER_TAG = 5  # max hechos FY/10-K por tag (recorte agresivo)
DOWNLOAD_DATE = "2026-04-27"


def _fetch_companyfacts(cik_padded: str, user_agent: str) -> dict:
    """Descarga el JSON companyfacts de EDGAR para un CIK dado."""
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_padded}.json"
    print(f"Descargando: {url}")
    time.sleep(0.15)  # rate limit EDGAR
    response = requests.get(
        url,
        headers={"User-Agent": user_agent.strip(), "Accept": "application/json"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _trim_companyfacts(data: dict) -> dict:
    """Recorta el companyfacts conservando solo los tags relevantes.

    Por cada tag en TAGS_TO_KEEP, conserva hasta MAX_RECORDS_PER_TAG
    hechos anuales (form==10-K, fp==FY) ordenados por filed desc.
    Solo unidades USD y USD/shares.

    Returns:
        Fixture recortado listo para guardar en JSON.
    """
    us_gaap_raw: dict = data.get("facts", {}).get("us-gaap", {})
    us_gaap_trimmed: dict = {}

    for tag in TAGS_TO_KEEP:
        if tag not in us_gaap_raw:
            continue
        tag_data = us_gaap_raw[tag]
        label = tag_data.get("label", tag)
        units_raw: dict = tag_data.get("units", {})
        units_trimmed: dict = {}

        for unit, records in units_raw.items():
            if unit not in ALLOWED_UNITS:
                continue
            fy_records = [
                r for r in records
                if r.get("form") == "10-K" and r.get("fp") == "FY"
            ]
            # Mas recientes primero.
            fy_records_sorted = sorted(
                fy_records, key=lambda r: r.get("filed", ""), reverse=True
            )[:MAX_RECORDS_PER_TAG]
            if fy_records_sorted:
                units_trimmed[unit] = fy_records_sorted

        if units_trimmed:
            us_gaap_trimmed[tag] = {"label": label, "units": units_trimmed}

    return {
        "_note": (
            f"Fixture recortado generado el {DOWNLOAD_DATE}. "
            "Solo contiene tags relevantes para LUCA (_TAG_CANDIDATES de "
            "agent3_extractor.py) con max 5 records FY/10-K por tag. "
            "Regenerar con tests/scripts/regen_companyfacts_fixture.py."
        ),
        "cik": data.get("cik"),
        "entityName": data.get("entityName"),
        "facts": {
            "us-gaap": us_gaap_trimmed,
        },
    }


def main() -> None:
    """Punto de entrada CLI: regen_companyfacts_fixture.py <TICKER>."""
    if len(sys.argv) < 2:
        print("Uso: regen_companyfacts_fixture.py <TICKER>")
        print(f"Tickers con CIK conocido: {sorted(KNOWN_CIKS)}")
        sys.exit(1)

    ticker = sys.argv[1].upper().strip()
    if ticker not in KNOWN_CIKS:
        print(
            f"ERROR: ticker '{ticker}' no tiene CIK en KNOWN_CIKS.\n"
            f"Añade manualmente '{ticker}': '<CIK_PADDED_10D>' a KNOWN_CIKS y vuelve a ejecutar."
        )
        sys.exit(1)

    cik_padded = KNOWN_CIKS[ticker]

    user_agent = get_env("SEC_USER_AGENT")
    if not user_agent or not user_agent.strip():
        print(
            "ERROR: SEC_USER_AGENT no esta configurado. "
            "Añade SEC_USER_AGENT=... al archivo .env del proyecto."
        )
        sys.exit(1)

    print(f"User-Agent: {user_agent}")
    print(f"Ticker: {ticker}  CIK: {cik_padded}")

    data = _fetch_companyfacts(cik_padded, user_agent)
    print(
        f"Descargado: entityName={data.get('entityName')!r}, "
        f"cik={data.get('cik')!r}"
    )

    trimmed = _trim_companyfacts(data)

    out_path = FIXTURES_DIR / f"companyfacts_{ticker}.json"
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        json.dump(trimmed, fh, ensure_ascii=False, indent=2)

    size_kb = out_path.stat().st_size / 1024
    tags_found = sorted(trimmed["facts"]["us-gaap"].keys())
    print(f"\nGuardado en: {out_path}")
    print(f"Tamano: {size_kb:.1f} KB")
    print(f"Tags incluidos ({len(tags_found)}): {tags_found}")


if __name__ == "__main__":
    main()
