"""Tests for the agent's HTTP surfaces: one-shot ask and OpenAI compatibility."""

import json
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.agent.principal import Principal, Surface
from src.api import routes_agent
from src.shared.database import get_db


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(routes_agent.router)
    app.state.limiter = routes_agent.limiter
    app.dependency_overrides[get_db] = lambda: AsyncMock()

    principal = Principal(
        org_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        email="caller@example.com",
        surface=Surface.API,
    )
    app.dependency_overrides[routes_agent.principal_from_api_key] = lambda: principal
    return TestClient(app)


def test_ask_returns_the_answer(client):
    with patch("src.api.routes_agent.run_agent_to_text", new=AsyncMock(return_value="Three tasks close Friday.")):
        response = client.post("/api/ask", json={"message": "what is due?"})

    assert response.status_code == 200
    assert response.json()["answer"] == "Three tasks close Friday."


def test_ask_rejects_an_empty_message(client):
    assert client.post("/api/ask", json={"message": "   "}).status_code == 422


def test_chat_completions_returns_openai_shape(client):
    with patch("src.api.routes_agent.run_agent_to_text", new=AsyncMock(return_value="Two pull requests are stale.")):
        response = client.post(
            "/api/v1/chat/completions",
            json={"model": "numen", "messages": [{"role": "user", "content": "anything stale?"}]},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["role"] == "assistant"
    assert body["choices"][0]["message"]["content"] == "Two pull requests are stale."
    assert body["choices"][0]["finish_reason"] == "stop"
    assert "usage" in body


def test_chat_completions_never_asks_the_client_to_run_tools(client):
    """Numen runs its own tools, so the loop is collapsed before responding."""
    with patch("src.api.routes_agent.run_agent_to_text", new=AsyncMock(return_value="done")):
        body = client.post(
            "/api/v1/chat/completions",
            json={"model": "numen", "messages": [{"role": "user", "content": "hi"}]},
        ).json()

    assert body["choices"][0]["finish_reason"] != "tool_calls"
    assert "tool_calls" not in body["choices"][0]["message"]


def test_chat_completions_passes_prior_turns_as_history(client):
    captured = {}

    async def _capture(_db, _principal, user_input, history=None):
        captured["input"] = user_input
        captured["history"] = history
        return "ok"

    with patch("src.api.routes_agent.run_agent_to_text", new=_capture):
        client.post(
            "/api/v1/chat/completions",
            json={
                "model": "numen",
                "messages": [
                    {"role": "user", "content": "first"},
                    {"role": "assistant", "content": "answer"},
                    {"role": "user", "content": "second"},
                ],
            },
        )

    assert captured["input"] == "second"
    assert captured["history"] == [("user", "first"), ("assistant", "answer")]


def test_chat_completions_requires_a_user_message(client):
    response = client.post(
        "/api/v1/chat/completions",
        json={"model": "numen", "messages": [{"role": "assistant", "content": "hello"}]},
    )
    assert response.status_code == 400


def test_chat_completions_streams_openai_chunks(client):
    from src.agent.events import DoneEvent, TokenEvent

    async def _events(*_args, **_kwargs):
        yield TokenEvent(content="Two ")
        yield TokenEvent(content="stale.")
        yield DoneEvent()

    with patch("src.api.routes_agent.run_agent", new=_events):
        response = client.post(
            "/api/v1/chat/completions",
            json={"model": "numen", "messages": [{"role": "user", "content": "hi"}], "stream": True},
        )

    assert response.status_code == 200
    frames = [line for line in response.text.splitlines() if line.startswith("data: ")]
    assert frames[-1] == "data: [DONE]"

    payloads = [json.loads(f[6:]) for f in frames[:-1]]
    assert all(p["object"] == "chat.completion.chunk" for p in payloads)
    text = "".join(p["choices"][0]["delta"].get("content", "") for p in payloads)
    assert text == "Two stale."


def test_ask_streams_native_events_when_requested(client):
    from src.agent.events import DoneEvent, StatusEvent, TokenEvent

    async def _events(*_args, **_kwargs):
        yield StatusEvent(content="Looking up tasks")
        yield TokenEvent(content="Two.")
        yield DoneEvent()

    with patch("src.api.routes_agent.run_agent", new=_events):
        response = client.post("/api/ask", json={"message": "hi", "stream": True})

    assert response.status_code == 200
    kinds = [json.loads(line[6:])["type"] for line in response.text.splitlines() if line.startswith("data: ")]
    assert kinds == ["status", "token", "done"]
