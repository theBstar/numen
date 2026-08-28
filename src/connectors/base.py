"""Abstract base class for all Numen ingestion connectors."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.models import OAuthToken
from src.shared.types import ConnectorSyncResult, SourceType

logger = logging.getLogger(__name__)


class BaseConnector(ABC):
    """Base class that every source connector must extend.

    Each concrete connector sets ``source`` to its SourceType and implements
    the three sync entry-points: full sync, delta sync, and webhook handling.
    """

    source: SourceType

    # ── abstract interface ────────────────────────────────────────────

    @abstractmethod
    async def sync_full(
        self,
        db: AsyncSession,
        org_id: UUID,
        token: OAuthToken,
    ) -> ConnectorSyncResult:
        """Full initial sync - pull all data from the source.

        Must NOT call ``db.commit()``; the caller owns the transaction.
        """

    @abstractmethod
    async def sync_delta(
        self,
        db: AsyncSession,
        org_id: UUID,
        token: OAuthToken,
        since: datetime,
    ) -> ConnectorSyncResult:
        """Incremental sync - pull changes since *since*.

        Must NOT call ``db.commit()``; the caller owns the transaction.
        """

    @abstractmethod
    async def handle_webhook(
        self,
        db: AsyncSession,
        org_id: UUID,
        payload: dict,
    ) -> ConnectorSyncResult:
        """Process an inbound webhook event from the source.

        Must NOT call ``db.commit()``; the caller owns the transaction.
        """

    # ── helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _make_http_client(token: OAuthToken) -> httpx.AsyncClient:
        """Return an ``httpx.AsyncClient`` with the OAuth bearer token set.

        The caller is responsible for closing the client (use ``async with``).
        """
        return httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {token.access_token}",
                "Accept": "application/json",
            },
            timeout=httpx.Timeout(30.0, connect=10.0),
        )
