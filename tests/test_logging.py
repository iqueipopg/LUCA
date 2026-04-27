"""Unit tests for agents._logging.get_logger.

Covers: return type, idempotency (no handler duplication), and
LUCA_LOG_LEVEL env override.
"""

from __future__ import annotations

import logging


class TestGetLoggerReturnType:
    def test_get_logger_returns_logger(self, tmp_logs_dir):
        """get_logger should return a stdlib logging.Logger instance."""
        from agents._logging import get_logger

        logger = get_logger("test_luca.return_type")
        assert isinstance(logger, logging.Logger)


class TestGetLoggerIdempotency:
    def test_get_logger_idempotent(self, tmp_logs_dir):
        """Calling get_logger twice with the same name must not duplicate handlers.

        Each call should produce at most one StreamHandler and one
        RotatingFileHandler marked with _luca_managed=True.
        """
        from logging.handlers import RotatingFileHandler

        from agents._logging import _HANDLER_MARKER, get_logger

        name = "test_luca.idempotent"
        _ = get_logger(name)
        _ = get_logger(name)

        logger = logging.getLogger(name)
        managed = [h for h in logger.handlers if getattr(h, _HANDLER_MARKER, False)]

        stream_count = sum(
            1 for h in managed
            if isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler)
        )
        file_count = sum(1 for h in managed if isinstance(h, RotatingFileHandler))

        assert stream_count <= 1, (
            f"Expected at most 1 managed StreamHandler, found {stream_count}"
        )
        assert file_count <= 1, (
            f"Expected at most 1 managed RotatingFileHandler, found {file_count}"
        )


class TestGetLoggerEnvOverride:
    def test_log_level_env_override(self, tmp_logs_dir, monkeypatch):
        """LUCA_LOG_LEVEL=DEBUG must result in a logger with level DEBUG."""
        monkeypatch.setenv("LUCA_LOG_LEVEL", "DEBUG")

        from agents._logging import get_logger

        logger = get_logger("test_luca.env_override")
        assert logger.level == logging.DEBUG, (
            f"Expected DEBUG ({logging.DEBUG}), got {logger.level}"
        )
