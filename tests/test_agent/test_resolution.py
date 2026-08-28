"""Name resolution behaviour, ported from the retired chat tool registry.

Conversations refer to people and projects by name. These tests pin the
three outcomes that matter: a clean match, an ambiguous one the model must
ask about, and no match at all.
"""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agent.principal import Principal, Surface
from src.agent.registry import ToolContext, build_langchain_tools
from src.shared.types import EntityType


def _principal():
    return Principal(
        org_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        email="asker@example.com",
        surface=Surface.WEB,
    )


def _make_person(name: str) -> MagicMock:
    person = MagicMock()
    person.id = uuid.uuid4()
    person.canonical_name = name
    person.type = EntityType.PERSON
    person.properties = {"email": f"{name.lower().replace(' ', '.')}@example.com"}
    person.updated_at = datetime.now(timezone.utc)
    return person


def _tool(named: str):
    ctx = ToolContext(db=AsyncMock(), principal=_principal())
    return next(t for t in build_langchain_tools(ctx) if t.name == named)


@pytest.mark.asyncio
async def test_single_match_resolves():
    person = _make_person("Ada Lovelace")
    with (
        patch("src.agent.resolvers.list_entities", return_value=[person]),
        patch("src.agent.registry.get_person_workload", return_value={"by_status": {"todo": 2}, "total": 2}),
    ):
        result = json.loads(await _tool("get_person_workload").ainvoke({"person_name": "Ada"}))

    assert "error" not in result
    assert result["person"]["name"] == "Ada Lovelace"
    assert result["workload"]["total"] == 2


@pytest.mark.asyncio
async def test_ambiguous_match_lists_candidates():
    """The model should ask which person, not silently pick the first."""
    people = [_make_person("Ada Lovelace"), _make_person("Ada Byron")]
    with patch("src.agent.resolvers.list_entities", return_value=people):
        result = json.loads(await _tool("get_person_workload").ainvoke({"person_name": "Ada"}))

    assert "error" in result
    assert set(result["candidates"]) == {"Ada Lovelace", "Ada Byron"}
    assert "ask the user" in result["hint"].lower()


@pytest.mark.asyncio
async def test_exact_name_wins_over_ambiguity():
    """'Ada Byron' should resolve even though 'Ada Byron King' also matches."""
    people = [_make_person("Ada Byron King"), _make_person("Ada Byron")]
    with (
        patch("src.agent.resolvers.list_entities", return_value=people),
        patch("src.agent.registry.get_person_workload", return_value={"by_status": {}, "total": 0}),
    ):
        result = json.loads(await _tool("get_person_workload").ainvoke({"person_name": "Ada Byron"}))

    assert "error" not in result
    assert result["person"]["name"] == "Ada Byron"


@pytest.mark.asyncio
async def test_no_match_reports_not_found():
    with patch("src.agent.resolvers.list_entities", return_value=[]):
        result = json.loads(await _tool("get_person_workload").ainvoke({"person_name": "Nobody"}))

    assert "error" in result
    assert "no person" in result["error"].lower()


@pytest.mark.asyncio
async def test_tool_failure_becomes_readable_json():
    """A raising handler must not abort the run; the model needs to see it."""
    person = _make_person("Ada Lovelace")
    with (
        patch("src.agent.resolvers.list_entities", return_value=[person]),
        patch("src.agent.registry.get_person_workload", side_effect=RuntimeError("graph down")),
    ):
        result = json.loads(await _tool("get_person_workload").ainvoke({"person_name": "Ada"}))

    assert "error" in result
    assert "graph down" in result["error"]
