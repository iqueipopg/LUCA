"""Tests for the L7 Writer agent (T3.1).

The LLM is mocked so prose is deterministic. The assertions focus on the
contract the memo must honour regardless of model quality: the six Spanish
headings, the deterministic Financial Highlights numbers (never from the LLM),
the Outlook limitation note, and the written file.
"""

from __future__ import annotations

import agents.agent7_writer as l7
from agents.agent7_writer import write_memo


class FakeLLM:
    def __init__(self, response="Texto de prueba generado.", model="qwen2.5:7b-instruct-q4_K_M"):
        self._response = response
        self.model = model
        self.calls = 0

    def chat(self, system, user, *, temperature=0.2, num_ctx=8192, max_tokens=None):
        self.calls += 1
        return self._response


def _metric(value, **kw):
    base = {"value": value, "fiscal_year": 2025, "period_end": "2025-09-27",
            "tag_used": "SomeTag", "accession": "0000320193-25-000079"}
    base.update(kw)
    return base


def _l3():
    return {"ticker": "AAPL", "company": "Apple Inc.", "fiscal_year": 2025, "metrics": {
        "revenue": _metric(416161000000.0), "net_income": _metric(112010000000.0),
        "operating_income": _metric(133000000000.0), "total_assets": _metric(359241000000.0),
        "total_equity": _metric(73000000000.0), "eps_diluted": _metric(7.46),
        "cash": _metric(30000000000.0), "long_term_debt": _metric(78000000000.0)}}


def _l5():
    return {"derived_metrics": {
        "margins": {"net_margin": 0.2692, "operating_margin": 0.3197, "gross_margin": None},
        "ratios": {"roe": 1.52},
        "yoy": {"revenue": {"yoy_pct": 0.0643}, "net_income": {"yoy_pct": 0.195}}},
        "risks_classified": [
            {"id": "R-AAPL-001", "title": "Supply chain", "summary": "Riesgo de suministro.",
             "category": "operational"}]}


def test_memo_has_six_spanish_sections(tmp_path):
    memo = write_memo(_l3(), _l5(), l2_output={"item_1": "Apple diseña productos."},
                      llm_client=FakeLLM(), output_dir=tmp_path)
    for heading in ("## Resumen ejecutivo", "## Visión general", "## Aspectos financieros",
                    "## Análisis de riesgos", "## Perspectivas y guidance", "## Apéndice"):
        assert heading in memo


def test_financial_table_numbers_are_deterministic(tmp_path):
    # The LLM returns garbage; the table must still carry the real figures.
    memo = write_memo(_l3(), _l5(), llm_client=FakeLLM("999 fake number"),
                      output_dir=tmp_path)
    assert "416,161 M USD" in memo       # revenue in millions
    assert "7.46 USD/acción" in memo      # diluted EPS
    assert "26.9%" in memo                # net margin from L5
    assert "6.4%" in memo                 # revenue YoY from L5


def test_outlook_limitation_note_present(tmp_path):
    memo = write_memo(_l3(), _l5(), llm_client=FakeLLM(), output_dir=tmp_path)
    assert "Nota de limitación" in memo
    assert "forward-looking" in memo


def test_memo_written_to_disk(tmp_path):
    write_memo(_l3(), _l5(), l2_output={"filing_date": "2025-10-31"},
               llm_client=FakeLLM(), output_dir=tmp_path)
    assert (tmp_path / "AAPL_2025-10-31.md").exists()


def test_works_without_l5_using_l3_fallback(tmp_path):
    # No L5: derived metrics computed from L3, risks from L4.
    l4 = {"risks": [{"id": "R-AAPL-001", "title": "X", "summary": "y"}]}
    memo = write_memo(_l3(), None, l4_output=l4, llm_client=FakeLLM(), output_dir=tmp_path)
    assert "## Aspectos financieros" in memo
    assert "416,161 M USD" in memo  # deterministic even without L5


def test_no_risks_emits_limitation(tmp_path):
    memo = write_memo(_l3(), None, l4_output={"risks": []}, llm_client=FakeLLM(),
                      output_dir=tmp_path)
    assert "No se ejecutó la extracción de riesgos" in memo


def test_appendix_has_traceability(tmp_path):
    memo = write_memo(_l3(), _l5(), llm_client=FakeLLM(), output_dir=tmp_path)
    assert "Tag XBRL" in memo
    assert "0000320193-25-000079" in memo  # accession in appendix
