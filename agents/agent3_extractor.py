"""LUCA L3 Structured Extractor agent.

Sprint 1 scope (T1.3 + T1.4 + T1.5): map a fixed set of canonical metrics
to an ordered chain of US-GAAP XBRL tags (preferred first, fallbacks
after) and pick the most recent annual fact across the **entire chain**.

History of the selection algorithm
----------------------------------
* T1.3 — single primary tag per metric. ``form == "10-K"`` + ``fp == "FY"``
  + USD + duration ≥ 320d. The most recent annual fact within that one
  tag wins.
* T1.4 — primary → ordered tuple of candidates (``_TAG_CANDIDATES``).
  Selection logic was *"first candidate with any valid annual fact
  wins"*. This caused a bug on AAPL: ``Revenues`` carries a stale FY2017
  fact (because EDGAR companyfacts aggregates the entire filing
  history), so the ASC-606 tag (FY2018+) never got evaluated. See
  ``experiments/error_log_sprint1.md`` (2026-04-27 T1.4 entry).
* T1.5 — selection is now *"most recent fact across the **whole**
  candidate chain wins"*. Ties on ``end`` date are broken by candidate
  priority (earlier in ``_TAG_CANDIDATES`` wins). ``tag_used`` records
  whichever tag actually resolved, which is the input T1.10 needs to
  measure primary-vs-fallback coverage.

Currency policy (T1.5)
----------------------
This sprint only supports USD (or USD/shares for EPS). If a metric only
appears in another currency (CAD, EUR, JPY, …), the extractor returns
``None`` — there is no FX conversion. Multi-currency support is an
explicit non-goal of Sprint 1; LUCA is scoped to US filers (10-K), and
internationalisation belongs to a later sprint.

Period policy (T1.5)
--------------------
Two fact shapes are accepted:

* **Income statement / cash flow** — facts have both ``start`` and
  ``end``. The duration must be at least :data:`_MIN_ANNUAL_DURATION_DAYS`
  (320d). EDGAR sometimes labels Q1/Q2/Q3 slices with ``fp == "FY"``
  inside a 10-K filing; the duration guard is what filters those out.
  We use 320d (~45 weeks) instead of e.g. 360d so we keep 52-week
  fiscal years (~364d) and 53-week years (~371d) but reject quarterly
  slices (~90d) and fiscal-year-change "stub" periods (200–300d).
* **Balance sheet** — facts are instantaneous (``start`` is absent).
  ``end`` alone is enough; the form/fp filter still applies.

Other design notes
------------------
* Numeric data must come from XBRL, never from the LLM (project rule
  "XBRL antes que LLM").
* The agent is pure: it takes the L1 ingest dict and returns a new dict.
  No I/O, no network calls.
* Missing metrics yield ``None`` — the agent never raises on absent or
  malformed XBRL data, it only logs a warning and keeps going.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Final

from agents._gold_schema import GOLD_METRICS
from agents._logging import get_logger

_LOGGER = get_logger(__name__)


# ---------------------------------------------------------------------------
# Mapping configuration
# ---------------------------------------------------------------------------

#: Canonical metric name → ordered tuple of US-GAAP tag candidates. The
#: first tag in each tuple is the preferred one; the rest are fallbacks.
#: Selection is *"most recent fact across the whole chain"* (T1.5); the
#: order only matters as a tie-breaker when two candidates have the same
#: ``end`` date. The ``tuple`` (not ``list``) signals immutability.
#:
#: Justification per fallback:
#:   * ``revenue`` — ``Revenues`` was the canonical pre-ASC-606 tag. Most
#:     issuers migrated to ``RevenueFromContractWithCustomerExcludingAssessedTax``
#:     in FY2018+ when ASC 606 took effect; Apple is a textbook example
#:     (see ``experiments/error_log_sprint1.md`` 2026-04-27 entry).
#:     ``SalesRevenueNet`` was deprecated by FASB on 2018-01-31 but still
#:     appears in legacy filings; kept as a fallback.
#:     ``InterestAndDividendIncomeOperating`` is added as the **last**
#:     candidate to rescue commercial banks (SIC 6022 — e.g. JPM): the
#:     ASC-606 tags rarely cover banking revenue, and ``Revenues`` is
#:     often absent in those filings. The interest-income line accounts
#:     for ~60–65% of JPM's Net Revenue, so we accept the residual
#:     under-estimation and document it explicitly in T1.10. For the
#:     nine non-bank tickers in the gold standard, this tag is either
#:     absent or appears as a partial number; placing it last in the
#:     chain prevents contamination, because T1.5 picks the most
#:     recent fact across the chain — a partial bank-style value can
#:     only "win" if no other candidate has any recent annual fact.
#:   * ``net_income`` — ``NetIncomeLoss`` is the post-2009 standard.
#:     ``ProfitLoss`` is used by some IFRS-leaning filers and by the few
#:     issuers who report at the consolidated (pre-NCI) level; useful as
#:     a fallback when ``NetIncomeLoss`` is absent.
#:   * ``operating_income`` — single tag, ``OperatingIncomeLoss`` is the
#:     only widely-used US-GAAP element.
#:   * ``total_assets`` — single tag, ``Assets`` is canonical.
#:   * ``total_equity`` —
#:     ``StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest``
#:     is the **preferred** tag (placed first by review of ,
#:     2026-04-27): the consolidated form is always numerically correct
#:     for filers both with and without minority interests. The
#:     parent-only ``StockholdersEquity`` tag, used as a fallback,
#:     under-states equity for issuers with partially-owned subsidiaries
#:     (e.g. GOOGL, META). When no NCI exists, both tags publish the
#:     same value, so promoting the consolidated tag carries no risk.
#:   * ``eps_diluted`` — ``EarningsPerShareDiluted`` is canonical.
#:     ``IncomeLossFromContinuingOperationsPerDilutedShare`` is a rarer
#:     fallback for companies that report only the continuing-ops EPS line
#:     (e.g. mid-restructuring filers). Kept as best-effort.
#:   * ``cash`` (T2.0c) —
#:     ``CashAndCashEquivalentsAtCarryingValue`` is the standard post-2009
#:     US-GAAP element for the "Cash and cash equivalents" balance-sheet
#:     line. It captures the broader scope: physical cash plus highly
#:     liquid instruments with original maturities of three months or
#:     less (T-bills, money market funds, commercial paper), which is
#:     what filers report on the balance sheet under that caption. The
#:     fallback ``Cash`` is the strict "cash only" element used by some
#:     legacy filers (pre-2009) or by filers who keep equivalents on a
#:     separate line; it under-states liquidity relative to the preferred
#:     tag. Order matters: when both tags coexist (the same legacy filer
#:     that kept ``Cash`` may still publish the broader element after
#:     migrating), placing the broader tag first guarantees that we
#:     always favour the most informative number even though T1.5's
#:     "most recent across the whole chain" rule typically resolves them
#:     by recency. This is a balance-sheet element ("instant"): facts
#:     have ``end`` only — no ``start`` — and ``_is_annual_fact``
#:     accepts that shape.
#:   * ``long_term_debt`` (T2.0c) —
#:     ``LongTermDebtNoncurrent`` is the strict non-current portion of
#:     long-term debt — the fraction maturing beyond twelve months from
#:     the balance-sheet date. This is the canonical figure most analysts
#:     mean when they say "long-term debt" and it lines up with the
#:     non-current liabilities subtotal published in the consolidated
#:     balance sheet. The fallback ``LongTermDebt`` is the aggregate that
#:     bundles the current and non-current portions in a single element;
#:     it appears more often in banking and insurance taxonomies, and in
#:     a handful of legacy industrials that did not split the current
#:     portion onto its own line.
#:     **Banking caveat (SIC 6022):** for commercial banks (e.g. JPM)
#:     neither tag may be canonical — the banking taxonomy reports
#:     long-dated obligations under ``LongTermDebt``, ``SubordinatedDebt``,
#:     ``BeneficialInterestRelatedToOffBalanceSheetSecuritization`` and
#:     similar SIC-specific elements that we do not chase here.
#:     ``long_term_debt`` for SIC 6022 filers may therefore resolve to
#:     ``None`` even after T2.0c. This is a known limitation analogous
#:     to the JPM/operating_income case (see ``test_jpm_operating_income_is_none_when_tag_absent``);
#:     a banking-specific extension is out of scope for Sprint 2.
#:     Like ``cash``, this is a balance-sheet element ("instant") with
#:     ``end`` only and no ``start``.
_TAG_CANDIDATES: Final[dict[str, tuple[str, ...]]] = {
    "revenue": (
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
        # Last-resort fallback for SIC 6022 commercial banks (e.g. JPM).
        # See justification block above.
        "InterestAndDividendIncomeOperating",
    ),
    "net_income": (
        "NetIncomeLoss",
        "ProfitLoss",
    ),
    "operating_income": (
        "OperatingIncomeLoss",
    ),
    "total_assets": (
        "Assets",
    ),
    "total_equity": (
        # Consolidated (NCI-inclusive) is preferred — always correct for
        # filers with or without minority interests. See justification
        # block above (review of , 2026-04-27).
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
        "StockholdersEquity",
    ),
    "eps_diluted": (
        "EarningsPerShareDiluted",
        "IncomeLossFromContinuingOperationsPerDilutedShare",
    ),
    # T2.0c — balance-sheet additions.
    "cash": (
        "CashAndCashEquivalentsAtCarryingValue",
        "Cash",
    ),
    "long_term_debt": (
        "LongTermDebtNoncurrent",
        "LongTermDebt",
    ),
}

#: Canonical metric name → expected XBRL unit key. Anything else is filtered
#: out at selection time. Sprint 1 is USD-only (see module docstring).
_METRIC_UNITS: Final[dict[str, str]] = {
    "revenue": "USD",
    "net_income": "USD",
    "operating_income": "USD",
    "total_assets": "USD",
    "total_equity": "USD",
    "cash": "USD",
    "long_term_debt": "USD",
    "eps_diluted": "USD/shares",
}

#: Minimum duration (in days) between ``start`` and ``end`` for a fact to be
#: treated as an annual period. EDGAR sometimes labels quarterly slices with
#: ``fp == "FY"`` inside a 10-K filing; this guard avoids picking them up.
#: 320d also rejects fiscal-year-change "stub" periods (typically 200–300
#: days) without dropping legitimate 52-week years (~364d).
_MIN_ANNUAL_DURATION_DAYS: Final[int] = 320

#: Required EDGAR form for annual figures.
_REQUIRED_FORM: Final[str] = "10-K"

#: Required fiscal-period code for annual figures.
_REQUIRED_FP: Final[str] = "FY"

#: Maximum age of an XBRL fact relative to the filing date. Beyond this
#: bound the fact is treated as stale and the extractor returns None
#: for the metric. 730d (~2 fiscal years) accommodates 53-week years and
#: typical filing-date lag while rejecting facts older than the prior
#: fiscal year — the latter signal a stale tag inherited from EDGAR's
#: aggregated companyfacts history (e.g. JNJ/OperatingIncomeLoss
#: published last in FY2014 and never since). See T2.0b in
#: SPRINT_PLAN.md and the diary entry for Sprint 2.
_MAX_FACT_AGE_DAYS: Final[int] = 730


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _lookup_tags(metric: str) -> list[str]:
    """Return the ordered list of US-GAAP tags to try for ``metric``.

    The list goes preferred-first; under T1.5 the ordering only matters
    as a tie-breaker when two candidate tags expose facts with the same
    ``end`` date. The function returns a fresh ``list`` (not the
    underlying tuple) to keep callers from accidentally mutating the
    project-wide mapping.

    Args:
        metric: Canonical metric name (e.g. ``"revenue"``).

    Returns:
        List of XBRL tag names. Empty list if ``metric`` is unknown.
    """
    candidates = _TAG_CANDIDATES.get(metric)
    if not candidates:
        return []
    return list(candidates)


def _parse_iso_date(value: Any) -> date | None:
    """Parse an ISO ``YYYY-MM-DD`` string into a :class:`datetime.date`.

    Args:
        value: Raw value from the XBRL fact (expected to be ``str``).

    Returns:
        A :class:`date` object, or ``None`` if the input is malformed.
    """
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def _is_annual_fact(fact: dict[str, Any]) -> bool:
    """Return True if ``fact`` represents a full fiscal-year period.

    Two cases are accepted:

    * Income-statement / cash-flow facts have ``start`` and ``end`` roughly
      one year apart (``>= _MIN_ANNUAL_DURATION_DAYS``).
    * Balance-sheet facts ("instant") have only ``end`` (no ``start``).

    The fact must additionally come from a 10-K filing with ``fp == "FY"``.

    Args:
        fact: One element of ``us-gaap[tag][units][unit_key]``.

    Returns:
        True if the fact looks like an annual datapoint, else False.
    """
    if not isinstance(fact, dict):
        return False
    if fact.get("form") != _REQUIRED_FORM or fact.get("fp") != _REQUIRED_FP:
        return False

    end = _parse_iso_date(fact.get("end"))
    if end is None:
        return False

    start_raw = fact.get("start")
    if start_raw is None:
        # Instant fact (balance-sheet style): ``end`` alone is enough.
        return True

    start = _parse_iso_date(start_raw)
    if start is None:
        return False
    duration_days = (end - start).days
    return duration_days >= _MIN_ANNUAL_DURATION_DAYS


def _collect_annual_candidates(
    us_gaap: dict[str, Any],
    tags: list[str],
    expected_unit: str,
) -> list[tuple[date, int, str, dict[str, Any]]]:
    """Walk the candidate chain and gather every valid annual USD fact.

    For each tag in ``tags`` (in priority order), pull the facts
    published in ``expected_unit`` and keep those that pass
    :func:`_is_annual_fact`. Each survivor is bundled with enough
    information for the caller to make a global "most recent" decision
    while preserving tag priority for tie-breaks.

    Args:
        us_gaap: The ``xbrl_data["facts"]["us-gaap"]`` sub-dict.
        tags: Ordered list of candidate XBRL tag names. Index 0 has the
            highest priority.
        expected_unit: Required unit key (e.g. ``"USD"``).

    Returns:
        List of tuples ``(end_date, tag_priority, tag_name, fact_dict)``.
        ``tag_priority`` is the position of ``tag_name`` in ``tags`` (0
        = highest priority). The list is not sorted.
    """
    collected: list[tuple[date, int, str, dict[str, Any]]] = []

    for priority, tag in enumerate(tags):
        tag_block = us_gaap.get(tag)
        if not isinstance(tag_block, dict):
            continue
        units = tag_block.get("units")
        if not isinstance(units, dict):
            continue
        facts = units.get(expected_unit)
        if not isinstance(facts, list) or not facts:
            _LOGGER.debug(
                "Tag %s no tiene hechos en unidad %s", tag, expected_unit,
            )
            continue

        for fact in facts:
            if not _is_annual_fact(fact):
                continue
            end = _parse_iso_date(fact.get("end"))
            if end is None:
                continue
            value = fact.get("val")
            if not isinstance(value, (int, float)):
                continue
            collected.append((end, priority, tag, fact))

    return collected


def _extract_metric(
    us_gaap: dict[str, Any],
    metric: str,
    filing_date: str | None,
) -> dict[str, Any] | None:
    """Extract a single metric from the ``us-gaap`` namespace.

    The selection algorithm (T1.5) walks the **entire** candidate chain
    (``_TAG_CANDIDATES[metric]``), collecting every annual USD fact that
    passes the form/fp/duration filter, then picks the fact with the
    most recent ``end`` date. Ties on ``end`` are broken by tag
    priority — i.e. an earlier tag in the chain wins. ``tag_used`` in
    the output records whichever tag actually resolved (essential for
    T1.10's primary-vs-fallback coverage analysis).

    Recency guard (T2.0b): once the winning fact is selected, its
    ``end`` date is compared against ``filing_date``. If the fact is
    older than :data:`_MAX_FACT_AGE_DAYS`, it is treated as a stale tag
    inherited from EDGAR's aggregated companyfacts history (e.g.
    JNJ/OperatingIncomeLoss published last in FY2014) and the metric
    resolves to ``None``. When ``filing_date`` is missing or malformed
    the guard is disabled and a warning is logged; the pipeline keeps
    going with whatever the selector returned.

    Args:
        us_gaap: The ``xbrl_data["facts"]["us-gaap"]`` sub-dict.
        metric: Canonical metric name.
        filing_date: Filing date of the source 10-K in ISO ``YYYY-MM-DD``
            format. Used by the recency guard. ``None`` disables the
            guard (with a warning).

    Returns:
        A dict with keys ``value``, ``fiscal_year``, ``period_end``,
        ``tag_used``, ``unit`` and ``accession``; or ``None`` if no
        candidate tag yielded a usable annual USD fact, or if the
        winning fact failed the recency guard.
    """
    expected_unit = _METRIC_UNITS.get(metric)
    if expected_unit is None:
        _LOGGER.warning("Métrica desconocida %s, no hay unidad esperada", metric)
        return None

    tags = _lookup_tags(metric)
    candidates = _collect_annual_candidates(us_gaap, tags, expected_unit)

    if not candidates:
        _LOGGER.debug(
            "Métrica %s sin candidatos válidos en ningún tag (%s)",
            metric, ", ".join(tags) or "<vacío>",
        )
        return None

    # Sort by recency (most recent end first); break ties by tag priority
    # (lowest index first). ``tag_priority`` is already 0 = highest, so we
    # sort ascending on it.
    candidates.sort(key=lambda item: (-item[0].toordinal(), item[1]))
    end_date, _priority, tag_used, fact = candidates[0]

    # Recency guard (T2.0b). Apply only to the winning fact: the sort
    # above already brought the most recent fact across the whole chain
    # to position 0, so if *that* fact is stale every other candidate is
    # at least as old.
    filing_date_obj = _parse_iso_date(filing_date) if filing_date is not None else None
    if filing_date is None or filing_date_obj is None:
        _LOGGER.warning(
            "filing_date ausente para %s/%s; guard de recencia desactivado",
            metric, tag_used,
        )
    else:
        delta_days = (filing_date_obj - end_date).days
        if delta_days > _MAX_FACT_AGE_DAYS:
            _LOGGER.info(
                "Métrica %s: fact más reciente (tag=%s, end=%s) está stale "
                "(%d días tras filing); devolviendo None",
                metric, tag_used, fact.get("end"), delta_days,
            )
            return None

    fiscal_year = fact.get("fy")
    accession = fact.get("accn")

    return {
        "value": float(fact["val"]),
        "fiscal_year": int(fiscal_year) if isinstance(fiscal_year, int) else None,
        "period_end": fact.get("end"),
        "tag_used": tag_used,
        "unit": expected_unit,
        "accession": accession if isinstance(accession, str) else None,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract(ingest_output: dict[str, Any]) -> dict[str, Any]:
    """Run L3 Structured Extraction on an L1 ingest payload.

    The extractor is **USD-only** for Sprint 1 (see module docstring).
    Metrics published exclusively in another currency yield ``None``;
    no FX conversion is attempted.

    Args:
        ingest_output: Output of L1 Ingestion. The relevant keys are
            ``company``, ``ticker`` and ``xbrl_data`` (the EDGAR
            companyfacts JSON).

    Returns:
        Dict with keys ``company``, ``ticker``, ``fiscal_year`` and
        ``metrics``. ``metrics`` maps every canonical metric name in
        :data:`agents._gold_schema.GOLD_METRICS` to either ``None`` or a
        dict ``{value, fiscal_year, period_end, tag_used, unit,
        accession}``. ``fiscal_year`` at the top level is the most
        common ``fy`` seen across the extracted metrics, or ``None``
        when nothing was found.
    """
    if not isinstance(ingest_output, dict):
        ingest_output = {}

    ticker = ingest_output.get("ticker", "") or ""
    company = ingest_output.get("company", "") or ""
    raw_filing_date = ingest_output.get("filing_date")
    filing_date: str | None = (
        raw_filing_date if isinstance(raw_filing_date, str) else None
    )
    _LOGGER.info("Extrayendo métricas estructuradas para %s", ticker or "<unknown>")

    xbrl_data = ingest_output.get("xbrl_data") or {}
    facts = xbrl_data.get("facts") if isinstance(xbrl_data, dict) else None
    us_gaap = facts.get("us-gaap") if isinstance(facts, dict) else None
    if not isinstance(us_gaap, dict):
        _LOGGER.warning(
            "L3 no encontró facts['us-gaap'] en xbrl_data para %s, "
            "todas las métricas serán None",
            ticker or "<unknown>",
        )
        us_gaap = {}

    metrics: dict[str, dict[str, Any] | None] = {}
    fiscal_years: list[int] = []
    for metric in GOLD_METRICS:
        result = _extract_metric(us_gaap, metric, filing_date)
        metrics[metric] = result
        if result is not None and isinstance(result.get("fiscal_year"), int):
            fiscal_years.append(result["fiscal_year"])

    # Top-level fiscal_year: pick the most frequent fy across extracted
    # metrics (ties broken by most recent value).
    fiscal_year: int | None = None
    if fiscal_years:
        fiscal_year = max(set(fiscal_years), key=lambda fy: (fiscal_years.count(fy), fy))

    found = sum(1 for v in metrics.values() if v is not None)
    _LOGGER.info(
        "L3 completado para %s: %d/%d métricas extraídas (FY=%s)",
        ticker or "<unknown>", found, len(GOLD_METRICS),
        fiscal_year if fiscal_year is not None else "n/a",
    )

    return {
        "company": company,
        "ticker": ticker,
        "fiscal_year": fiscal_year,
        "metrics": metrics,
    }


# ---------------------------------------------------------------------------
# Fiscal-year-targeted selection (T5.0, corpus scale-up)
# ---------------------------------------------------------------------------
#
# ``extract`` above always picks the most recent annual fact across the
# chain — correct for "latest 10-K" pipelines and for the gold-standard
# evaluation, but useless for a corpus run that needs company C *at*
# fiscal year Y. The functions below add that capability without
# touching ``extract`` (gold-standard behavior is frozen; the corpus
# regression gate in ``experiments/corpus_run.py`` verifies both paths
# agree on the gold tickers).
#
# Selection semantics (as-originally-reported):
#
# 1. Anchor the fiscal year label Y to its period end E_Y: among ALL
#    us-gaap duration facts (form 10-K, fp FY, duration >= 320d) whose
#    ``fy`` field equals Y, E_Y is the latest ``end``. Duration facts
#    only — instant facts dated after year-end (subsequent events,
#    dividends declared) would corrupt the anchor. The accession most
#    frequently attached to those anchor facts is FY Y's own 10-K.
# 2. Per metric, walk the candidate chain and keep annual facts whose
#    ``end`` equals E_Y. Prefer the instance reported in FY Y's own
#    10-K (``fy == Y``); chain priority breaks ties. If the period only
#    survives as a comparative in a later filing, fall back to the
#    earliest such instance and mark ``source = "comparative"``.
# 3. Any later-filing instance of the chosen tag whose value differs
#    from the as-originally-reported value is returned under
#    ``restatements`` so the corpus runner can log it; the original
#    value is always the one kept.


def _fy_of_fact(fact: dict[str, Any]) -> int | None:
    """Return the ``fy`` field of an XBRL fact as an int, or ``None``."""
    fy = fact.get("fy")
    if isinstance(fy, bool):
        return None
    if isinstance(fy, int):
        return fy
    if isinstance(fy, str) and fy.strip().isdigit():
        return int(fy.strip())
    return None


def _anchor_fiscal_year(
    us_gaap: dict[str, Any],
    fiscal_year: int,
) -> tuple[date, str | None] | None:
    """Resolve fiscal-year label ``fiscal_year`` to its period end and 10-K.

    Scans every us-gaap tag for duration facts (``start`` + ``end``,
    duration >= :data:`_MIN_ANNUAL_DURATION_DAYS`) with ``form == 10-K``,
    ``fp == FY`` and ``fy == fiscal_year``. The latest ``end`` among them
    is the fiscal period end E_Y; the accession most frequently attached
    to facts at E_Y is that fiscal year's own 10-K.

    Args:
        us_gaap: The ``xbrl_data["facts"]["us-gaap"]`` sub-dict.
        fiscal_year: Target fiscal-year label (EDGAR ``fy`` field).

    Returns:
        Tuple ``(period_end, accession)``; ``accession`` may be ``None``
        if no fact carries a usable ``accn``. ``None`` when the company
        has no annual duration facts labelled ``fy == fiscal_year`` —
        i.e. it filed no 10-K for that fiscal year.
    """
    ends: list[tuple[date, str | None]] = []
    for tag_block in us_gaap.values():
        if not isinstance(tag_block, dict):
            continue
        units = tag_block.get("units")
        if not isinstance(units, dict):
            continue
        for facts in units.values():
            if not isinstance(facts, list):
                continue
            for fact in facts:
                if not isinstance(fact, dict):
                    continue
                if fact.get("form") != _REQUIRED_FORM or fact.get("fp") != _REQUIRED_FP:
                    continue
                if _fy_of_fact(fact) != fiscal_year:
                    continue
                start = _parse_iso_date(fact.get("start"))
                end = _parse_iso_date(fact.get("end"))
                if start is None or end is None:
                    continue
                if (end - start).days < _MIN_ANNUAL_DURATION_DAYS:
                    continue
                accn = fact.get("accn")
                ends.append((end, accn if isinstance(accn, str) else None))

    if not ends:
        return None

    period_end = max(end for end, _accn in ends)
    accn_counts: dict[str, int] = {}
    for end, accn in ends:
        if end == period_end and accn:
            accn_counts[accn] = accn_counts.get(accn, 0) + 1
    if not accn_counts:
        return period_end, None
    # Deterministic: highest count wins, lexicographic order breaks ties.
    accession = sorted(accn_counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    return period_end, accession


def _extract_metric_for_fy(
    us_gaap: dict[str, Any],
    metric: str,
    fiscal_year: int,
    period_end: date,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    """Extract ``metric`` for the fiscal year anchored at ``period_end``.

    Args:
        us_gaap: The ``xbrl_data["facts"]["us-gaap"]`` sub-dict.
        metric: Canonical metric name.
        fiscal_year: Target fiscal-year label.
        period_end: Period end E_Y resolved by :func:`_anchor_fiscal_year`.

    Returns:
        Tuple ``(result, restatements)``. ``result`` is ``None`` when no
        chain tag has an annual fact at ``period_end``; otherwise a dict
        with ``value``, ``fiscal_year``, ``period_end``, ``tag_used``,
        ``unit``, ``accession``, ``source_fy`` and ``source``
        (``"original"`` | ``"comparative"``). ``restatements`` lists
        later-filing instances of the chosen tag whose value differs
        from the kept one.
    """
    expected_unit = _METRIC_UNITS.get(metric)
    if expected_unit is None:
        _LOGGER.warning("Métrica desconocida %s, no hay unidad esperada", metric)
        return None, []

    candidates = _collect_annual_candidates(us_gaap, _lookup_tags(metric), expected_unit)
    matching = [c for c in candidates if c[0] == period_end]
    if not matching:
        return None, []

    originals = [c for c in matching if _fy_of_fact(c[3]) == fiscal_year]
    if originals:
        originals.sort(key=lambda c: c[1])
        chosen = originals[0]
        source = "original"
    else:
        # Only later comparatives carry this period: earliest report wins.
        matching.sort(key=lambda c: (_fy_of_fact(c[3]) or 9999, c[1]))
        chosen = matching[0]
        source = "comparative"

    _end, _priority, tag_used, fact = chosen
    chosen_value = float(fact["val"])
    chosen_fy = _fy_of_fact(fact)

    restatements: list[dict[str, Any]] = []
    seen: set[tuple[int | None, float]] = set()
    for c in matching:
        if c[2] != tag_used:
            continue
        other = c[3]
        other_fy = _fy_of_fact(other)
        if other_fy == chosen_fy:
            continue
        other_value = float(other["val"])
        key = (other_fy, other_value)
        if key in seen:
            continue
        seen.add(key)
        differs = (
            abs(other_value - chosen_value) / abs(chosen_value) > 1e-9
            if chosen_value != 0.0
            else other_value != 0.0
        )
        if differs:
            other_accn = other.get("accn")
            restatements.append({
                "metric": metric,
                "tag": tag_used,
                "period_end": fact.get("end"),
                "original_value": chosen_value,
                "original_fy": chosen_fy,
                "restated_value": other_value,
                "restated_fy": other_fy,
                "restated_accession": other_accn if isinstance(other_accn, str) else None,
            })

    accession = fact.get("accn")
    result = {
        "value": chosen_value,
        "fiscal_year": fiscal_year,
        "period_end": fact.get("end"),
        "tag_used": tag_used,
        "unit": expected_unit,
        "accession": accession if isinstance(accession, str) else None,
        "source_fy": chosen_fy,
        "source": source,
    }
    return result, restatements


def extract_for_fiscal_year(
    ingest_output: dict[str, Any],
    fiscal_year: int,
    metrics: tuple[str, ...] | None = None,
) -> dict[str, Any]:
    """Run L3 extraction targeted at one specific fiscal year.

    Unlike :func:`extract` (most-recent-wins, used by the pipeline and
    the gold-standard evaluation), this selects each metric *at* the
    given fiscal-year label, preferring the value as originally
    reported in that fiscal year's own 10-K. See the section comment
    above for the full semantics.

    Args:
        ingest_output: Output of L1 Ingestion (needs ``company``,
            ``ticker`` and ``xbrl_data``).
        fiscal_year: Target fiscal-year label (EDGAR ``fy`` field, the
            filer's own labelling convention).
        metrics: Metric names to extract. Defaults to
            :data:`agents._gold_schema.GOLD_METRICS`.

    Returns:
        Dict with ``company``, ``ticker``, ``fiscal_year``,
        ``period_end`` (ISO string or ``None``), ``accession`` (the
        fiscal year's own 10-K, or ``None``), ``metrics`` (per-metric
        result dicts or ``None``) and ``restatements`` (flat list across
        metrics). When the company has no 10-K facts for the fiscal
        year, every metric is ``None`` and ``period_end`` is ``None``.
    """
    if not isinstance(ingest_output, dict):
        ingest_output = {}
    if metrics is None:
        metrics = GOLD_METRICS

    ticker = ingest_output.get("ticker", "") or ""
    company = ingest_output.get("company", "") or ""

    xbrl_data = ingest_output.get("xbrl_data") or {}
    facts = xbrl_data.get("facts") if isinstance(xbrl_data, dict) else None
    us_gaap = facts.get("us-gaap") if isinstance(facts, dict) else None
    if not isinstance(us_gaap, dict):
        _LOGGER.warning(
            "L3-FY no encontró facts['us-gaap'] para %s (FY%s)",
            ticker or "<unknown>", fiscal_year,
        )
        us_gaap = {}

    anchor = _anchor_fiscal_year(us_gaap, fiscal_year)
    if anchor is None:
        _LOGGER.info(
            "L3-FY: %s no tiene hechos anuales 10-K con fy=%s",
            ticker or "<unknown>", fiscal_year,
        )
        return {
            "company": company,
            "ticker": ticker,
            "fiscal_year": fiscal_year,
            "period_end": None,
            "accession": None,
            "metrics": {m: None for m in metrics},
            "restatements": [],
        }

    period_end, filing_accession = anchor
    results: dict[str, dict[str, Any] | None] = {}
    all_restatements: list[dict[str, Any]] = []
    for metric in metrics:
        result, restatements = _extract_metric_for_fy(
            us_gaap, metric, fiscal_year, period_end,
        )
        results[metric] = result
        all_restatements.extend(restatements)

    found = sum(1 for v in results.values() if v is not None)
    _LOGGER.info(
        "L3-FY completado para %s FY%s (end=%s): %d/%d métricas",
        ticker or "<unknown>", fiscal_year, period_end.isoformat(),
        found, len(metrics),
    )

    return {
        "company": company,
        "ticker": ticker,
        "fiscal_year": fiscal_year,
        "period_end": period_end.isoformat(),
        "accession": filing_accession,
        "metrics": results,
        "restatements": all_restatements,
    }


__all__ = ["extract", "extract_for_fiscal_year"]
