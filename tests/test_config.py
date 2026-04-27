"""Unit tests for agents._config.

Covers: load_config structure and caching, get_agent_config happy path and
unknown-key error.
"""

from __future__ import annotations

from typing import Any

import pytest


@pytest.fixture(autouse=True)
def reset_config_cache():
    """Reset the _CACHE singleton before and after each test.

    Without this, the first test that calls load_config() would poison the
    cache for all subsequent tests.  This is the SAM bug referenced in the
    test spec.
    """
    import agents._config as cfg_mod
    cfg_mod._CACHE = None
    yield
    cfg_mod._CACHE = None


class TestLoadConfigReturnShape:
    def test_load_config_returns_combined_dict(self):
        """load_config() must return a dict with keys global, agents, env."""
        from agents._config import load_config

        cfg = load_config()
        assert isinstance(cfg, dict)
        assert "global" in cfg, "Missing 'global' key in load_config() output"
        assert "agents" in cfg, "Missing 'agents' key in load_config() output"
        assert "env" in cfg, "Missing 'env' key in load_config() output"


class TestLoadConfigCaching:
    def test_load_config_caches(self):
        """Consecutive calls to load_config() must return the same object."""
        from agents._config import load_config

        a = load_config()
        b = load_config()
        assert a is b, "load_config() returned two different dict instances (caching broken)"


class TestGetAgentConfig:
    def test_get_agent_config_known(self):
        """get_agent_config('L3_extractor') must return a non-empty dict."""
        from agents._config import get_agent_config

        cfg: Any = get_agent_config("L3_extractor")
        assert isinstance(cfg, dict)
        assert len(cfg) > 0, "L3_extractor config block is empty"

    def test_get_agent_config_unknown_raises(self):
        """get_agent_config with an unknown id must raise KeyError mentioning the id."""
        from agents._config import get_agent_config

        unknown_id = "L99_nonexistent"
        with pytest.raises(KeyError) as exc_info:
            get_agent_config(unknown_id)

        # The agent id must appear in the error message so the caller knows
        # which key is missing.
        assert unknown_id in str(exc_info.value), (
            f"KeyError message does not mention the unknown agent id {unknown_id!r}"
        )
