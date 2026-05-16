# T2.2 — Blockers

## Blocker 1 — JPM Summary detection window too narrow  *(RESOLVED)*

**Resolved in:** `ed77a8c` (spec amendment) + `b25c225` / `bc6f520`
(chunker implementation). The "~500 char" bullet window was replaced
by "until the next level-2 anchor (or `item1a_start + 10000` as a
defensive bound)". Smoke + integration tests on JPM now yield
`summary_present=True` and 13 summary chunks (≥ 8). Original blocker
content retained below for audit trail.

---


**Detected at:** Step 3 (chunker.py), smoke test on JPM_0001628280-26-008131.html.
**Symptom:** `chunk_item1a` on JPM returns `summary_present=False` and `len(summary_chunks)=0`, violating the closing criterion "JPM `len(summary_chunks) >= 8`" and triggering the marked hard stop "JPM `summary_chunks` vacío".
**Last known good commit:** `b43f410` (models commit; chunker not yet committed).
**Suspected cause:** spec/data mismatch.

The spec (`docs/architecture/T2_2_chunker_spec.md` § "Aislamiento del Risk Factor Summary" / "Detección") prescribes:

> 1. Localizar el primer sub-header con texto de ≤ 2 palabras.
> 2. En los ~500 chars siguientes a ese sub-header, contar caracteres `•`.
> 3. Si hay ≥ 3 bullets, marcar `summary_start = offset del sub-header`.

Empirically, JPM's "Summary" header sits at plain-text offset 279 864. The first 12 Summary bullets are at deltas (from the header):

| # | delta | label |
|---|---:|---|
| 1 | 44 | "Legal and Regulatory" |
| 2 | 1 121 | "Political" |
| 3 | 1 278 | "Market" |
| 4 | 1 614 | "Credit" |
| 5 | 2 010 | "Liquidity" |
| 6 | 2 341 | "Capital" |
| 7 | 2 566 | "Operational" |
| 8 | 3 563 | "Strategic" |
| 9 | 3 910 | "Conduct" |
| 10 | 4 021 | "Reputation" |
| 11 | 4 343 | "Country" |
| 12 | 4 687 | "People" |

Within `[summary_pos, summary_pos + 500]` only **1** bullet lives, so the spec's `≥ 3` threshold never fires; the detector returns `summary_start=None`. The JPM bullets are each ~300–1 000 chars long because they enumerate sub-risks inline — the 500-char window assumed by the spec underestimates their density by an order of magnitude.

**Needs human decision on:** which of the following is the intended fix.

1. **Widen the window** to ~5 000 chars (same as `_SUMMARY_SEARCH_RANGE_CHARS`). Lossless: AAPL/WMT still fail summary detection because they have **zero** `•` bullets in Item 1A at all.
2. **Bound the window** at "either ~500 chars OR up to the next bold-leading anchor of level ≥ 2, whichever comes later". More principled — it tracks the structural end of the Summary region.
3. **Lower the bullet threshold** below 3. Risky: a single stray `•` elsewhere in Item 1A could mis-trigger summary detection.
4. **Different definition of the Summary window** the spec author had in mind.

Recommendation (for the human, not applied): option 2. It is robust to bullet density and aligns with the spec's existing `summary_end` rule (first level-2 anchor after the last `•`).

Stopping here per the marked hard stop. Chunker code as of this blocker is NOT committed (only models commit `b43f410` is on `main`); resuming requires a single-character edit (window constant) once the human decides.

*(End of resolved Blocker 1 — see header for resolution commits.)*

## Blocker — gold de anchors pendiente de anotación manual
**Detected at:** 2026-05-16T05:33:18+00:00 (scripts/eval_chunker.py run).
**Symptom:** `data/gold_chunker_anchors.json` does not exist.
**Needs human decision on:** the gold of anchors is pending manual annotation (1–2 h per spec). Format is documented in the docstring of `scripts/eval_chunker.py`.
