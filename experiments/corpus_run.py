"""T5.1 — Corpus scale-up: structured extraction across the S&P 100, FY2022-FY2024.

Grounds the public claim "structured extraction across N 10-K filings
from M companies" with a real corpus run. This run produces **coverage**,
not accuracy: the N=60 hand-annotated gold standard remains the only
accuracy claim. No LLM is invoked at any point.

Subcommands
-----------
``screen``
    Resolve the pre-registered S&P 100 ticker list against EDGAR, apply
    the exclusion rules (20-F filers; fewer than 3 annual 10-Ks with
    XBRL company facts covering FY2022-FY2024; duplicate share classes
    of the same CIK; tickers absent from EDGAR's map), download and
    cache submissions + companyfacts, and freeze the included list in
    ``experiments/corpus_tickers.txt`` plus the exclusion log in
    ``experiments/tickers_excluded.md``. Must run BEFORE ``run``.

``run``
    For every included company x fiscal year in ``TARGET_FYS``, run the
    FY-targeted L3 selector (:func:`agents.agent3_extractor.extract_for_fiscal_year`)
    over the cached companyfacts and write
    ``experiments/corpus_manifest.csv`` plus
    ``experiments/restatements_log.md``.

``gate``
    Coherence gate (hard stop). (a) manifest rows == companies x years,
    no duplicate accessions; (b) every accession is a 10-K per the
    submissions index; (c) regression: the FY-targeted selector,
    pointed at each gold ticker's annotated fiscal year, reproduces the
    gold standard 60/60 under the shared comparator
    (:func:`experiments._eval_common.compare_values`, 0.5% relative
    tolerance). On failure writes ``experiments/corpus_blockers.md``
    and exits non-zero.

``report``
    Compute coverage stats from the manifest and write
    ``experiments/coverage_report.md``.

Network policy
--------------
All EDGAR access goes through :mod:`agents._edgar_client` (rate limit +
``SEC_USER_AGENT``). Every JSON payload is cached under
``data/cache/corpus_facts/`` so re-runs after chain triage are offline.

Usage
-----
::

    /home/<user>/luca-ai-lab/venv/bin/python experiments/corpus_run.py screen
    /home/<user>/luca-ai-lab/venv/bin/python experiments/corpus_run.py run
    /home/<user>/luca-ai-lab/venv/bin/python experiments/corpus_run.py gate
    /home/<user>/luca-ai-lab/venv/bin/python experiments/corpus_run.py report
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Final

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from agents._config import load_config  # noqa: E402
from agents._edgar_client import (  # noqa: E402
    fetch_companyfacts,
    fetch_submissions,
    ticker_to_cik,
)
from agents._gold_schema import GOLD_TICKERS  # noqa: E402
from agents._logging import get_logger  # noqa: E402
from agents.agent3_extractor import extract_for_fiscal_year  # noqa: E402
from experiments._eval_common import compare_values, load_gold_standard  # noqa: E402

_LOGGER = get_logger(__name__)

# ---------------------------------------------------------------------------
# Pre-registered inputs
# ---------------------------------------------------------------------------

#: S&P 100 constituents as listed on Wikipedia ("S&P 100", components
#: table, list dated 2025-09-22; accessed 2026-08-19). Frozen here BEFORE
#: any extraction ran. Exclusions are applied by ``screen`` and logged
#: one by one in ``experiments/tickers_excluded.md`` — no post-hoc
#: removals from ``corpus_tickers.txt`` are permitted.
RAW_SP100: Final[tuple[tuple[str, str], ...]] = (
    ("AAPL", "Apple Inc."), ("ABBV", "AbbVie"), ("ABT", "Abbott Laboratories"),
    ("ACN", "Accenture"), ("ADBE", "Adobe Inc."), ("AMAT", "Applied Materials"),
    ("AMD", "Advanced Micro Devices"), ("AMGN", "Amgen"), ("AMT", "American Tower"),
    ("AMZN", "Amazon"), ("AVGO", "Broadcom"), ("AXP", "American Express"),
    ("BA", "Boeing"), ("BAC", "Bank of America"), ("BKNG", "Booking Holdings"),
    ("BLK", "BlackRock"), ("BMY", "Bristol Myers Squibb"), ("BNY", "BNY Mellon"),
    ("BRK.B", "Berkshire Hathaway (Class B)"), ("C", "Citigroup"),
    ("CAT", "Caterpillar Inc."), ("CL", "Colgate-Palmolive"), ("CMCSA", "Comcast"),
    ("COF", "Capital One"), ("COP", "ConocoPhillips"), ("COST", "Costco"),
    ("CRM", "Salesforce"), ("CSCO", "Cisco"), ("CVS", "CVS Health"),
    ("CVX", "Chevron Corporation"), ("DE", "Deere & Company"),
    ("DHR", "Danaher Corporation"), ("DIS", "Walt Disney Company (The)"),
    ("DUK", "Duke Energy"), ("EMR", "Emerson Electric"), ("FDX", "FedEx"),
    ("GD", "General Dynamics"), ("GE", "GE Aerospace"), ("GEV", "GE Vernova"),
    ("GILD", "Gilead Sciences"), ("GM", "General Motors"),
    ("GOOG", "Alphabet Inc. (Class C)"), ("GOOGL", "Alphabet Inc. (Class A)"),
    ("GS", "Goldman Sachs"), ("HD", "Home Depot"), ("HONA", "Honeywell Aerospace"),
    ("IBM", "IBM"), ("INTC", "Intel"), ("INTU", "Intuit"),
    ("ISRG", "Intuitive Surgical"), ("JNJ", "Johnson & Johnson"),
    ("JPM", "JPMorgan Chase"), ("KO", "Coca-Cola Company (The)"),
    ("LIN", "Linde plc"), ("LLY", "Eli Lilly and Company"),
    ("LMT", "Lockheed Martin"), ("LOW", "Lowe's"), ("LRCX", "Lam Research"),
    ("MA", "Mastercard"), ("MCD", "McDonald's"), ("MDLZ", "Mondelez International"),
    ("MDT", "Medtronic"), ("META", "Meta Platforms"), ("MMM", "3M"),
    ("MO", "Altria"), ("MRK", "Merck & Co."), ("MS", "Morgan Stanley"),
    ("MSFT", "Microsoft"), ("MU", "Micron Technology"), ("NEE", "NextEra Energy"),
    ("NFLX", "Netflix, Inc."), ("NKE", "Nike, Inc."), ("NOW", "ServiceNow"),
    ("NVDA", "Nvidia"), ("ORCL", "Oracle Corporation"), ("PEP", "PepsiCo"),
    ("PFE", "Pfizer"), ("PG", "Procter & Gamble"),
    ("PLTR", "Palantir Technologies"), ("PM", "Philip Morris International"),
    ("QCOM", "Qualcomm"), ("RTX", "RTX Corporation"), ("SBUX", "Starbucks"),
    ("SCHW", "Charles Schwab Corporation"), ("SO", "Southern Company"),
    ("SPG", "Simon Property Group"), ("T", "AT&T"),
    ("TMO", "Thermo Fisher Scientific"), ("TMUS", "T-Mobile US"),
    ("TSLA", "Tesla, Inc."), ("TXN", "Texas Instruments"), ("UBER", "Uber"),
    ("UNH", "UnitedHealth Group"), ("UNP", "Union Pacific Corporation"),
    ("UPS", "United Parcel Service"), ("USB", "U.S. Bancorp"),
    ("V", "Visa Inc."), ("VZ", "Verizon"), ("WFC", "Wells Fargo"),
    ("WMT", "Walmart"), ("XOM", "ExxonMobil"),
)

#: Ticker-format aliases (Wikipedia notation → EDGAR company_tickers.json
#: notation). Format-only mappings; never map one entity to another.
TICKER_ALIASES: Final[dict[str, str]] = {
    "BRK.B": "BRK-B",
}

#: Target fiscal-year labels (EDGAR ``fy`` field — the filer's own
#: labelling convention; e.g. NVDA's fiscal year ending 2024-01-28 is
#: labelled fy=2024).
TARGET_FYS: Final[tuple[int, ...]] = (2022, 2023, 2024)

#: The six core metrics evaluated against the gold standard. ``cash``
#: and ``long_term_debt`` are extracted by L3 but not yet annotated, so
#: they stay out of the corpus manifest.
CORE_METRICS: Final[tuple[str, ...]] = (
    "revenue",
    "net_income",
    "operating_income",
    "total_assets",
    "total_equity",
    "eps_diluted",
)

#: Null-reason vocabulary for the manifest.
REASON_TAG_ABSENT: Final[str] = "tag_absent"
REASON_CONVENTION: Final[str] = "not_applicable_convention"
REASON_ERROR: Final[str] = "error"

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

CACHE_DIR: Final[Path] = _PROJECT_ROOT / "data" / "cache" / "corpus_facts"
EXPERIMENTS_DIR: Final[Path] = _PROJECT_ROOT / "experiments"
TICKERS_PATH: Final[Path] = EXPERIMENTS_DIR / "corpus_tickers.txt"
EXCLUDED_PATH: Final[Path] = EXPERIMENTS_DIR / "tickers_excluded.md"
MANIFEST_PATH: Final[Path] = EXPERIMENTS_DIR / "corpus_manifest.csv"
RESTATEMENTS_PATH: Final[Path] = EXPERIMENTS_DIR / "restatements_log.md"
BLOCKERS_PATH: Final[Path] = EXPERIMENTS_DIR / "corpus_blockers.md"
COVERAGE_PATH: Final[Path] = EXPERIMENTS_DIR / "coverage_report.md"
CHANGELOG_PATH: Final[Path] = EXPERIMENTS_DIR / "chain_changelog.md"
SCREEN_META_PATH: Final[Path] = CACHE_DIR / "screen_meta.json"
GOLD_PATH: Final[Path] = _PROJECT_ROOT / "data" / "gold_standard.xlsx"


# ---------------------------------------------------------------------------
# SIC → sector (SIC division ranges, deterministic)
# ---------------------------------------------------------------------------


def sic_to_sector(sic: int | None) -> str:
    """Map a SIC code to its SIC division name (coarse sector)."""
    if sic is None:
        return "Unknown"
    if 100 <= sic <= 999:
        return "Agriculture"
    if 1000 <= sic <= 1499:
        return "Mining & Energy Extraction"
    if 1500 <= sic <= 1799:
        return "Construction"
    if 2000 <= sic <= 3999:
        return "Manufacturing"
    if 4000 <= sic <= 4999:
        return "Transportation, Communications & Utilities"
    if 5000 <= sic <= 5199:
        return "Wholesale Trade"
    if 5200 <= sic <= 5999:
        return "Retail Trade"
    if 6000 <= sic <= 6799:
        return "Finance, Insurance & Real Estate"
    if 7000 <= sic <= 8999:
        return "Services"
    return "Other"


def _is_financial(sic: int | None) -> bool:
    """True for the SIC Finance/Insurance/Real Estate division (6000-6799)."""
    return sic is not None and 6000 <= sic <= 6799


# ---------------------------------------------------------------------------
# Cached EDGAR access
# ---------------------------------------------------------------------------


def _cached_json(path: Path, fetch) -> dict[str, Any]:
    """Return JSON from ``path`` if present, else fetch, store and return."""
    if path.is_file():
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    payload = fetch()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    return payload


def load_submissions(cik: str) -> dict[str, Any]:
    """Submissions index for ``cik``, disk-cached."""
    return _cached_json(
        CACHE_DIR / f"{cik}_submissions.json", lambda: fetch_submissions(cik)
    )


def load_companyfacts(cik: str) -> dict[str, Any]:
    """Companyfacts bundle for ``cik``, disk-cached."""
    return _cached_json(
        CACHE_DIR / f"{cik}_facts.json", lambda: fetch_companyfacts(cik)
    )


def _forms_map_from_block(block: dict[str, Any]) -> dict[str, tuple[str, str]]:
    """Zip a submissions block's parallel arrays into accn → (form, filed)."""
    forms = block.get("form") or []
    accessions = block.get("accessionNumber") or []
    dates = block.get("filingDate") or []
    result: dict[str, tuple[str, str]] = {}
    for idx, accn in enumerate(accessions):
        if not isinstance(accn, str):
            continue
        form = forms[idx] if idx < len(forms) and isinstance(forms[idx], str) else ""
        filed = dates[idx] if idx < len(dates) and isinstance(dates[idx], str) else ""
        result[accn] = (form, filed)
    return result


def submissions_form_map(cik: str) -> dict[str, tuple[str, str]]:
    """Full accession → (form, filingDate) map, following paged archives.

    The submissions index holds only the most recent ~1000 filings under
    ``filings.recent``; older filings live in paged archive files listed
    under ``filings.files``. All pages are fetched (and cached) so the
    gate can verify any accession in the manifest.
    """
    subs = load_submissions(cik)
    filings = subs.get("filings") or {}
    mapping = _forms_map_from_block(filings.get("recent") or {})
    for page in filings.get("files") or []:
        name = page.get("name") if isinstance(page, dict) else None
        if not isinstance(name, str) or not name:
            continue
        page_path = CACHE_DIR / f"{cik}_{name}"
        from agents._edgar_client import _request_json  # local import: paged URL

        page_payload = _cached_json(
            page_path,
            lambda n=name: _request_json(f"https://data.sec.gov/submissions/{n}"),
        )
        mapping.update(_forms_map_from_block(page_payload))
    return mapping


# ---------------------------------------------------------------------------
# screen
# ---------------------------------------------------------------------------


def _edgar_ticker(raw: str) -> str:
    """Normalise a Wikipedia ticker to EDGAR notation."""
    return TICKER_ALIASES.get(raw, raw.replace(".", "-"))


def cmd_screen() -> int:
    """Apply the pre-registered exclusion rules and freeze the corpus list."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    excluded: list[tuple[str, str]] = []  # (ticker, reason)
    resolved: dict[str, str] = {}  # raw ticker → cik

    for raw, _name in RAW_SP100:
        edgar_ticker = _edgar_ticker(raw)
        try:
            resolved[raw] = ticker_to_cik(edgar_ticker)
        except ValueError:
            excluded.append((
                raw,
                f"ticker `{edgar_ticker}` no aparece en el mapa de tickers de "
                "EDGAR (company_tickers.json); sin CIK no hay filings que evaluar",
            ))

    # Duplicate share classes: one entity, one row. Prefer the gold ticker
    # if present, else the alphabetically-first ticker of the group.
    by_cik: dict[str, list[str]] = defaultdict(list)
    for raw, cik in resolved.items():
        by_cik[cik].append(raw)
    kept: dict[str, str] = {}  # raw ticker → cik
    for cik, group in by_cik.items():
        group_sorted = sorted(group)
        gold_in_group = [t for t in group_sorted if t in GOLD_TICKERS]
        keep = gold_in_group[0] if gold_in_group else group_sorted[0]
        kept[keep] = cik
        for other in group_sorted:
            if other != keep:
                excluded.append((
                    other,
                    f"clase de acción duplicada de {keep} (mismo CIK {cik}); "
                    "una sola fila por entidad",
                ))

    included: list[str] = []
    meta: dict[str, dict[str, Any]] = {}
    for raw in sorted(kept):
        cik = kept[raw]
        subs = load_submissions(cik)
        filings = subs.get("filings") or {}
        recent_forms = set((filings.get("recent") or {}).get("form") or [])
        if "10-K" not in recent_forms:
            entity = subs.get("name") or "entidad desconocida"
            if any(f.startswith("20-F") for f in recent_forms):
                excluded.append((raw, "presenta 20-F en lugar de 10-K"))
            else:
                excluded.append((
                    raw,
                    f"la entidad a la que EDGAR mapea el ticker ({entity}, "
                    f"CIK {cik}) no tiene ningún 10-K en su índice de "
                    "submissions (entidad de nueva creación: spin-off o "
                    "reorganización en holding; los 10-K históricos "
                    "pertenecen a otro CIK y no se persiguen: sin "
                    "special-casing por empresa)",
                ))
            continue

        facts = load_companyfacts(cik)
        ingest_stub = {
            "company": subs.get("name") or "",
            "ticker": raw,
            "xbrl_data": facts,
        }
        missing_fys = [
            fy for fy in TARGET_FYS
            if extract_for_fiscal_year(ingest_stub, fy, metrics=("revenue",))["period_end"] is None
        ]
        if missing_fys:
            missing_str = ", ".join(f"FY{fy}" for fy in missing_fys)
            excluded.append((
                raw,
                "menos de 3 10-K anuales con company facts XBRL cubriendo "
                f"FY2022-FY2024 (faltan: {missing_str})",
            ))
            continue

        sic_raw = subs.get("sic")
        try:
            sic = int(sic_raw) if sic_raw not in (None, "") else None
        except (TypeError, ValueError):
            sic = None
        included.append(raw)
        meta[raw] = {
            "cik": cik,
            "name": subs.get("name") or "",
            "sic": sic,
            "sic_description": subs.get("sicDescription") or "",
            "sector": sic_to_sector(sic),
        }

    missing_gold = [t for t in GOLD_TICKERS if t not in included]
    if missing_gold:
        _LOGGER.error("Tickers gold fuera del corpus: %s", missing_gold)
        return 2

    TICKERS_PATH.write_text("\n".join(included) + "\n", encoding="utf-8")
    with SCREEN_META_PATH.open("w", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=2, ensure_ascii=False)

    lines = [
        "# Corpus S&P 100 — exclusiones del screening (T5.1)",
        "",
        "Lista fuente: constituyentes del S&P 100 según Wikipedia",
        "(tabla de componentes fechada 2025-09-22, consultada 2026-08-19),",
        f"{len(RAW_SP100)} tickers. Reglas de exclusión pre-registradas:",
        "presenta 20-F en lugar de 10-K; menos de 3 10-K anuales con company",
        "facts XBRL cubriendo FY2022-FY2024; clase de acción duplicada del",
        "mismo CIK; ticker ausente del mapa de EDGAR. La lista incluida se",
        "congela en `corpus_tickers.txt` ANTES de la extracción; no se",
        "permiten retiradas post-hoc.",
        "",
        f"**Incluidos: {len(included)}. Excluidos: {len(excluded)}.**",
        "",
        "| Ticker | Motivo de exclusión |",
        "|--------|---------------------|",
    ]
    for ticker, reason in sorted(excluded):
        lines.append(f"| {ticker} | {reason} |")
    EXCLUDED_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"screen: {len(included)} incluidos, {len(excluded)} excluidos")
    for ticker, reason in sorted(excluded):
        print(f"  EXCLUIDO {ticker}: {reason}")
    if len(included) < 52:
        _LOGGER.error("Objetivo >=52 empresas incluidas no alcanzado: %d", len(included))
        return 2
    return 0


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


def _load_frozen_list() -> tuple[list[str], dict[str, dict[str, Any]]]:
    tickers = [
        line.strip()
        for line in TICKERS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    with SCREEN_META_PATH.open(encoding="utf-8") as fh:
        meta = json.load(fh)
    return tickers, meta


def _format_value(value: float) -> str:
    """Render a metric value for the CSV without float noise."""
    if value == int(value):
        return str(int(value))
    return repr(value)


def cmd_run() -> int:
    """Extract every included company x target fiscal year into the manifest."""
    tickers, meta = _load_frozen_list()
    rows: list[dict[str, str]] = []
    restatement_entries: list[dict[str, Any]] = []

    for ticker in tickers:
        info = meta[ticker]
        cik = info["cik"]
        sic = info["sic"]
        facts = load_companyfacts(cik)
        form_map = submissions_form_map(cik)
        ingest_stub = {
            "company": info["name"],
            "ticker": ticker,
            "xbrl_data": facts,
        }
        for fy in TARGET_FYS:
            row: dict[str, str] = {
                "ticker": ticker,
                "cik": cik,
                "sector": info["sector"],
                "fy": str(fy),
                "accession": "",
                "filed_date": "",
            }
            try:
                result = extract_for_fiscal_year(ingest_stub, fy, metrics=CORE_METRICS)
            except Exception:  # noqa: BLE001 — a row must never kill the run
                _LOGGER.exception("Extracción falló para %s FY%s", ticker, fy)
                for metric in CORE_METRICS:
                    row[metric] = "NULL"
                    row[f"{metric}_null_reason"] = REASON_ERROR
                rows.append(row)
                continue

            accession = result.get("accession") or ""
            row["accession"] = accession
            form, filed = form_map.get(accession, ("", ""))
            row["filed_date"] = filed
            if accession and form != "10-K":
                _LOGGER.warning(
                    "Accession %s de %s FY%s no es 10-K según submissions (form=%r)",
                    accession, ticker, fy, form,
                )

            for metric in CORE_METRICS:
                entry = result["metrics"].get(metric)
                if entry is None:
                    row[metric] = "NULL"
                    if metric == "operating_income" and _is_financial(sic):
                        row[f"{metric}_null_reason"] = REASON_CONVENTION
                    else:
                        row[f"{metric}_null_reason"] = REASON_TAG_ABSENT
                else:
                    row[metric] = _format_value(entry["value"])
                    row[f"{metric}_null_reason"] = ""
            for restatement in result.get("restatements", []):
                restatement_entries.append({"ticker": ticker, "target_fy": fy, **restatement})
            rows.append(row)

    fieldnames = (
        ["ticker", "cik", "sector", "fy", "accession", "filed_date"]
        + list(CORE_METRICS)
        + [f"{m}_null_reason" for m in CORE_METRICS]
    )
    with MANIFEST_PATH.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    lines = [
        "# Corpus S&P 100 — restatements detectados (T5.1)",
        "",
        "Valores donde un filing posterior re-publica el mismo periodo con",
        "una cifra distinta a la originalmente reportada. El manifiesto",
        "conserva SIEMPRE el valor as-originally-reported; esta bitácora",
        "documenta la discrepancia. Comparación sobre el mismo tag US-GAAP",
        "y el mismo period_end; se registra cualquier diferencia relativa",
        "mayor que 1e-9.",
        "",
        f"**Total: {len(restatement_entries)} discrepancias.**",
        "",
        "| Ticker | FY | Métrica | Tag | Original | Restated | Restated en FY | Accession posterior |",
        "|--------|----|---------|-----|----------|----------|----------------|---------------------|",
    ]
    for e in restatement_entries:
        lines.append(
            f"| {e['ticker']} | {e['target_fy']} | {e['metric']} | {e['tag']} "
            f"| {e['original_value']:.6g} | {e['restated_value']:.6g} "
            f"| {e['restated_fy']} | {e['restated_accession'] or 'n/a'} |"
        )
    RESTATEMENTS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"run: {len(rows)} filas en {MANIFEST_PATH.name}, "
          f"{len(restatement_entries)} restatements")
    return 0


# ---------------------------------------------------------------------------
# gate
# ---------------------------------------------------------------------------


def _read_manifest() -> list[dict[str, str]]:
    with MANIFEST_PATH.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def cmd_gate() -> int:
    """Coherence gate. Hard stop (exit 2 + blockers file) if any check fails."""
    failures: list[str] = []
    tickers, meta = _load_frozen_list()
    rows = _read_manifest()

    # (a) row count and duplicate accessions.
    expected = len(tickers) * len(TARGET_FYS)
    if len(rows) != expected:
        failures.append(
            f"(a) filas del manifiesto = {len(rows)}, esperadas {expected} "
            f"({len(tickers)} empresas x {len(TARGET_FYS)} años)"
        )
    accession_counts = Counter(r["accession"] for r in rows if r["accession"])
    duplicates = {a: n for a, n in accession_counts.items() if n > 1}
    if duplicates:
        failures.append(f"(a) accessions duplicados: {duplicates}")
    missing_accn = [(r["ticker"], r["fy"]) for r in rows if not r["accession"]]
    if missing_accn:
        failures.append(f"(a) filas sin accession: {missing_accn}")

    # (b) every accession is a 10-K per the submissions index.
    for ticker in tickers:
        cik = meta[ticker]["cik"]
        form_map = submissions_form_map(cik)
        for row in (r for r in rows if r["ticker"] == ticker):
            accn = row["accession"]
            if not accn:
                continue
            form, _filed = form_map.get(accn, ("", ""))
            if form != "10-K":
                failures.append(
                    f"(b) {ticker} FY{row['fy']}: accession {accn} tiene "
                    f"form={form!r} en el índice de submissions, no 10-K"
                )

    # (c) regression: FY-targeted selection reproduces the gold standard
    # 60/60 at each gold ticker's annotated fiscal year. The corpus
    # covers FY2022-FY2024 while the gold standard annotates each
    # ticker's most recent 10-K (FY2025 / FY2026), so the regression
    # exercises the same selector at the gold fiscal years instead of
    # comparing manifest rows directly.
    gold = load_gold_standard(GOLD_PATH)
    gold_matches = 0
    gold_total = 0
    for (ticker, metric), entry in sorted(gold.items()):
        gold_total += 1
        info = meta[ticker]
        facts = load_companyfacts(info["cik"])
        result = extract_for_fiscal_year(
            {"company": info["name"], "ticker": ticker, "xbrl_data": facts},
            entry.fiscal_year,
            metrics=(metric,),
        )
        metric_entry = result["metrics"][metric]
        predicted = metric_entry["value"] if metric_entry else None
        match, _abs_err, rel_err = compare_values(entry.value, predicted)
        if match:
            gold_matches += 1
        else:
            failures.append(
                f"(c) {ticker}/{metric} FY{entry.fiscal_year}: gold={entry.value} "
                f"vs extraído={predicted} (rel_err={rel_err})"
            )
    if gold_matches != gold_total:
        failures.append(f"(c) regresión gold: {gold_matches}/{gold_total}, se exige 60/60")

    if failures:
        lines = [
            "# Corpus S&P 100 — bloqueadores del gate de coherencia (T5.1)",
            "",
            "El gate falló; NO se toca el repo público hasta resolverlos.",
            "",
        ]
        lines.extend(f"- {f}" for f in failures)
        BLOCKERS_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("GATE FAILED:")
        for f in failures:
            print(f"  {f}")
        return 2

    print(f"GATE OK: {len(rows)} filas, {len(tickers)} empresas, "
          f"regresión gold {gold_matches}/{gold_total}")
    return 0


# ---------------------------------------------------------------------------
# report
# ---------------------------------------------------------------------------


def cmd_report() -> int:
    """Write coverage_report.md from the manifest."""
    tickers, _meta = _load_frozen_list()
    rows = _read_manifest()
    n_filings = len(rows)
    n_companies = len(tickers)
    total_cells = n_filings * len(CORE_METRICS)
    filled = sum(1 for r in rows for m in CORE_METRICS if r[m] != "NULL")
    coverage_pct = 100.0 * filled / total_cells if total_cells else 0.0

    per_metric: list[tuple[str, int, int, str]] = []
    for m in CORE_METRICS:
        got = sum(1 for r in rows if r[m] != "NULL")
        reasons = Counter(
            r[f"{m}_null_reason"] for r in rows if r[m] == "NULL"
        )
        dominant = reasons.most_common(1)[0][0] if reasons else "n/a"
        per_metric.append((m, got, n_filings, dominant))

    per_sector: dict[str, tuple[int, int]] = {}
    for sector in sorted({r["sector"] for r in rows}):
        sector_rows = [r for r in rows if r["sector"] == sector]
        got = sum(1 for r in sector_rows for m in CORE_METRICS if r[m] != "NULL")
        per_sector[sector] = (got, len(sector_rows) * len(CORE_METRICS))

    null_reason_counts = Counter(
        r[f"{m}_null_reason"] for r in rows for m in CORE_METRICS if r[m] == "NULL"
    )

    restatement_count = 0
    if RESTATEMENTS_PATH.is_file():
        for line in RESTATEMENTS_PATH.read_text(encoding="utf-8").splitlines():
            if line.startswith("**Total:"):
                restatement_count = int(line.split()[1])
                break

    chain_changes = "ninguna"
    if CHANGELOG_PATH.is_file():
        entries = [
            line for line in CHANGELOG_PATH.read_text(encoding="utf-8").splitlines()
            if line.startswith("## ") and "+=" in line
        ]
        if entries:
            chain_changes = f"{len(entries)} (ver `chain_changelog.md`)"

    lines = [
        "# Corpus S&P 100 — informe de cobertura (T5.1)",
        "",
        "Cobertura de la extracción estructurada L3 (sin LLM) sobre el",
        "corpus congelado en `corpus_tickers.txt`. Este informe mide",
        "COBERTURA, no accuracy: la única afirmación de accuracy sigue",
        "siendo el gold standard N=60 (`docs/eval/results_real.md`).",
        "",
        "## Totales",
        "",
        f"- Filings 10-K procesados: **{n_filings}**",
        f"- Empresas: **{n_companies}** (FY2022-FY2024, 3 años por empresa)",
        f"- Celdas métrica: {total_cells} ({len(CORE_METRICS)} métricas core x {n_filings} filings)",
        f"- Cobertura de campos: **{filled}/{total_cells} = {coverage_pct:.1f}%**",
        "- Nulls por motivo: "
        + ", ".join(f"{k or 'sin motivo'}={v}" for k, v in sorted(null_reason_counts.items())),
        f"- Restatements documentados: {restatement_count} (ver `restatements_log.md`)",
        f"- Extensiones de la cadena de tags: {chain_changes}",
        "",
        "## Cobertura por métrica",
        "",
        "| Métrica | Cobertura | % | Motivo dominante de null |",
        "|---------|-----------|---|--------------------------|",
    ]
    for m, got, total, dominant in per_metric:
        pct = 100.0 * got / total if total else 0.0
        lines.append(f"| {m} | {got}/{total} | {pct:.1f}% | {dominant} |")
    lines += [
        "",
        "## Cobertura por sector (división SIC)",
        "",
        "| Sector | Cobertura | % |",
        "|--------|-----------|---|",
    ]
    for sector, (got, total) in per_sector.items():
        pct = 100.0 * got / total if total else 0.0
        lines.append(f"| {sector} | {got}/{total} | {pct:.1f}% |")
    COVERAGE_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"report: {n_filings} filings, {n_companies} empresas, "
          f"cobertura {coverage_pct:.1f}%")
    return 0


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["screen", "run", "gate", "report"])
    args = parser.parse_args(argv)
    load_config()  # populates os.environ from .env (SEC_USER_AGENT)
    handlers = {
        "screen": cmd_screen,
        "run": cmd_run,
        "gate": cmd_gate,
        "report": cmd_report,
    }
    return handlers[args.command]()


if __name__ == "__main__":
    raise SystemExit(main())
