"""Tests for the L4 output Pydantic contract (``agents/_schemas.py``).

The contract is documented in ``docs/architecture/L4_schema.md`` (schema
version 1.0). These tests load canonical valid / invalid JSON fixtures
from ``tests/fixtures/l4_output_*.json`` and verify that:

- a fully-formed L4 output round-trips through Pydantic without loss, and
- each documented invariant raises a :class:`pydantic.ValidationError`
  with a human-readable message that points at the offending field.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from agents._schemas import (
    Chunk,
    EvidenceQuote,
    HedgeStrength,
    L4Output,
    ManagementTone,
    Meta,
    TimeHorizon,
    ToneLabel,
    default_management_tone_when_item7_missing,
)

# ---------------------------------------------------------------------------
# Fixture-loading helpers
# ---------------------------------------------------------------------------

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _load_fixture(name: str) -> dict[str, Any]:
    """Return a fresh copy of fixture ``name`` so tests can mutate freely."""
    path = _FIXTURES_DIR / name
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture
def valid_l4_dict() -> dict[str, Any]:
    """Fresh dict from the valid L4 fixture (mutable per-test)."""
    return _load_fixture("l4_output_valid.json")


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------


class TestRoundTrip:
    """The valid fixture must validate, serialise, and re-validate cleanly."""

    def test_valid_fixture_loads_and_serializes_round_trip(
        self, valid_l4_dict: dict[str, Any]
    ) -> None:
        # Validate once.
        model = L4Output.model_validate(valid_l4_dict)

        # Serialise to JSON and back to a dict.
        as_json = model.model_dump_json()
        round_tripped = json.loads(as_json)

        # Re-validate to be sure the serialised form is itself accepted.
        L4Output.model_validate(round_tripped)

        # The round-tripped dict must equal the original input.
        assert round_tripped == valid_l4_dict


# ---------------------------------------------------------------------------
# Invalid fixtures: each documented invariant has its own canonical fixture.
# ---------------------------------------------------------------------------


class TestInvalidFixtures:
    """Each invalid fixture must raise a legible :class:`ValidationError`."""

    def test_invalid_orphan_source_chunk_raises(self) -> None:
        data = _load_fixture("l4_output_invalid_orphan_source_chunk.json")
        with pytest.raises(ValidationError) as exc_info:
            L4Output.model_validate(data)
        msg = str(exc_info.value)
        assert "source_chunk_id" in msg
        assert "1A_999" in msg
        assert "does not exist in chunks[]" in msg
        # The error must point at the offending list (risks), not at chunks.
        assert "risks[id=R-AAPL-001]" in msg

    def test_invalid_duplicate_risk_id_raises(self) -> None:
        data = _load_fixture("l4_output_invalid_duplicate_risk_id.json")
        with pytest.raises(ValidationError) as exc_info:
            L4Output.model_validate(data)
        msg = str(exc_info.value)
        assert "duplicate" in msg
        assert "risks[]" in msg
        assert "R-AAPL-001" in msg

    def test_invalid_score_label_mismatch_raises(self) -> None:
        data = _load_fixture("l4_output_invalid_score_label_mismatch.json")
        with pytest.raises(ValidationError) as exc_info:
            L4Output.model_validate(data)
        msg = str(exc_info.value)
        # Must point at management_tone and explain the mismatch.
        assert "management_tone" in msg
        assert "score 4" in msg
        assert "neutral" in msg
        assert "expected 3" in msg

    def test_invalid_extracted_at_no_z_raises(self) -> None:
        data = _load_fixture("l4_output_invalid_extracted_at_no_z.json")
        with pytest.raises(ValidationError) as exc_info:
            L4Output.model_validate(data)
        msg = str(exc_info.value)
        assert "extracted_at" in msg
        assert "ISO 8601" in msg
        assert "'Z'" in msg or '"Z"' in msg

    def test_invalid_literal_quote_too_long_raises(self) -> None:
        data = _load_fixture("l4_output_invalid_literal_quote_too_long.json")
        with pytest.raises(ValidationError) as exc_info:
            L4Output.model_validate(data)
        msg = str(exc_info.value)
        # Pydantic's built-in ``string_too_long`` error includes the path.
        assert "risks.0.literal_quote" in msg
        assert "300 characters" in msg


# ---------------------------------------------------------------------------
# Defaults helper
# ---------------------------------------------------------------------------


class TestDefaults:
    """The Item-7-missing default must match the schema spec verbatim."""

    def test_default_management_tone_when_item7_missing(self) -> None:
        tone = default_management_tone_when_item7_missing()
        assert isinstance(tone, ManagementTone)
        assert tone.score == 3
        assert tone.label is ToneLabel.NEUTRAL
        assert tone.rationale == "Item 7 not available in filing."
        assert tone.evidence_quotes == []


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Extra-strictness behaviours and exhaustive label/score parametrisation."""

    def test_extra_field_rejected(self, valid_l4_dict: dict[str, Any]) -> None:
        valid_l4_dict["surprise_field"] = "should not be here"
        with pytest.raises(ValidationError) as exc_info:
            L4Output.model_validate(valid_l4_dict)
        msg = str(exc_info.value)
        # extra="forbid" surfaces both the field name and the policy reason.
        assert "surprise_field" in msg
        assert "Extra inputs are not permitted" in msg or "extra_forbidden" in msg

    @pytest.mark.parametrize(
        "label,score",
        [
            (ToneLabel.NEGATIVE, 1),
            (ToneLabel.CAUTIOUS, 2),
            (ToneLabel.NEUTRAL, 3),
            (ToneLabel.CAUTIOUSLY_OPTIMISTIC, 4),
            (ToneLabel.OPTIMISTIC, 5),
        ],
    )
    def test_management_tone_consistent_pairs_accepted(
        self, label: ToneLabel, score: int
    ) -> None:
        tone = ManagementTone(
            score=score,
            label=label,
            rationale="ok",
            evidence_quotes=[],
        )
        assert tone.score == score
        assert tone.label is label

    @pytest.mark.parametrize(
        "label,score",
        [
            (ToneLabel.NEGATIVE, 2),
            (ToneLabel.CAUTIOUS, 1),
            (ToneLabel.NEUTRAL, 4),
            (ToneLabel.CAUTIOUSLY_OPTIMISTIC, 3),
            (ToneLabel.OPTIMISTIC, 1),
        ],
    )
    def test_management_tone_inconsistent_pairs_rejected(
        self, label: ToneLabel, score: int
    ) -> None:
        with pytest.raises(ValidationError) as exc_info:
            ManagementTone(
                score=score,
                label=label,
                rationale="bad",
                evidence_quotes=[],
            )
        msg = str(exc_info.value)
        assert "inconsistent" in msg
        assert label.value in msg

    def test_orphan_source_chunk_in_evidence_quotes_raises(
        self, valid_l4_dict: dict[str, Any]
    ) -> None:
        # Deep-copy so other tests' fixture is unaffected (defensive even
        # though _load_fixture already returns a fresh dict).
        data = copy.deepcopy(valid_l4_dict)
        # Risks and forward_looking still reference real chunks; only the
        # tone evidence_quote is orphaned. This isolates the third
        # source_chunk_id checking branch in the L4Output validator.
        data["management_tone"]["evidence_quotes"][1]["source_chunk_id"] = "7_999"

        with pytest.raises(ValidationError) as exc_info:
            L4Output.model_validate(data)
        msg = str(exc_info.value)
        assert "management_tone.evidence_quotes" in msg
        assert "7_999" in msg
        assert "does not exist in chunks[]" in msg


# ---------------------------------------------------------------------------
# Smoke: enums import-able and stringly-comparable.
# ---------------------------------------------------------------------------


class TestEnumImports:
    """Sanity check: enums are StrEnum and equal to their string values."""

    def test_time_horizon_string_values(self) -> None:
        assert TimeHorizon.NEXT_FY == "next_fy"
        assert TimeHorizon.MEDIUM_3_5Y == "medium_3_5y"

    def test_hedge_strength_string_values(self) -> None:
        assert HedgeStrength.MEDIUM == "medium"
        assert HedgeStrength.NONE == "none"

    def test_evidence_quote_minimal_construct(self) -> None:
        eq = EvidenceQuote(text="x", source_chunk_id="7_001")
        assert eq.text == "x"
        assert eq.source_chunk_id == "7_001"


# ---------------------------------------------------------------------------
# Lower-level model invariants (defensive branches not exercised above).
# ---------------------------------------------------------------------------


class TestModelInvariants:
    """Targeted tests for invariants on individual leaf / cross-field models."""

    def test_chunk_offset_end_lt_start_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            Chunk(
                chunk_id="1A_001",
                item="1A",
                offset_start=100,
                offset_end=50,
            )
        msg = str(exc_info.value)
        assert "offset_end" in msg
        assert "offset_start" in msg

    def test_meta_chunks_with_risks_exceeds_processed_raises(self) -> None:
        with pytest.raises(ValidationError) as exc_info:
            Meta(
                chunks_processed=2,
                chunks_with_risks=5,
                total_input_tokens_estimated=100,
                warnings=[],
            )
        msg = str(exc_info.value)
        assert "chunks_with_risks" in msg
        assert "chunks_processed" in msg

    def test_duplicate_chunk_id_raises(
        self, valid_l4_dict: dict[str, Any]
    ) -> None:
        # Force a duplicate chunk_id by overwriting the second chunk.
        valid_l4_dict["chunks"][1]["chunk_id"] = valid_l4_dict["chunks"][0][
            "chunk_id"
        ]
        valid_l4_dict["chunks"][1]["item"] = valid_l4_dict["chunks"][0]["item"]
        # Repoint downstream references that used the now-removed "7_001"
        # to the surviving chunk so the orphan check does not fire first.
        for fl in valid_l4_dict["forward_looking"]:
            fl["source_chunk_id"] = "1A_001"
        for eq in valid_l4_dict["management_tone"]["evidence_quotes"]:
            eq["source_chunk_id"] = "1A_001"

        with pytest.raises(ValidationError) as exc_info:
            L4Output.model_validate(valid_l4_dict)
        msg = str(exc_info.value)
        assert "duplicate chunk_id" in msg
        assert "1A_001" in msg

    def test_duplicate_forward_looking_id_raises(
        self, valid_l4_dict: dict[str, Any]
    ) -> None:
        valid_l4_dict["forward_looking"][1]["id"] = valid_l4_dict[
            "forward_looking"
        ][0]["id"]

        with pytest.raises(ValidationError) as exc_info:
            L4Output.model_validate(valid_l4_dict)
        msg = str(exc_info.value)
        assert "duplicate" in msg
        assert "forward_looking[]" in msg
        assert "FL-AAPL-001" in msg

    def test_orphan_source_chunk_in_forward_looking_raises(
        self, valid_l4_dict: dict[str, Any]
    ) -> None:
        valid_l4_dict["forward_looking"][0]["source_chunk_id"] = "7_999"

        with pytest.raises(ValidationError) as exc_info:
            L4Output.model_validate(valid_l4_dict)
        msg = str(exc_info.value)
        assert "forward_looking[id=FL-AAPL-001]" in msg
        assert "7_999" in msg
        assert "does not exist in chunks[]" in msg
