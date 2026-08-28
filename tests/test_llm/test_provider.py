"""Tests for the pluggable LLM provider adapter.

Numen talks to any OpenAI-compatible endpoint (OpenAI, Azure, OpenRouter,
Ollama, vLLM, LiteLLM). These tests pin the resolution rules that make
bring-your-own-LLM work for self-hosters.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.llm.provider import (
    LLMConfigurationError,
    build_client_kwargs,
    resolve_api_key,
    resolve_base_url,
    resolve_chat_model,
    resolve_embedding_dimensions,
    resolve_embedding_model,
)


def _settings(**overrides):
    """A settings stub carrying only the LLM-relevant fields."""
    base = {
        "llm_api_key": "",
        "llm_base_url": "",
        "llm_model": "",
        "embedding_model": "",
        "embedding_dimensions": 0,
        "openai_api_key": "",
        "openai_model": "",
    }
    base.update(overrides)
    return MagicMock(**base)


# --- base URL resolution -------------------------------------------------


def test_base_url_defaults_to_none_for_openai():
    """With no override, the SDK default (api.openai.com) is used."""
    assert resolve_base_url(_settings(llm_api_key="sk-test")) is None


def test_base_url_override_is_used():
    """LLM_BASE_URL points Numen at any OpenAI-compatible server."""
    s = _settings(llm_api_key="x", llm_base_url="http://localhost:11434/v1")
    assert resolve_base_url(s) == "http://localhost:11434/v1"


def test_base_url_strips_trailing_slash():
    """A trailing slash would produce a double slash against the SDK paths."""
    s = _settings(llm_api_key="x", llm_base_url="http://localhost:8000/v1/")
    assert resolve_base_url(s) == "http://localhost:8000/v1"


# --- API key resolution --------------------------------------------------


def test_api_key_prefers_llm_api_key():
    s = _settings(llm_api_key="new-style", openai_api_key="legacy")
    assert resolve_api_key(s) == "new-style"


def test_api_key_falls_back_to_openai_api_key():
    """OPENAI_API_KEY keeps working so existing installs don't break."""
    s = _settings(openai_api_key="legacy")
    assert resolve_api_key(s) == "legacy"


def test_api_key_placeholder_for_keyless_local_server():
    """Ollama and vLLM need no key, but the OpenAI SDK requires a non-empty one."""
    s = _settings(llm_base_url="http://localhost:11434/v1")
    assert resolve_api_key(s) == "not-needed"


def test_api_key_missing_without_base_url_raises():
    """A hosted provider with no key is a misconfiguration, not a default."""
    with pytest.raises(LLMConfigurationError, match="LLM_API_KEY"):
        resolve_api_key(_settings())


# --- model resolution ----------------------------------------------------


def test_chat_model_prefers_llm_model():
    s = _settings(llm_model="llama3.3", openai_model="gpt-4o")
    assert resolve_chat_model(s) == "llama3.3"


def test_chat_model_falls_back_to_openai_model():
    assert resolve_chat_model(_settings(openai_model="gpt-4o")) == "gpt-4o"


def test_chat_model_has_a_default():
    """A self-hoster who sets only an API key still gets a working model."""
    assert resolve_chat_model(_settings()) != ""


def test_embedding_model_is_configurable():
    s = _settings(embedding_model="nomic-embed-text")
    assert resolve_embedding_model(s) == "nomic-embed-text"


def test_embedding_model_has_a_default():
    assert resolve_embedding_model(_settings()) == "text-embedding-3-small"


def test_embedding_dimensions_default_matches_graph_index():
    """The FalkorDB vector index is built at this width."""
    assert resolve_embedding_dimensions(_settings()) == 1536


def test_embedding_dimensions_override():
    """Local embedding models have different widths (e.g. nomic = 768)."""
    assert resolve_embedding_dimensions(_settings(embedding_dimensions=768)) == 768


# --- client kwargs -------------------------------------------------------


def test_build_client_kwargs_openai_shape():
    s = _settings(llm_api_key="sk-test")
    assert build_client_kwargs(s) == {"api_key": "sk-test"}


def test_build_client_kwargs_includes_base_url_when_set():
    s = _settings(llm_api_key="sk-test", llm_base_url="https://openrouter.ai/api/v1")
    kwargs = build_client_kwargs(s)
    assert kwargs["api_key"] == "sk-test"
    assert kwargs["base_url"] == "https://openrouter.ai/api/v1"


def test_build_client_kwargs_for_ollama_needs_no_key():
    s = _settings(llm_base_url="http://localhost:11434/v1")
    kwargs = build_client_kwargs(s)
    assert kwargs["base_url"] == "http://localhost:11434/v1"
    assert kwargs["api_key"] == "not-needed"


# --- integration with the real settings object ---------------------------


def test_real_settings_expose_llm_fields():
    """The Settings model must carry the adapter's fields."""
    from src.config import settings

    for field in (
        "llm_api_key",
        "llm_base_url",
        "llm_model",
        "embedding_model",
        "embedding_dimensions",
    ):
        assert hasattr(settings, field), f"Settings is missing {field}"


def test_client_uses_provider_kwargs():
    """get_client must route through the adapter, not construct OpenAI directly."""
    import src.llm.client as client_mod

    original = client_mod._client
    client_mod._client = None
    try:
        with patch.object(client_mod.settings, "llm_api_key", "sk-test"), patch.object(
            client_mod.settings, "llm_base_url", "http://localhost:11434/v1"
        ), patch("src.llm.client.openai.AsyncOpenAI") as mock_cls:
            client_mod.get_client()
            _, kwargs = mock_cls.call_args
            assert kwargs["base_url"] == "http://localhost:11434/v1"
    finally:
        client_mod._client = original
