"""Shared test fixtures."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.shared.types import EntityType, RoleType, SourceType

TEST_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
TEST_PERSON_ID = uuid.UUID("00000000-0000-0000-0000-000000000010")
TEST_TASK_ID = uuid.UUID("00000000-0000-0000-0000-000000000020")
TEST_GOAL_ID = uuid.UUID("00000000-0000-0000-0000-000000000030")
TEST_PR_ID = uuid.UUID("00000000-0000-0000-0000-000000000040")
TEST_DEPLOY_ID = uuid.UUID("00000000-0000-0000-0000-000000000050")
TEST_MEMBER_ID = uuid.UUID("00000000-0000-0000-0000-000000000060")


@pytest.fixture
def org_id():
    return TEST_ORG_ID


@pytest.fixture
def mock_db():
    """Create a mock AsyncSession."""
    db = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.get = AsyncMock(return_value=None)
    return db


@pytest.fixture
def mock_entity():
    """Create a mock Entity object (TASK type)."""
    entity = MagicMock()
    entity.id = TEST_TASK_ID
    entity.org_id = TEST_ORG_ID
    entity.type = EntityType.TASK
    entity.source = SourceType.LINEAR
    entity.source_ids = {"linear": "TEST-1"}
    entity.canonical_name = "TEST-1: Fix the bug"
    entity.properties = {"status": "in_progress", "priority": "high"}
    entity.updated_at = datetime.now(timezone.utc) - timedelta(days=3)
    entity.created_at = datetime.now(timezone.utc) - timedelta(days=10)
    return entity


@pytest.fixture
def mock_person():
    """Create a mock Person entity."""
    entity = MagicMock()
    entity.id = TEST_PERSON_ID
    entity.org_id = TEST_ORG_ID
    entity.type = EntityType.PERSON
    entity.source = SourceType.MANUAL
    entity.source_ids = {"email": "alice@test.com"}
    entity.canonical_name = "Alice Test"
    entity.properties = {"email": "alice@test.com"}
    entity.updated_at = datetime.now(timezone.utc)
    entity.created_at = datetime.now(timezone.utc) - timedelta(days=30)
    return entity


@pytest.fixture
def mock_goal():
    """Create a mock Goal entity."""
    entity = MagicMock()
    entity.id = TEST_GOAL_ID
    entity.org_id = TEST_ORG_ID
    entity.type = EntityType.GOAL
    entity.source = SourceType.MANUAL
    entity.source_ids = {"manual": "goal-1"}
    entity.canonical_name = "Retention +15%"
    entity.properties = {"target_value": 15, "current_value": 7.5, "status": "active"}
    entity.updated_at = datetime.now(timezone.utc)
    entity.created_at = datetime.now(timezone.utc) - timedelta(days=90)
    return entity


@pytest.fixture
def mock_pr_entity():
    """Create a mock PR entity."""
    entity = MagicMock()
    entity.id = TEST_PR_ID
    entity.org_id = TEST_ORG_ID
    entity.type = EntityType.COMMIT_PR
    entity.source = SourceType.GITHUB
    entity.source_ids = {"github": "org/repo#42"}
    entity.canonical_name = "PR #42: Fix auth flow"
    entity.properties = {
        "status": "open",
        "diff": "diff --git a/auth.py\n+fixed",
        "description": "Fixes auth redirect",
        "author": "alice",
        "html_url": "https://github.com/org/repo/pull/42",
    }
    entity.updated_at = datetime.now(timezone.utc)
    entity.created_at = datetime.now(timezone.utc) - timedelta(days=2)
    return entity


@pytest.fixture
def mock_member():
    """Create a mock OrgMember."""
    member = MagicMock()
    member.id = TEST_MEMBER_ID
    member.org_id = TEST_ORG_ID
    member.person_entity_id = TEST_PERSON_ID
    member.role = RoleType.ENGINEER
    member.email = "alice@test.com"
    member.display_name = "Alice Test"
    member.preferences = {}
    member.timezone = "America/New_York"
    return member
