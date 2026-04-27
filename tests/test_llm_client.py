"""Unit tests for agents._llm_client.

All Ollama network calls are mocked — no GPU/Ollama server required.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def reset_config_cache():
    """Keep _config cache clean between tests."""
    import agents._config as cfg_mod
    cfg_mod._CACHE = None
    yield
    cfg_mod._CACHE = None


class TestLLMClientDefaults:
    def test_client_resolves_defaults_from_config(self):
        """LLMClient() with no args must populate host, model, timeout_s."""
        from agents._llm_client import LLMClient

        with patch("ollama.Client"):
            client = LLMClient()

        assert client.host is not None and client.host != ""
        assert client.model is not None and client.model != ""
        assert client.timeout_s is not None and client.timeout_s > 0


class TestLLMClientChat:
    def test_chat_calls_ollama_with_correct_options(self, mock_ollama_chat):
        """chat() must forward temperature, num_ctx, and num_predict to Ollama."""
        from agents._llm_client import LLMClient

        mock_ollama_chat.return_value = {"message": {"content": "ok"}}

        client = LLMClient()
        client.chat(
            system="sys",
            user="user",
            temperature=0.7,
            num_ctx=4096,
            max_tokens=512,
        )

        call_kwargs = mock_ollama_chat.call_args
        options = call_kwargs.kwargs.get("options") or call_kwargs[1].get("options") or call_kwargs[0][2] if call_kwargs[0] and len(call_kwargs[0]) > 2 else {}

        # Retrieve options from however they were passed
        if call_kwargs.kwargs:
            options = call_kwargs.kwargs.get("options", {})
        else:
            options = call_kwargs[1].get("options", {})

        assert options.get("temperature") == 0.7, f"temperature not forwarded, got options={options}"
        assert options.get("num_ctx") == 4096, f"num_ctx not forwarded, got options={options}"
        assert options.get("num_predict") == 512, f"num_predict not forwarded, got options={options}"

    def test_chat_returns_content_string(self, mock_ollama_chat):
        """chat() must extract and return message.content as a plain string."""
        from agents._llm_client import LLMClient

        mock_ollama_chat.return_value = {"message": {"content": "hello world"}}

        client = LLMClient()
        result = client.chat(system="sys", user="user")

        assert result == "hello world"
        assert isinstance(result, str)


class TestParseJsonResponse:
    def test_parse_json_response_strips_fences(self):
        """parse_json_response must handle ```json ... ``` fences from Qwen."""
        from agents._llm_client import parse_json_response

        raw = "```json\n{}\n```"
        result = parse_json_response(raw)
        assert result == {}

    def test_parse_json_response_strips_fences_with_content(self):
        """parse_json_response must correctly parse fenced JSON with content."""
        from agents._llm_client import parse_json_response

        raw = '```json\n{"key": "value", "number": 42}\n```'
        result = parse_json_response(raw)
        assert result == {"key": "value", "number": 42}

    def test_parse_json_response_invalid_raises(self):
        """parse_json_response must raise ValueError when no valid JSON exists."""
        from agents._llm_client import parse_json_response

        with pytest.raises(ValueError):
            parse_json_response("this is not json at all")
