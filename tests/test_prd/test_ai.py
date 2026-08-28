"""Tests for PRD AI service: auto-complete, section editing, reviewer suggestions."""

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.prd.ai import (
    _build_product_context,
    _parse_llm_json,
    _section_to_tiptap_blocks,
    auto_complete_prd,
    edit_section,
    suggest_reviewers,
)

TEST_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
TEST_ENTITY_ID = uuid.UUID("00000000-0000-0000-0000-000000000070")
TEST_MEMBER_ID = uuid.UUID("00000000-0000-0000-0000-000000000060")


# ── Unit tests for helper functions ──────────────────────────────────


class TestParseLlmJson:
    """Test JSON parsing from LLM responses."""

    def test_valid_json_array(self):
        text = '[{"heading": "Overview", "content": "Some content"}]'
        result = _parse_llm_json(text)
        assert len(result) == 1
        assert result[0]["heading"] == "Overview"

    def test_json_with_markdown_fence(self):
        text = '```json\n[{"heading": "A", "content": "B"}]\n```'
        result = _parse_llm_json(text)
        assert len(result) == 1
        assert result[0]["heading"] == "A"

    def test_invalid_json(self):
        text = "This is not JSON at all"
        result = _parse_llm_json(text)
        assert result == []

    def test_json_object_not_array(self):
        text = '{"heading": "A"}'
        result = _parse_llm_json(text)
        assert result == []

    def test_empty_array(self):
        text = "[]"
        result = _parse_llm_json(text)
        assert result == []


class TestSectionToTiptapBlocks:
    """Test TipTap block conversion."""

    def test_heading_and_paragraph(self):
        blocks = _section_to_tiptap_blocks("Overview", "This is the overview.", 0.0)
        assert len(blocks) == 2
        assert blocks[0]["block_type"] == "heading"
        assert blocks[0]["heading_level"] == 2
        assert blocks[0]["ai_generated"] is True
        assert blocks[1]["block_type"] == "paragraph"
        assert blocks[1]["ai_generated"] is True

    def test_multiple_paragraphs(self):
        content = "First paragraph.\n\nSecond paragraph."
        blocks = _section_to_tiptap_blocks("Test", content, 0.0)
        # 1 heading + 2 paragraphs
        assert len(blocks) == 3
        assert blocks[0]["block_type"] == "heading"
        assert blocks[1]["block_type"] == "paragraph"
        assert blocks[2]["block_type"] == "paragraph"

    def test_bullet_list_detection(self):
        content = "- First item\n- Second item\n- Third item"
        blocks = _section_to_tiptap_blocks("List Section", content, 0.0)
        # 1 heading + 1 bullet list
        assert len(blocks) == 2
        assert blocks[0]["block_type"] == "heading"
        assert blocks[1]["block_type"] == "bullet_list"
        # Check list items
        list_content = blocks[1]["content"]["content"]
        assert len(list_content) == 3

    def test_position_incrementing(self):
        blocks = _section_to_tiptap_blocks("Section", "Para one.\n\nPara two.", 5.0)
        positions = [b["position"] for b in blocks]
        assert positions == [5.0, 6.0, 7.0]

    def test_empty_content(self):
        blocks = _section_to_tiptap_blocks("Empty", "", 0.0)
        # heading + one empty-ish paragraph
        assert len(blocks) >= 1
        assert blocks[0]["block_type"] == "heading"


class TestBuildProductContext:
    """Test product context extraction from graph neighborhood."""

    def test_with_goals_and_people(self):
        entities = [
            MagicMock(
                type="goal",
                canonical_name="Retention +15%",
                properties={},
            ),
            MagicMock(
                type="person",
                canonical_name="Alice",
                properties={},
            ),
        ]
        neighborhood = {"entities": entities, "edges": []}
        context = _build_product_context(neighborhood)
        assert "Retention +15%" in context
        assert "Alice" in context

    def test_empty_neighborhood(self):
        neighborhood = {"entities": [], "edges": []}
        context = _build_product_context(neighborhood)
        assert "No additional product context available" in context


# ── Integration tests with mocked LLM ───────────────────────────────


@pytest.mark.asyncio
async def test_auto_complete_prd_success():
    """Should return TipTap blocks from LLM-generated sections."""
    db = AsyncMock()

    llm_response = json.dumps(
        [
            {"heading": "Overview", "content": "This is the product overview."},
            {"heading": "Problem Statement", "content": "Users face issues with X."},
        ]
    )

    with (
        patch("src.prd.ai.get_prd_impact_graph", return_value={"entities": [], "edges": []}),
        patch("src.prd.ai.find_connected_entities", return_value=[]),
        patch("src.prd.ai.call_llm", return_value=llm_response),
    ):
        blocks = await auto_complete_prd(
            db,
            TEST_ORG_ID,
            TEST_ENTITY_ID,
            TEST_MEMBER_ID,
            "A feature for data export",
        )

    assert len(blocks) > 0
    # Should have headings and paragraphs
    block_types = {b["block_type"] for b in blocks}
    assert "heading" in block_types
    assert "paragraph" in block_types
    # All blocks should be marked as AI-generated
    assert all(b.get("ai_generated") is True for b in blocks)


@pytest.mark.asyncio
async def test_auto_complete_prd_empty_response():
    """Should return empty list when LLM returns invalid JSON."""
    db = AsyncMock()

    with (
        patch("src.prd.ai.get_prd_impact_graph", return_value={"entities": [], "edges": []}),
        patch("src.prd.ai.find_connected_entities", return_value=[]),
        patch("src.prd.ai.call_llm", return_value="I cannot generate that."),
    ):
        blocks = await auto_complete_prd(
            db,
            TEST_ORG_ID,
            TEST_ENTITY_ID,
            TEST_MEMBER_ID,
            "Something",
        )

    assert blocks == []


@pytest.mark.asyncio
async def test_edit_section_success():
    """Should return updated blocks based on edit instruction."""
    db = AsyncMock()

    # Mock existing blocks
    block1_id = uuid.uuid4()
    mock_blocks = [
        MagicMock(
            id=block1_id,
            block_type="paragraph",
            content={"type": "paragraph", "content": [{"type": "text", "text": "Original text."}]},
            position=1.0,
            heading_level=None,
        ),
    ]

    llm_response = json.dumps(
        [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": "Edited text with more detail."}],
            },
        ]
    )

    with (
        patch("src.prd.ai.get_blocks", return_value=mock_blocks),
        patch("src.prd.ai.call_llm", return_value=llm_response),
    ):
        blocks = await edit_section(
            db,
            TEST_ORG_ID,
            TEST_ENTITY_ID,
            [block1_id],
            "Make it more detailed",
        )

    assert len(blocks) == 1
    assert blocks[0]["block_type"] == "paragraph"
    assert blocks[0].get("ai_generated") is True


@pytest.mark.asyncio
async def test_edit_section_no_matching_blocks():
    """Should return empty list when no blocks match the given IDs."""
    db = AsyncMock()

    with patch("src.prd.ai.get_blocks", return_value=[]):
        blocks = await edit_section(
            db,
            TEST_ORG_ID,
            TEST_ENTITY_ID,
            [uuid.uuid4()],
            "Edit this",
        )

    assert blocks == []


@pytest.mark.asyncio
async def test_suggest_reviewers_success():
    """Should return ranked reviewer suggestions from graph."""
    db = AsyncMock()

    # Mock graph query results
    mock_graph = AsyncMock()

    # Goal owner query
    goal_owner_result = MagicMock()
    goal_owner_result.result_set = [
        ["person-1", "Alice", "Retention Goal"],
    ]

    # Related author query
    related_author_result = MagicMock()
    related_author_result.result_set = [
        ["person-2", "Bob", "Sibling PRD"],
    ]

    # Implementer query
    implementer_result = MagicMock()
    implementer_result.result_set = []

    # Lead query
    lead_result = MagicMock()
    lead_result.result_set = []

    mock_graph.query = AsyncMock(
        side_effect=[
            goal_owner_result,
            related_author_result,
            implementer_result,
            lead_result,
        ]
    )

    with (
        patch(
            "src.graph.falkor_client.get_org_graph", new_callable=AsyncMock, return_value=mock_graph
        ),
        patch("src.prd.ai.get_prd_stakeholders", new_callable=AsyncMock, return_value=[]),
    ):
        reviewers = await suggest_reviewers(db, TEST_ORG_ID, TEST_ENTITY_ID)

    assert len(reviewers) == 2
    # Alice should rank higher (goal owner = 3.0 score)
    assert reviewers[0]["person_name"] == "Alice"
    assert reviewers[0]["score"] >= reviewers[1]["score"]
    assert "reason" in reviewers[0]
    assert "member_id" in reviewers[0]


@pytest.mark.asyncio
async def test_suggest_reviewers_excludes_owner():
    """Should not suggest the PRD owner as a reviewer."""
    db = AsyncMock()

    mock_graph = AsyncMock()

    # Only one person found - who is also the owner
    goal_owner_result = MagicMock()
    goal_owner_result.result_set = [
        ["person-1", "Alice", "Some Goal"],
    ]

    empty_result = MagicMock()
    empty_result.result_set = []

    mock_graph.query = AsyncMock(
        side_effect=[
            goal_owner_result,
            empty_result,
            empty_result,
            empty_result,
        ]
    )

    # Alice is already the owner
    stakeholders = [
        {"person_id": "person-1", "person_name": "Alice", "role_type": "owner"},
    ]

    with (
        patch(
            "src.graph.falkor_client.get_org_graph", new_callable=AsyncMock, return_value=mock_graph
        ),
        patch("src.prd.ai.get_prd_stakeholders", new_callable=AsyncMock, return_value=stakeholders),
    ):
        reviewers = await suggest_reviewers(db, TEST_ORG_ID, TEST_ENTITY_ID)

    assert len(reviewers) == 0


@pytest.mark.asyncio
async def test_suggest_reviewers_excludes_existing_reviewers():
    """Should not suggest people already assigned as reviewers."""
    db = AsyncMock()

    mock_graph = AsyncMock()

    goal_owner_result = MagicMock()
    goal_owner_result.result_set = [
        ["person-1", "Alice", "Goal A"],
        ["person-2", "Bob", "Goal B"],
    ]

    empty_result = MagicMock()
    empty_result.result_set = []

    mock_graph.query = AsyncMock(
        side_effect=[
            goal_owner_result,
            empty_result,
            empty_result,
            empty_result,
        ]
    )

    # Bob is already a reviewer
    stakeholders = [
        {"person_id": "person-2", "person_name": "Bob", "role_type": "reviewer"},
    ]

    with (
        patch(
            "src.graph.falkor_client.get_org_graph", new_callable=AsyncMock, return_value=mock_graph
        ),
        patch("src.prd.ai.get_prd_stakeholders", new_callable=AsyncMock, return_value=stakeholders),
    ):
        reviewers = await suggest_reviewers(db, TEST_ORG_ID, TEST_ENTITY_ID)

    assert len(reviewers) == 1
    assert reviewers[0]["person_name"] == "Alice"
