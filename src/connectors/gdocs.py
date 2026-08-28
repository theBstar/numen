"""Google Docs connector -- ingests documents from a workspace into the graph.

Discovery via Drive API (``files.list`` with ``mimeType=application/vnd.google-apps.document``),
content via Docs API (``documents.get``). Same chunking + embedding pattern
as the Notion connector. Bearer-token auth via ``OAuthToken``.

Honors a soft 3 req/sec rate limit with exponential backoff on 429 / 403
quota responses, mirroring the Notion connector.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from src.connectors._rate_limit import RateLimiter
from src.connectors.base import BaseConnector
from src.connectors.notion import _build_chunks, _now_iso, _parse_iso  # reuse helpers
from src.connectors.schemas.gdocs import GDocsDocumentProperties
from src.graph import (
    get_entity_by_source,
    update_entity,
    upsert_entity,
)
from src.shared.models import OAuthToken
from src.shared.types import (
    ConnectorSyncResult,
    EntityCreate,
    EntityType,
    SourceType,
)

logger = logging.getLogger(__name__)

DRIVE_API = "https://www.googleapis.com/drive/v3"
DOCS_API = "https://docs.googleapis.com/v1"

_MIN_INTERVAL_SECONDS = 1.0 / 3.0
_MAX_RETRIES = 5

_LIMITER = RateLimiter(
    requests_per_second=1.0 / _MIN_INTERVAL_SECONDS,
    max_retries=_MAX_RETRIES,
    name="gdocs",
)

GDOC_MIME = "application/vnd.google-apps.document"


class GDocsAuthError(RuntimeError):
    """Raised when Google returns 401 - the OAuth token is invalid/expired."""


class GDocsConnector(BaseConnector):
    source = SourceType.GDOCS

    # ── public interface ──────────────────────────────────────────────

    async def sync_full(
        self,
        db: AsyncSession,
        org_id: UUID,
        token: OAuthToken,
    ) -> ConnectorSyncResult:
        result = ConnectorSyncResult(source=self.source)
        try:
            async with self._make_http_client(token) as client:
                async for doc in self._iter_documents(client, since=None):
                    await self._index_document(db, org_id, client, doc, result)
        except GDocsAuthError:
            raise
        except Exception as exc:
            msg = f"gdocs full sync error: {exc}"
            logger.exception(msg)
            result.errors.append(msg)
        logger.info(
            "gdocs full sync org=%s entities=%d/%d errors=%d",
            org_id,
            result.entities_created,
            result.entities_updated,
            len(result.errors),
        )
        return result

    async def sync_delta(
        self,
        db: AsyncSession,
        org_id: UUID,
        token: OAuthToken,
        since: datetime,
    ) -> ConnectorSyncResult:
        result = ConnectorSyncResult(source=self.source)
        try:
            async with self._make_http_client(token) as client:
                async for doc in self._iter_documents(client, since=since):
                    await self._index_document(db, org_id, client, doc, result)
        except GDocsAuthError:
            raise
        except Exception as exc:
            msg = f"gdocs delta sync error: {exc}"
            logger.exception(msg)
            result.errors.append(msg)
        logger.info(
            "gdocs delta sync org=%s since=%s entities=%d/%d errors=%d",
            org_id,
            since.isoformat(),
            result.entities_created,
            result.entities_updated,
            len(result.errors),
        )
        return result

    async def handle_webhook(
        self,
        db: AsyncSession,
        org_id: UUID,
        payload: dict,
    ) -> ConnectorSyncResult:
        """Handle a Drive change notification.

        Drive push notifications carry the file id in headers
        (``X-Goog-Resource-Id``) on the wire; the API layer normalizes those
        into the payload before calling this method. We accept either
        ``{file_id}`` or ``{resource_id}`` keys.
        """
        result = ConnectorSyncResult(source=self.source)
        file_id = (
            payload.get("file_id")
            or payload.get("fileId")
            or payload.get("resource_id")
            or payload.get("resourceId")
            or payload.get("id")
        )
        if not file_id:
            msg = "gdocs webhook: missing file id"
            logger.warning("%s payload=%s", msg, payload)
            result.errors.append(msg)
            return result

        change_type = (payload.get("change_type") or payload.get("event_type") or "").lower()

        try:
            if change_type in ("trash", "trashed", "remove", "removed", "delete", "deleted"):
                await self._mark_doc_deleted(db, org_id, str(file_id), result)
            else:
                # Soft-tombstone existing chunks so retrieval can't serve
                # stale content while next sync_delta pulls fresh body.
                entity = await get_entity_by_source(
                    db, org_id, SourceType.GDOCS, str(file_id)
                )
                if entity is not None:
                    await update_entity(
                        db,
                        entity.id,
                        org_id=org_id,
                        properties={"chunks_invalidated_at": _now_iso()},
                        merge_properties=True,
                    )
                    result.entities_updated += 1
        except Exception as exc:
            msg = f"gdocs webhook error: {exc}"
            logger.exception(msg)
            result.errors.append(msg)

        return result

    # ── internal: document iteration ─────────────────────────────────

    async def _iter_documents(
        self,
        client: httpx.AsyncClient,
        since: datetime | None,
    ):
        """Yield Drive ``file`` resources for Google Docs in modifiedTime DESC order."""
        query_parts = [f"mimeType='{GDOC_MIME}'", "trashed=false"]
        if since is not None:
            since_iso = since.strftime("%Y-%m-%dT%H:%M:%S")
            query_parts.append(f"modifiedTime > '{since_iso}'")
        q = " and ".join(query_parts)

        page_token: str | None = None
        while True:
            params: dict[str, Any] = {
                "q": q,
                "pageSize": 100,
                "fields": (
                    "nextPageToken, files(id, name, mimeType, modifiedTime, "
                    "createdTime, webViewLink, "
                    "owners(displayName, emailAddress), trashed)"
                ),
                "orderBy": "modifiedTime desc",
            }
            if page_token:
                params["pageToken"] = page_token

            data = await self._request(
                client, "GET", f"{DRIVE_API}/files", params=params
            )
            for file_obj in data.get("files", []) or []:
                yield file_obj

            page_token = data.get("nextPageToken")
            if not page_token:
                break

    # ── internal: index one doc ──────────────────────────────────────

    async def _index_document(
        self,
        db: AsyncSession,
        org_id: UUID,
        client: httpx.AsyncClient,
        file_obj: dict,
        result: ConnectorSyncResult,
    ) -> None:
        file_id = file_obj.get("id")
        if not file_id:
            return

        title = file_obj.get("name") or f"Google Doc {file_id}"
        content = ""
        try:
            content = await self._fetch_doc_text(client, file_id)
        except Exception as exc:
            logger.warning("gdocs fetch_doc_text failed file=%s: %s", file_id, exc)
            result.errors.append(f"gdocs doc fetch error {file_id}: {exc}")

        chunks = await _build_chunks(content) if content else []

        owners = [
            (owner.get("emailAddress") or owner.get("displayName") or "")
            for owner in (file_obj.get("owners") or [])
            if isinstance(owner, dict)
        ]
        owners = [o for o in owners if o]

        properties = GDocsDocumentProperties(
            title=title,
            url=file_obj.get("webViewLink"),
            created_time=file_obj.get("createdTime"),
            modified_time=file_obj.get("modifiedTime"),
            chunk_count=len(chunks),
            chunks=chunks,
            mime_type=file_obj.get("mimeType"),
            owners=owners,
        ).model_dump(exclude_none=True)

        entity = await upsert_entity(
            db,
            EntityCreate(
                org_id=org_id,
                type=EntityType.DOCUMENT,
                source=SourceType.GDOCS,
                source_ids={"gdocs": file_id},
                canonical_name=title,
                properties=properties,
            ),
        )
        was_new = entity.created_at == entity.updated_at
        if was_new:
            result.entities_created += 1
        else:
            result.entities_updated += 1

    async def _fetch_doc_text(
        self, client: httpx.AsyncClient, document_id: str
    ) -> str:
        """Pull the document and concatenate text runs into a markdown-ish blob."""
        data = await self._request(
            client, "GET", f"{DOCS_API}/documents/{document_id}"
        )
        body = data.get("body") or {}
        content = body.get("content") or []
        return _flatten_doc_content(content)

    async def _mark_doc_deleted(
        self,
        db: AsyncSession,
        org_id: UUID,
        file_id: str,
        result: ConnectorSyncResult,
    ) -> None:
        entity = await get_entity_by_source(db, org_id, SourceType.GDOCS, file_id)
        if entity is None:
            return
        await update_entity(
            db,
            entity.id,
            org_id=org_id,
            properties={
                "trashed": True,
                "chunks": [],
                "chunk_count": 0,
                "deleted_at": _now_iso(),
            },
            merge_properties=True,
        )
        result.entities_updated += 1

    # ── HTTP helpers ──────────────────────────────────────────────────

    @staticmethod
    def _make_http_client(token: OAuthToken) -> httpx.AsyncClient:  # type: ignore[override]
        return httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {token.access_token}",
                "Accept": "application/json",
            },
            timeout=httpx.Timeout(30.0, connect=10.0),
        )

    async def _request(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        *,
        params: dict | None = None,
        json: dict | None = None,
    ) -> dict:
        return await _LIMITER.request_json(
            client,
            method,
            url,
            params=params,
            json=json,
            retry_on_status={429},
            raise_on_status={401: GDocsAuthError},
            is_retryable_403=_is_quota_error,
        )

        raise RuntimeError("gdocs request exhausted retries")


# ── module-level helpers ────────────────────────────────────────────


def _is_quota_error(response: httpx.Response) -> bool:
    try:
        body = response.json()
    except ValueError:
        return False
    err = body.get("error") if isinstance(body, dict) else None
    if not isinstance(err, dict):
        return False
    reasons = {
        item.get("reason", "")
        for item in err.get("errors", []) or []
        if isinstance(item, dict)
    }
    return bool(reasons & {"rateLimitExceeded", "userRateLimitExceeded"})


def _flatten_doc_content(content: list[dict]) -> str:
    """Walk a Docs API ``body.content`` list, concatenating text runs."""
    parts: list[str] = []
    for element in content or []:
        if not isinstance(element, dict):
            continue
        paragraph = element.get("paragraph")
        if isinstance(paragraph, dict):
            parts.append(_paragraph_text(paragraph))
            continue
        table = element.get("table")
        if isinstance(table, dict):
            parts.append(_table_text(table))
            continue
        toc = element.get("tableOfContents")
        if isinstance(toc, dict):
            parts.append(_flatten_doc_content(toc.get("content") or []))
    return "\n".join(p for p in parts if p)


def _paragraph_text(paragraph: dict) -> str:
    parts: list[str] = []
    for elem in paragraph.get("elements", []) or []:
        if not isinstance(elem, dict):
            continue
        text_run = elem.get("textRun")
        if isinstance(text_run, dict):
            parts.append(text_run.get("content", ""))
    joined = "".join(parts)
    return joined.rstrip("\n")


def _table_text(table: dict) -> str:
    rows: list[str] = []
    for row in table.get("tableRows", []) or []:
        if not isinstance(row, dict):
            continue
        cells: list[str] = []
        for cell in row.get("tableCells", []) or []:
            if not isinstance(cell, dict):
                continue
            cell_text = _flatten_doc_content(cell.get("content") or [])
            cells.append(cell_text.replace("\n", " ").strip())
        rows.append(" | ".join(cells))
    return "\n".join(rows)


# Suppress the unused parse helper import warning - re-exported for tests.
__all__ = ["GDocsConnector", "GDocsAuthError"]
_ = _parse_iso  # keep import alive for tests / future delta-since logic
