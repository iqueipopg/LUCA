"""Thin wrapper around the Ollama Python client used across the LUCA pipeline.

This module exposes two public symbols:

* :class:`LLMClient` — a minimal client that resolves connection defaults
  (host, model, timeout, retries) from the project configuration and wraps
  :meth:`ollama.Client.chat` with structured logging and exponential backoff.
* :func:`parse_json_response` — a defensive JSON parser that tolerates the
  markdown fences Qwen 2.5 sometimes prepends to its output.

The module never calls Ollama at import time and never owns a network socket
until :meth:`LLMClient.chat` is invoked, so it is cheap to instantiate (and
safe to mock) in tests.

Configuration resolution follows the rule fixed for T0.4:

1. Explicit constructor arguments win over everything.
2. Then ``os.environ`` / ``.env`` (``OLLAMA_HOST``, ``OLLAMA_MODEL``).
3. Finally ``config.yaml::llm`` (``host``, ``model``, ``timeout_s``,
   ``retries``) provides project-wide defaults.

Note:
    The retry loop is intentionally synchronous and minimal. Streaming and
    async usage are out of scope for the Sprint 0 scaffold; the L4/L7 agents
    will reach for those directly when they need them.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

import ollama
import requests

from agents._config import get_env, load_config
from agents._logging import get_logger

# ---------------------------------------------------------------------------
# Constants (internal)
# ---------------------------------------------------------------------------

#: Hard-coded fallbacks used only if both ``config.yaml`` and the explicit
#: constructor arguments leave a field unresolved. In practice ``config.yaml``
#: always defines these, so these values exist purely as a defensive backstop
#: that keeps the client from crashing in degraded environments (e.g. a unit
#: test running with a stripped-down config).
_FALLBACK_HOST: str = "http://localhost:11434"
_FALLBACK_MODEL: str = "qwen2.5:7b-instruct-q4_K_M"
_FALLBACK_TIMEOUT_S: float = 120.0
_FALLBACK_MAX_RETRIES: int = 2

#: Backoff parameters for the chat retry loop. Base 2 exponential with a cap.
_BACKOFF_BASE: float = 2.0
_BACKOFF_CAP_S: float = 8.0

_LOGGER = get_logger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_llm_defaults() -> dict[str, Any]:
    """Return the ``llm`` block from ``config.yaml`` as a plain dict.

    Returns:
        The mapping under ``config.yaml::llm``, or an empty dict if the key
        is missing or malformed. The function never raises so that it can be
        called from :class:`LLMClient.__init__` without forcing every caller
        to handle config failures.
    """
    try:
        cfg = load_config()
    except Exception:  # pragma: no cover - defensive, _config has its own tests
        return {}
    block = cfg.get("global", {}).get("llm", {})
    return block if isinstance(block, dict) else {}


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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class LLMClient:
    """Configured wrapper around :class:`ollama.Client` for the LUCA pipeline.

    Instances are cheap to construct and safe to share between agents. The
    underlying :class:`ollama.Client` is created eagerly so that ``host``
    misconfigurations surface at construction time rather than on the first
    chat call.

    Attributes:
        host: Effective Ollama base URL.
        model: Effective Ollama model identifier.
        timeout_s: Per-request timeout passed to the underlying HTTP client.
        max_retries: Number of retry attempts performed by :meth:`chat` after
            the initial call (so the total number of attempts is
            ``max_retries + 1``).
    """

    def __init__(
        self,
        host: str | None = None,
        model: str | None = None,
        timeout_s: float | None = None,
        max_retries: int | None = None,
    ) -> None:
        """Initialize the client, resolving defaults from config and env.

        Args:
            host: Ollama base URL. If ``None``, falls back to the
                ``OLLAMA_HOST`` environment variable, then to
                ``config.yaml::llm.host``.
            model: Ollama model identifier. If ``None``, falls back to the
                ``OLLAMA_MODEL`` environment variable, then to
                ``config.yaml::llm.model``.
            timeout_s: Per-request timeout in seconds. If ``None``, taken from
                ``config.yaml::llm.timeout_s``.
            max_retries: Number of retry attempts for transient errors. If
                ``None``, taken from ``config.yaml::llm.retries``.
        """
        defaults = _resolve_llm_defaults()

        resolved_host = (
            host
            or get_env("OLLAMA_HOST")
            or defaults.get("host")
            or _FALLBACK_HOST
        )
        resolved_model = (
            model
            or get_env("OLLAMA_MODEL")
            or defaults.get("model")
            or _FALLBACK_MODEL
        )
        resolved_timeout = (
            timeout_s
            if timeout_s is not None
            else _coerce_float(defaults.get("timeout_s"), _FALLBACK_TIMEOUT_S)
        )
        resolved_retries = (
            max_retries
            if max_retries is not None
            else _coerce_int(defaults.get("retries"), _FALLBACK_MAX_RETRIES)
        )

        self.host: str = str(resolved_host)
        self.model: str = str(resolved_model)
        self.timeout_s: float = float(resolved_timeout)
        self.max_retries: int = max(0, int(resolved_retries))

        # ``ollama.Client`` forwards ``**kwargs`` to ``httpx.Client``; ``timeout``
        # is the documented knob for per-request timeouts.
        self._client: ollama.Client = ollama.Client(
            host=self.host, timeout=self.timeout_s
        )

        _LOGGER.debug(
            "LLMClient initialised host=%s model=%s timeout_s=%.1f max_retries=%d",
            self.host,
            self.model,
            self.timeout_s,
            self.max_retries,
        )

    # ------------------------------------------------------------------ chat

    def chat(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.2,
        num_ctx: int = 8192,
        max_tokens: int | None = None,
    ) -> str:
        """Send a single-turn chat request and return the response content.

        Builds a ``[system, user]`` message pair, forwards it to
        :meth:`ollama.Client.chat`, and returns ``response["message"]["content"]``.
        On transient failures the call is retried up to :attr:`max_retries`
        times with an exponential backoff (base 2, capped at 8 seconds).

        Args:
            system: The system prompt. Conventionally written in English so
                Qwen follows instructions reliably.
            user: The user prompt. May contain document text in Spanish or
                English.
            temperature: Sampling temperature passed under ``options``.
            num_ctx: Context window in tokens, passed under ``options``.
                Defaults to 8192, the recommended value for Qwen 2.5 7B
                Q4_K_M on 8 GB VRAM.
            max_tokens: Optional cap on output tokens, mapped to Ollama's
                ``num_predict`` option. If ``None``, the model uses its own
                default.

        Returns:
            The textual content of the assistant message.

        Raises:
            ollama.ResponseError: If the server returns an error after all
                retries are exhausted.
            requests.exceptions.RequestException: If the HTTP layer keeps
                failing after all retries.
            TimeoutError: If the call keeps timing out after all retries.
            RuntimeError: If the response payload does not contain the
                expected ``message.content`` field.
        """
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        options: dict[str, Any] = {
            "temperature": temperature,
            "num_ctx": num_ctx,
        }
        if max_tokens is not None:
            options["num_predict"] = max_tokens

        attempts = self.max_retries + 1
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                response = self._client.chat(
                    model=self.model,
                    messages=messages,
                    options=options,
                )
                return _extract_content(response)
            except (
                requests.exceptions.RequestException,
                ollama.ResponseError,
                TimeoutError,
            ) as exc:
                last_error = exc
                if attempt >= attempts:
                    _LOGGER.error(
                        "LLM chat falló tras %d intentos (model=%s): %s",
                        attempts,
                        self.model,
                        exc,
                    )
                    raise
                delay = min(_BACKOFF_CAP_S, _BACKOFF_BASE ** (attempt - 1))
                _LOGGER.warning(
                    "LLM chat intento %d/%d falló (model=%s): %s. "
                    "Reintentando en %.1fs.",
                    attempt,
                    attempts,
                    self.model,
                    exc,
                    delay,
                )
                time.sleep(delay)

        # Defensive: the loop above either returns or raises. This line is
        # only reachable if ``attempts`` is non-positive, which we prevent in
        # ``__init__`` by clamping ``max_retries`` to ``>= 0``.
        raise RuntimeError(  # pragma: no cover
            f"LLM chat exhausted retries without raising; last_error={last_error!r}"
        )


def _extract_content(response: Any) -> str:
    """Pull the assistant content out of an Ollama chat response.

    Args:
        response: The object returned by :meth:`ollama.Client.chat`. Either a
            ``ChatResponse`` (attribute access) or a plain mapping (dict
            access), depending on the ``ollama`` library version.

    Returns:
        The content string of the assistant message.

    Raises:
        RuntimeError: If the response does not expose a ``message.content``
            field.
    """
    message: Any = None
    if hasattr(response, "message"):
        message = response.message
    elif isinstance(response, dict):
        message = response.get("message")

    if message is None:
        raise RuntimeError(
            f"Unexpected Ollama response shape (no 'message'): {response!r}"
        )

    if hasattr(message, "content"):
        content = message.content
    elif isinstance(message, dict):
        content = message.get("content")
    else:
        content = None

    if content is None:
        raise RuntimeError(
            f"Unexpected Ollama response shape (no 'content'): {response!r}"
        )
    return str(content)


# ---------------------------------------------------------------------------
# JSON parsing helper
# ---------------------------------------------------------------------------


def parse_json_response(raw: str) -> dict:
    """Parse a JSON object from a (possibly fenced) LLM response string.

    Qwen 2.5 occasionally wraps JSON in ```json ... ``` fences even when
    explicitly told not to. This helper:

    1. Strips an optional ```json / ``` opening fence and ``` closing fence.
    2. Tries :func:`json.loads` on the cleaned string.
    3. On failure, falls back to extracting the first ``{...}`` substring and
       loading that.

    Args:
        raw: The raw text returned by the LLM.

    Returns:
        The decoded JSON object as a ``dict``.

    Raises:
        ValueError: If no valid JSON object can be extracted from ``raw``.
    """
    cleaned = re.sub(
        r"^```(?:json)?\s*|\s*```$",
        "",
        raw.strip(),
        flags=re.MULTILINE,
    )
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError as inner:
                raise ValueError(
                    f"Invalid JSON in LLM response: {inner}"
                ) from inner
        raise ValueError(f"Invalid JSON in LLM response: {exc}") from exc


__all__ = ["LLMClient", "parse_json_response"]
