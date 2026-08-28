"""delete_prd delegates to cascade_archive_prd.

Regression guard: the DELETE endpoint must archive the PRD AND kick off the
cascade (wiki cache invalidation, JSONB ref pruning, graph edge cleanup,
async regen). Full cascade behavior is covered in test_cascade_archive.py;
this file just pins the delegation.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from src.prd import service as prd_service

TEST_ORG_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
TEST_ENTITY_ID = uuid.UUID("00000000-0000-0000-0000-000000000070")


@pytest.mark.asyncio
async def test_delete_prd_delegates_to_cascade(mock_db):
    with patch.object(
        prd_service, "cascade_archive_prd", AsyncMock()
    ) as mock_cascade:
        await prd_service.delete_prd(mock_db, TEST_ORG_ID, TEST_ENTITY_ID)

    mock_cascade.assert_awaited_once_with(mock_db, TEST_ORG_ID, TEST_ENTITY_ID)
