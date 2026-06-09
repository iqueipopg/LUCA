"""Tests for the L5 Analyst agent (T2.5 + T2.6).

Derived metrics are pure arithmetic (no mock). YoY is exercised against a
synthetic companyfacts block for tight control, including the 730-day stale
guard. Classification uses a scripted :class:`FakeLLM`.
"""

from __future__ import annotations

import json

from agents.agent5_analyst import (
    analyze,
    classify_risks,
    compute_margins,
    compute_ratios,
    compute_yoy,
)


def _metric(value, period_end="2025-09-27"):
    return {"value": value, "period_end": period_end, "fiscal_year": 2025}


class FakeLLM:
    def __init__(self, response, model="qwen2.5:7b-instruct-q4_K_M"):
        self._response = response
        self.model = model
        self.calls = []

    def chat(self, system, user, *, temperature=0.2, num_ctx=8192, max_tokens=None):
        self.calls.append({"system": system, "user": user})
        return self._response


# ---------------------------------------------------------------------------
# Deterministic derived metrics
# ---------------------------------------------------------------------------


def test_margins_exact():
    metrics = {"revenue": _metric(1000.0), "net_income": _metric(250.0),
               "operating_income": _metric(300.0)}
    m = compute_margins(metrics)
    assert m["net_margin"] == 0.25
    assert m["operating_margin"] == 0.30
    assert m["gross_margin"] is None


def test_margins_none_safe_when_operating_income_missing():
    # JPM-like: operating_income is None.
    metrics = {"revenue": _metric(1000.0), "net_income": _metric(250.0),
               "operating_income": None}
    m = compute_margins(metrics)
    assert m["net_margin"] == 0.25
    assert m["operating_margin"] is None


def test_ratios_exact_and_none_safe():
    metrics = {"net_income": _metric(200.0), "total_equity": _metric(800.0),
               "total_assets": _metric(2000.0), "long_term_debt": _metric(400.0)}
    r = compute_ratios(metrics)
    assert r["roe"] == 0.25
    assert r["roa"] == 0.10
    assert r["debt_to_equity"] == 0.5
    assert r["equity_ratio"] == 0.4
    # Missing long_term_debt -> None
    r2 = compute_ratios({"net_income": _metric(200.0), "total_equity": _metric(800.0)})
    assert r2["debt_to_equity"] is None
    assert r2["roa"] is None  # total_assets missing


def test_ratio_zero_denominator_is_none():
    metrics = {"net_income": _metric(200.0), "total_equity": _metric(0.0)}
    assert compute_ratios(metrics)["roe"] is None


# ---------------------------------------------------------------------------
# YoY
# ---------------------------------------------------------------------------


def _synthetic_usgaap(current_val, prior_val, prior_end="2024-09-28"):
    return {
        "Revenues": {"units": {"USD": [
            {"form": "10-K", "fp": "FY", "start": "2024-09-29", "end": "2025-09-27",
             "val": current_val, "fy": 2025, "accn": "a"},
            {"form": "10-K", "fp": "FY", "start": "2023-10-01", "end": prior_end,
             "val": prior_val, "fy": 2024, "accn": "b"},
        ]}}
    }


def test_yoy_computed_from_companyfacts():
    metrics = {"revenue": _metric(416161000000.0), "net_income": _metric(112010000000.0)}
    us_gaap = _synthetic_usgaap(416161000000.0, 391035000000.0)
    yoy = compute_yoy(metrics, us_gaap, filing_date="2025-10-31")
    rev = yoy["revenue"]
    assert rev["prior"] == 391035000000.0
    assert abs(rev["yoy_pct"] - (416161000000.0 - 391035000000.0) / 391035000000.0) < 1e-9
    assert rev["prior_period_end"] == "2024-09-28"


def test_yoy_none_when_prior_stale():
    metrics = {"revenue": _metric(416161000000.0)}
    # Prior fact ends in 2020 -> >730 days before a 2025-10-31 filing.
    us_gaap = _synthetic_usgaap(416161000000.0, 300000000000.0, prior_end="2020-09-26")
    yoy = compute_yoy(metrics, us_gaap, filing_date="2025-10-31")
    assert yoy["revenue"]["prior"] is None
    assert yoy["revenue"]["yoy_pct"] is None


def test_yoy_none_when_no_usgaap():
    metrics = {"revenue": _metric(416161000000.0)}
    yoy = compute_yoy(metrics, None, filing_date="2025-10-31")
    assert yoy["revenue"]["prior"] is None


def test_yoy_against_real_aapl_fixture(companyfacts_aapl):
    # Integration: must not crash and should find a prior revenue fact.
    us_gaap = companyfacts_aapl["facts"]["us-gaap"]
    metrics = {"revenue": _metric(416161000000.0), "net_income": _metric(112010000000.0)}
    yoy = compute_yoy(metrics, us_gaap, filing_date="2025-10-31")
    assert "revenue" in yoy and "net_income" in yoy


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

_CATS = ["operational", "financial", "regulatory", "market", "technological", "geopolitical"]
_RISKS = [
    {"id": "R-AAPL-001", "title": "Supply chain", "summary": "..."},
    {"id": "R-AAPL-002", "title": "FX exposure", "summary": "..."},
]


def test_classification_assigns_categories():
    resp = json.dumps({"classifications": [
        {"id": "R-AAPL-001", "category": "operational"},
        {"id": "R-AAPL-002", "category": "financial"},
    ]})
    warnings: list[str] = []
    out = classify_risks(_RISKS, _CATS, FakeLLM(resp), temperature=0.1, warnings=warnings)
    assert {r["id"]: r["category"] for r in out} == {
        "R-AAPL-001": "operational", "R-AAPL-002": "financial"}
    assert warnings == []


def test_classification_out_of_vocab_becomes_none_with_warning():
    resp = json.dumps({"classifications": [
        {"id": "R-AAPL-001", "category": "made_up_category"},
        {"id": "R-AAPL-002", "category": "FINANCIAL"},  # case-insensitive ok
    ]})
    warnings: list[str] = []
    out = classify_risks(_RISKS, _CATS, FakeLLM(resp), temperature=0.1, warnings=warnings)
    by = {r["id"]: r["category"] for r in out}
    assert by["R-AAPL-001"] is None
    assert by["R-AAPL-002"] == "financial"
    assert any("unclassified" in w for w in warnings)


def test_classification_malformed_json_degrades_gracefully():
    warnings: list[str] = []
    out = classify_risks(_RISKS, _CATS, FakeLLM("not json"), temperature=0.1, warnings=warnings)
    assert all(r["category"] is None for r in out)
    assert any("failed" in w.lower() for w in warnings)
    assert len(out) == 2  # order/count preserved


# ---------------------------------------------------------------------------
# Full analyze()
# ---------------------------------------------------------------------------


def test_analyze_end_to_end(tmp_path, monkeypatch):
    import agents.agent5_analyst as l5
    monkeypatch.setattr(l5, "PROJECT_ROOT", tmp_path)

    l3 = {"ticker": "AAPL", "fiscal_year": 2025, "metrics": {
        "revenue": _metric(1000.0), "net_income": _metric(250.0),
        "operating_income": _metric(300.0), "total_assets": _metric(2000.0),
        "total_equity": _metric(800.0), "long_term_debt": _metric(400.0)}}
    l4 = {"risks": [{"id": "R-AAPL-001", "title": "Supply chain", "summary": "x"}]}
    resp = json.dumps({"classifications": [{"id": "R-AAPL-001", "category": "operational"}]})

    out = analyze(l3, l4, ingest_output=None, llm=FakeLLM(resp))
    assert out["agent"] == "L5"
    assert out["derived_metrics"]["margins"]["net_margin"] == 0.25
    assert out["risks_classified"][0]["category"] == "operational"
    # ingest_output=None -> YoY unavailable warning
    assert any("yoy unavailable" in w.lower() for w in out["meta"]["warnings"])
    assert (tmp_path / "outputs" / "intermediate" / "AAPL_L5.json").exists()
