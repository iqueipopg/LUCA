"""Pydantic v2 models for the T2.2 Item 1A chunker.

The chunker is a *structural* component: it slices the Item 1A range of
an iXBRL 10-K into chunks consumable by L4 (Qualitative Extractor) and
emits per-chunk metadata. The schema is fixed by
``docs/architecture/T2_2_chunker_spec.md`` § Inputs / Outputs.

Two models live here:

* :class:`Chunk` — one slice of Item 1A. ``char_start`` / ``char_end``
  are offsets into the *plain-text* representation of the 10-K (the
  output of BeautifulSoup ``get_text(separator=" ")`` + whitespace
  collapse), not into the raw HTML bytes. This is the same coordinate
  system used by ``agents/agent2_parser.py``.
* :class:`Item1AChunkSet` — the chunker's top-level output. Contains
  the (possibly empty) ``summary_chunks`` list, the ``body_chunks``
  list and any non-fatal ``warnings`` collected during chunking.

These are deliberately separate from the ``Chunk`` model in
``agents/_schemas.py``: that one is the L4 contract and uses the
``1A_NNN`` chunk_id pattern; the chunker is upstream of L4 and uses a
richer per-ticker chunk_id (``AAPL_2024_item1a_007``).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Chunk(BaseModel):
    """One chunk of Item 1A produced by :func:`chunker.chunk_item1a`.

    The literal ``text`` is carried inline because downstream L4
    consumers run prompts directly against it. ``token_estimate`` is
    ``len(text) // 4`` per scouting; the chunker enforces an upper
    bound of 4 000 tokens per chunk via length-based fallback.
    """

    model_config = ConfigDict(extra="forbid")

    chunk_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    char_start: int = Field(ge=0)
    char_end: int = Field(ge=0)
    anchor_text: str | None = None
    anchor_level: int = Field(ge=1, le=3)
    in_summary: bool
    token_estimate: int = Field(ge=0)

    @model_validator(mode="after")
    def _check_offsets(self) -> "Chunk":
        if self.char_end < self.char_start:
            raise ValueError(
                f"char_end ({self.char_end}) must be >= char_start "
                f"({self.char_start}) in chunk {self.chunk_id}"
            )
        return self


class Item1AChunkSet(BaseModel):
    """Top-level output of the Item 1A chunker.

    ``summary_chunks`` is empty unless a Risk Factor Summary is
    detected (only JPM-like filings ≥15 000 words). ``body_chunks``
    covers the rest of Item 1A end-to-end; per the chunker contract
    it never emits a chunk with ``token_estimate > 4000``.
    """

    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1)
    fiscal_year: int = Field(ge=1900)
    item1a_token_estimate: int = Field(ge=0)
    summary_present: bool
    summary_chunks: list[Chunk] = Field(default_factory=list)
    body_chunks: list[Chunk] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


__all__ = ["Chunk", "Item1AChunkSet"]
