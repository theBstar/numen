"""A failed audit write must not take the caller's request down with it.

`log_action_safely` caught the exception and logged a warning, but left the
session in SQLAlchemy's pending-rollback state, so the next statement raised
PendingRollbackError. Against a live stack that turned every unauthenticated
request to an org route into a 500 instead of a 401: the audit row referenced
an org that does not exist, the foreign key rejected it, and the poisoned
session failed the real query afterwards.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from src.shared.audit import log_action, log_action_safely


def _session(*, flush_fails: bool = False):
    db = AsyncMock()
    db.add = MagicMock()
    db.rollback = AsyncMock()
    savepoint = AsyncMock()
    savepoint.__aenter__ = AsyncMock(return_value=savepoint)
    savepoint.__aexit__ = AsyncMock(return_value=False)
    db.begin_nested = MagicMock(return_value=savepoint)
    if flush_fails:
        db.flush = AsyncMock(
            side_effect=IntegrityError("INSERT", {}, Exception("fk violation"))
        )
    else:
        db.flush = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_a_failed_audit_write_is_swallowed():
    db = _session(flush_fails=True)

    await log_action_safely(db, org_id=uuid4(), action="test.action")

    # No exception reached the caller.
    db.add.assert_called_once()


@pytest.mark.asyncio
async def test_a_failed_audit_write_leaves_the_session_usable():
    """The whole point: the caller's own query must still work afterwards.

    Without a savepoint the failed flush poisons the session and the next
    statement raises PendingRollbackError.
    """
    db = _session(flush_fails=True)

    await log_action_safely(db, org_id=uuid4(), action="test.action")

    assert db.begin_nested.called, (
        "the audit insert must run inside a savepoint so its failure cannot "
        "poison the caller's transaction"
    )


@pytest.mark.asyncio
async def test_a_successful_audit_write_still_records():
    db = _session()

    await log_action_safely(db, org_id=uuid4(), action="test.action")

    db.add.assert_called_once()
    db.flush.assert_awaited()


@pytest.mark.asyncio
async def test_cancellation_still_propagates():
    """Task cancellation must not be swallowed as an audit failure."""
    db = _session()
    db.flush = AsyncMock(side_effect=asyncio.CancelledError())

    with pytest.raises(asyncio.CancelledError):
        await log_action_safely(db, org_id=uuid4(), action="test.action")


@pytest.mark.asyncio
async def test_log_action_itself_still_raises():
    """The strict variant keeps propagating - callers that need the row rely on it."""
    db = _session(flush_fails=True)

    with pytest.raises(IntegrityError):
        await log_action(db, org_id=uuid4(), action="test.action")
