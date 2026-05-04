"""Pydantic v2 contract for the L4 (Qualitative Extractor) output.

This module is the single source of truth for the JSON schema produced by
``agents/agent4_qualitative.py``. The contract itself is documented in
``docs/architecture/L4_schema.md``; the models in this file enforce it
programmatically so that L4 (and any test/fixture) cannot emit invalid
output without raising a :class:`pydantic.ValidationError`.

Schema version: ``1.0``. Any **breaking** change here requires:

1. Bumping :attr:`L4Output.schema_version` (1.0 → 2.0).
2. A migration script in ``scripts/migrate_l4_schema.py``.
3. Re-running L4 over the entire gold standard.

Additive changes (new optional fields) keep the version at ``1.0.x``. See
``docs/architecture/L4_schema.md`` § Versionado for the full policy.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

# ---------------------------------------------------------------------------
# Regex constants
# ---------------------------------------------------------------------------

#: Regex for a chunk_id ("1A_001", "7_003", "7A_012"). Used in multiple
#: models so we centralise it here.
_CHUNK_ID_PATTERN: str = r"^(1A|7|7A)_\d{3}$"

#: ISO 8601 UTC with optional fractional seconds and mandatory ``Z`` suffix.
_EXTRACTED_AT_RE: re.Pattern[str] = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$"
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TimeHorizon(StrEnum):
    """Temporal horizon for a forward-looking statement."""

    CURRENT_QUARTER = "current_quarter"
    NEXT_FY = "next_fy"
    MEDIUM_3_5Y = "medium_3_5y"
    LONG_TERM = "long_term"
    UNSPECIFIED = "unspecified"


class HedgeStrength(StrEnum):
    """Strength of hedging language in a forward-looking statement."""

    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ToneLabel(StrEnum):
    """Categorical label for management tone (mapped 1:1 to ``score``)."""

    NEGATIVE = "negative"
    CAUTIOUS = "cautious"
    NEUTRAL = "neutral"
    CAUTIOUSLY_OPTIMISTIC = "cautiously_optimistic"
    OPTIMISTIC = "optimistic"


#: Mandatory mapping between :class:`ToneLabel` and the integer ``score`` in
#: :class:`ManagementTone`. Documented in
#: ``docs/architecture/L4_schema.md`` § ``management_tone`` schema.
#:
#: Internal: not exported via ``__all__``. Consumers should validate by
#: instantiating :class:`ManagementTone`, not by importing this dict.
_TONE_SCORE_BY_LABEL: dict[ToneLabel, int] = {
    ToneLabel.NEGATIVE: 1,
    ToneLabel.CAUTIOUS: 2,
    ToneLabel.NEUTRAL: 3,
    ToneLabel.CAUTIOUSLY_OPTIMISTIC: 4,
    ToneLabel.OPTIMISTIC: 5,
}


# ---------------------------------------------------------------------------
# Leaf models
# ---------------------------------------------------------------------------


class Chunk(BaseModel):
    """A processed chunk of an Item 1A / 7 / 7A section.

    The literal text is **not** carried here; it lives alongside in
    ``outputs/intermediate/{TICKER}_chunks.json`` and is loaded on demand by
    L8 (Explainer). Only the offsets and item membership are persisted in
    the L4 contract.
    """

    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(pattern=_CHUNK_ID_PATTERN)
    item: Literal["1A", "7", "7A"]
    offset_start: int = Field(ge=0)
    offset_end: int = Field(ge=0)
    subheader: str | None = None

    @model_validator(mode="after")
    def _check_offsets(self) -> "Chunk":
        if self.offset_end < self.offset_start:
            raise ValueError(
                f"offset_end ({self.offset_end}) must be >= "
                f"offset_start ({self.offset_start}) in chunk {self.chunk_id}"
            )
        return self


class RiskItem(BaseModel):
    """A single risk extracted from Item 1A by L4.

    Note: ``category`` is **not** part of L4 — it is added by L5 (Analyst).
    ``severity`` is out of scope for Sprint 2.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^R-[A-Z]+-\d{3}$")
    title: str = Field(min_length=1, max_length=100)
    summary: str = Field(min_length=1)
    literal_quote: str = Field(min_length=1, max_length=300)
    source_chunk_id: str = Field(pattern=_CHUNK_ID_PATTERN)


class ForwardLookingStatement(BaseModel):
    """A forward-looking statement extracted from Item 7 (MD&A) by L4."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^FL-[A-Z]+-\d{3}$")
    text: str = Field(min_length=1)
    time_horizon: TimeHorizon
    hedge_strength: HedgeStrength
    source_chunk_id: str = Field(pattern=_CHUNK_ID_PATTERN)


class EvidenceQuote(BaseModel):
    """A short quote backing the management-tone score, with traceability."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    source_chunk_id: str = Field(pattern=_CHUNK_ID_PATTERN)


class ManagementTone(BaseModel):
    """Aggregate qualitative signal of management tone over Item 7.

    The pair (``score``, ``label``) must be consistent with the canonical
    mapping in :data:`_TONE_SCORE_BY_LABEL`. The ``model_validator`` below
    enforces this; callers must not bypass it.
    """

    model_config = ConfigDict(extra="forbid")

    score: int = Field(ge=1, le=5)
    label: ToneLabel
    rationale: str = Field(min_length=1)
    evidence_quotes: list[EvidenceQuote] = Field(
        default_factory=list, max_length=5
    )

    @model_validator(mode="after")
    def _check_score_label_consistency(self) -> "ManagementTone":
        expected = _TONE_SCORE_BY_LABEL[self.label]
        if self.score != expected:
            raise ValueError(
                f"score {self.score} inconsistent with label "
                f"{self.label.value!r}; expected {expected}"
            )
        return self


class ModelMetadata(BaseModel):
    """Metadata about the LLM invocation that produced the L4 output."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    temperature: float = Field(ge=0.0, le=2.0)
    seed: int


class Meta(BaseModel):
    """Run-level statistics and warnings for one L4 invocation."""

    model_config = ConfigDict(extra="forbid")

    chunks_processed: int = Field(ge=0)
    chunks_with_risks: int = Field(ge=0)
    total_input_tokens_estimated: int = Field(ge=0)
    warnings: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_chunks_with_risks_le_processed(self) -> "Meta":
        if self.chunks_with_risks > self.chunks_processed:
            raise ValueError(
                f"chunks_with_risks ({self.chunks_with_risks}) cannot exceed "
                f"chunks_processed ({self.chunks_processed})"
            )
        return self


# ---------------------------------------------------------------------------
# Root model
# ---------------------------------------------------------------------------


class L4Output(BaseModel):
    """Root contract for the JSON written by L4.

    Strictness:
        - ``extra="forbid"`` so unknown top-level fields raise instead of
          being silently ignored.
        - All cross-field invariants documented in
          ``docs/architecture/L4_schema.md`` § Invariantes are enforced
          here (unique ids, source_chunk_id existence, etc.).
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"]
    agent: Literal["L4"]
    ticker: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,9}$")
    filing_accession: str = Field(pattern=r"^\d{10}-\d{2}-\d{6}$")
    filing_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    extracted_at: str
    model: ModelMetadata
    chunks: list[Chunk]
    risks: list[RiskItem]
    forward_looking: list[ForwardLookingStatement]
    management_tone: ManagementTone
    meta: Meta

    @field_validator("extracted_at")
    @classmethod
    def _check_extracted_at_iso_utc(cls, value: str) -> str:
        if not _EXTRACTED_AT_RE.match(value):
            raise ValueError(
                f"extracted_at must be ISO 8601 UTC ending in 'Z' "
                f"(e.g. '2026-05-04T15:23:00Z'); got {value!r}"
            )
        return value

    @model_validator(mode="after")
    def _check_unique_ids_and_source_refs(self) -> "L4Output":
        # 1) Unique chunk_ids
        chunk_ids: list[str] = [c.chunk_id for c in self.chunks]
        chunk_id_set: set[str] = set(chunk_ids)
        if len(chunk_id_set) != len(chunk_ids):
            dupes = sorted({cid for cid in chunk_ids if chunk_ids.count(cid) > 1})
            raise ValueError(
                f"duplicate chunk_id(s) in chunks[]: {dupes}"
            )

        # 2) Unique risk ids
        risk_ids: list[str] = [r.id for r in self.risks]
        if len(set(risk_ids)) != len(risk_ids):
            dupes = sorted({rid for rid in risk_ids if risk_ids.count(rid) > 1})
            raise ValueError(
                f"duplicate id(s) in risks[]: {dupes}"
            )

        # 3) Unique forward_looking ids
        fl_ids: list[str] = [fl.id for fl in self.forward_looking]
        if len(set(fl_ids)) != len(fl_ids):
            dupes = sorted({fid for fid in fl_ids if fl_ids.count(fid) > 1})
            raise ValueError(
                f"duplicate id(s) in forward_looking[]: {dupes}"
            )

        # 4) source_chunk_id existence across the three referencing lists.
        for risk in self.risks:
            if risk.source_chunk_id not in chunk_id_set:
                raise ValueError(
                    f"risks[id={risk.id}].source_chunk_id "
                    f"{risk.source_chunk_id!r} does not exist in chunks[]"
                )
        for fl in self.forward_looking:
            if fl.source_chunk_id not in chunk_id_set:
                raise ValueError(
                    f"forward_looking[id={fl.id}].source_chunk_id "
                    f"{fl.source_chunk_id!r} does not exist in chunks[]"
                )
        for idx, eq in enumerate(self.management_tone.evidence_quotes):
            if eq.source_chunk_id not in chunk_id_set:
                raise ValueError(
                    f"management_tone.evidence_quotes[{idx}].source_chunk_id "
                    f"{eq.source_chunk_id!r} does not exist in chunks[]"
                )

        return self


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def default_management_tone_when_item7_missing() -> ManagementTone:
    """Return the canonical default :class:`ManagementTone` for missing Item 7.

    When L4 cannot find or load Item 7 (MD&A) from the filing, it must
    still emit a well-formed ``management_tone`` block. The defaults here
    match ``docs/architecture/L4_schema.md`` § ``management_tone`` schema
    (lines 180-187 of the spec):

    - ``score = 3``
    - ``label = ToneLabel.NEUTRAL``
    - ``rationale = "Item 7 not available in filing."``
    - ``evidence_quotes = []``

    Note:
        The caller (the L4 agent) is also responsible for appending
        ``"Item 7 not found or empty"`` to ``meta.warnings``. This helper
        only constructs the tone block; it does **not** mutate any
        :class:`Meta` instance.

    Returns:
        A :class:`ManagementTone` with the documented defaults.
    """
    return ManagementTone(
        score=3,
        label=ToneLabel.NEUTRAL,
        rationale="Item 7 not available in filing.",
        evidence_quotes=[],
    )


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


__all__ = [
    # Enums
    "TimeHorizon",
    "HedgeStrength",
    "ToneLabel",
    # Models
    "Chunk",
    "RiskItem",
    "ForwardLookingStatement",
    "EvidenceQuote",
    "ManagementTone",
    "ModelMetadata",
    "Meta",
    "L4Output",
    # Helpers
    "default_management_tone_when_item7_missing",
    # Re-export pydantic ValidationError for downstream convenience
    "ValidationError",
]
