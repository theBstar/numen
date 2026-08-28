"""Tests for PR-PRD alignment checking service."""

import json
import uuid
from unittest.mock import MagicMock, patch

import pytest

from src.prd.alignment import (
    _extract_text_from_tiptap,
    _parse_llm_response,
    acknowledge_finding,
    check_pr_alignment,
    get_alignment_checks,
    resolve_finding,
)

TEST_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
TEST_PR_ID = uuid.UUID("00000000-0000-0000-0000-000000000040")
TEST_PRD_ID = uuid.UUID("00000000-0000-0000-0000-000000000070")
TEST_CHECK_ID = uuid.UUID("00000000-0000-0000-0000-000000000099")


# ── Unit tests for helpers ─────────────────────────────────────────────


class TestParseLlmResponse:
    """Test JSON parsing from LLM alignment responses."""

    def test_valid_json(self):
        text = json.dumps(
            {
                "findings": [
                    {
                        "type": "missing_requirement",
                        "prd_section": "Auth Flow",
                        "detail": "Missing SSO support",
                        "severity": "high",
                    }
                ],
                "coverage_score": 0.7,
            }
        )
        result = _parse_llm_response(text)
        assert len(result["findings"]) == 1
        assert result["coverage_score"] == 0.7

    def test_json_with_markdown_fence(self):
        text = '```json\n{"findings": [], "coverage_score": 1.0}\n```'
        result = _parse_llm_response(text)
        assert result["findings"] == []
        assert result["coverage_score"] == 1.0

    def test_invalid_json_returns_empty(self):
        result = _parse_llm_response("This is not JSON")
        assert result["findings"] == []
        assert result["coverage_score"] is None

    def test_empty_findings(self):
        text = json.dumps({"findings": [], "coverage_score": 1.0})
        result = _parse_llm_response(text)
        assert result["findings"] == []
        assert result["coverage_score"] == 1.0


class TestExtractTextFromTiptap:
    """Test TipTap content text extraction."""

    def test_simple_text_node(self):
        content = {"type": "text", "text": "Hello world"}
        assert _extract_text_from_tiptap(content) == "Hello world"

    def test_paragraph_with_text(self):
        content = {
            "type": "paragraph",
            "content": [
                {"type": "text", "text": "First sentence."},
                {"type": "text", "text": " Second sentence."},
            ],
        }
        result = _extract_text_from_tiptap(content)
        assert "First sentence." in result
        assert "Second sentence." in result

    def test_empty_content(self):
        assert _extract_text_from_tiptap({}) == ""
        assert _extract_text_from_tiptap(None) == ""

    def test_nested_content(self):
        content = {
            "type": "doc",
            "content": [
                {
                    "type": "heading",
                    "content": [{"type": "text", "text": "Overview"}],
                },
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Details here."}],
                },
            ],
        }
        result = _extract_text_from_tiptap(content)
        assert "Overview" in result
        assert "Details here." in result


# ── Integration tests ─────────────────────────────────────────────────


class TestCheckPrAlignment:
    """Test the main alignment check function."""

    @pytest.mark.asyncio
    @patch("src.prd.alignment._find_linked_prds")
    async def test_no_linked_prds_returns_empty(self, mock_find_prds, mock_db):
        mock_find_prds.return_value = []
        result = await check_pr_alignment(mock_db, TEST_ORG_ID, TEST_PR_ID)
        assert result == []

    @pytest.mark.asyncio
    @patch("src.prd.alignment._get_prd_sections")
    @patch("src.prd.alignment._get_pr_summary")
    @patch("src.prd.alignment._find_linked_prds")
    async def test_no_pr_title_returns_empty(
        self,
        mock_find_prds,
        mock_get_pr,
        mock_get_sections,
        mock_db,
    ):
        mock_find_prds.return_value = [
            {"prd_id": str(TEST_PRD_ID), "prd_title": "Test PRD"},
        ]
        mock_get_pr.return_value = {"title": "", "description": "", "changed_files": []}
        result = await check_pr_alignment(mock_db, TEST_ORG_ID, TEST_PR_ID)
        assert result == []

    @pytest.mark.asyncio
    @patch("src.prd.alignment.call_llm_with_trace")
    @patch("src.prd.alignment._get_prd_sections")
    @patch("src.prd.alignment._get_pr_summary")
    @patch("src.prd.alignment._find_linked_prds")
    async def test_full_alignment_check(
        self,
        mock_find_prds,
        mock_get_pr,
        mock_get_sections,
        mock_call_llm,
        mock_db,
    ):
        mock_find_prds.return_value = [
            {"prd_id": str(TEST_PRD_ID), "prd_title": "Auth PRD"},
        ]
        mock_get_pr.return_value = {
            "title": "PR #42: Fix auth flow",
            "description": "Fixes OAuth redirect",
            "changed_files": ["src/auth.py", "tests/test_auth.py"],
        }
        mock_get_sections.return_value = [
            {
                "slug": "overview",
                "block_type": "heading",
                "heading_level": 2,
                "text": "Overview - Auth system requirements",
            },
            {
                "slug": "requirements",
                "block_type": "paragraph",
                "heading_level": None,
                "text": "Must support SSO and OAuth2",
            },
        ]

        llm_response = MagicMock()
        llm_response.text = json.dumps(
            {
                "findings": [
                    {
                        "type": "missing_requirement",
                        "prd_section": "Overview",
                        "detail": "SSO support is not addressed in this PR",
                        "severity": "medium",
                    },
                ],
                "coverage_score": 0.6,
            }
        )
        llm_response.model = "gpt-4o"
        llm_response.input_token_count = 500
        llm_response.output_token_count = 200
        llm_response.latency_ms = 1500
        mock_call_llm.return_value = llm_response

        result = await check_pr_alignment(mock_db, TEST_ORG_ID, TEST_PR_ID)

        assert len(result) == 1
        check = result[0]
        assert check["prd_title"] == "Auth PRD"
        assert check["pr_title"] == "PR #42: Fix auth flow"
        assert len(check["findings"]) == 1
        assert check["findings"][0]["type"] == "missing_requirement"
        assert check["coverage_score"] == 0.6

        # Verify the check was stored
        mock_db.add.assert_called_once()
        mock_db.flush.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.prd.alignment.call_llm_with_trace")
    @patch("src.prd.alignment._get_prd_sections")
    @patch("src.prd.alignment._get_pr_summary")
    @patch("src.prd.alignment._find_linked_prds")
    async def test_clean_pr_marks_resolved(
        self,
        mock_find_prds,
        mock_get_pr,
        mock_get_sections,
        mock_call_llm,
        mock_db,
    ):
        """When LLM returns no findings, check should be auto-resolved."""
        mock_find_prds.return_value = [
            {"prd_id": str(TEST_PRD_ID), "prd_title": "Clean PRD"},
        ]
        mock_get_pr.return_value = {
            "title": "PR #99: Perfect implementation",
            "description": "Covers all requirements",
            "changed_files": ["src/feature.py"],
        }
        mock_get_sections.return_value = [
            {
                "slug": "requirements",
                "block_type": "paragraph",
                "heading_level": None,
                "text": "Implement the feature",
            },
        ]

        llm_response = MagicMock()
        llm_response.text = json.dumps(
            {
                "findings": [],
                "coverage_score": 1.0,
            }
        )
        llm_response.model = "gpt-4o"
        llm_response.input_token_count = 300
        llm_response.output_token_count = 50
        llm_response.latency_ms = 800
        mock_call_llm.return_value = llm_response

        result = await check_pr_alignment(mock_db, TEST_ORG_ID, TEST_PR_ID)

        assert len(result) == 1
        # The stored check should have status "resolved" since no findings
        stored_check = mock_db.add.call_args[0][0]
        assert stored_check.status == "resolved"

    @pytest.mark.asyncio
    @patch("src.prd.alignment._get_prd_sections")
    @patch("src.prd.alignment._get_pr_summary")
    @patch("src.prd.alignment._find_linked_prds")
    async def test_no_prd_sections_skips(
        self,
        mock_find_prds,
        mock_get_pr,
        mock_get_sections,
        mock_db,
    ):
        mock_find_prds.return_value = [
            {"prd_id": str(TEST_PRD_ID), "prd_title": "Empty PRD"},
        ]
        mock_get_pr.return_value = {
            "title": "PR #10",
            "description": "",
            "changed_files": [],
        }
        mock_get_sections.return_value = []

        result = await check_pr_alignment(mock_db, TEST_ORG_ID, TEST_PR_ID)
        assert result == []


class TestGetAlignmentChecks:
    """Test querying alignment checks."""

    @pytest.mark.asyncio
    async def test_query_by_org(self, mock_db):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = await get_alignment_checks(mock_db, TEST_ORG_ID)
        assert result == []
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_by_prd(self, mock_db):
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        result = await get_alignment_checks(
            mock_db,
            TEST_ORG_ID,
            prd_entity_id=TEST_PRD_ID,
        )
        assert result == []


class TestAcknowledgeFinding:
    """Test acknowledging alignment findings."""

    @pytest.mark.asyncio
    async def test_acknowledge_success(self, mock_db):
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db.execute.return_value = mock_result

        await acknowledge_finding(mock_db, TEST_ORG_ID, TEST_CHECK_ID)
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_acknowledge_not_found(self, mock_db):
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await acknowledge_finding(mock_db, TEST_ORG_ID, TEST_CHECK_ID)
        assert exc_info.value.status_code == 404


class TestResolveFinding:
    """Test resolving alignment findings."""

    @pytest.mark.asyncio
    async def test_resolve_success(self, mock_db):
        mock_result = MagicMock()
        mock_result.rowcount = 1
        mock_db.execute.return_value = mock_result

        await resolve_finding(mock_db, TEST_ORG_ID, TEST_CHECK_ID)
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_resolve_not_found(self, mock_db):
        mock_result = MagicMock()
        mock_result.rowcount = 0
        mock_db.execute.return_value = mock_result

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await resolve_finding(mock_db, TEST_ORG_ID, TEST_CHECK_ID)
        assert exc_info.value.status_code == 404
