"""Tests for the single tool registry shared by every surface."""

import uuid
from unittest.mock import AsyncMock

import pytest

from src.agent.principal import Audience, Principal, Surface
from src.agent.registry import (
    TOOL_SPECS,
    ToolContext,
    build_langchain_tools,
    tools_for,
)


def _principal(**overrides):
    base = {
        "org_id": uuid.uuid4(),
        "user_id": uuid.uuid4(),
        "email": "someone@example.com",
        "surface": Surface.WEB,
    }
    base.update(overrides)
    return Principal(**base)


def test_registry_is_not_empty():
    assert len(TOOL_SPECS) > 20, "the registry should expose the full graph surface"


def test_tool_names_are_unique():
    names = [spec.name for spec in TOOL_SPECS]
    assert len(names) == len(set(names))


def test_every_spec_has_a_description_and_handler():
    for spec in TOOL_SPECS:
        assert spec.description.strip(), f"{spec.name} has no description"
        assert callable(spec.handler), f"{spec.name} has no handler"


def test_registry_includes_writes():
    assert any(spec.writes for spec in TOOL_SPECS)


def test_read_only_principal_gets_no_write_tools():
    """This is what a public channel or an unbound API key sees."""
    selected = tools_for(_principal(user_id=None))
    assert selected, "read tools must still be available"
    assert all(not spec.writes for spec in selected)


def test_bound_private_principal_gets_write_tools():
    selected = tools_for(_principal())
    assert any(spec.writes for spec in selected)


def test_shared_audience_excludes_private_grounding_tools():
    """Answers readable by a channel must not retrieve private documents."""
    shared = tools_for(_principal(surface=Surface.SLACK, audience=Audience.SHARED))
    names = {spec.name for spec in shared}
    assert "get_context" not in names
    assert all(not spec.writes for spec in shared)


def test_private_audience_includes_retrieval():
    names = {spec.name for spec in tools_for(_principal())}
    assert "get_context" in names


def test_build_langchain_tools_returns_structured_tools():
    ctx = ToolContext(db=AsyncMock(), principal=_principal())
    tools = build_langchain_tools(ctx)
    assert tools
    names = {t.name for t in tools}
    assert "search_entities" in names
    assert "get_urgency_scores" in names
    for tool in tools:
        assert tool.description, f"{tool.name} exposed with no description"


def test_build_langchain_tools_respects_permissions():
    read_only = ToolContext(db=AsyncMock(), principal=_principal(user_id=None))
    names = {t.name for t in build_langchain_tools(read_only)}
    assert "create_task" not in names

    writable = ToolContext(db=AsyncMock(), principal=_principal())
    names = {t.name for t in build_langchain_tools(writable)}
    assert "create_task" in names


@pytest.mark.asyncio
async def test_write_handler_refuses_without_a_bound_user():
    """Defence in depth: even if a write tool were bound, it must refuse."""
    from src.agent.registry import SPECS_BY_NAME

    ctx = ToolContext(db=AsyncMock(), principal=_principal(user_id=None))
    spec = SPECS_BY_NAME["create_task"]
    result = await spec.handler(ctx, title="anything")
    assert "error" in result.lower()
