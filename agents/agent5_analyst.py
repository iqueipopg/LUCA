"""L5 Analyst agent (T2.5 + T2.6).

Two responsibilities:

* **Derived metrics (deterministic, no LLM).** Margins, ratios and YoY growth
  computed by pure arithmetic over the L3 metric set. Per the project rule
  "XBRL antes que LLM", numbers never come from the model.
* **Risk classification (LLM).** Each L4 risk is tagged with exactly one
  category from ``config/agents.json::L5_analyst.risk_categories`` (the 6-item
  list is the source of truth; see ``docs/review/pending_human_review.md``).

YoY data source:
    L3 (``agent3_extractor.extract``) exposes only the current fiscal year, so
    YoY reads the prior-year fact straight from ``ingest_output["xbrl_data"]``,
    reusing L3's tag-chain helpers **without modifying L3** (frozen). The same
    730-day recency guard (T2.0b) is applied against ``filing_date``: a stale
    prior fact yields ``None`` rather than an absurd YoY against an old value.

L5 has no frozen schema yet; the output here is ``schema_version 0.1``.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from agents._config import PROJECT_ROOT, get_agent_config
from agents._llm_client import LLMClient, parse_json_response
from agents._logging import get_logger
from agents.agent3_extractor import (
    _MAX_FACT_AGE_DAYS,
    _METRIC_UNITS,
    _collect_annual_candidates,
    _lookup_tags,
    _parse_iso_date,
)

_LOGGER = get_logger(__name__)

#: Classification temperature. Read from config if present (rule: temperatures
#: live in config/agents.json); defaults low for stable, near-deterministic
#: category assignment. A ``temperature`` key could be added to the
#: L5_analyst block to override (flagged in pending_human_review.md).
_DEFAULT_CLASSIFY_TEMPERATURE: float = 0.1

#: Metrics for which YoY is computed (period-flow income-statement items).
_YOY_METRICS: tuple[str, ...] = ("revenue", "net_income")

#: Max risks per classification call. A single call with ~100 risks overflows
#: the response and silently drops items; batching keeps each response small
#: enough to come back complete.
_CLASSIFY_BATCH_SIZE: int = 20


# ---------------------------------------------------------------------------
# Deterministic derived metrics
# ---------------------------------------------------------------------------


def _mval(metrics: dict[str, Any], name: str) -> float | None:
    """Return the numeric value of an L3 metric, or ``None`` if absent."""
    entry = metrics.get(name)
    if isinstance(entry, dict):
        v = entry.get("value")
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return float(v)
    return None


def _ratio(num: float | None, den: float | None) -> float | None:
    """Safe division: ``None`` if either operand missing or denominator zero."""
    if num is None or den is None or den == 0:
        return None
    return num / den


def compute_margins(metrics: dict[str, Any]) -> dict[str, Any]:
    """Net/operating margins. ``gross_margin`` is not computable (no COGS)."""
    revenue = _mval(metrics, "revenue")
    return {
        "net_margin": _ratio(_mval(metrics, "net_income"), revenue),
        "operating_margin": _ratio(_mval(metrics, "operating_income"), revenue),
        "gross_margin": None,
        "_notes": {
            "gross_margin": "no computable: COGS/gross_profit fuera del set de métricas L3",
        },
    }


def compute_ratios(metrics: dict[str, Any]) -> dict[str, Any]:
    """ROE, ROA, debt-to-equity and equity ratio (all None-safe)."""
    net_income = _mval(metrics, "net_income")
    total_equity = _mval(metrics, "total_equity")
    total_assets = _mval(metrics, "total_assets")
    long_term_debt = _mval(metrics, "long_term_debt")
    return {
        "roe": _ratio(net_income, total_equity),
        "roa": _ratio(net_income, total_assets),
        "debt_to_equity": _ratio(long_term_debt, total_equity),
        "equity_ratio": _ratio(total_equity, total_assets),
    }


def _prior_year_fact(
    us_gaap: dict[str, Any],
    metric: str,
    current_period_end: str | None,
    filing_date: str | None,
) -> dict[str, Any] | None:
    """Return the FY-1 annual fact for ``metric`` from companyfacts.

    Selects the annual fact (across the whole tag chain, L3 logic) with the
    largest ``end`` strictly earlier than ``current_period_end``, tie-broken by
    tag priority. Applies the 730-day recency guard against ``filing_date``: a
    stale prior fact returns ``None``.
    """
    expected_unit = _METRIC_UNITS.get(metric)
    cur_end = _parse_iso_date(current_period_end)
    if expected_unit is None or cur_end is None or not isinstance(us_gaap, dict):
        return None

    candidates = _collect_annual_candidates(us_gaap, _lookup_tags(metric), expected_unit)
    priors = [c for c in candidates if c[0] < cur_end]
    if not priors:
        return None
    # Most recent prior first; tie-break by tag priority (lower index wins).
    priors.sort(key=lambda it: (-it[0].toordinal(), it[1]))
    end_date, _priority, tag, fact = priors[0]

    filing_date_obj = _parse_iso_date(filing_date)
    if filing_date_obj is not None and (filing_date_obj - end_date).days > _MAX_FACT_AGE_DAYS:
        _LOGGER.info(
            "YoY %s: prior fact (end=%s) stale (>%dd tras filing); None",
            metric, fact.get("end"), _MAX_FACT_AGE_DAYS,
        )
        return None
    return {
        "value": float(fact["val"]),
        "period_end": fact.get("end"),
        "fiscal_year": fact.get("fy") if isinstance(fact.get("fy"), int) else None,
        "tag_used": tag,
    }


def compute_yoy(
    metrics: dict[str, Any],
    us_gaap: dict[str, Any] | None,
    filing_date: str | None,
) -> dict[str, Any]:
    """Year-over-year growth for revenue and net_income.

    Returns ``{metric: {current, prior, yoy_pct, prior_period_end}}``. When the
    prior fact is missing or stale, ``prior`` and ``yoy_pct`` are ``None``.
    """
    out: dict[str, Any] = {}
    for metric in _YOY_METRICS:
        entry = metrics.get(metric)
        current = _mval(metrics, metric)
        period_end = entry.get("period_end") if isinstance(entry, dict) else None
        prior_fact = (
            _prior_year_fact(us_gaap, metric, period_end, filing_date)
            if us_gaap is not None and current is not None
            else None
        )
        prior = prior_fact["value"] if prior_fact else None
        yoy_pct = None
        if prior is not None and prior != 0 and current is not None:
            yoy_pct = (current - prior) / abs(prior)
        out[metric] = {
            "current": current,
            "prior": prior,
            "yoy_pct": yoy_pct,
            "prior_period_end": prior_fact["period_end"] if prior_fact else None,
        }
    return out


# ---------------------------------------------------------------------------
# Risk classification (LLM)
# ---------------------------------------------------------------------------

_CLASSIFY_SYSTEM_PROMPT_TMPL: str = (
    "You are a financial-risk taxonomist. Assign each risk to EXACTLY ONE "
    "category from this closed set: {categories}.\n"
    "Guidance: operational = execution/supply/people/operations; financial = "
    "liquidity/credit/capital/FX/rates; regulatory = laws/compliance/legal/tax; "
    "market = demand/competition/pricing/macro; technological = IT/cyber/IP/"
    "innovation; geopolitical = war/sanctions/trade/country risk.\n"
    "Output STRICT JSON only: "
    '{{"classifications": [{{"id": "<risk id>", "category": "<one of the set>"}}]}}. '
    "Use the exact ids given; do not invent risks."
)


def classify_risks(
    risks: list[dict[str, Any]],
    categories: list[str],
    client: LLMClient,
    *,
    temperature: float,
    warnings: list[str],
) -> list[dict[str, Any]]:
    """Classify L4 risks into categories via a single batched LLM call.

    Each returned risk gets a ``category`` field (one of ``categories`` or
    ``None`` if the model failed). Never raises: parse/transport errors degrade
    to ``category=None`` with a warning.
    """
    if not risks:
        return []

    valid = {c.lower(): c for c in categories}
    by_id = {r["id"]: dict(r) for r in risks}
    for r in by_id.values():
        r["category"] = None

    system = _CLASSIFY_SYSTEM_PROMPT_TMPL.format(categories=", ".join(categories))

    # Batch so each response stays small enough to come back complete: a single
    # call with ~100 risks silently drops most of them.
    for start in range(0, len(risks), _CLASSIFY_BATCH_SIZE):
        batch = risks[start:start + _CLASSIFY_BATCH_SIZE]
        compact = [
            {"id": r["id"], "title": r.get("title", ""), "summary": r.get("summary", "")}
            for r in batch
        ]
        user = "Classify these risks:\n" + json.dumps(compact, ensure_ascii=False)
        try:
            raw = client.chat(system=system, user=user, temperature=temperature, num_ctx=8192)
            parsed = parse_json_response(raw)
            rows = parsed.get("classifications", []) if isinstance(parsed, dict) else []
        except Exception as exc:  # noqa: BLE001 — a bad batch must not abort the run
            warnings.append(
                f"Risk classification batch {start}-{start + len(batch)} failed ({exc})"
            )
            _LOGGER.warning("L5 clasificación batch %d falló (%s)", start, exc)
            continue
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            rid = row.get("id")
            cat = str(row.get("category", "")).strip().lower()
            if rid in by_id and cat in valid:
                by_id[rid]["category"] = valid[cat]

    unclassified = [rid for rid, r in by_id.items() if r["category"] is None]
    if unclassified:
        warnings.append(
            f"{len(unclassified)} risks left unclassified (category=None): "
            f"{unclassified[:5]}{'...' if len(unclassified) > 5 else ''}"
        )
    # Preserve original risk order.
    return [by_id[r["id"]] for r in risks]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze(
    l3_output: dict[str, Any],
    l4_output: dict[str, Any],
    *,
    ingest_output: dict[str, Any] | None = None,
    llm: LLMClient | None = None,
) -> dict[str, Any]:
    """Run L5: deterministic derived metrics + LLM risk classification.

    Args:
        l3_output: Output of :func:`agents.agent3_extractor.extract`.
        l4_output: L4 JSON (or ``L4Output.model_dump()``) with ``risks``.
        ingest_output: L1 payload; **required for YoY** (carries ``xbrl_data``).
            If ``None``, YoY fields are ``None`` and a warning is recorded.
        llm: Injectable client for classification (tests mock it).

    Returns:
        The L5 analysis dict (also written to
        ``outputs/intermediate/{TICKER}_L5.json``).
    """
    cfg = get_agent_config("L5_analyst")
    categories = list(cfg.get("risk_categories", []))
    min_risks = int(cfg.get("min_risks", 0))
    max_risks = int(cfg.get("max_risks", 10_000))
    temperature = float(cfg.get("temperature", _DEFAULT_CLASSIFY_TEMPERATURE))

    client = llm if llm is not None else LLMClient()

    ticker = l3_output.get("ticker", "")
    fiscal_year = l3_output.get("fiscal_year")
    metrics = l3_output.get("metrics", {}) or {}
    risks = list(l4_output.get("risks", []) or [])
    warnings: list[str] = []

    us_gaap = None
    filing_date = None
    if ingest_output is not None:
        xbrl = ingest_output.get("xbrl_data") or {}
        us_gaap = (xbrl.get("facts") or {}).get("us-gaap")
        filing_date = ingest_output.get("filing_date")
    else:
        warnings.append("ingest_output not provided: YoY unavailable")

    derived = {
        "margins": compute_margins(metrics),
        "ratios": compute_ratios(metrics),
        "yoy": compute_yoy(metrics, us_gaap, filing_date),
    }

    if len(risks) < min_risks:
        warnings.append(f"risk count {len(risks)} below configured minimum {min_risks}")
    if len(risks) > max_risks:
        warnings.append(f"risk count {len(risks)} above configured maximum {max_risks}")

    classified = classify_risks(
        risks, categories, client, temperature=temperature, warnings=warnings
    )
    cat_counts: dict[str, int] = {}
    for r in classified:
        key = r.get("category") or "unclassified"
        cat_counts[key] = cat_counts.get(key, 0) + 1

    result = {
        "schema_version": "0.1",
        "agent": "L5",
        "ticker": ticker,
        "fiscal_year": fiscal_year,
        "derived_metrics": derived,
        "risks_classified": classified,
        "meta": {
            "n_risks": len(classified),
            "categories_used": cat_counts,
            "warnings": warnings,
            "model": {"name": client.model, "temperature": temperature},
        },
    }

    out_dir = PROJECT_ROOT / "outputs" / "intermediate"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{ticker}_L5.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _LOGGER.info(
        "L5 %s: %d riesgos clasificados, categorías=%s",
        ticker, len(classified), cat_counts,
    )
    return result


__all__ = ["analyze", "compute_margins", "compute_ratios", "compute_yoy", "classify_risks"]
