"""T1.9 — LLM-naive baselines evaluated against the gold standard.

Two complementary baselines share this script. They differ **only** in
the preprocessing of the document text fed to the LLM; the prompt, the
model, and the response parser are identical.

* ``--mode naive`` (T1.9a): the first ~25,000 characters of the **full
  10-K HTML**, lightly de-tagged via BeautifulSoup. No Item slicing, no
  table extraction. Represents the ceiling of a "naive baseline:
  someone throws an LLM at the problem without knowing what they are
  doing".

* ``--mode structured`` (T1.9b): the **first three** consolidated
  tables from Item 8 as extracted by L2's parser
  (``raw_tables[:3]``), concatenated with a clear separator. These
  three tables are typically the Income Statement, the Balance Sheet,
  and the Cash Flow Statement. Subsequent tables are notes and
  breakdowns and would inject noise.

The same gold-standard reader, the same numeric comparator, and the
same artefacts (CSV + Markdown) are produced as in
:mod:`experiments.eval_extraction` (T1.8). T1.10 can therefore
juxtapose the L3 / Naive / Structured tables side by side without any
post-processing.

Network policy
--------------
L1 ingest is invoked **only** when a ticker's HTML is not already
present in ``data/cache/``. After T1.8, the 10 gold-standard tickers
are all cached, so a typical T1.9 run hits EDGAR exactly zero times
and only talks to Ollama on ``localhost``. The LLM is queried once per
ticker (no per-metric calls), so the experiment is ~10 round-trips
per mode.

Usage
-----
::

    /home/<user>/luca-ai-lab/venv/bin/python \\
        experiments/eval_baseline_llm.py \\
        --mode naive \\
        [--gold-path PATH] \\
        [--output-dir PATH] \\
        [--limit N]

``--limit N`` runs against only the first ``N`` tickers from
:data:`agents._gold_schema.GOLD_TICKERS` and is intended for fast
iteration during development.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import time
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

# When invoked as a script, the project root is not on ``sys.path``.
_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from bs4 import BeautifulSoup  # noqa: E402

from agents._config import load_config  # noqa: E402
from agents._gold_schema import GOLD_METRICS, GOLD_TICKERS  # noqa: E402
from agents._llm_client import LLMClient  # noqa: E402
from agents._logging import get_logger  # noqa: E402
from agents.agent1_ingestion import ingest as default_ingest  # noqa: E402
from agents.agent2_parser import parse as default_parse  # noqa: E402
from experiments._eval_common import (  # noqa: E402
    GoldEntry,
    compare_values,
    load_gold_standard,
)

_LOGGER = get_logger(__name__)


# ---------------------------------------------------------------------------
# Defaults / constants
# ---------------------------------------------------------------------------

DEFAULT_GOLD_PATH: Path = _PROJECT_ROOT / "data" / "gold_standard.xlsx"
DEFAULT_OUTPUT_DIR: Path = _PROJECT_ROOT / "experiments" / "output"
DEFAULT_PROMPT_PATH: Path = (
    _PROJECT_ROOT / "config" / "prompts" / "baseline_extraction.txt"
)
DEFAULT_CACHE_DIR: Path = _PROJECT_ROOT / "data" / "cache"

#: Modes accepted by :func:`main`. Centralised here so the parser, tests,
#: and the markdown report all stay in sync.
VALID_MODES: tuple[str, ...] = ("naive", "structured")

#: Number of characters from the **beginning** of the de-tagged 10-K
#: text fed to the LLM in ``--mode naive``. Captures the cover page,
#: registrant identification (CIK, fiscal year, ticker) and the start
#: of Item 1.
NAIVE_HEAD_CHARS: int = 5_000

#: Number of characters from the **end** of the de-tagged 10-K text
#: fed to the LLM in ``--mode naive``. Item 8 (consolidated financial
#: statements) lives in the last third of a 10-K — for the AAPL 2025
#: filing it starts at character ~138,963 of 220,566 total — and is
#: therefore systematically excluded by a head-only truncation. The
#: head + tail composition gives the LLM a chance to see both the
#: registrant context and the financial statements section. See error
#: log T1.9 / Bug #3 for the diagnosis.
NAIVE_TAIL_CHARS: int = 35_000

#: Inserted between head and tail so the LLM sees an explicit cue
#: that text was elided.
NAIVE_HEAD_TAIL_SEPARATOR: str = "\n[...]\n"

#: Total naive-mode budget. The Qwen 2.5 7B context on RTX 4060 8 GB
#: with Q4_K_M tops out at ~12 K tokens before the KV cache pushes us
#: out of VRAM; 40 K characters ≈ 10 K tokens leave a comfortable
#: margin for the prompt scaffolding and the model's response.
NAIVE_MAX_CHARS: int = NAIVE_HEAD_CHARS + NAIVE_TAIL_CHARS

#: Maximum number of characters of concatenated tables the structured
#: mode forwards. Slightly larger than ``NAIVE_MAX_CHARS`` because
#: tables are dense; we still leave a margin for the prompt scaffolding.
STRUCTURED_MAX_CHARS: int = 28_000

#: Number of consolidated tables included by the structured mode.
#: Bumped from 3 to 5 in T1.9b: a real 10-K typically presents five
#: consolidated statements (Operations, Comprehensive Income, Balance
#: Sheet, Stockholders' Equity, Cash Flow). Selecting only three was
#: leaving Cash Flow out for some filers.
STRUCTURED_TABLE_COUNT: int = 5

#: Regex matching a dollar amount of six or more digit/comma
#: characters, optionally separated from the ``$`` by whitespace and
#: a single ``|`` (the cell separator emitted by L2's
#: ``_extract_tables``). Used to identify candidate consolidated
#: financial statement tables.
_DOLLAR_AMOUNT_RE: re.Pattern[str] = re.compile(r"\$[\s|]*[\d,]{6,}")

#: Minimum number of dollar amounts a table must contain to be
#: considered a candidate consolidated financial statement.
_MIN_DOLLAR_AMOUNTS_PER_FIN_TABLE: int = 3

#: Lowercase substrings that consolidated statements contain but
#: MD&A breakdowns (segment revenue, gross-margin %, opex by line,
#: effective tax rate) do not. Used as a keyword filter on top of
#: the dollar-amount count: the AAPL 2025 filing shows that the
#: first three tables that pass the dollar-amount-only filter are
#: MD&A breakdowns (Americas/Europe segments, iPhone/Mac products,
#: R&D/SG&A) — they have $-amounts of the right shape but lack any
#: of the canonical line items below.
_FINANCIAL_STATEMENT_KEYWORDS: tuple[str, ...] = (
    "net income",
    "total assets",
    "total liabilities",
    "total shareholders",
    "total stockholders",
    "operating activities",
    "comprehensive income",
    "earnings per share",
    "cash and cash equivalents",
)

#: Per-call timeout for the LLM. Bigger HTMLs and longer tables take a
#: while on a 4060.
LLM_TIMEOUT_S: float = 90.0

#: Sampling temperature. Low because we want deterministic extraction,
#: not creative writing.
LLM_TEMPERATURE: float = 0.1

#: Output truncation length for the ``raw_llm_response`` CSV column.
#: Long enough to be diagnostic, short enough to keep the CSV browsable.
RAW_RESPONSE_CSV_TRUNCATE: int = 200

#: Whitespace runs that should collapse to a single space.
_WS_RE: re.Pattern[str] = re.compile(r"\s+")

#: System message used by the LLM. The user prompt comes from the
#: versioned template at :data:`DEFAULT_PROMPT_PATH`.
_LLM_SYSTEM_PROMPT: str = (
    "You are a careful financial analyst. Your only job is to extract "
    "numeric metrics from a 10-K excerpt and return them as a strict "
    "JSON object. Never invent numbers; emit JSON null when unsure."
)

CSV_FIELDNAMES: tuple[str, ...] = (
    "ticker",
    "metric",
    "gold_value",
    "gold_fiscal_year",
    "predicted_value",
    "match",
    "abs_error",
    "rel_error",
    "raw_llm_response",
    "notes_gold",
)


# ---------------------------------------------------------------------------
# Helpers — prompt loading
# ---------------------------------------------------------------------------


def load_prompt_template(path: Path) -> str:
    """Read the baseline-extraction prompt template from disk.

    The file may contain trailing comment lines starting with ``#``;
    those are stripped so they never reach the model. Exactly one
    ``{content}`` placeholder must be present, otherwise we raise: the
    experiment is meaningless without it.

    Args:
        path: Path to the versioned prompt template (typically
            :data:`DEFAULT_PROMPT_PATH`).

    Returns:
        The cleaned prompt template, ready for ``.format(content=...)``.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
        ValueError: If the template does not contain exactly one
            ``{content}`` placeholder.
    """
    if not path.is_file():
        raise FileNotFoundError(
            f"No se encuentra el template de prompt en {path}."
        )
    raw = path.read_text(encoding="utf-8")

    # Drop trailing comment-only lines (used for the version stamp).
    cleaned_lines: list[str] = []
    for line in raw.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        cleaned_lines.append(line)
    template = "\n".join(cleaned_lines).strip() + "\n"

    placeholder_count = template.count("{content}")
    if placeholder_count != 1:
        raise ValueError(
            f"El template en {path} debe contener exactamente un "
            f"placeholder {{content}}; encontrados: {placeholder_count}."
        )
    return template


# ---------------------------------------------------------------------------
# Helpers — content preparation
# ---------------------------------------------------------------------------


def html_to_plain_text(html: str) -> str:
    """De-tag ``html`` and collapse whitespace runs.

    Mirrors the cleanup done by :func:`agents.agent2_parser._html_to_text`
    so both modes start from the same kind of plain text.

    Args:
        html: Raw HTML string.

    Returns:
        Plain text with single-space whitespace runs.
    """
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(separator=" ")
    return _WS_RE.sub(" ", text).strip()


def _truncate(text: str, limit: int, *, ticker: str, mode: str) -> str:
    """Return ``text[:limit]`` and log a warning if truncation occurred."""
    if len(text) <= limit:
        return text
    _LOGGER.warning(
        "Modo %s: contenido para %s excede %d chars (%d). Truncado.",
        mode, ticker, limit, len(text),
    )
    return text[:limit]


def prepare_naive_content(html: str, *, ticker: str) -> str:
    """Build the LLM input for ``--mode naive``.

    De-tag ``html`` and, when the plain text exceeds
    :data:`NAIVE_MAX_CHARS`, return ``text[:NAIVE_HEAD_CHARS] +
    NAIVE_HEAD_TAIL_SEPARATOR + text[-NAIVE_TAIL_CHARS:]``. The
    head-plus-tail composition is required because Item 8 (the
    consolidated financial statements) lives in the last third of a
    10-K; a head-only truncation excluded it systematically and
    yielded a 0% baseline that was indistinguishable from "the LLM
    can't extract anything" — see error log T1.9 / Bug #3.

    Documents shorter than the budget are returned untouched.

    Args:
        html: Raw HTML of the 10-K.
        ticker: For logging context only.

    Returns:
        Plain-text content ready to be inserted into the prompt
        template's ``{content}`` placeholder.
    """
    plain = html_to_plain_text(html)
    if len(plain) <= NAIVE_MAX_CHARS:
        return plain
    head = plain[:NAIVE_HEAD_CHARS]
    tail = plain[-NAIVE_TAIL_CHARS:]
    _LOGGER.warning(
        "Modo naive: %s con %d chars supera el budget %d. "
        "Recortado a head %d + tail %d.",
        ticker, len(plain), NAIVE_MAX_CHARS, NAIVE_HEAD_CHARS, NAIVE_TAIL_CHARS,
    )
    return head + NAIVE_HEAD_TAIL_SEPARATOR + tail


def _is_financial_table(text: object) -> bool:
    """Return ``True`` iff ``text`` looks like a consolidated statement.

    Two conditions must hold:

    1. At least :data:`_MIN_DOLLAR_AMOUNTS_PER_FIN_TABLE` dollar
       amounts of six or more digits/commas. The literal pattern
       requested in T1.9 was ``\\$\\s*[\\d,]{6,}``; we relax the gap
       to ``[\\s|]*`` because L2's ``_extract_tables`` flattens cells
       with ``" | "`` separators, so a $-amount appears as
       ``"$ | 332,952"`` rather than ``"$332,952"``.

    2. The cell text contains at least one
       :data:`_FINANCIAL_STATEMENT_KEYWORDS` term (e.g.,
       ``"net income"``, ``"total assets"``,
       ``"operating activities"``). The keyword check is required
       because the dollar-amount count alone selects MD&A breakdown
       tables (Americas/Europe segment revenue, R&D / SG&A by line,
       income tax provision) before the consolidated statements;
       these tables have many $-amounts but lack the canonical line
       items below — see error log T1.9 / Bug #2.

    Cover-page tables (registrant address, trading symbols, filer
    status) fall to condition 1; MD&A breakdowns fall to condition 2.
    """
    if not isinstance(text, str):
        return False
    if len(_DOLLAR_AMOUNT_RE.findall(text)) < _MIN_DOLLAR_AMOUNTS_PER_FIN_TABLE:
        return False
    text_lower = text.lower()
    return any(kw in text_lower for kw in _FINANCIAL_STATEMENT_KEYWORDS)


def prepare_structured_content(
    ingest_output: dict[str, Any],
    *,
    ticker: str,
    parse_fn: Callable[[dict[str, Any]], dict[str, Any]] = default_parse,
) -> str:
    """Build the LLM input for ``--mode structured``.

    Run L2's parser on ``ingest_output``, then select the first
    :data:`STRUCTURED_TABLE_COUNT` tables that pass
    :func:`_is_financial_table`. Real 10-Ks place several tables before
    the consolidated statements (cover-page address, trading symbols,
    filer status, the TOC itself, Item 5 share-repurchase data, MD&A
    breakdowns), so the previous "first three tables" heuristic was
    feeding the LLM the registrant's California address instead of the
    income statement — see error log T1.9 / Bug #2.

    The selection preserves document order so the LLM sees Income
    Statement → (Comprehensive Income) → Balance Sheet → Equity →
    Cash Flow in their canonical sequence.

    Args:
        ingest_output: The L1 output dict; must contain ``html_content``.
        ticker: For logging context only.
        parse_fn: Override for tests; defaults to the real L2 entry
            point.

    Returns:
        A string of the form
        ``"--- TABLA 1 ---\\n<text>\\n\\n--- TABLA 2 ---\\n<text>\\n..."``,
        clipped to :data:`STRUCTURED_MAX_CHARS`. May be empty if the
        parser found no financial-looking tables.

    Future improvement
    ------------------
    A more precise heuristic would scan the raw HTML for the canonical
    heading ``r"consolidated\\s+statements?\\s+of\\s+(operations|
    income)"`` and take the next ``N`` tables in document order. That
    requires correlating tables to their HTML offsets (a piece of
    metadata L2 currently does not preserve) and is deferred until
    Sprint 2.
    """
    parsed = parse_fn(ingest_output)
    raw_tables = parsed.get("raw_tables") if isinstance(parsed, dict) else None
    if not isinstance(raw_tables, list):
        raw_tables = []

    financial_tables = [t for t in raw_tables if _is_financial_table(t)]
    selected = financial_tables[:STRUCTURED_TABLE_COUNT]

    if not selected:
        _LOGGER.warning(
            "Modo structured: %s no produjo tablas con perfil financiero "
            "(>=%d montos en dólares).",
            ticker, _MIN_DOLLAR_AMOUNTS_PER_FIN_TABLE,
        )
        return ""

    blocks: list[str] = []
    for idx, table in enumerate(selected, start=1):
        if not isinstance(table, str) or not table.strip():
            continue
        blocks.append(f"--- TABLA {idx} ---\n{table.strip()}")

    if len(selected) < STRUCTURED_TABLE_COUNT:
        _LOGGER.warning(
            "Modo structured: %s solo aporta %d tablas financieras "
            "(esperaban %d).",
            ticker, len(selected), STRUCTURED_TABLE_COUNT,
        )

    joined = "\n\n".join(blocks)
    return _truncate(
        joined, STRUCTURED_MAX_CHARS, ticker=ticker, mode="structured"
    )


# ---------------------------------------------------------------------------
# Helpers — LLM response parsing
# ---------------------------------------------------------------------------


def _strip_markdown_fence(text: str) -> str:
    """Remove ```json / ``` markdown fences if present.

    Handles both ``"```json\\n{...}\\n```"`` and ``"```\\n{...}\\n```"``.
    Operates on a stripped copy of ``text``.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Drop the opening fence (with or without ``json``).
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, count=1)
    if cleaned.endswith("```"):
        cleaned = re.sub(r"\s*```$", "", cleaned, count=1)
    return cleaned.strip()


def _coerce_metric_value(raw: Any) -> float | None:
    """Coerce a single value from the parsed LLM JSON to a float-or-None.

    Accepts:

    * ``None`` / the string ``"null"`` / ``""`` → ``None``.
    * ``int``/``float`` (excluding ``bool``) → ``float``.
    * Strings that parse as floats (e.g. ``"391035000000"``,
      ``"6.13"``) → ``float``.

    Any other type is logged and coerced to ``None``: we want a "soft"
    failure path because a single weird value should not blow up the
    full evaluation run.
    """
    if raw is None:
        return None
    if isinstance(raw, bool):
        _LOGGER.warning("Valor LLM booleano (%r) coercionado a None.", raw)
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    if isinstance(raw, str):
        s = raw.strip()
        if not s or s.lower() == "null":
            return None
        try:
            return float(s.replace(",", ""))
        except ValueError:
            _LOGGER.warning(
                "Valor LLM string no numérico (%r) coercionado a None.", raw
            )
            return None
    _LOGGER.warning("Valor LLM tipo inesperado (%r) coercionado a None.", raw)
    return None


def parse_llm_response(raw: str) -> dict[str, float | None]:
    """Parse the raw LLM response into a ``metric → value`` dict.

    The function is deliberately defensive:

    1. Strip whitespace and an optional ```json / ``` markdown wrapper.
    2. Try :func:`json.loads` on the cleaned string.
    3. On failure, locate the **first** ``{`` and the **last** ``}``
       and try to load the substring between them. This handles the
       common Qwen failure mode of prepending or appending a sentence
       to the JSON.
    4. If parsing still fails, log the raw response and return a
       dict of six ``None`` values so the row counts as misses but
       does not crash the run.
    5. Validate the keys: missing keys → ``None``; extra keys are
       ignored.
    6. Coerce each value with :func:`_coerce_metric_value`.

    Args:
        raw: The full LLM response text.

    Returns:
        A dict keyed by :data:`GOLD_METRICS` with float-or-None
        values. The dict always has exactly six entries.
    """
    nulls: dict[str, float | None] = {m: None for m in GOLD_METRICS}

    if not isinstance(raw, str) or not raw.strip():
        _LOGGER.warning("Respuesta LLM vacía; devolviendo nulls.")
        return nulls

    cleaned = _strip_markdown_fence(raw)

    parsed: Any | None = None
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        # Fallback: extract the first {...} block by greedy bracket match.
        first_open = cleaned.find("{")
        last_close = cleaned.rfind("}")
        if first_open != -1 and last_close != -1 and last_close > first_open:
            substring = cleaned[first_open : last_close + 1]
            try:
                parsed = json.loads(substring)
            except json.JSONDecodeError as inner:
                _LOGGER.warning(
                    "JSON inválido tras fallback. Inner: %s. Raw: %r",
                    inner, raw[:500],
                )
                return nulls
        else:
            _LOGGER.warning(
                "Sin JSON parseable en respuesta LLM. Raw: %r", raw[:500]
            )
            return nulls

    if not isinstance(parsed, dict):
        _LOGGER.warning(
            "JSON parseado no es objeto (tipo=%s). Devolviendo nulls.",
            type(parsed).__name__,
        )
        return nulls

    out: dict[str, float | None] = {}
    for metric in GOLD_METRICS:
        out[metric] = _coerce_metric_value(parsed.get(metric))
    return out


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BaselineRow:
    """A single (ticker, metric) row in the LLM-baseline evaluation table."""

    ticker: str
    metric: str
    gold_value: float | None
    gold_fiscal_year: int | None
    predicted_value: float | None
    match: bool
    abs_error: float | None
    rel_error: float | None
    raw_llm_response: str
    notes_gold: str

    def as_csv_dict(self) -> dict[str, Any]:
        """Return a dict suitable for ``csv.DictWriter``."""
        truncated = self.raw_llm_response or ""
        if len(truncated) > RAW_RESPONSE_CSV_TRUNCATE:
            truncated = truncated[:RAW_RESPONSE_CSV_TRUNCATE]
        # Newlines mess up casual CSV viewing — normalise to spaces.
        truncated = _WS_RE.sub(" ", truncated).strip()
        return {
            "ticker": self.ticker,
            "metric": self.metric,
            "gold_value": _fmt_optional(self.gold_value),
            "gold_fiscal_year": _fmt_optional(self.gold_fiscal_year),
            "predicted_value": _fmt_optional(self.predicted_value),
            "match": "True" if self.match else "False",
            "abs_error": _fmt_optional(self.abs_error),
            "rel_error": _fmt_optional(self.rel_error),
            "raw_llm_response": truncated,
            "notes_gold": self.notes_gold or "",
        }


@dataclass(frozen=True)
class TickerCallStats:
    """Per-ticker bookkeeping for the run-level summary."""

    ticker: str
    content_chars: int
    elapsed_s: float
    raw_response_chars: int
    parsed_ok: bool


def _fmt_optional(value: object) -> str:
    """Render ``value`` for the CSV, treating ``None`` as empty string."""
    if value is None:
        return ""
    if isinstance(value, float):
        return repr(value)
    return str(value)


# ---------------------------------------------------------------------------
# Cache-aware HTML loading
# ---------------------------------------------------------------------------


def _cached_html_path(ticker: str, cache_dir: Path) -> Path | None:
    """Return the cached HTML file for ``ticker`` if any.

    The cache layout is ``data/cache/<TICKER>_<accession>.html``. We
    glob by prefix and pick the lexicographically largest accession
    (which, for SEC accession numbers, is also the most recent).
    """
    pattern = f"{ticker.upper()}_*.html"
    matches = sorted(cache_dir.glob(pattern))
    if not matches:
        return None
    return matches[-1]


def _load_ingest_output(
    ticker: str,
    *,
    cache_dir: Path,
    ingest_fn: Callable[[str], dict[str, Any]] = default_ingest,
) -> dict[str, Any]:
    """Return an L1-shaped dict for ``ticker``, preferring the on-disk cache.

    If the cache contains an HTML for ``ticker``, we synthesise a
    minimal ingest output (just enough for L2's ``parse``: a
    ``ticker``, an ``html_content``, and a ``filing_date``). Otherwise
    we delegate to ``ingest_fn`` and return its full payload.
    """
    cached = _cached_html_path(ticker, cache_dir)
    if cached is not None:
        _LOGGER.info("HTML en cache para %s: %s", ticker, cached.name)
        accession = cached.stem.split("_", 1)[1] if "_" in cached.stem else ""
        html = cached.read_text(encoding="utf-8")
        return {
            "company": "",
            "ticker": ticker.upper(),
            "cik": "",
            "filing_date": None,
            "accession_number": accession,
            "html_content": html,
            "xbrl_data": {},
            "source_urls": {},
        }

    _LOGGER.info("HTML no cacheado para %s; llamando a L1 ingest.", ticker)
    return ingest_fn(ticker)


# ---------------------------------------------------------------------------
# Core evaluation
# ---------------------------------------------------------------------------


def build_user_prompt(template: str, content: str) -> str:
    """Inject ``content`` into the prompt template's placeholder."""
    return template.replace("{content}", content)


def evaluate_ticker(
    ticker: str,
    gold: dict[tuple[str, str], GoldEntry],
    *,
    mode: str,
    prompt_template: str,
    llm_client: LLMClient,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    ingest_fn: Callable[[str], dict[str, Any]] = default_ingest,
    parse_fn: Callable[[dict[str, Any]], dict[str, Any]] = default_parse,
) -> tuple[list[BaselineRow], TickerCallStats]:
    """Run a single LLM extraction for ``ticker`` and produce per-metric rows.

    Args:
        ticker: One of :data:`GOLD_TICKERS`.
        gold: Gold standard map (output of :func:`load_gold_standard`).
        mode: ``"naive"`` or ``"structured"``.
        prompt_template: Prompt with a single ``{content}`` placeholder.
        llm_client: Configured :class:`LLMClient` (mocked in tests).
        cache_dir: Where to look for cached HTML.
        ingest_fn: Test override for L1 ingest.
        parse_fn: Test override for L2 parse.

    Returns:
        ``(rows, stats)`` — one :class:`BaselineRow` per metric in
        :data:`GOLD_METRICS` for which the gold standard has an entry,
        plus a :class:`TickerCallStats` describing the LLM call.

    Raises:
        ValueError: If ``mode`` is not in :data:`VALID_MODES`.
    """
    if mode not in VALID_MODES:
        raise ValueError(
            f"Modo desconocido: {mode!r}. Esperado uno de {VALID_MODES}."
        )

    _LOGGER.info("Evaluando %s en modo %s", ticker, mode)
    ingest_output = _load_ingest_output(
        ticker, cache_dir=cache_dir, ingest_fn=ingest_fn,
    )

    if mode == "naive":
        content = prepare_naive_content(
            ingest_output.get("html_content", ""), ticker=ticker
        )
    else:  # mode == "structured"
        content = prepare_structured_content(
            ingest_output, ticker=ticker, parse_fn=parse_fn
        )

    user_prompt = build_user_prompt(prompt_template, content)

    raw_response = ""
    parsed_ok = False
    elapsed_s = 0.0
    started = time.monotonic()
    try:
        raw_response = llm_client.chat(
            system=_LLM_SYSTEM_PROMPT,
            user=user_prompt,
            temperature=LLM_TEMPERATURE,
        )
        parsed_ok = True
    except Exception as exc:  # noqa: BLE001 — broad on purpose: never crash a run.
        _LOGGER.error(
            "Llamada al LLM falló para %s en modo %s: %s",
            ticker, mode, exc,
        )
    finally:
        elapsed_s = time.monotonic() - started

    predictions = parse_llm_response(raw_response)

    rows: list[BaselineRow] = []
    for metric in GOLD_METRICS:
        gold_entry = gold.get((ticker, metric))
        if gold_entry is None:
            _LOGGER.warning(
                "No hay anotación gold para (%s, %s); fila omitida",
                ticker, metric,
            )
            continue
        predicted_value = predictions.get(metric)
        match, abs_error, rel_error = compare_values(
            gold_entry.value, predicted_value
        )
        rows.append(
            BaselineRow(
                ticker=ticker,
                metric=metric,
                gold_value=gold_entry.value,
                gold_fiscal_year=gold_entry.fiscal_year,
                predicted_value=predicted_value,
                match=match,
                abs_error=abs_error,
                rel_error=rel_error,
                raw_llm_response=raw_response,
                notes_gold=gold_entry.notes,
            )
        )

    stats = TickerCallStats(
        ticker=ticker,
        content_chars=len(content),
        elapsed_s=elapsed_s,
        raw_response_chars=len(raw_response or ""),
        parsed_ok=parsed_ok,
    )
    return rows, stats


def run_evaluation(
    gold_path: Path,
    *,
    mode: str,
    prompt_template: str,
    llm_client: LLMClient,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    tickers: tuple[str, ...] = GOLD_TICKERS,
    ingest_fn: Callable[[str], dict[str, Any]] = default_ingest,
    parse_fn: Callable[[dict[str, Any]], dict[str, Any]] = default_parse,
) -> tuple[list[BaselineRow], list[TickerCallStats]]:
    """Load the gold standard and evaluate every ticker in ``tickers``.

    Args:
        gold_path: Path to ``data/gold_standard.xlsx``.
        mode: ``"naive"`` or ``"structured"``.
        prompt_template: Loaded prompt template.
        llm_client: Configured LLM client (mocked in tests).
        cache_dir: Where to look for cached HTMLs.
        tickers: Subset of tickers to evaluate. Defaults to
            :data:`GOLD_TICKERS`. ``--limit`` in the CLI maps to a
            slice of this tuple.
        ingest_fn: Test override.
        parse_fn: Test override.

    Returns:
        ``(rows, stats)`` — flat list of rows and one stats entry per
        ticker.
    """
    gold = load_gold_standard(gold_path)
    _LOGGER.info(
        "Gold standard cargado: %d filas. Evaluando %d tickers en modo %s.",
        len(gold), len(tickers), mode,
    )

    all_rows: list[BaselineRow] = []
    all_stats: list[TickerCallStats] = []
    for idx, ticker in enumerate(tickers, start=1):
        _LOGGER.info(
            "Progreso %d/%d → %s (modo=%s)",
            idx, len(tickers), ticker, mode,
        )
        rows, stats = evaluate_ticker(
            ticker, gold,
            mode=mode,
            prompt_template=prompt_template,
            llm_client=llm_client,
            cache_dir=cache_dir,
            ingest_fn=ingest_fn,
            parse_fn=parse_fn,
        )
        all_rows.extend(rows)
        all_stats.append(stats)
    return all_rows, all_stats


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------


def write_csv(rows: list[BaselineRow], path: Path) -> None:
    """Write the rows to ``path`` as UTF-8 CSV with the canonical header."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(CSV_FIELDNAMES))
        writer.writeheader()
        for row in rows:
            writer.writerow(row.as_csv_dict())


def _accuracy(matches: int, total: int) -> float:
    """Return ``matches / total`` with 0.0 fallback for empty buckets."""
    return (matches / total) if total else 0.0


def _fmt_value(value: float | None) -> str:
    """Render a numeric value for the Markdown tables."""
    if value is None:
        return "null"
    if abs(value) >= 1e6:
        return f"{value:,.0f}"
    return f"{value:,.4f}".rstrip("0").rstrip(".")


def _fmt_match(flag: bool) -> str:
    return "OK" if flag else "MISS"


def write_markdown_report(
    rows: list[BaselineRow],
    stats: list[TickerCallStats],
    path: Path,
    *,
    csv_path: Path,
    mode: str,
    prompt_path: Path,
) -> None:
    """Write the human-readable Markdown report.

    The report mirrors :func:`experiments.eval_extraction.write_markdown_report`
    so T1.10 can yuxtapose the L3 / Naive / Structured tables side by side.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    total = len(rows)
    matches = sum(1 for r in rows if r.match)
    accuracy = _accuracy(matches, total)

    lines: list[str] = []
    lines.append(f"# T1.9 — Baseline LLM ({mode}) vs gold standard\n")
    lines.append(
        f"Generado: {datetime.now().isoformat(timespec='seconds')}\n"
    )
    lines.append(f"CSV detallado: `{csv_path.name}`\n")
    lines.append(f"Prompt: `{prompt_path.relative_to(_PROJECT_ROOT)}`\n")
    lines.append("")

    # --- Mode summary -------------------------------------------------------
    n_calls = len(stats) or 1
    avg_chars = sum(s.content_chars for s in stats) / n_calls
    avg_tokens_est = avg_chars / 4.0  # rough English-ish estimate
    avg_seconds = sum(s.elapsed_s for s in stats) / n_calls
    parsed_ok = sum(1 for s in stats if s.parsed_ok)
    lines.append("## Modo de input\n")
    lines.append(f"- Modo: **{mode}**")
    lines.append(f"- Tickers evaluados: **{len(stats)}**")
    lines.append(
        f"- Llamadas LLM con respuesta: **{parsed_ok}/{len(stats)}**"
    )
    lines.append(
        f"- Tamaño medio de contenido: **{avg_chars:,.0f} chars** "
        f"(~{avg_tokens_est:,.0f} tokens estimados)"
    )
    lines.append(
        f"- Tiempo medio por llamada: **{avg_seconds:,.1f} s**"
    )
    lines.append("")

    # --- Aggregate ----------------------------------------------------------
    lines.append("## Resumen agregado\n")
    lines.append(f"- Pares evaluados: **{total}**")
    lines.append(f"- Coincidencias: **{matches}**")
    lines.append(
        f"- Accuracy global: **{accuracy:.1%}** ({matches}/{total})"
    )
    lines.append("")

    # --- Per-metric breakdown ----------------------------------------------
    lines.append("## Breakdown por métrica\n")
    rows_by_metric: dict[str, list[BaselineRow]] = {m: [] for m in GOLD_METRICS}
    for row in rows:
        rows_by_metric.setdefault(row.metric, []).append(row)
    for metric in GOLD_METRICS:
        bucket = rows_by_metric.get(metric, [])
        m_total = len(bucket)
        m_matches = sum(1 for r in bucket if r.match)
        m_accuracy = _accuracy(m_matches, m_total)
        lines.append(
            f"### `{metric}` — accuracy {m_accuracy:.1%} "
            f"({m_matches}/{m_total})\n"
        )
        lines.append("| ticker | gold | predicted | match | rel_error |")
        lines.append("|---|---:|---:|:---:|---:|")
        for row in bucket:
            rel_err_str = (
                f"{row.rel_error:.4%}"
                if row.rel_error is not None else "—"
            )
            lines.append(
                f"| {row.ticker} | {_fmt_value(row.gold_value)} "
                f"| {_fmt_value(row.predicted_value)} "
                f"| {_fmt_match(row.match)} | {rel_err_str} |"
            )
        lines.append("")

    # --- Per-company breakdown ---------------------------------------------
    lines.append("## Breakdown por empresa\n")
    rows_by_ticker: dict[str, list[BaselineRow]] = {}
    for row in rows:
        rows_by_ticker.setdefault(row.ticker, []).append(row)
    for ticker in [s.ticker for s in stats]:
        bucket = rows_by_ticker.get(ticker, [])
        t_total = len(bucket)
        t_matches = sum(1 for r in bucket if r.match)
        t_accuracy = _accuracy(t_matches, t_total)
        lines.append(
            f"### {ticker} — accuracy {t_accuracy:.1%} "
            f"({t_matches}/{t_total})\n"
        )
        lines.append("| metric | gold | predicted | match |")
        lines.append("|---|---:|---:|:---:|")
        for row in bucket:
            lines.append(
                f"| {row.metric} | {_fmt_value(row.gold_value)} "
                f"| {_fmt_value(row.predicted_value)} "
                f"| {_fmt_match(row.match)} |"
            )
        lines.append("")

    # --- Distribution of failure reasons -----------------------------------
    lines.append("## Distribución de tipos de respuesta\n")
    counter: Counter[str] = Counter()
    for row in rows:
        if row.match:
            counter["match"] += 1
        elif row.predicted_value is None and row.gold_value is not None:
            counter["miss_predicted_null"] += 1
        elif row.predicted_value is not None and row.gold_value is None:
            counter["miss_hallucination"] += 1
        elif row.predicted_value is None and row.gold_value is None:
            # Cannot happen because compare_values returns match=True there;
            # guarded for completeness.
            counter["both_null_match"] += 1
        else:
            counter["miss_wrong_value"] += 1
    lines.append("| categoría | n |")
    lines.append("|---|---:|")
    for label, n in counter.most_common():
        lines.append(f"| {label} | {n} |")
    lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")


# ---------------------------------------------------------------------------
# Console summary
# ---------------------------------------------------------------------------


def _print_console_summary(
    rows: list[BaselineRow], stats: list[TickerCallStats], *, mode: str,
) -> None:
    """Print a compact summary suitable for terminal output."""
    total = len(rows)
    matches = sum(1 for r in rows if r.match)
    accuracy = _accuracy(matches, total)

    print()
    print("=" * 60)
    print(f"T1.9 — Baseline LLM ({mode}) vs gold standard")
    print("=" * 60)
    print(f"Pares evaluados: {total}")
    print(f"Coincidencias:   {matches}")
    print(f"Accuracy global: {accuracy:.1%} ({matches}/{total})")
    if stats:
        avg_chars = sum(s.content_chars for s in stats) / len(stats)
        avg_seconds = sum(s.elapsed_s for s in stats) / len(stats)
        print(
            f"Tamaño medio:    {avg_chars:,.0f} chars  "
            f"Tiempo medio:    {avg_seconds:,.1f} s/llamada"
        )
    print()
    print("Accuracy por métrica:")
    rows_by_metric: dict[str, list[BaselineRow]] = {m: [] for m in GOLD_METRICS}
    for row in rows:
        rows_by_metric.setdefault(row.metric, []).append(row)
    for metric in GOLD_METRICS:
        bucket = rows_by_metric.get(metric, [])
        m_matches = sum(1 for r in bucket if r.match)
        m_total = len(bucket)
        m_accuracy = _accuracy(m_matches, m_total)
        print(
            f"  {metric:<20s} {m_accuracy:>6.1%}  ({m_matches}/{m_total})"
        )
    print("=" * 60)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_output_paths(output_dir: Path, mode: str) -> tuple[Path, Path]:
    """Return ``(csv_path, md_path)`` with a shared timestamp."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = output_dir / f"eval_baseline_{mode}_{stamp}.csv"
    md_path = output_dir / f"eval_baseline_{mode}_{stamp}.md"
    return csv_path, md_path


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="eval_baseline_llm.py",
        description=(
            "Evalúa un baseline LLM-naive (HTML crudo) o estructurado "
            "(3 tablas Item 8) contra el gold standard y genera CSV + "
            "Markdown bajo experiments/output/."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=VALID_MODES,
        required=True,
        help="Estrategia de input al LLM: 'naive' o 'structured'.",
    )
    parser.add_argument(
        "--gold-path",
        type=Path,
        default=DEFAULT_GOLD_PATH,
        help=(
            f"Ruta del Excel de gold standard "
            f"(por defecto: {DEFAULT_GOLD_PATH.relative_to(_PROJECT_ROOT)})."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=(
            f"Directorio de salida "
            f"(por defecto: {DEFAULT_OUTPUT_DIR.relative_to(_PROJECT_ROOT)})."
        ),
    )
    parser.add_argument(
        "--prompt-path",
        type=Path,
        default=DEFAULT_PROMPT_PATH,
        help=(
            f"Ruta del template de prompt "
            f"(por defecto: {DEFAULT_PROMPT_PATH.relative_to(_PROJECT_ROOT)})."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Limita la evaluación a los N primeros tickers de "
            "GOLD_TICKERS. Útil para iterar rápido durante desarrollo."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""
    args = _parse_args(argv)

    # Load global config + .env so the LLM client picks up host/model.
    load_config()

    prompt_template = load_prompt_template(args.prompt_path)

    tickers: tuple[str, ...] = GOLD_TICKERS
    if args.limit is not None and args.limit > 0:
        tickers = GOLD_TICKERS[: args.limit]

    llm_client = LLMClient(timeout_s=LLM_TIMEOUT_S)

    rows, stats = run_evaluation(
        args.gold_path,
        mode=args.mode,
        prompt_template=prompt_template,
        llm_client=llm_client,
        tickers=tickers,
    )

    csv_path, md_path = _build_output_paths(args.output_dir, args.mode)
    write_csv(rows, csv_path)
    write_markdown_report(
        rows, stats, md_path,
        csv_path=csv_path, mode=args.mode, prompt_path=args.prompt_path,
    )

    _LOGGER.info("CSV escrito en %s", csv_path)
    _LOGGER.info("Markdown escrito en %s", md_path)

    _print_console_summary(rows, stats, mode=args.mode)
    print(f"\nCSV : {csv_path}")
    print(f"MD  : {md_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BaselineRow",
    "CSV_FIELDNAMES",
    "DEFAULT_GOLD_PATH",
    "DEFAULT_OUTPUT_DIR",
    "DEFAULT_PROMPT_PATH",
    "NAIVE_HEAD_CHARS",
    "NAIVE_HEAD_TAIL_SEPARATOR",
    "NAIVE_MAX_CHARS",
    "NAIVE_TAIL_CHARS",
    "STRUCTURED_MAX_CHARS",
    "STRUCTURED_TABLE_COUNT",
    "TickerCallStats",
    "VALID_MODES",
    "build_user_prompt",
    "evaluate_ticker",
    "html_to_plain_text",
    "load_prompt_template",
    "main",
    "parse_llm_response",
    "prepare_naive_content",
    "prepare_structured_content",
    "run_evaluation",
    "write_csv",
    "write_markdown_report",
]
