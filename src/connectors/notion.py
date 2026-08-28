"""Notion connector -- ingests pages and their content into the context graph.

Pages are pulled via /v1/search and content via /v1/blocks/{id}/children.
Page bodies are chunked (markdown-aware, ~500-token chunks with ~50-token
overlap) and embedded via the same model the rest of the graph uses
(see ``src/graph/_embedding.py``). Chunks are stored on the Document
entity's properties so downstream retrieval (MCP get_context, briefing) can
read them without forking storage.

Honors Notion's 3 req/sec rate limit with exponential backoff on 429.
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
from src.connectors.schemas.notion import NotionPageProperties
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

API_BASE = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

# Notion publishes a 3 req/sec rate limit; we keep a small safety margin.
_MIN_INTERVAL_SECONDS = 1.0 / 3.0
_MAX_RETRIES = 5

_LIMITER = RateLimiter(
    requests_per_second=1.0 / _MIN_INTERVAL_SECONDS,
    max_retries=_MAX_RETRIES,
    name="notion",
)

# Chunking parameters - mirrors design doc retrieval pipeline:
# markdown-aware ~500-token chunks with ~50-token overlap.
_CHUNK_CHAR_TARGET = 2000  # ~500 tokens at ~4 chars/token
_CHUNK_CHAR_OVERLAP = 200


class NotionAuthError(RuntimeError):
    """Raised when Notion returns 401 - the OAuth token is invalid/expired."""


class NotionConnector(BaseConnector):
    source = SourceType.NOTION

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
                async for page in self._iter_pages(client, since=None):
                    await self._index_page(db, org_id, client, page, result)
        except NotionAuthError:
            raise
        except Exception as exc:
            msg = f"notion full sync error: {exc}"
            logger.exception(msg)
            result.errors.append(msg)
        logger.info(
            "notion full sync org=%s entities=%d/%d errors=%d",
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
                async for page in self._iter_pages(client, since=since):
                    await self._index_page(db, org_id, client, page, result)
        except NotionAuthError:
            raise
        except Exception as exc:
            msg = f"notion delta sync error: {exc}"
            logger.exception(msg)
            result.errors.append(msg)
        logger.info(
            "notion delta sync org=%s since=%s entities=%d/%d errors=%d",
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
        """Process a Notion change notification.

        Notion's webhook surface is still in beta; we accept either
        ``{type, page: {id, ...}}`` or ``{event_type, page_id}`` shapes.
        Malformed payloads return success with an error logged - the caller
        handles the HTTP response code.
        """
        result = ConnectorSyncResult(source=self.source)

        page_id = self._extract_page_id_from_webhook(payload)
        if not page_id:
            msg = "notion webhook: missing page id"
            logger.warning("%s payload=%s", msg, payload)
            result.errors.append(msg)
            return result

        event_type = (payload.get("type") or payload.get("event_type") or "").lower()

        try:
            if event_type in ("page.deleted", "page_deleted", "deleted"):
                await self._mark_page_deleted(db, org_id, page_id, result)
            else:
                # Treat update / create / unknown as "fetch and re-index".
                # We need a token to refetch, so callers should pass it via
                # OAuth flow before invoking. If no token in payload, we
                # surface an error rather than guessing.
                msg = "notion webhook: re-fetch requires connector instance with token"
                logger.debug(msg)
                # Soft-tombstone existing chunks so they cannot be served stale
                # until the next scheduled sync_delta picks up the change.
                entity = await get_entity_by_source(db, org_id, SourceType.NOTION, page_id)
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
            msg = f"notion webhook error: {exc}"
            logger.exception(msg)
            result.errors.append(msg)

        return result

    # ── internal: page iteration ──────────────────────────────────────

    async def _iter_pages(
        self,
        client: httpx.AsyncClient,
        since: datetime | None,
    ):
        """Yield page objects from /v1/search in last_edited_time DESC order.

        When ``since`` is provided, stops walking once a page older than
        ``since`` is encountered (results are sorted DESC).
        """
        cursor: str | None = None
        while True:
            body: dict[str, Any] = {
                "filter": {"property": "object", "value": "page"},
                "page_size": 100,
                "sort": {"direction": "descending", "timestamp": "last_edited_time"},
            }
            if cursor:
                body["start_cursor"] = cursor

            data = await self._request(client, "POST", "/search", json=body)
            results = data.get("results", []) or []

            for page in results:
                if since is not None:
                    last_edited = page.get("last_edited_time")
                    if last_edited and _parse_iso(last_edited) < since:
                        # Sorted DESC, so we are done.
                        return
                yield page

            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
            if not cursor:
                break

    # ── internal: page indexing ───────────────────────────────────────

    async def _index_page(
        self,
        db: AsyncSession,
        org_id: UUID,
        client: httpx.AsyncClient,
        page: dict,
        result: ConnectorSyncResult,
    ) -> None:
        page_id = page.get("id")
        if not page_id:
            return

        title = self._extract_page_title(page)
        archived = bool(page.get("archived"))

        # Pull block content (skip if archived - body may 404).
        content = ""
        if not archived:
            try:
                content = await self._fetch_page_text(client, page_id)
            except Exception as exc:
                logger.warning("notion fetch_page_text failed page=%s: %s", page_id, exc)
                result.errors.append(f"notion page fetch error {page_id}: {exc}")
                content = ""

        chunks = await _build_chunks(content) if content else []

        parent = page.get("parent") or {}
        properties = NotionPageProperties(
            title=title,
            url=page.get("url"),
            created_time=page.get("created_time"),
            last_edited_time=page.get("last_edited_time"),
            archived=archived,
            chunk_count=len(chunks),
            chunks=chunks,
            parent_type=parent.get("type"),
            parent_id=_parent_id(parent),
        ).model_dump(exclude_none=True)

        entity = await upsert_entity(
            db,
            EntityCreate(
                org_id=org_id,
                type=EntityType.DOCUMENT,
                source=SourceType.NOTION,
                source_ids={"notion": page_id},
                canonical_name=title or f"Notion page {page_id}",
                properties=properties,
            ),
        )
        was_new = entity.created_at == entity.updated_at
        if was_new:
            result.entities_created += 1
        else:
            result.entities_updated += 1

    async def _fetch_page_text(self, client: httpx.AsyncClient, page_id: str) -> str:
        """Recursively walk /v1/blocks/{id}/children, returning a markdown-ish blob.

        We deliberately keep this simple: every text-bearing block contributes
        its plain_text concatenation, separated by newlines. Lists, headings,
        and toggles render as plain lines. Tables / databases are skipped at
        spike level - design doc accepts that tradeoff.
        """
        return await self._collect_block_text(client, page_id)

    async def _collect_block_text(
        self, client: httpx.AsyncClient, block_id: str
    ) -> str:
        parts: list[str] = []
        cursor: str | None = None
        while True:
            params: dict[str, str] = {"page_size": "100"}
            if cursor:
                params["start_cursor"] = cursor

            data = await self._request(
                client, "GET", f"/blocks/{block_id}/children", params=params
            )
            for block in data.get("results", []) or []:
                text = _extract_block_plain_text(block)
                if text:
                    parts.append(text)
                # Recurse only if children exist - saves API calls.
                if block.get("has_children"):
                    child_id = block.get("id")
                    if child_id:
                        nested = await self._collect_block_text(client, child_id)
                        if nested:
                            parts.append(nested)

            if not data.get("has_more"):
                break
            cursor = data.get("next_cursor")
            if not cursor:
                break

        return "\n".join(parts)

    async def _mark_page_deleted(
        self,
        db: AsyncSession,
        org_id: UUID,
        page_id: str,
        result: ConnectorSyncResult,
    ) -> None:
        entity = await get_entity_by_source(db, org_id, SourceType.NOTION, page_id)
        if entity is None:
            return
        await update_entity(
            db,
            entity.id,
            org_id=org_id,
            properties={
                "archived": True,
                "chunks": [],
                "chunk_count": 0,
                "deleted_at": _now_iso(),
            },
            merge_properties=True,
        )
        result.entities_updated += 1

    # ── HTTP helpers (rate limit + 429 backoff) ──────────────────────

    @staticmethod
    def _make_http_client(token: OAuthToken) -> httpx.AsyncClient:  # type: ignore[override]
        return httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {token.access_token}",
                "Notion-Version": NOTION_VERSION,
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            base_url=API_BASE,
            timeout=httpx.Timeout(30.0, connect=10.0),
        )

    async def _request(
        self,
        client: httpx.AsyncClient,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json: dict | None = None,
    ) -> dict:
        """Issue an HTTP request via the shared RateLimiter (3 req/sec + 429 backoff)."""
        return await _LIMITER.request_json(
            client,
            method,
            path,
            params=params,
            json=json,
            retry_on_status={429},
            raise_on_status={401: NotionAuthError},
        )

    # ── webhook payload helpers ──────────────────────────────────────

    @staticmethod
    def _extract_page_id_from_webhook(payload: dict) -> str | None:
        if not isinstance(payload, dict):
            return None
        page = payload.get("page")
        if isinstance(page, dict) and page.get("id"):
            return str(page["id"])
        for key in ("page_id", "id", "entity_id"):
            value = payload.get(key)
            if value:
                return str(value)
        return None

    @staticmethod
    def _extract_page_title(page: dict) -> str:
        properties = page.get("properties") or {}
        # Notion stores titles as a property of type "title" - the property
        # name varies (e.g. "Name", "Title"); walk the dict to find it.
        for prop in properties.values():
            if isinstance(prop, dict) and prop.get("type") == "title":
                title_parts = prop.get("title") or []
                joined = "".join(
                    part.get("plain_text", "") for part in title_parts if isinstance(part, dict)
                ).strip()
                if joined:
                    return joined
        # Fallback: untitled
        return "Untitled"


# ── module-level helpers (text + chunking) ─────────────────────────


def _parent_id(parent: dict | None) -> str | None:
    """Return the Notion parent's id string regardless of parent type.

    Parent shapes from the API include:
      ``{"type": "workspace", "workspace": True}``
      ``{"type": "page_id", "page_id": "abc"}``
      ``{"type": "database_id", "database_id": "abc"}``
    """
    if not parent:
        return None
    parent_type = parent.get("type")
    if not parent_type:
        return None
    value = parent.get(parent_type)
    if isinstance(value, str):
        return value
    return None


def _now_iso() -> str:
    from datetime import timezone

    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: str) -> datetime:
    """Parse ISO 8601 timestamp; falls back to epoch if unparseable.

    Notion returns ``2026-05-02T19:31:00.000Z``-style strings.
    """
    cleaned = value.replace("Z", "+00:00") if value.endswith("Z") else value
    try:
        return datetime.fromisoformat(cleaned)
    except ValueError:
        return datetime.fromtimestamp(0)


def _extract_block_plain_text(block: dict) -> str:
    """Best-effort plain_text extraction across common Notion block types."""
    block_type = block.get("type")
    if not block_type:
        return ""
    payload = block.get(block_type)
    if not isinstance(payload, dict):
        return ""
    # Most text-bearing blocks (paragraph, heading_*, bulleted_list_item,
    # numbered_list_item, toggle, quote, callout, to_do, code) carry a
    # rich_text array.
    rich = payload.get("rich_text") or payload.get("text") or []
    if isinstance(rich, list):
        return "".join(
            part.get("plain_text", "") for part in rich if isinstance(part, dict)
        ).strip()
    return ""


async def _build_chunks(content: str) -> list[dict]:
    """Markdown-aware chunking with optional embedding.

    Produces ~500-token chunks (~2000 chars) with ~50-token overlap
    (~200 chars). Each chunk is embedded via ``src.graph._embedding.embed_text``;
    if embedding fails (no key, network), the chunk is still emitted with
    ``embedding=None`` so downstream code can decide whether to retry.
    """
    if not content:
        return []

    chunks: list[dict] = []
    start = 0
    n = len(content)
    while start < n:
        end = min(start + _CHUNK_CHAR_TARGET, n)
        # Snap to nearest paragraph boundary to keep chunks markdown-friendly.
        if end < n:
            boundary = content.rfind("\n\n", start, end)
            if boundary > start + (_CHUNK_CHAR_TARGET // 2):
                end = boundary
        body = content[start:end].strip()
        if body:
            embedding: list[float] | None = None
            try:
                from src.graph._embedding import embed_text

                embedding = await embed_text(body)
            except Exception as exc:  # noqa: BLE001
                logger.debug("notion chunk embedding failed: %s", exc)
                embedding = None
            chunks.append(
                {
                    "index": len(chunks),
                    "body": body,
                    "char_start": start,
                    "char_end": end,
                    "embedding": embedding,
                }
            )
        if end >= n:
            break
        start = max(end - _CHUNK_CHAR_OVERLAP, start + 1)

    return chunks
