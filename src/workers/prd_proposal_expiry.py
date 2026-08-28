"""Daily worker: expire pending PRD proposals past their deadline (WS1).

Runs from the same scheduler as briefing/sync workers. Idempotent.
"""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.services.proposals import expire_stale_proposals

logger = logging.getLogger(__name__)


async def run_expiry_sweep(session_factory: async_sessionmaker[AsyncSession]) -> int:
    """Entrypoint for cron/celery beat. Returns count of proposals expired."""
    async with session_factory() as db:
        n = await expire_stale_proposals(db)
    logger.info("prd_proposal expiry sweep: expired=%d", n)
    return n
