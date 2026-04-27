"""Centralized configuration loader for the LUCA pipeline.

This module is the single entry point for any agent or script that needs to
read configuration. It merges three sources into one cached dict:

* ``config.yaml`` at the project root (global config, sacred zone).
* ``config/agents.json`` (per-agent pipeline config).
* ``.env`` at the project root (secrets, loaded via ``python-dotenv``).

The loader is intentionally dependency-light: it does not import
:mod:`agents._logging` to avoid circular imports during early bootstrap. It
also does not mutate any of the source files.

Note:
    ``load_dotenv`` is called with ``override=False`` so that real environment
    variables (e.g. those exported by the user's shell or CI) take precedence
    over the ``.env`` file. This avoids a class of subtle bugs we hit in SAM,
    where stale ``.env`` values silently shadowed CI secrets.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import os
import yaml
from dotenv import dotenv_values, load_dotenv

# ---------------------------------------------------------------------------
# Constants (public)
# ---------------------------------------------------------------------------

#: Project root, derived from this file's location (``agents/_config.py``).
PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Constants (internal)
# ---------------------------------------------------------------------------

_GLOBAL_CONFIG_PATH: Path = PROJECT_ROOT / "config.yaml"
_AGENTS_CONFIG_PATH: Path = PROJECT_ROOT / "config" / "agents.json"
_DOTENV_PATH: Path = PROJECT_ROOT / ".env"

#: Cache for :func:`load_config`. ``None`` means "not loaded yet".
_CACHE: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_global() -> dict[str, Any]:
    """Read and parse ``config.yaml``.

    Returns:
        The parsed YAML content as a dict (empty dict if the file is empty).

    Raises:
        FileNotFoundError: If ``config.yaml`` does not exist at the expected
            location.
    """
    if not _GLOBAL_CONFIG_PATH.is_file():
        raise FileNotFoundError(
            f"Global config not found at {_GLOBAL_CONFIG_PATH}. "
            "This file is required and is part of the project's sacred zone."
        )
    with _GLOBAL_CONFIG_PATH.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        raise ValueError(
            f"{_GLOBAL_CONFIG_PATH} must contain a YAML mapping at the top "
            f"level, got {type(data).__name__}."
        )
    return data


def _load_agents() -> dict[str, Any]:
    """Read and parse ``config/agents.json``, stripping the ``_note`` key.

    Returns:
        The ``agents`` sub-mapping with internal documentation keys removed.

    Raises:
        FileNotFoundError: If ``config/agents.json`` does not exist.
        KeyError: If the JSON file does not contain a top-level ``agents`` key.
    """
    if not _AGENTS_CONFIG_PATH.is_file():
        raise FileNotFoundError(
            f"Agents config not found at {_AGENTS_CONFIG_PATH}. "
            "Expected a JSON file with an 'agents' top-level key."
        )
    with _AGENTS_CONFIG_PATH.open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    if "agents" not in data:
        raise KeyError(
            f"{_AGENTS_CONFIG_PATH} is missing the required 'agents' key."
        )
    agents = dict(data["agents"])
    agents.pop("_note", None)
    return agents


def _load_env() -> dict[str, str]:
    """Load ``.env`` into ``os.environ`` (no override) and return its contents.

    Returns:
        A dict of the variables defined in ``.env``. Values already present in
        the real environment win over ``.env`` because of ``override=False``;
        the returned dict reflects the *effective* value seen by the process.
        If ``.env`` does not exist, an empty dict is returned.
    """
    if not _DOTENV_PATH.is_file():
        return {}
    load_dotenv(dotenv_path=_DOTENV_PATH, override=False)
    raw = dotenv_values(_DOTENV_PATH)
    effective: dict[str, str] = {}
    for key in raw:
        value = os.environ.get(key, raw[key])
        if value is not None:
            effective[key] = value
    return effective


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_config() -> dict[str, Any]:
    """Load and return the merged LUCA configuration.

    The result is cached after the first call: subsequent calls return the
    same dict instance, so callers can rely on identity (``is``) checks and
    avoid re-parsing files on hot paths.

    Returns:
        A dict with three top-level keys:

        * ``"global"`` — content of ``config.yaml``.
        * ``"agents"`` — content of ``config/agents.json``'s ``agents`` block,
          with the ``_note`` key removed.
        * ``"env"`` — variables loaded from ``.env`` (effective values, after
          merging with ``os.environ`` without override).

    Raises:
        FileNotFoundError: If ``config.yaml`` or ``config/agents.json`` is
            missing.
    """
    global _CACHE
    if _CACHE is None:
        _CACHE = {
            "global": _load_global(),
            "agents": _load_agents(),
            "env": _load_env(),
        }
    return _CACHE


def get_agent_config(agent_id: str) -> dict[str, Any]:
    """Return the config block for a single agent.

    Args:
        agent_id: The agent identifier as it appears in ``config/agents.json``
            (e.g. ``"L3_extractor"``, ``"L4_qualitative"``).

    Returns:
        The dict of settings for that agent.

    Raises:
        KeyError: If ``agent_id`` is not defined in ``config/agents.json``.
    """
    agents = load_config()["agents"]
    if agent_id not in agents:
        available = ", ".join(sorted(agents)) or "(none)"
        raise KeyError(
            f"Unknown agent_id {agent_id!r}. Available agents: {available}."
        )
    return agents[agent_id]


def get_env(name: str, default: str | None = None) -> str | None:
    """Return an environment variable, falling back to ``default``.

    The lookup order is:

    1. ``os.environ`` (which already includes ``.env`` after :func:`load_config`).
    2. The ``env`` block of the cached config (defensive: covers the case
       where :func:`load_config` was called and the variable existed only in
       ``.env``, in which case it is also in ``os.environ`` thanks to
       ``load_dotenv``, but we double-check here to remain robust).
    3. ``default``.

    Args:
        name: The variable name to look up.
        default: Value to return if the variable is not set anywhere.

    Returns:
        The variable's string value, or ``default`` if not found.
    """
    if name in os.environ:
        return os.environ[name]
    if _CACHE is not None:
        env_block: dict[str, str] = _CACHE.get("env", {})
        if name in env_block:
            return env_block[name]
    return default


__all__ = [
    "PROJECT_ROOT",
    "load_config",
    "get_agent_config",
    "get_env",
]
