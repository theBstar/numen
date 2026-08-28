"""Tests for cross-source person duplicate detection."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.graph.falkor_repository import GraphNode
from src.graph.resolution import _compute_match, detect_person_duplicates
from src.shared.types import EntityType, SourceType


@pytest.fixture
def org_id():
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


def _make_person(
    source: SourceType,
    source_ids: dict,
    canonical_name: str = "Test",
    merged_into=None,
    properties=None,
):
    return GraphNode(
        {
            "id": str(uuid.uuid4()),
            "org_id": "00000000-0000-0000-0000-000000000001",
            "type": EntityType.PERSON.value,
            "source": source,
            "source_ids": source_ids,
            "canonical_name": canonical_name,
            "properties": properties or {},
            "merged_into": merged_into,
        }
    )


class TestDetectDuplicatesExcludesMergedStubs:
    """Merged stubs (merged_into IS NOT NULL) must not participate in detection."""

    @pytest.mark.asyncio
    async def test_merged_stub_excluded_from_candidates(self, org_id):
        """A merged stub should not be treated as a candidate for new resolutions."""
        db = AsyncMock()

        primary = _make_person(SourceType.MANUAL, {"email": "dana@test.com"}, "Dana Okafor")
        merged_stub = _make_person(
            SourceType.GITHUB,
            {"github": "dokafor"},
            "dokafor",
            merged_into=primary.id,
        )

        # existing pairs query returns empty
        pairs_result = MagicMock()
        pairs_result.all.return_value = []
        db.execute.return_value = pairs_result

        with patch(
            "src.graph.resolution.list_entities",
            AsyncMock(return_value=[primary, merged_stub]),
        ):
            resolutions = await detect_person_duplicates(db, org_id)

        # No duplicates detected - the stub was filtered out by the merged_into check
        assert len(resolutions) == 0

    @pytest.mark.asyncio
    async def test_unmerged_cross_source_creates_resolution(self, org_id):
        """Two unmerged cross-source entities with matching identifiers
        should create a resolution."""
        db = AsyncMock()

        github_person = _make_person(SourceType.GITHUB, {"github": "dokafor"}, "dokafor")
        manual_person = _make_person(
            SourceType.MANUAL,
            {"github": "dokafor", "email": "dana@test.com"},
            "Dana Okafor",
        )

        pairs_result = MagicMock()
        pairs_result.all.return_value = []
        db.execute.return_value = pairs_result
        db.add = MagicMock()

        with patch(
            "src.graph.resolution.list_entities",
            AsyncMock(return_value=[github_person, manual_person]),
        ):
            resolutions = await detect_person_duplicates(db, org_id)

        assert len(resolutions) == 1
        assert resolutions[0].status == "pending"


class TestComputeMatch:
    """Unit tests for the match confidence computation."""

    def test_github_username_match(self):
        a = _make_person(SourceType.GITHUB, {"github": "alice"}, "alice")
        b = _make_person(SourceType.MANUAL, {"github": "alice"}, "Alice Chen")
        confidence, reasons = _compute_match(a, b)
        assert confidence == 0.85
        assert any(r["type"] == "github_username" for r in reasons)

    def test_email_match(self):
        a = _make_person(SourceType.GITHUB, {"email": "alice@test.com"}, "alice")
        b = _make_person(SourceType.MANUAL, {"email": "alice@test.com"}, "Alice")
        confidence, reasons = _compute_match(a, b)
        assert confidence == 0.95
        assert any(r["type"] == "email" for r in reasons)

    def test_no_match(self):
        a = _make_person(SourceType.GITHUB, {"github": "alice"}, "alice")
        b = _make_person(SourceType.MANUAL, {"email": "bob@test.com"}, "Bob")
        confidence, reasons = _compute_match(a, b)
        assert confidence < 0.35
