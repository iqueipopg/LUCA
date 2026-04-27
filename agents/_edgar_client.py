"""Thin SEC EDGAR HTTP client used by the LUCA L1 Ingestion agent.

This module exposes four pure functions wrapping the three public EDGAR
endpoints LUCA cares about:

* :func:`ticker_to_cik` — resolve a ticker to a 10-digit padded CIK using
  ``https://www.sec.gov/files/company_tickers.json``. The mapping is fetched
  once and memoised in process-local state.
* :func:`fetch_companyfacts` — download the ``companyfacts`` XBRL bundle for
  a given CIK. This is the data source feeding L3 extraction.
* :func:`fetch_submissions` — download the filings submission index for a
  given CIK.
* :func:`latest_10k_accession` — pure helper that scans a submissions JSON
  payload and returns the most recent ``10-K`` accession number.

The HTTP layer follows the rules fixed for T0.5:

1. Every request carries a ``User-Agent`` header read from ``SEC_USER_AGENT``
   (in ``.env`` or the real environment). Missing/empty values raise
   :class:`RuntimeError` with an actionable message.
2. Before every request we ``time.sleep`` for ``sources.sec_edgar.rate_limit_s``
   seconds (configured in ``config.yaml``, defaults to 0.15s ≈ 7 req/s, well
   below SEC's hard cap of 10 req/s).
3. On HTTP 429 the call sleeps 10 seconds and retries up to
   ``L1_ingestion.max_retries`` times (from ``config/agents.json``).
4. On transient ``requests.RequestException`` the call retries with
   exponential backoff (base 2, cap 8s), mirroring :mod:`agents._llm_client`.
5. Any other ``4xx``/``5xx`` is raised verbatim via
   :meth:`requests.Response.raise_for_status` — we do not silently swallow
   server errors.

The module never calls EDGAR at import time. Tests in T0.8 patch
:func:`requests.get` and feed fixtures from ``tests/fixtures/``.
"""

from __future__ import annotations

import time
from typing import Any

import requests

from agents._config import get_agent_config, get_env, load_config
from agents._logging import get_logger

# ---------------------------------------------------------------------------
# Constants (internal)
# ---------------------------------------------------------------------------

_TICKERS_URL: str = "https://www.sec.gov/files/company_tickers.json"
_COMPANYFACTS_URL_TMPL: str = (
    "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
)
_SUBMISSIONS_URL_TMPL: str = (
    "https://data.sec.gov/submissions/CIK{cik}.json"
)
_FILING_INDEX_JSON_URL_TMPL: str = (
    "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_nodash}/index.json"
)
_FILING_DOCUMENT_URL_TMPL: str = (
    "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_nodash}/{filename}"
)

#: Defensive fallbacks used only when ``config.yaml`` / ``config/agents.json``
#: leave a field unresolved. In the normal LUCA layout the values resolve
#: against the project's config files, so these fallbacks exist purely to
#: keep the module importable in degraded environments (e.g. unit tests
#: running with a stripped-down config).
_FALLBACK_RATE_LIMIT_S: float = 0.15
_FALLBACK_TIMEOUT_S: float = 30.0
_FALLBACK_MAX_RETRIES: int = 3

#: Backoff parameters for retry loops on transient network failures.
_BACKOFF_BASE: float = 2.0
_BACKOFF_CAP_S: float = 8.0

#: Hard-coded by SEC docs: on HTTP 429 they ask clients to back off ≥10s.
_RATE_LIMIT_RETRY_DELAY_S: float = 10.0

#: Process-local cache for the ticker → CIK map. ``None`` means "not loaded".
_TICKER_CACHE: dict[str, str] | None = None

_LOGGER = get_logger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _coerce_float(value: Any, fallback: float) -> float:
    """Best-effort cast of ``value`` to ``float``, returning ``fallback`` on failure."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _coerce_int(value: Any, fallback: int) -> int:
    """Best-effort cast of ``value`` to ``int``, returning ``fallback`` on failure."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def _resolve_rate_limit_s() -> float:
    """Return the configured inter-request sleep, in seconds."""
    try:
        cfg = load_config()
    except Exception:  # pragma: no cover - defensive, _config has its own tests
        return _FALLBACK_RATE_LIMIT_S
    block = cfg.get("global", {}).get("sources", {}).get("sec_edgar", {})
    if not isinstance(block, dict):
        return _FALLBACK_RATE_LIMIT_S
    return _coerce_float(block.get("rate_limit_s"), _FALLBACK_RATE_LIMIT_S)


def _resolve_l1_settings() -> tuple[float, int]:
    """Return ``(timeout_s, max_retries)`` for the L1 Ingestion agent."""
    try:
        agent_cfg = get_agent_config("L1_ingestion")
    except (KeyError, FileNotFoundError):
        return _FALLBACK_TIMEOUT_S, _FALLBACK_MAX_RETRIES
    timeout_s = _coerce_float(agent_cfg.get("timeout_s"), _FALLBACK_TIMEOUT_S)
    max_retries = max(
        0, _coerce_int(agent_cfg.get("max_retries"), _FALLBACK_MAX_RETRIES)
    )
    return timeout_s, max_retries


def _build_headers() -> dict[str, str]:
    """Return the request headers, validating ``SEC_USER_AGENT`` is set.

    Returns:
        A dict with at least the ``User-Agent`` header populated from the
        ``SEC_USER_AGENT`` environment variable.

    Raises:
        RuntimeError: If ``SEC_USER_AGENT`` is unset or empty. The error
            message tells the user exactly which file to edit.
    """
    user_agent = get_env("SEC_USER_AGENT")
    if not user_agent or not user_agent.strip():
        raise RuntimeError(
            "SEC_USER_AGENT is not set. SEC EDGAR requires an identifying "
            "User-Agent header (e.g. 'Nombre Apellido email@dominio.com'). "
            "Add SEC_USER_AGENT=... to your .env file at the project root."
        )
    return {
        "User-Agent": user_agent.strip(),
        "Accept": "application/json",
    }


def _normalize_cik(cik: str) -> str:
    """Return ``cik`` left-padded with zeros to 10 digits.

    Args:
        cik: A CIK as a string. Accepts either the integer form ``"320193"``
            or the already-padded form ``"0000320193"``. Surrounding
            whitespace is stripped.

    Returns:
        The 10-digit zero-padded CIK string.

    Raises:
        ValueError: If ``cik`` is empty, longer than 10 digits or contains
            non-digit characters.
    """
    if not isinstance(cik, str):
        raise ValueError(f"CIK must be a string, got {type(cik).__name__}.")
    stripped = cik.strip()
    if not stripped:
        raise ValueError("CIK must not be empty.")
    if not stripped.isdigit():
        raise ValueError(f"CIK must contain only digits, got {cik!r}.")
    if len(stripped) > 10:
        raise ValueError(f"CIK has more than 10 digits: {cik!r}.")
    return stripped.zfill(10)


def _request_raw(url: str, accept: str = "application/json") -> requests.Response:
    """Issue a rate-limited ``GET`` for ``url`` and return the raw response.

    The function honours the project rate limit, retries on HTTP 429 and on
    transient :class:`requests.RequestException` instances, and raises any
    other ``4xx``/``5xx`` via :meth:`requests.Response.raise_for_status`.

    Args:
        url: Absolute URL to fetch. The caller is responsible for building
            the URL (we do not interpolate query strings here).
        accept: Value to send in the ``Accept`` header. Defaults to
            ``"application/json"``; HTML callers should pass ``"text/html"``.

    Returns:
        The successful :class:`requests.Response` object. The caller is in
        charge of decoding it (``.json()`` or ``.text``).

    Raises:
        requests.HTTPError: For non-429 ``4xx``/``5xx`` responses.
        requests.RequestException: For transient errors that persist after
            all retries.
    """
    headers = _build_headers()
    headers["Accept"] = accept
    timeout_s, max_retries = _resolve_l1_settings()
    rate_limit_s = _resolve_rate_limit_s()

    attempts = max_retries + 1
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        if rate_limit_s > 0:
            time.sleep(rate_limit_s)
        try:
            _LOGGER.debug(
                "EDGAR GET attempt=%d/%d url=%s", attempt, attempts, url
            )
            response = requests.get(url, headers=headers, timeout=timeout_s)
        except requests.RequestException as exc:
            last_error = exc
            if attempt >= attempts:
                _LOGGER.error(
                    "Petición EDGAR falló tras %d intentos (url=%s): %s",
                    attempts,
                    url,
                    exc,
                )
                raise
            delay = min(_BACKOFF_CAP_S, _BACKOFF_BASE ** (attempt - 1))
            _LOGGER.warning(
                "Petición EDGAR intento %d/%d falló (url=%s): %s. "
                "Reintentando en %.1fs.",
                attempt,
                attempts,
                url,
                exc,
                delay,
            )
            time.sleep(delay)
            continue

        if response.status_code == 429:
            last_error = requests.HTTPError(
                f"429 Too Many Requests for {url}", response=response
            )
            if attempt >= attempts:
                _LOGGER.error(
                    "EDGAR rate limit (429) tras %d intentos (url=%s).",
                    attempts,
                    url,
                )
                response.raise_for_status()
            _LOGGER.warning(
                "EDGAR devolvió 429 (url=%s). Esperando %.1fs antes del "
                "reintento %d/%d.",
                url,
                _RATE_LIMIT_RETRY_DELAY_S,
                attempt + 1,
                attempts,
            )
            time.sleep(_RATE_LIMIT_RETRY_DELAY_S)
            continue

        # Any other 4xx/5xx surfaces immediately — no point retrying a 404.
        response.raise_for_status()
        return response

    # Defensive: the loop above either returns or raises. This line is only
    # reachable if ``attempts`` is non-positive, which we prevent by clamping
    # ``max_retries`` to ``>= 0`` in :func:`_resolve_l1_settings`.
    raise RuntimeError(  # pragma: no cover
        f"EDGAR request exhausted retries without raising; "
        f"last_error={last_error!r}"
    )


def _request_json(url: str) -> dict[str, Any]:
    """Issue a rate-limited ``GET`` for ``url`` and return the decoded JSON.

    Thin wrapper around :func:`_request_raw` that decodes the body as JSON
    and validates the top level is a dict (every EDGAR JSON endpoint LUCA
    consumes returns an object, never an array).

    Args:
        url: Absolute URL to fetch.

    Returns:
        The decoded JSON payload as a dict.

    Raises:
        RuntimeError: If the response is not a JSON object at the top level.
        requests.HTTPError: For non-429 ``4xx``/``5xx`` responses.
        requests.RequestException: For transient errors that persist after
            all retries.
    """
    response = _request_raw(url, accept="application/json")
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(
            f"Unexpected EDGAR response shape for {url}: "
            f"top level is {type(payload).__name__}, expected dict."
        )
    return payload


def _request_text(url: str) -> str:
    """Issue a rate-limited ``GET`` for ``url`` and return the body as text.

    Used by :func:`fetch_10k_html` to download filing HTML.

    Args:
        url: Absolute URL to fetch.

    Returns:
        The decoded response body as a string.

    Raises:
        requests.HTTPError: For non-429 ``4xx``/``5xx`` responses.
        requests.RequestException: For transient errors that persist after
            all retries.
    """
    response = _request_raw(url, accept="text/html")
    return response.text


def _load_ticker_map() -> dict[str, str]:
    """Fetch and cache the ticker → padded CIK mapping.

    Returns:
        A dict mapping uppercase tickers to 10-digit zero-padded CIKs.
    """
    global _TICKER_CACHE
    if _TICKER_CACHE is not None:
        return _TICKER_CACHE

    payload = _request_json(_TICKERS_URL)
    mapping: dict[str, str] = {}
    # The endpoint returns ``{"0": {...}, "1": {...}, ...}``.
    for entry in payload.values():
        if not isinstance(entry, dict):
            continue
        ticker = entry.get("ticker")
        cik_int = entry.get("cik_str")
        if not isinstance(ticker, str) or cik_int is None:
            continue
        try:
            mapping[ticker.upper()] = str(int(cik_int)).zfill(10)
        except (TypeError, ValueError):
            continue

    _LOGGER.info("Mapa de tickers EDGAR cargado: %d entradas.", len(mapping))
    _TICKER_CACHE = mapping
    return _TICKER_CACHE


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def ticker_to_cik(ticker: str) -> str:
    """Resolve a stock ticker to its 10-digit zero-padded CIK.

    The first call downloads ``company_tickers.json`` from SEC.gov and caches
    the resulting mapping in process memory. Subsequent calls are O(1).

    Args:
        ticker: Stock ticker symbol, case-insensitive (e.g. ``"AAPL"``,
            ``"msft"``).

    Returns:
        The CIK as a 10-digit zero-padded string, e.g. ``"0000320193"``.

    Raises:
        ValueError: If ``ticker`` is empty or not present in EDGAR's mapping.
        RuntimeError: If ``SEC_USER_AGENT`` is not configured.
        requests.HTTPError: If EDGAR returns a non-success response.
    """
    if not isinstance(ticker, str) or not ticker.strip():
        raise ValueError("ticker must be a non-empty string.")
    key = ticker.strip().upper()
    mapping = _load_ticker_map()
    if key not in mapping:
        raise ValueError(
            f"Ticker {key!r} not found in SEC EDGAR ticker map."
        )
    return mapping[key]


def fetch_companyfacts(cik: str) -> dict[str, Any]:
    """Download the companyfacts XBRL bundle for a given CIK.

    Args:
        cik: The CIK in either padded (``"0000320193"``) or unpadded
            (``"320193"``) form. The function normalises it internally.

    Returns:
        The decoded companyfacts JSON document. Top-level keys include
        ``cik``, ``entityName`` and ``facts`` (with ``us-gaap`` /
        ``dei`` sub-mappings).

    Raises:
        ValueError: If ``cik`` is malformed.
        RuntimeError: If ``SEC_USER_AGENT`` is not configured.
        requests.HTTPError: If EDGAR returns a non-success response.
    """
    padded = _normalize_cik(cik)
    url = _COMPANYFACTS_URL_TMPL.format(cik=padded)
    _LOGGER.info("Descargando companyfacts cik=%s", padded)
    return _request_json(url)


def fetch_submissions(cik: str) -> dict[str, Any]:
    """Download the filings submissions index for a given CIK.

    Args:
        cik: The CIK in either padded or unpadded form. Normalised internally.

    Returns:
        The decoded submissions JSON document. The recent filings live under
        ``payload["filings"]["recent"]`` as parallel arrays keyed by
        ``form``, ``accessionNumber``, ``filingDate``, etc.

    Raises:
        ValueError: If ``cik`` is malformed.
        RuntimeError: If ``SEC_USER_AGENT`` is not configured.
        requests.HTTPError: If EDGAR returns a non-success response.
    """
    padded = _normalize_cik(cik)
    url = _SUBMISSIONS_URL_TMPL.format(cik=padded)
    _LOGGER.info("Descargando submissions cik=%s", padded)
    return _request_json(url)


def latest_10k_accession(submissions: dict[str, Any]) -> str | None:
    """Return the accession number of the most recent ``10-K`` filing.

    The EDGAR submissions endpoint stores recent filings as parallel arrays
    under ``payload["filings"]["recent"]``. We pair ``form`` with
    ``accessionNumber`` and ``filingDate``, filter for ``form == "10-K"``,
    and pick the one with the latest ``filingDate``. If two filings share
    the same date, list order (most recent first, per EDGAR convention)
    breaks the tie.

    Args:
        submissions: The dict returned by :func:`fetch_submissions`.

    Returns:
        The ``accessionNumber`` string of the most recent 10-K, or ``None``
        if the company has never filed one (or the structure is missing).
    """
    if not isinstance(submissions, dict):
        return None
    filings = submissions.get("filings")
    if not isinstance(filings, dict):
        return None
    recent = filings.get("recent")
    if not isinstance(recent, dict):
        return None

    forms = recent.get("form") or []
    accessions = recent.get("accessionNumber") or []
    dates = recent.get("filingDate") or []

    if not isinstance(forms, list) or not isinstance(accessions, list):
        return None

    # Pair them up; tolerate missing dates by using the empty string, which
    # sorts before any real ISO date.
    pairs: list[tuple[str, str, int]] = []
    for idx, form in enumerate(forms):
        if form != "10-K":
            continue
        if idx >= len(accessions):
            continue
        accession = accessions[idx]
        if not isinstance(accession, str) or not accession:
            continue
        date = (
            dates[idx]
            if isinstance(dates, list) and idx < len(dates) and isinstance(dates[idx], str)
            else ""
        )
        pairs.append((date, accession, idx))

    if not pairs:
        return None

    # Sort by (date desc, idx asc). Same date → trust EDGAR's native order.
    pairs.sort(key=lambda t: (t[0], -t[2]), reverse=True)
    return pairs[0][1]


def _resolve_primary_10k_filename(items: list[dict[str, Any]]) -> str | None:
    """Pick the primary 10-K HTML document filename from an index.json listing.

    Heuristic, in order of preference:

    1. The ``.htm``/``.html`` item whose ``type`` field equals ``"10-K"``
       exactly. This is the canonical primary document for EDGAR 10-K filings.
    2. The ``.htm``/``.html`` item whose ``type`` starts with ``"10-K"`` (covers
       ``"10-K/A"`` amendments and similar variants).
    3. Fallback: the largest ``.htm``/``.html`` item by ``size``. We exclude
       index/exhibit files (names starting with ``"R"`` followed by digits, the
       inline-XBRL viewer files, or names ending with ``"index.htm"``) before
       picking the largest. This is a safety net for filings whose ``type``
       fields are missing or mislabelled — empirically rare but observed.

    Args:
        items: The ``directory.item`` array from the EDGAR ``index.json``
            payload. Each entry is a dict with ``name``, ``type``, ``size``
            and ``last-modified`` keys.

    Returns:
        The selected filename (e.g. ``"aapl-20230930.htm"``), or ``None`` if
        no plausible HTML document is present.
    """
    if not isinstance(items, list):
        return None

    html_items: list[dict[str, Any]] = []
    for entry in items:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if not isinstance(name, str):
            continue
        lower = name.lower()
        if not (lower.endswith(".htm") or lower.endswith(".html")):
            continue
        html_items.append(entry)

    if not html_items:
        return None

    # 1) Exact ``type == "10-K"``.
    for entry in html_items:
        if entry.get("type") == "10-K":
            return entry["name"]

    # 2) ``type`` starts with ``"10-K"`` (amendments etc.).
    for entry in html_items:
        type_field = entry.get("type")
        if isinstance(type_field, str) and type_field.startswith("10-K"):
            return entry["name"]

    # 3) Fallback: largest .htm by ``size``, excluding obvious non-primary files.
    def _is_candidate(entry: dict[str, Any]) -> bool:
        name = str(entry.get("name", "")).lower()
        if name.endswith("index.htm") or name.endswith("index.html"):
            return False
        # Filing-summary helper files like R1.htm, R2.htm etc. are inline-XBRL
        # viewer fragments, not the primary document.
        stem = name.rsplit(".", 1)[0]
        if stem.startswith("r") and stem[1:].isdigit():
            return False
        return True

    candidates = [e for e in html_items if _is_candidate(e)]
    if not candidates:
        return None

    def _size(entry: dict[str, Any]) -> int:
        try:
            return int(entry.get("size", 0))
        except (TypeError, ValueError):
            return 0

    candidates.sort(key=_size, reverse=True)
    return candidates[0]["name"]


def fetch_10k_html(cik: str, accession: str) -> str:
    """Download the HTML body of a 10-K filing's primary document.

    The function resolves the primary document by reading the filing's
    ``index.json`` listing on EDGAR, applying the heuristic in
    :func:`_resolve_primary_10k_filename`, and then downloading that file as
    text. Caching is the caller's responsibility.

    Args:
        cik: The CIK in either padded (``"0000320193"``) or unpadded
            (``"320193"``) form. Normalised internally.
        accession: Accession number with dashes, e.g.
            ``"0000320193-23-000106"``.

    Returns:
        The HTML body as a string.

    Raises:
        ValueError: If ``cik`` is malformed or ``accession`` is empty.
        RuntimeError: If ``SEC_USER_AGENT`` is not configured, the index
            payload has no ``directory.item`` array, or no primary HTML
            document can be identified.
        requests.HTTPError: If EDGAR returns a non-success response.
    """
    if not isinstance(accession, str) or not accession.strip():
        raise ValueError("accession must be a non-empty string.")
    padded = _normalize_cik(cik)
    cik_int = str(int(padded))
    accession_nodash = accession.strip().replace("-", "")

    index_url = _FILING_INDEX_JSON_URL_TMPL.format(
        cik_int=cik_int,
        accession_nodash=accession_nodash,
    )
    _LOGGER.info(
        "Resolviendo primary document 10-K cik=%s accession=%s",
        padded,
        accession,
    )
    index_payload = _request_json(index_url)

    directory = index_payload.get("directory")
    if not isinstance(directory, dict):
        raise RuntimeError(
            f"EDGAR index.json missing 'directory' object for accession "
            f"{accession!r} (url={index_url})."
        )
    items = directory.get("item")
    if not isinstance(items, list):
        raise RuntimeError(
            f"EDGAR index.json missing 'directory.item' array for accession "
            f"{accession!r} (url={index_url})."
        )

    filename = _resolve_primary_10k_filename(items)
    if filename is None:
        raise RuntimeError(
            f"No 10-K primary HTML document found for accession {accession!r} "
            f"(url={index_url}). Inspect the filing manually."
        )

    document_url = _FILING_DOCUMENT_URL_TMPL.format(
        cik_int=cik_int,
        accession_nodash=accession_nodash,
        filename=filename,
    )
    _LOGGER.info(
        "Descargando 10-K HTML cik=%s accession=%s file=%s",
        padded,
        accession,
        filename,
    )
    return _request_text(document_url)


__all__ = [
    "ticker_to_cik",
    "fetch_companyfacts",
    "fetch_submissions",
    "latest_10k_accession",
    "fetch_10k_html",
]
