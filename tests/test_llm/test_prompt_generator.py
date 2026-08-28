"""Tests for the AI task prompt generator."""

from unittest.mock import AsyncMock, MagicMock, patch

from src.llm.prompts import build_prompt_refinement_prompt, build_task_prompt_template
from src.shared.types import EntityType
from tests.conftest import TEST_ORG_ID, TEST_TASK_ID


def test_build_task_prompt_template_full_context():
    """Template with all context produces a comprehensive prompt."""
    task = {
        "name": "Fix auth redirect",
        "properties": {
            "status": "in_progress",
            "priority": "high",
            "description": "Users are redirected to the wrong URL after login",
            "labels": ["auth", "bug"],
            "due_date": "2026-04-10",
        },
        "source_ids": {},
    }
    goals = [
        {
            "name": "Retention +15%",
            "progress": {"percentage": 50, "tasks_done": 5, "tasks_total": 10},
        },
    ]
    blocking_chain = [
        {"name": "Fix session store", "status": "todo"},
    ]
    related_prs = [
        {
            "name": "PR #42: Fix session store",
            "properties": {"state": "open", "html_url": "https://github.com/org/repo/pull/42"},
        },
    ]
    project = {
        "name": "Auth Rewrite",
        "properties": {"status": "active"},
        "stats": {"done": 3, "total": 10},
    }
    urgency = {
        "score": 85,
        "provenance": [{"explanation": "Blocks 2 downstream tasks"}],
    }
    assignee = {"name": "Alice"}

    result = build_task_prompt_template(task, goals, blocking_chain, related_prs, project, urgency, assignee)

    assert "Fix auth redirect" in result
    assert "Retention +15%" in result
    assert "Fix session store" in result
    assert "PR #42" in result
    assert "Auth Rewrite" in result
    assert "85/100" in result
    assert "Alice" in result
    assert "auth, bug" in result
    assert "https://github.com/org/repo" in result


def test_build_task_prompt_template_minimal_context():
    """Template with minimal context still produces a valid prompt."""
    task = {
        "name": "Simple task",
        "properties": {"status": "todo", "priority": "low"},
        "source_ids": {},
    }

    result = build_task_prompt_template(
        task,
        goals=[],
        blocking_chain=[],
        related_prs=[],
        project=None,
        urgency=None,
        assignee=None,
    )

    assert "Simple task" in result
    assert "No blocking dependencies" in result
    assert "Unassigned" in result
    assert "Instructions" in result


def test_build_prompt_refinement_prompt():
    """Refinement prompt produces system/user pair."""
    raw = "# Task: Fix auth\n\n## Status\n- Current status: todo"
    system, user = build_prompt_refinement_prompt(raw)

    assert "senior engineering lead" in system
    assert "hyphens" in system  # Style rule
    assert raw in user


@patch("src.llm.prompt_generator.call_llm_with_trace")
@patch("src.llm.prompt_generator.get_entity")
async def test_generate_task_prompt_calls_llm(mock_get_entity, mock_llm):
    """End-to-end test that generate_task_prompt gathers context and calls LLM."""
    from src.llm.prompt_generator import generate_task_prompt

    # Mock task entity
    task = MagicMock()
    task.id = TEST_TASK_ID
    task.org_id = TEST_ORG_ID
    task.type = EntityType.TASK
    task.source = MagicMock(value="linear")
    task.canonical_name = "Fix auth redirect"
    task.source_ids = {}
    task.properties = {"status": "in_progress", "priority": "high", "description": "Fix it"}
    task.created_at = MagicMock(isoformat=lambda: "2026-01-01T00:00:00+00:00")
    task.updated_at = MagicMock(isoformat=lambda: "2026-01-02T00:00:00+00:00")
    mock_get_entity.return_value = task

    # Mock LLM response
    mock_response = MagicMock()
    mock_response.text = "Refined prompt here"
    mock_response.model = "gpt-4o"
    mock_response.input_token_count = 100
    mock_response.output_token_count = 50
    mock_response.latency_ms = 500
    mock_llm.return_value = mock_response

    # Mock DB session
    db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=mock_result)

    with (
        patch("src.llm.prompt_generator.get_entities_via_edge", return_value=[]),
        patch("src.llm.prompt_generator.get_blocking_chain", return_value=[]),
    ):
        result = await generate_task_prompt(db, TEST_TASK_ID, TEST_ORG_ID)

    assert result["prompt"] == "Refined prompt here"
    assert result["task_title"] == "Fix auth redirect"
    assert result["llm_trace"] is not None
    assert result["llm_trace"]["model"] == "gpt-4o"
    assert "Fix auth redirect" in result["raw_prompt"]
