"""The scheduler is what makes the org context *continuous* rather than a
one-off import at connect time. It had no test coverage, which is how it came
to be missing Jira entirely.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.connectors.registry import SUPPORTED_SOURCES
from src.events import bus as event_bus
from src.shared.types import ConnectorSyncResult, SourceType, SyncStatus
from src.workers.sync_scheduler import SyncScheduler


@pytest.fixture
def scheduler():
    return SyncScheduler()


@pytest.fixture
def sync_state():
    state = MagicMock()
    state.status = SyncStatus.IDLE
    state.last_sync_at = None
    state.error_message = None
    return state


@pytest.fixture
def token():
    tok = MagicMock()
    tok.id = uuid4()
    return tok


def _result(source: SourceType, **counts) -> ConnectorSyncResult:
    return ConnectorSyncResult(source=source, **counts)


def _db_returning(token):
    db = AsyncMock()
    db.flush = AsyncMock()
    db.rollback = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.first.return_value = token
    db.execute = AsyncMock(return_value=result)
    return db


@pytest.mark.asyncio
@pytest.mark.parametrize("source", sorted(SUPPORTED_SOURCES, key=lambda s: s.value))
async def test_every_supported_source_actually_delta_syncs(
    scheduler, sync_state, token, source
):
    """Regression: Jira was OAuth-connectable but the scheduler skipped it, so it
    silently stopped updating after the initial backfill."""
    db = _db_returning(token)
    connector = AsyncMock()
    connector.sync_delta = AsyncMock(return_value=_result(source, entities_created=1))

    with (
        patch.object(scheduler, "_get_or_create_sync_state", return_value=sync_state),
        patch("src.workers.sync_scheduler.get_connector", return_value=connector),
        patch.object(event_bus, "emit", new=AsyncMock()),
    ):
        await scheduler._sync_one(db, token.id, uuid4(), source)

    connector.sync_delta.assert_awaited_once()
    assert sync_state.status == SyncStatus.IDLE
    assert sync_state.error_message is None
    assert sync_state.last_sync_at is not None


@pytest.mark.asyncio
async def test_unsupported_source_is_visible_not_silent(scheduler, sync_state, token):
    """A source with no connector must surface as an error on the sync state.

    It used to be a debug-level log, so an org could have a connector that never
    synced and nothing anywhere said so.
    """
    db = _db_returning(token)

    with patch.object(scheduler, "_get_or_create_sync_state", return_value=sync_state):
        await scheduler._sync_one(db, token.id, uuid4(), SourceType.DATADOG)

    assert sync_state.status == SyncStatus.ERROR
    assert sync_state.error_message
    assert "datadog" in sync_state.error_message.lower()


@pytest.mark.asyncio
async def test_sync_in_progress_is_not_restarted(scheduler, sync_state, token):
    """Overlapping syncs would double-write entities."""
    db = _db_returning(token)
    sync_state.status = SyncStatus.SYNCING
    connector = AsyncMock()

    with (
        patch.object(scheduler, "_get_or_create_sync_state", return_value=sync_state),
        patch("src.workers.sync_scheduler.get_connector", return_value=connector),
    ):
        await scheduler._sync_one(db, token.id, uuid4(), SourceType.GITHUB)

    connector.sync_delta.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_sync_records_the_error_and_rolls_back(scheduler, sync_state, token):
    db = _db_returning(token)
    connector = AsyncMock()
    connector.sync_delta = AsyncMock(side_effect=RuntimeError("upstream 503"))

    with (
        patch.object(scheduler, "_get_or_create_sync_state", return_value=sync_state),
        patch("src.workers.sync_scheduler.get_connector", return_value=connector),
    ):
        await scheduler._sync_one(db, token.id, uuid4(), SourceType.LINEAR)

    db.rollback.assert_awaited_once()
    assert sync_state.status == SyncStatus.ERROR
    assert "upstream 503" in sync_state.error_message


@pytest.mark.asyncio
async def test_missing_token_is_skipped(scheduler):
    """The token can be revoked between the poll and the sync."""
    db = _db_returning(None)

    with patch("src.workers.sync_scheduler.get_connector") as get_conn:
        await scheduler._sync_one(db, uuid4(), uuid4(), SourceType.GITHUB)

    get_conn.assert_not_called()


@pytest.mark.asyncio
async def test_delta_sync_resumes_from_last_sync_at(scheduler, sync_state, token):
    """Delta sync must resume from the watermark, not refetch all history."""
    db = _db_returning(token)
    watermark = datetime(2026, 8, 1, tzinfo=timezone.utc)
    sync_state.last_sync_at = watermark

    connector = AsyncMock()
    connector.sync_delta = AsyncMock(return_value=_result(SourceType.GITHUB))

    with (
        patch.object(scheduler, "_get_or_create_sync_state", return_value=sync_state),
        patch("src.workers.sync_scheduler.get_connector", return_value=connector),
        patch.object(event_bus, "emit", new=AsyncMock()),
    ):
        await scheduler._sync_one(db, token.id, uuid4(), SourceType.GITHUB)

    assert connector.sync_delta.await_args.kwargs["since"] == watermark
