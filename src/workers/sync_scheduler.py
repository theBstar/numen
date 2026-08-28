"""Background worker that orchestrates periodic delta syncs for all connected orgs."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.connectors.registry import get_connector
from src.shared.database import async_session
from src.shared.models import OAuthToken, Organization, SyncState
from src.shared.types import ConnectorSyncResult, SourceType, SyncStatus

logger = logging.getLogger(__name__)


class SyncScheduler:
    """Polls on a fixed interval and runs delta syncs for every org+connector pair."""

    def __init__(self) -> None:
        self._running: bool = False

    # ── public interface ──────────────────────────────────────────────

    async def run(self) -> None:
        """Main loop — runs every ``settings.sync_interval_seconds``."""
        self._running = True
        logger.info(
            "Starting sync scheduler (interval: %ds)",
            settings.sync_interval_seconds,
        )

        while self._running:
            try:
                await self._sync_all_orgs()
            except Exception as exc:
                logger.error("Sync cycle failed: %s", exc, exc_info=True)

            await asyncio.sleep(settings.sync_interval_seconds)

    def stop(self) -> None:
        self._running = False
        logger.info("Sync scheduler stopped")

    # ── internals ─────────────────────────────────────────────────────

    async def _sync_all_orgs(self) -> None:
        """For each org with connected tools, run a delta sync."""
        async with async_session() as db:
            # Skip demo orgs - they have fake tokens that don't work against real APIs
            demo_result = await db.execute(
                select(Organization.id).where(Organization.is_demo.is_(True))
            )
            demo_org_ids = {row for row in demo_result.scalars().all()}

            # Fetch all active OAuth tokens (one per org+connector pair).
            result = await db.execute(select(OAuthToken))
            tokens: list[OAuthToken] = list(result.scalars().all())

            if not tokens:
                logger.debug("No OAuth tokens found — nothing to sync")
                return

            # Extract IDs eagerly while tokens are still fresh in session
            token_info = [(token.id, token.org_id, token.connector) for token in tokens]

            for token_id, org_id, connector in token_info:
                if org_id in demo_org_ids:
                    continue
                await self._sync_one(db, token_id, org_id, connector)

            await db.commit()

    async def _sync_one(
        self, db: AsyncSession, token_id: UUID, org_id: UUID, source: SourceType
    ) -> None:
        """Run a single delta sync for one org+connector pair."""
        # Re-fetch token fresh to avoid stale ORM state from prior iterations
        token_result = await db.execute(select(OAuthToken).where(OAuthToken.id == token_id))
        token = token_result.scalars().first()
        if token is None:
            logger.warning("Token %s no longer exists — skipping", token_id)
            return

        # Retrieve (or create) the SyncState row.
        sync_state = await self._get_or_create_sync_state(db, org_id, source)

        try:
            connector = get_connector(source)
        except ValueError as exc:
            # An org holds a token for a source Numen cannot ingest. This used to
            # be a debug log, which meant the connector appeared connected in the
            # UI and quietly never synced. Surface it on the sync state instead.
            logger.warning(
                "No connector implementation for source=%s (org=%s) - "
                "the token exists but nothing will sync",
                source.value,
                org_id,
            )
            sync_state.status = SyncStatus.ERROR
            sync_state.error_message = str(exc)[:2000]
            await db.flush()
            return

        # Guard against overlapping syncs.
        if sync_state.status == SyncStatus.SYNCING:
            logger.warning(
                "Sync already in progress for org=%s source=%s — skipping",
                org_id,
                source.value,
            )
            return

        since = sync_state.last_sync_at or datetime(2000, 1, 1, tzinfo=timezone.utc)

        # Mark as syncing.
        sync_state.status = SyncStatus.SYNCING
        sync_state.error_message = None
        await db.flush()

        try:
            sync_result: ConnectorSyncResult = await connector.sync_delta(
                db,
                org_id,
                token,
                since=since,
            )

            # Update sync state on success.
            sync_state.last_sync_at = datetime.now(timezone.utc)
            sync_state.status = SyncStatus.IDLE
            sync_state.error_message = None

            # Emit SyncCompleted event - triggers person detection, link suggestions, etc.
            from src.events import SyncCompleted, bus

            await bus.emit(
                SyncCompleted(
                    db=db,
                    org_id=org_id,
                    source=source,
                    result=sync_result,
                )
            )

            logger.info(
                "Sync completed for org=%s source=%s — "
                "entities_created=%d entities_updated=%d edges_created=%d edges_updated=%d",
                org_id,
                source.value,
                sync_result.entities_created,
                sync_result.entities_updated,
                sync_result.edges_created,
                sync_result.edges_updated,
            )

            if sync_result.errors:
                logger.warning(
                    "Sync for org=%s source=%s had %d errors: %s",
                    org_id,
                    source.value,
                    len(sync_result.errors),
                    sync_result.errors[:5],
                )

        except Exception as exc:
            logger.error(
                "Sync failed for org=%s source=%s: %s",
                org_id,
                source.value,
                exc,
                exc_info=True,
            )
            # Rollback the failed transaction before updating sync state
            await db.rollback()
            sync_state = await self._get_or_create_sync_state(db, org_id, source)
            sync_state.status = SyncStatus.ERROR
            sync_state.error_message = str(exc)[:2000]
            await db.flush()

    async def _get_or_create_sync_state(
        self,
        db: AsyncSession,
        org_id: UUID,
        source: SourceType,
    ) -> SyncState:
        """Return the existing SyncState row or create a fresh one."""
        result = await db.execute(
            select(SyncState).where(
                SyncState.org_id == org_id,
                SyncState.connector == source,
            )
        )
        sync_state = result.scalar_one_or_none()

        if sync_state is None:
            sync_state = SyncState(
                org_id=org_id,
                connector=source,
                status=SyncStatus.IDLE,
            )
            db.add(sync_state)
            await db.flush()

        return sync_state


# Module-level singleton
sync_scheduler = SyncScheduler()
