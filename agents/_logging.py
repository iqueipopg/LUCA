"""Centralized logging utilities for the LUCA pipeline.

This module exposes a single public function, :func:`get_logger`, which all
agents and scripts in the pipeline should use to obtain a configured
:class:`logging.Logger`. The logger writes human-readable records to stderr
and rotates them to a file on disk (``logs/luca.log`` by default).

Configuration is read from ``config.yaml`` (key ``logging``) located at the
project root. Defaults are applied for any missing keys so that the module is
usable even with a minimal configuration. The log level can be overridden at
runtime through the ``LUCA_LOG_LEVEL`` environment variable, which is useful
for plumbing a ``--verbose`` flag from the CLI without touching the config
file.

Note:
    This is a temporary self-contained config reader. It will be replaced by
    the dedicated config module (T0.3) as soon as that lands.
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Project root, derived from this file's location (agents/_logging.py).
_PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

#: Path to the global YAML config file.
_CONFIG_PATH: Path = _PROJECT_ROOT / "config.yaml"

#: Environment variable that overrides the configured log level.
_ENV_LEVEL_VAR: str = "LUCA_LOG_LEVEL"

#: Default values used when ``config.yaml::logging`` is missing entries.
_DEFAULTS: dict[str, Any] = {
    "level": "INFO",
    "file": "logs/luca.log",
    "rotation_mb": 10,
}

#: Common format for both stream and file handlers.
_LOG_FORMAT: str = (
    "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
)
_DATE_FORMAT: str = "%Y-%m-%d %H:%M:%S"

#: Sentinel attribute used to mark handlers installed by this module so we
#: can detect them on subsequent calls and remain idempotent.
_HANDLER_MARKER: str = "_luca_managed"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _load_logging_config() -> dict[str, Any]:
    """Load the ``logging`` section from ``config.yaml``.

    Returns:
        A dict with keys ``level``, ``file`` and ``rotation_mb``. Missing keys
        are filled in with values from :data:`_DEFAULTS`. If the config file
        does not exist or cannot be parsed, all defaults are returned.
    """
    cfg: dict[str, Any] = dict(_DEFAULTS)

    if not _CONFIG_PATH.is_file():
        return cfg

    try:
        with _CONFIG_PATH.open("r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
    except (OSError, yaml.YAMLError):
        # Fall back to defaults; we cannot log this yet because the logger
        # itself is being built. Silently degrading is acceptable here.
        return cfg

    section = raw.get("logging") or {}
    if isinstance(section, dict):
        for key in _DEFAULTS:
            if key in section and section[key] is not None:
                cfg[key] = section[key]

    return cfg


def _resolve_level(configured: str) -> int:
    """Resolve the effective log level.

    The ``LUCA_LOG_LEVEL`` environment variable, when set, takes precedence
    over the value coming from the config file.

    Args:
        configured: Level string from the config file (e.g. ``"INFO"``).

    Returns:
        A numeric level usable with :meth:`logging.Logger.setLevel`. Falls
        back to :data:`logging.INFO` if neither value can be parsed.
    """
    candidate = os.environ.get(_ENV_LEVEL_VAR, configured)
    if not isinstance(candidate, str):
        return logging.INFO

    level = logging.getLevelName(candidate.strip().upper())
    if isinstance(level, int):
        return level
    return logging.INFO


def _resolve_log_path(file_value: str) -> Path:
    """Resolve the log file path, anchoring relative paths to the project root.

    Args:
        file_value: Path string read from the config file.

    Returns:
        An absolute :class:`~pathlib.Path` pointing to the log file.
    """
    path = Path(file_value)
    if not path.is_absolute():
        path = _PROJECT_ROOT / path
    return path


def _has_managed_handler(logger: logging.Logger, kind: type) -> bool:
    """Return True if ``logger`` already has a managed handler of ``kind``."""
    return any(
        getattr(h, _HANDLER_MARKER, False) and isinstance(h, kind)
        for h in logger.handlers
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger for the given name.

    The logger is wired with two handlers managed by this module:

    * A :class:`logging.StreamHandler` writing to ``stderr``.
    * A :class:`logging.handlers.RotatingFileHandler` writing to the file
      configured under ``config.yaml::logging::file`` (``logs/luca.log`` by
      default), with a ``maxBytes`` derived from ``rotation_mb``.

    The function is idempotent: calling it more than once with the same
    ``name`` does not duplicate handlers, so log records are not emitted
    multiple times.

    Args:
        name: Logger name, typically ``__name__`` from the calling module.

    Returns:
        A :class:`logging.Logger` instance ready to use.
    """
    cfg = _load_logging_config()
    level = _resolve_level(str(cfg["level"]))

    logger = logging.getLogger(name)
    logger.setLevel(level)
    # Avoid double-emission via the root logger if it ends up configured too.
    logger.propagate = False

    formatter = logging.Formatter(fmt=_LOG_FORMAT, datefmt=_DATE_FORMAT)

    # --- stderr handler ---------------------------------------------------
    if not _has_managed_handler(logger, logging.StreamHandler):
        stream_handler = logging.StreamHandler(stream=sys.stderr)
        stream_handler.setLevel(level)
        stream_handler.setFormatter(formatter)
        setattr(stream_handler, _HANDLER_MARKER, True)
        logger.addHandler(stream_handler)
    else:
        # Keep existing managed handlers in sync with the (possibly new) level.
        for h in logger.handlers:
            if getattr(h, _HANDLER_MARKER, False) and isinstance(
                h, logging.StreamHandler
            ) and not isinstance(h, RotatingFileHandler):
                h.setLevel(level)

    # --- rotating file handler -------------------------------------------
    log_path = _resolve_log_path(str(cfg["file"]))
    log_path.parent.mkdir(parents=True, exist_ok=True)

    if not _has_managed_handler(logger, RotatingFileHandler):
        try:
            rotation_mb = float(cfg["rotation_mb"])
        except (TypeError, ValueError):
            rotation_mb = float(_DEFAULTS["rotation_mb"])
        max_bytes = max(1, int(rotation_mb * 1024 * 1024))

        file_handler = RotatingFileHandler(
            filename=str(log_path),
            maxBytes=max_bytes,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        setattr(file_handler, _HANDLER_MARKER, True)
        logger.addHandler(file_handler)
    else:
        for h in logger.handlers:
            if getattr(h, _HANDLER_MARKER, False) and isinstance(
                h, RotatingFileHandler
            ):
                h.setLevel(level)

    return logger


__all__ = ["get_logger"]
