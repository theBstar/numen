"""Tests for find_matching_task recommend_threshold (WS7)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

from src.mcp.tools import find_matching_task
from tests.conftest import TEST_ORG_ID


def _candidate(task_id: str, name: str = "Some task") -> MagicMock:
    e = MagicMock()
    e.id = task_id
    e.org_id = TEST_ORG_ID
    e.canonical_name = name
    e.properties = {"status": "todo", "priority": "medium"}
    return e


def _entity_dict(task_id: str, name: str = "Some task") -> dict:
    return {
        "id": task_id,
        "name": name,
        "canonical_name": name,
        "properties": {"status": "todo", "priority": "medium"},
    }


@patch("src.mcp.tools.list_entities")
@patch("src.mcp.tools.entity_to_dict")
@patch("src.llm.client.call_llm", )
async def test_recommendation_emitted_when_top_confidence_above_threshold(
    mock_llm, mock_to_dict, mock_list_ents
):
    mock_list_ents.return_value = [_candidate("t1"), _candidate("t2")]
    mock_to_dict.side_effect = lambda e: _entity_dict(e.id, e.canonical_name)
    mock_llm.return_value = json.dumps(
        {
            "matches": [
                {"task_id": "t1", "confidence": 0.92, "reason": "very similar"},
                {"task_id": "t2", "confidence": 0.40, "reason": "different scope"},
            ]
        }
    )
    db = AsyncMock()
    out = json.loads(
        await find_matching_task(db, TEST_ORG_ID, "fix login bug")
    )
    assert out["method"] == "llm_rerank"
    assert out.get("recommended_action") == "use_existing"
    assert out.get("recommended_task_id") == "t1"
    assert out.get("recommended_confidence") == 0.92
    assert out.get("recommend_threshold") == 0.85


@patch("src.mcp.tools.list_entities")
@patch("src.mcp.tools.entity_to_dict")
@patch("src.llm.client.call_llm", )
async def test_no_recommendation_when_below_threshold(
    mock_llm, mock_to_dict, mock_list_ents
):
    mock_list_ents.return_value = [_candidate("t1")]
    mock_to_dict.side_effect = lambda e: _entity_dict(e.id, e.canonical_name)
    mock_llm.return_value = json.dumps(
        {"matches": [{"task_id": "t1", "confidence": 0.55, "reason": "maybe"}]}
    )
    db = AsyncMock()
    out = json.loads(
        await find_matching_task(db, TEST_ORG_ID, "fix login bug")
    )
    assert "recommended_action" not in out
    assert out["candidates"][0]["confidence"] == 0.55


@patch("src.mcp.tools.list_entities")
@patch("src.mcp.tools.entity_to_dict")
@patch("src.llm.client.call_llm", )
async def test_per_call_threshold_override(mock_llm, mock_to_dict, mock_list_ents):
    mock_list_ents.return_value = [_candidate("t1")]
    mock_to_dict.side_effect = lambda e: _entity_dict(e.id, e.canonical_name)
    mock_llm.return_value = json.dumps(
        {"matches": [{"task_id": "t1", "confidence": 0.7, "reason": "ok"}]}
    )
    db = AsyncMock()

    # 0.7 is below default 0.85 - no rec.
    out = json.loads(await find_matching_task(db, TEST_ORG_ID, "x"))
    assert "recommended_action" not in out

    # Lower threshold to 0.6 - now rec fires.
    out = json.loads(
        await find_matching_task(db, TEST_ORG_ID, "x", recommend_threshold=0.6)
    )
    assert out["recommended_action"] == "use_existing"
    assert out["recommend_threshold"] == 0.6


@patch("src.mcp.tools.list_entities")
@patch("src.mcp.tools.entity_to_dict")
@patch("src.llm.client.call_llm", )
async def test_threshold_none_suppresses_recommendation(
    mock_llm, mock_to_dict, mock_list_ents
):
    mock_list_ents.return_value = [_candidate("t1")]
    mock_to_dict.side_effect = lambda e: _entity_dict(e.id, e.canonical_name)
    mock_llm.return_value = json.dumps(
        {"matches": [{"task_id": "t1", "confidence": 0.99, "reason": "perfect"}]}
    )
    db = AsyncMock()
    out = json.loads(
        await find_matching_task(db, TEST_ORG_ID, "x", recommend_threshold=None)
    )
    assert "recommended_action" not in out


@patch("src.mcp.tools.list_entities")
@patch("src.mcp.tools.entity_to_dict")
@patch("src.llm.client.call_llm", )
async def test_substring_fallback_no_recommendation(
    mock_llm, mock_to_dict, mock_list_ents
):
    mock_list_ents.return_value = [_candidate("t1")]
    mock_to_dict.side_effect = lambda e: _entity_dict(e.id, e.canonical_name)
    mock_llm.side_effect = RuntimeError("LLM down")
    db = AsyncMock()
    out = json.loads(await find_matching_task(db, TEST_ORG_ID, "x"))
    assert out["method"] == "substring_fallback"
    assert "recommended_action" not in out
    assert out["candidates"][0]["confidence"] is None
