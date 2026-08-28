"""Tests for LLM (OpenAI) client wrapper."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.llm.client import (
    LLMResponse,
    call_llm,
    call_llm_with_trace,
    get_client,
)


def test_llm_response_dataclass():
    """LLMResponse should hold text and metadata."""
    resp = LLMResponse(
        text="Summary of changes",
        model="gpt-4o",
        input_token_count=100,
        output_token_count=50,
        latency_ms=450,
    )
    assert resp.text == "Summary of changes"
    assert resp.model == "gpt-4o"
    assert resp.input_token_count == 100
    assert resp.output_token_count == 50
    assert resp.latency_ms == 450


def test_llm_response_defaults():
    """Default values should be set for optional fields."""
    resp = LLMResponse(text="hello")
    assert resp.model == ""
    assert resp.input_token_count == 0
    assert resp.output_token_count == 0
    assert resp.latency_ms == 0


def test_get_client_requires_api_key():
    """get_client should raise when neither a key nor an endpoint is configured."""
    import src.llm.client as client_mod

    original = client_mod._client
    client_mod._client = None

    with patch.object(client_mod.settings, "llm_api_key", ""), patch.object(
        client_mod.settings, "llm_base_url", ""
    ), patch.object(client_mod.settings, "openai_api_key", ""):
        with pytest.raises(RuntimeError, match="LLM_API_KEY"):
            get_client()

    client_mod._client = original


def test_get_client_creates_singleton():
    """get_client should return the same client on subsequent calls."""
    import src.llm.client as client_mod

    original = client_mod._client
    client_mod._client = None

    with patch.object(client_mod.settings, "llm_api_key", "test-key"), patch.object(
        client_mod.settings, "llm_base_url", ""
    ):
        with patch("src.llm.client.openai.AsyncOpenAI") as mock_cls:
            mock_instance = MagicMock()
            mock_cls.return_value = mock_instance

            client1 = get_client()
            client2 = get_client()

            assert client1 is client2
            mock_cls.assert_called_once_with(api_key="test-key")

    client_mod._client = original


def test_get_client_honours_legacy_openai_key():
    """Existing installs setting only OPENAI_API_KEY must keep working."""
    import src.llm.client as client_mod

    original = client_mod._client
    client_mod._client = None

    with patch.object(client_mod.settings, "llm_api_key", ""), patch.object(
        client_mod.settings, "llm_base_url", ""
    ), patch.object(client_mod.settings, "openai_api_key", "legacy-key"):
        with patch("src.llm.client.openai.AsyncOpenAI") as mock_cls:
            get_client()
            mock_cls.assert_called_once_with(api_key="legacy-key")

    client_mod._client = original


@pytest.mark.asyncio
async def test_call_llm_with_trace_success():
    """call_llm_with_trace should return an LLMResponse on success."""
    import src.llm.client as client_mod

    mock_client = AsyncMock()

    # Build mock OpenAI response
    mock_message = MagicMock()
    mock_message.content = "PR summary here"

    mock_choice = MagicMock()
    mock_choice.message = mock_message

    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 150
    mock_usage.completion_tokens = 75

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.model = "gpt-4o"
    mock_response.usage = mock_usage

    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    original = client_mod._client
    client_mod._client = mock_client

    try:
        result = await call_llm_with_trace(
            system="You are helpful",
            user="Summarize this PR",
        )

        assert isinstance(result, LLMResponse)
        assert result.text == "PR summary here"
        assert result.model == "gpt-4o"
        assert result.input_token_count == 150
        assert result.output_token_count == 75
        assert result.latency_ms >= 0
    finally:
        client_mod._client = original


@pytest.mark.asyncio
async def test_call_llm_returns_text():
    """call_llm should return just the text string."""
    import src.llm.client as client_mod

    mock_client = AsyncMock()

    mock_message = MagicMock()
    mock_message.content = "Just text"

    mock_choice = MagicMock()
    mock_choice.message = mock_message

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.model = "gpt-4o"
    mock_response.usage = None

    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    original = client_mod._client
    client_mod._client = mock_client

    try:
        result = await call_llm(system="system", user="user")
        assert result == "Just text"
    finally:
        client_mod._client = original


@pytest.mark.asyncio
async def test_call_llm_retries_on_rate_limit():
    """Should retry on RateLimitError and succeed on second attempt."""
    import openai

    import src.llm.client as client_mod

    mock_client = AsyncMock()

    mock_message = MagicMock()
    mock_message.content = "Success after retry"

    mock_choice = MagicMock()
    mock_choice.message = mock_message

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.model = "gpt-4o"
    mock_response.usage = None

    rate_limit_response = MagicMock()
    rate_limit_response.status_code = 429
    rate_limit_response.headers = {}
    rate_limit_response.json.return_value = {}
    rate_limit_error = openai.RateLimitError(
        message="Rate limited",
        response=rate_limit_response,
        body=None,
    )

    mock_client.chat.completions.create = AsyncMock(side_effect=[rate_limit_error, mock_response])

    original = client_mod._client
    client_mod._client = mock_client

    try:
        with patch("src.llm.client.asyncio.sleep", new_callable=AsyncMock):
            result = await call_llm_with_trace(system="sys", user="usr")

        assert result.text == "Success after retry"
        assert mock_client.chat.completions.create.call_count == 2
    finally:
        client_mod._client = original


@pytest.mark.asyncio
async def test_call_llm_raises_after_3_retries():
    """Should raise RuntimeError after 3 failed attempts."""
    import openai

    import src.llm.client as client_mod

    mock_client = AsyncMock()

    rate_limit_response = MagicMock()
    rate_limit_response.status_code = 429
    rate_limit_response.headers = {}
    rate_limit_response.json.return_value = {}
    rate_limit_error = openai.RateLimitError(
        message="Rate limited",
        response=rate_limit_response,
        body=None,
    )

    mock_client.chat.completions.create = AsyncMock(side_effect=rate_limit_error)

    original = client_mod._client
    client_mod._client = mock_client

    try:
        with patch("src.llm.client.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(RuntimeError, match="failed after 3 attempts"):
                await call_llm_with_trace(system="sys", user="usr")

        assert mock_client.chat.completions.create.call_count == 3
    finally:
        client_mod._client = original


@pytest.mark.asyncio
async def test_call_llm_no_content_raises():
    """Should raise ValueError if response has no text content."""
    import src.llm.client as client_mod

    mock_client = AsyncMock()

    mock_message = MagicMock()
    mock_message.content = None  # No content

    mock_choice = MagicMock()
    mock_choice.message = mock_message

    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_response.model = "gpt-4o"
    mock_response.usage = None

    mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

    original = client_mod._client
    client_mod._client = mock_client

    try:
        with pytest.raises(ValueError, match="no text content"):
            await call_llm_with_trace(system="sys", user="usr")
    finally:
        client_mod._client = original
