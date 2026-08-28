"""Tests for Claude dispatch actions."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.llm.actions import generate_briefing_narrative, summarize_pr_diff
from src.llm.client import LLMResponse
from src.shared.types import BriefingItem, EntityType, RoleType


@pytest.mark.asyncio
async def test_summarize_pr_diff_not_found():
    """Should raise ValueError if PR entity does not exist."""
    db = AsyncMock()

    with patch("src.llm.actions.get_entity", return_value=None):
        with pytest.raises(ValueError, match="PR entity not found"):
            await summarize_pr_diff(db, uuid.uuid4(), org_id=uuid.uuid4())


@pytest.mark.asyncio
async def test_summarize_pr_diff_success():
    """Should return a draft summary dict with expected keys."""
    db = AsyncMock()
    pr_id = uuid.uuid4()
    org_id = uuid.uuid4()

    # Mock PR entity
    pr_entity = MagicMock()
    pr_entity.id = pr_id
    pr_entity.type = EntityType.COMMIT_PR
    pr_entity.canonical_name = "PR #42: Fix auth"
    pr_entity.properties = {
        "diff": "diff --git a/auth.py\n+fixed",
        "description": "Fixes auth redirect",
    }

    mock_response = LLMResponse(
        text="Summary: This PR fixes the auth redirect issue.",
        model="claude-sonnet-4-20250514",
        input_token_count=200,
        output_token_count=50,
        latency_ms=500,
    )

    with (
        patch("src.llm.actions.get_entity", return_value=pr_entity),
        patch("src.llm.actions.get_edges", return_value=[]),
        patch("src.llm.actions.call_llm_with_trace", return_value=mock_response),
    ):
        result = await summarize_pr_diff(db, pr_id, org_id=org_id)

    assert result["draft"] is True
    assert "summary" in result
    assert result["summary"] == "Summary: This PR fixes the auth redirect issue."
    assert result["pr_title"] == "PR #42: Fix auth"
    assert result["entity_id"] == str(pr_id)
    assert "llm_trace" in result


@pytest.mark.asyncio
async def test_summarize_pr_diff_with_linked_tasks():
    """Should include linked task info in the summary."""
    db = AsyncMock()
    pr_id = uuid.uuid4()
    task_id = uuid.uuid4()
    org_id = uuid.uuid4()

    # Mock PR entity
    pr_entity = MagicMock()
    pr_entity.id = pr_id
    pr_entity.type = EntityType.COMMIT_PR
    pr_entity.canonical_name = "PR #42: Fix auth"
    pr_entity.properties = {"diff": "diff", "description": "desc"}

    # Mock edge
    mock_edge = MagicMock()
    mock_edge.to_entity_id = task_id

    # Mock linked task
    mock_task = MagicMock()
    mock_task.type = EntityType.TASK
    mock_task.canonical_name = "ENG-4501: Fix OAuth"
    mock_task.properties = {"goal_tags": ["Retention"], "status": "in_progress"}

    mock_response = LLMResponse(
        text="Summary with linked tasks",
        model="claude-sonnet-4-20250514",
    )

    with (
        patch("src.llm.actions.get_entity", return_value=pr_entity),
        patch("src.llm.actions.get_edges", return_value=[mock_edge]),
        patch("src.llm.actions.get_entities_by_ids", return_value=[mock_task]),
        patch("src.llm.actions.call_llm_with_trace", return_value=mock_response),
    ):
        result = await summarize_pr_diff(db, pr_id, org_id=org_id)

    assert result["draft"] is True
    assert result["summary"] == "Summary with linked tasks"


@pytest.mark.asyncio
async def test_generate_briefing_narrative_success():
    """Should return narrative text and llm_trace."""
    items = [
        BriefingItem(
            entity_id=uuid.uuid4(),
            entity_type=EntityType.TASK,
            title="Fix auth bug",
            why_it_matters="Blocking 3 items",
            urgency_score=0.9,
            goal_tags=["Retention"],
        ),
    ]

    mock_response = LLMResponse(
        text="Good morning Alice! Today you have a critical auth fix to focus on.",
        model="claude-sonnet-4-20250514",
        input_token_count=300,
        output_token_count=80,
        latency_ms=600,
    )

    with patch("src.llm.actions.call_llm_with_trace", return_value=mock_response):
        result = await generate_briefing_narrative(
            items=items,
            role=RoleType.ENGINEER,
            person_name="Alice",
        )

    assert "narrative" in result
    assert "llm_trace" in result
    assert "Alice" in result["narrative"]


@pytest.mark.asyncio
async def test_generate_briefing_narrative_empty_items():
    """Should handle empty items list gracefully."""
    mock_response = LLMResponse(
        text="No urgent items today - a good day to focus on deep work!",
        model="claude-sonnet-4-20250514",
    )

    with patch("src.llm.actions.call_llm_with_trace", return_value=mock_response):
        result = await generate_briefing_narrative(
            items=[],
            role=RoleType.PM,
            person_name="Eve",
        )

    assert "narrative" in result
    assert result["narrative"] == "No urgent items today - a good day to focus on deep work!"
