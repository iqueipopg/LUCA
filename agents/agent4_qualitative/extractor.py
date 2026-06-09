"""L4 Qualitative Extractor — risk extraction from Item 1A (T2.3, L4-mínimo).

This module turns the structural chunks produced by the T2.2 chunker
(:func:`chunker.chunk_item1a`) into the ``risks`` array of the L4 contract
(:class:`agents._schemas.L4Output`). It calls Qwen once per chunk, parses the
JSON, and assigns deterministic ids in code (never trusting the LLM with id
formatting or uniqueness).

Scope (L4-mínimo): **risk extraction only**. ``forward_looking`` is emitted as
an empty list and ``management_tone`` as the documented default
(:func:`agents._schemas.default_management_tone_when_item7_missing`); both are
future work and are flagged in ``meta.warnings``.

chunk_id remap:
    The chunker emits rich ids (``AAPL_2025_item1a_007``) but the frozen L4
    contract requires ``^(1A|7|7A)_\\d{3}$``. We remap to ``1A_NNN`` in chunker
    order (summary chunks first, then body) and carry an ``id_map`` so every
    ``RiskItem.source_chunk_id`` references a chunk present in ``chunks[]``. The
    contract in ``agents/_schemas.py`` is **not** modified.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents._config import PROJECT_ROOT, get_agent_config
from agents._llm_client import LLMClient, parse_json_response
from agents._logging import get_logger
from agents._schemas import (
    Chunk,
    L4Output,
    Meta,
    ModelMetadata,
    RiskItem,
    default_management_tone_when_item7_missing,
)
from agents.agent4_qualitative.chunker import chunk_item1a, find_item1a_range
from agents.agent4_qualitative.models import Chunk as ChunkerChunk

_LOGGER = get_logger(__name__)

#: Recorded seed for the L4 contract. NOTE: ``LLMClient.chat`` does not forward
#: a seed to Ollama, so runs are not actually seed-deterministic. This is a
#: documentary constant only (see ``docs/eval/results_real.md`` reproducibility).
_RECORDED_SEED: int = 42

#: Schema-contract field bounds, mirrored here for defensive truncation so a
#: too-long LLM field never aborts the whole document at validation time.
_TITLE_MAX: int = 100
_QUOTE_MAX: int = 300

_RISK_SYSTEM_PROMPT: str = (
    "You are a financial-risk extraction assistant. You receive ONE chunk of "
    "the Risk Factors section (Item 1A) of a US SEC 10-K filing. Extract the "
    "distinct risks described ONLY in this chunk. Do not invent risks not "
    "present in the text. If the chunk is a header, intro, or boilerplate with "
    "no concrete risk, return an empty list.\n\n"
    "Output STRICT JSON only — no prose, no markdown fences — with this shape:\n"
    '{"risks": [{"title": "<English noun phrase, <=100 chars>", '
    '"summary": "<2-3 sentence paraphrase in SPANISH>", '
    '"literal_quote": "<verbatim quote copied EXACTLY from the chunk, <=300 chars>"}]}\n\n'
    "Rules:\n"
    "- 'summary' MUST be in Spanish (the project output language).\n"
    "- 'literal_quote' MUST be a substring copied verbatim from the provided "
    "chunk, for downstream traceability.\n"
    "- Do NOT output ids; they are assigned by the calling system.\n"
    "- One JSON object per risk; if there are no risks, return {\"risks\": []}."
)


def _build_user_prompt(chunk: ChunkerChunk) -> str:
    """Compose the per-chunk user prompt (optional subheader + chunk text)."""
    header = f"Sub-section: {chunk.anchor_text}\n\n" if chunk.anchor_text else ""
    return f"{header}Chunk text:\n{chunk.text}"


def _coerce_risk_fields(
    raw: dict[str, Any], *, chunk_text: str, warnings: list[str], l4_chunk_id: str
) -> dict[str, str] | None:
    """Validate/normalise one raw risk dict from the LLM.

    Returns a dict with ``title``/``summary``/``literal_quote`` ready for
    :class:`RiskItem`, or ``None`` if the risk is unusable (and a warning is
    appended). Truncates over-long fields to the contract bounds.
    """
    title = str(raw.get("title", "")).strip()[:_TITLE_MAX]
    summary = str(raw.get("summary", "")).strip()
    quote = str(raw.get("literal_quote", "")).strip()[:_QUOTE_MAX]

    if not title or not summary or not quote:
        warnings.append(
            f"Chunk {l4_chunk_id}: risk dropped (missing title/summary/quote)"
        )
        return None

    if quote not in chunk_text:
        # Best-effort: Qwen sometimes paraphrases or adds ellipsis. Keep the
        # risk but flag it for human review rather than rejecting it.
        warnings.append(
            f"Chunk {l4_chunk_id}: literal_quote not verbatim (best-effort)"
        )

    return {"title": title, "summary": summary, "literal_quote": quote}


def extract_qualitative(
    ingest_output: dict[str, Any], *, llm: LLMClient | None = None
) -> dict[str, Any]:
    """Run L4-mínimo risk extraction on an L1 ingest payload.

    Args:
        ingest_output: Output of :func:`agents.agent1_ingestion.ingest`. Must
            carry ``html_content``, ``ticker``, ``filing_date`` and
            ``accession_number``.
        llm: Injectable client (tests pass one whose ``ollama.Client.chat`` is
            mocked). Defaults to a fresh :class:`LLMClient`.

    Returns:
        A validated ``L4Output`` as a plain dict (``model_dump``). The same
        payload is written to ``outputs/intermediate/{TICKER}_L4.json`` and a
        text sidecar to ``{TICKER}_chunks.json``.

    Raises:
        pydantic.ValidationError: if the assembled output breaks the contract.
        ValueError: if ``accession_number`` is missing (cannot satisfy the
            contract pattern).
    """
    cfg = get_agent_config("L4_qualitative")
    temperature = float(cfg.get("temperature", 0.2))
    max_output_tokens = int(cfg.get("max_output_tokens", 1500))
    max_input_chars = int(cfg.get("max_input_chars", 24000))

    client = llm if llm is not None else LLMClient()

    ticker = ingest_output["ticker"]
    html = ingest_output.get("html_content") or ""
    filing_date = ingest_output.get("filing_date")
    accession = ingest_output.get("accession_number")

    if not accession:
        raise ValueError(
            f"L4 requires a valid accession_number for {ticker}; got {accession!r}"
        )

    fiscal_year = int(filing_date[:4]) if filing_date else 1900

    warnings: list[str] = [
        "Item 7 not processed (forward_looking and management_tone out of "
        "scope for L4-mínimo)"
    ]

    _LOGGER.info("L4 extracción cualitativa para %s", ticker)

    # ----------------------------------------------------------------- chunks
    all_chunks: list[ChunkerChunk] = []
    try:
        item1a_start, item1a_end = find_item1a_range(html)
        chunk_set = chunk_item1a(
            html, item1a_start, item1a_end, ticker, fiscal_year
        )
        all_chunks = list(chunk_set.summary_chunks) + list(chunk_set.body_chunks)
        warnings.extend(chunk_set.warnings)
    except RuntimeError as exc:
        item1a_start = 0
        warnings.append(f"Item 1A not found or unparseable: {exc}")
        _LOGGER.warning("L4 %s: no se pudo localizar Item 1A (%s)", ticker, exc)

    # Build the L4 chunks[] array + the chunker->contract id map.
    l4_chunks: list[Chunk] = []
    id_map: dict[str, str] = {}
    chunk_sidecar: dict[str, dict[str, Any]] = {}
    for i, ch in enumerate(all_chunks, start=1):
        l4_id = f"1A_{i:03d}"
        id_map[ch.chunk_id] = l4_id
        offset_start = max(0, ch.char_start - item1a_start)
        offset_end = max(offset_start, ch.char_end - item1a_start)
        l4_chunks.append(
            Chunk(
                chunk_id=l4_id,
                item="1A",
                offset_start=offset_start,
                offset_end=offset_end,
                subheader=ch.anchor_text,
            )
        )
        chunk_sidecar[l4_id] = {
            "text": ch.text,
            "char_start": ch.char_start,
            "char_end": ch.char_end,
            "native_chunk_id": ch.chunk_id,
        }

    # ------------------------------------------------------ per-chunk LLM pass
    risks: list[RiskItem] = []
    chunks_processed = 0
    chunks_with_risks = 0
    risk_counter = 0

    for ch in all_chunks:
        l4_id = id_map[ch.chunk_id]
        chunk_text = ch.text[:max_input_chars]
        chunks_processed += 1
        try:
            raw = client.chat(
                system=_RISK_SYSTEM_PROMPT,
                user=_build_user_prompt(ch),
                temperature=temperature,
                num_ctx=8192,
                max_tokens=max_output_tokens,
            )
            parsed = parse_json_response(raw)
        except ValueError as exc:
            warnings.append(f"Chunk {l4_id}: unparseable LLM JSON, skipped ({exc})")
            _LOGGER.warning("L4 %s chunk %s: JSON inválido (%s)", ticker, l4_id, exc)
            continue
        except Exception as exc:  # noqa: BLE001 — one bad chunk must not abort the run
            warnings.append(f"Chunk {l4_id}: LLM error, skipped ({exc})")
            _LOGGER.warning("L4 %s chunk %s: error LLM (%s)", ticker, l4_id, exc)
            continue

        raw_risks = parsed.get("risks") if isinstance(parsed, dict) else None
        if not isinstance(raw_risks, list):
            warnings.append(f"Chunk {l4_id}: no 'risks' list in response")
            continue

        chunk_had_risk = False
        for raw_risk in raw_risks:
            if not isinstance(raw_risk, dict):
                continue
            fields = _coerce_risk_fields(
                raw_risk, chunk_text=chunk_text, warnings=warnings, l4_chunk_id=l4_id
            )
            if fields is None:
                continue
            risk_counter += 1
            risks.append(
                RiskItem(
                    id=f"R-{ticker}-{risk_counter:03d}",
                    title=fields["title"],
                    summary=fields["summary"],
                    literal_quote=fields["literal_quote"],
                    source_chunk_id=l4_id,
                )
            )
            chunk_had_risk = True
        if chunk_had_risk:
            chunks_with_risks += 1

    # ----------------------------------------------------------- soft limits
    if all_chunks and not risks:
        warnings.append("Item 1A processed but zero risks extracted")
    if len(risks) > 30:
        warnings.append(f"{len(risks)} risks extracted (>30 soft threshold)")

    extracted_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    payload = L4Output(
        schema_version="1.0",
        agent="L4",
        ticker=ticker,
        filing_accession=accession,
        filing_date=filing_date,
        extracted_at=extracted_at,
        model=ModelMetadata(
            name=client.model, temperature=temperature, seed=_RECORDED_SEED
        ),
        chunks=l4_chunks,
        risks=risks,
        forward_looking=[],
        management_tone=default_management_tone_when_item7_missing(),
        meta=Meta(
            chunks_processed=chunks_processed,
            chunks_with_risks=chunks_with_risks,
            total_input_tokens_estimated=sum(c.token_estimate for c in all_chunks),
            warnings=warnings,
        ),
    )

    out_dir = PROJECT_ROOT / "outputs" / "intermediate"
    out_dir.mkdir(parents=True, exist_ok=True)
    result = payload.model_dump()
    (out_dir / f"{ticker}_L4.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / f"{ticker}_chunks.json").write_text(
        json.dumps(chunk_sidecar, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    _LOGGER.info(
        "L4 %s: %d riesgos de %d chunks (%d con riesgos)",
        ticker, len(risks), chunks_processed, chunks_with_risks,
    )
    return result


__all__ = ["extract_qualitative"]
