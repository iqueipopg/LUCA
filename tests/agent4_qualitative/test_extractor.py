"""Tests for the L4-mínimo risk extractor (T2.3).

The LLM is replaced by a :class:`FakeLLM` so chunk-by-chunk behaviour is
deterministic. The chunker itself is exercised for real on a small synthetic
Item 1A document (same shape as ``test_chunker.py``), so the chunk_id remap
and ``source_chunk_id`` invariants are tested end-to-end against the real
:class:`agents._schemas.L4Output` contract.
"""

from __future__ import annotations

import json

import pytest

from agents._schemas import L4Output
from agents.agent4_qualitative import extractor as l4
from agents.agent4_qualitative.extractor import extract_qualitative


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# Filler long enough that Item 1A spans well past the 200-char offset
# find_item1a_range() uses when searching for the Item 1B closing anchor.
_FILLER = (
    " body content here. The following describes material factors that could "
    "adversely affect our business, financial condition and results of "
    "operations, and the trading price of our securities in future periods."
)


def _bold_div(text: str, body: str = _FILLER, *, weight: str = "700") -> str:
    return f'<div><span style="font-weight:{weight}">{text}</span>{body}</div>'


def _build_item1a_html(body_divs: list[str]) -> str:
    head = "<html><body>"
    intro = (
        '<div>Item 1A. Risk Factors The following discussion sets forth '
        "the risk factors that could materially adversely affect our business "
        "and the value of an investment in our securities, and should be read "
        "together with the consolidated financial statements.</div>"
    )
    tail = "<div>Item 1B. Unresolved Staff Comments. None.</div></body></html>"
    return head + intro + "".join(body_divs) + tail


def _ingest(html: str, ticker: str = "TEST") -> dict:
    return {
        "ticker": ticker,
        "company": f"{ticker} Inc.",
        "filing_date": "2025-10-31",
        "accession_number": "0000320193-25-000079",
        "html_content": html,
    }


class FakeLLM:
    """Minimal stand-in for :class:`LLMClient` with scripted responses."""

    def __init__(self, responses, model: str = "qwen2.5:7b-instruct-q4_K_M"):
        # ``responses`` may be a single string (reused) or a list cycled per call.
        self._responses = responses
        self.model = model
        self.calls: list[dict] = []

    def chat(self, system, user, *, temperature=0.2, num_ctx=8192, max_tokens=None):
        self.calls.append({"system": system, "user": user})
        if isinstance(self._responses, str):
            return self._responses
        idx = min(len(self.calls) - 1, len(self._responses) - 1)
        return self._responses[idx]


def _risk_json(title="Supply chain disruption", summary="Riesgo de cadena de suministro.",
               quote="body content here."):
    return json.dumps(
        {"risks": [{"title": title, "summary": summary, "literal_quote": quote}]}
    )


@pytest.fixture(autouse=True)
def _isolate_output(tmp_path, monkeypatch):
    """Redirect outputs/intermediate to a tmp dir so tests don't pollute repo."""
    monkeypatch.setattr(l4, "PROJECT_ROOT", tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_extract_produces_valid_l4output():
    html = _build_item1a_html([_bold_div("Risks related to our supply chain")])
    fake = FakeLLM(_risk_json())
    result = extract_qualitative(_ingest(html), llm=fake)

    # Re-validating must not raise — the contract holds.
    L4Output(**result)
    assert result["agent"] == "L4"
    assert result["ticker"] == "TEST"
    assert result["forward_looking"] == []
    assert result["management_tone"]["label"] == "neutral"
    assert len(result["risks"]) >= 1


def test_risk_ids_unique_and_source_chunk_ids_resolve():
    html = _build_item1a_html(
        [_bold_div("Risk one heading"), _bold_div("Risk two heading")]
    )
    fake = FakeLLM(_risk_json())
    result = extract_qualitative(_ingest(html), llm=fake)

    risk_ids = [r["id"] for r in result["risks"]]
    assert len(risk_ids) == len(set(risk_ids))  # unique
    assert all(rid.startswith("R-TEST-") for rid in risk_ids)

    chunk_ids = {c["chunk_id"] for c in result["chunks"]}
    assert all(c.startswith("1A_") for c in chunk_ids)
    for r in result["risks"]:
        assert r["source_chunk_id"] in chunk_ids


def test_outputs_written_to_disk(_isolate_output):
    html = _build_item1a_html([_bold_div("Some risk heading")])
    extract_qualitative(_ingest(html, "AAPL"), llm=FakeLLM(_risk_json()))

    inter = _isolate_output / "outputs" / "intermediate"
    assert (inter / "AAPL_L4.json").exists()
    sidecar = json.loads((inter / "AAPL_chunks.json").read_text())
    # Sidecar keys are the contract ids and carry the literal text + native id.
    assert all(k.startswith("1A_") for k in sidecar)
    assert all("native_chunk_id" in v and "text" in v for v in sidecar.values())


# ---------------------------------------------------------------------------
# Robustness
# ---------------------------------------------------------------------------


def test_malformed_json_chunk_skipped_with_warning():
    html = _build_item1a_html([_bold_div("Heading")])
    result = extract_qualitative(_ingest(html), llm=FakeLLM("totally not json"))

    L4Output(**result)  # still valid
    assert result["risks"] == []
    assert any("unparseable" in w.lower() for w in result["meta"]["warnings"])


def test_zero_risks_records_warning():
    html = _build_item1a_html([_bold_div("Heading")])
    result = extract_qualitative(
        _ingest(html), llm=FakeLLM(json.dumps({"risks": []}))
    )
    assert result["risks"] == []
    assert any("zero risks" in w.lower() for w in result["meta"]["warnings"])


def test_non_verbatim_quote_kept_but_flagged():
    html = _build_item1a_html([_bold_div("Heading")])
    fake = FakeLLM(_risk_json(quote="THIS QUOTE IS NOT IN THE CHUNK AT ALL"))
    result = extract_qualitative(_ingest(html), llm=fake)
    assert len(result["risks"]) >= 1
    assert any("not verbatim" in w.lower() for w in result["meta"]["warnings"])


def test_overlong_fields_truncated_to_contract_bounds():
    html = _build_item1a_html([_bold_div("Heading")])
    fake = FakeLLM(
        _risk_json(title="T" * 250, quote="body content here. " + "Q" * 500)
    )
    result = extract_qualitative(_ingest(html), llm=fake)
    L4Output(**result)  # would raise if title>100 or quote>300
    r = result["risks"][0]
    assert len(r["title"]) <= 100
    assert len(r["literal_quote"]) <= 300


def test_missing_accession_raises():
    html = _build_item1a_html([_bold_div("Heading")])
    bad = _ingest(html)
    bad["accession_number"] = None
    with pytest.raises(ValueError):
        extract_qualitative(bad, llm=FakeLLM(_risk_json()))


def test_no_item1a_emits_empty_valid_output():
    html = "<html><body><div>Item 7. MD&A only, no risk factors.</div></body></html>"
    result = extract_qualitative(_ingest(html), llm=FakeLLM(_risk_json()))
    L4Output(**result)
    assert result["risks"] == []
    assert result["chunks"] == []
    assert any("item 1a not found" in w.lower() for w in result["meta"]["warnings"])
