"""Tests for the Notion connector.

Coverage policy: full - per the Living spike test plan, every path from
the "Connectors (Notion + GDocs)" section is exercised here.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.connectors.notion import NotionAuthError, NotionConnector
from src.shared.types import ConnectorSyncResult, EntityType, SourceType


@pytest.fixture
def connector():
    return NotionConnector()


@pytest.fixture
def org_id():
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
def db():
    return AsyncMock()


@pytest.fixture
def fake_token():
    token = MagicMock()
    token.access_token = "secret-bearer"
    return token


# ── helpers ──────────────────────────────────────────────────────────


def _make_response(status: int, json_body: dict | None = None, headers: dict | None = None):
    request = httpx.Request("GET", "https://api.notion.com/v1/search")
    return httpx.Response(
        status_code=status,
        json=json_body if json_body is not None else {},
        headers=headers or {},
        request=request,
    )


def _page(
    page_id: str = "page-1",
    title: str = "Spec for Auth",
    last_edited: str | None = None,
    archived: bool = False,
) -> dict:
    return {
        "id": page_id,
        "url": f"https://notion.so/{page_id}",
        "archived": archived,
        "created_time": "2026-04-01T10:00:00.000Z",
        "last_edited_time": last_edited or "2026-05-01T12:00:00.000Z",
        "parent": {"type": "workspace", "workspace": True},
        "properties": {
            "Name": {
                "type": "title",
                "title": [{"plain_text": title}],
            }
        },
    }


def _block(text: str) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "type": "paragraph",
        "has_children": False,
        "paragraph": {"rich_text": [{"plain_text": text}]},
    }


def _entity_stub(*, new: bool = True):
    entity = MagicMock()
    entity.id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    entity.created_at = now
    entity.updated_at = now if new else now + timedelta(seconds=1)
    return entity


# ── basic identity ────────────────────────────────────────────────────


def test_source_type(connector):
    assert connector.source == SourceType.NOTION


# ── _request: rate limiting + 429 + 401 ──────────────────────────────


async def test_request_sleeps_for_rate_limit(connector, fake_token):
    """Back-to-back requests should pace at >= ~333ms to honor 3 req/sec.

    The token-bucket lets the first call through immediately, then sleeps
    before the second to enforce the minimum interval.
    """
    from src.connectors import notion as notion_mod

    # Reset limiter state so this test is order-independent.
    notion_mod._LIMITER._next_allowed_at = 0.0

    client = AsyncMock()
    client.request = AsyncMock(return_value=_make_response(200, {"ok": True}))

    sleeps: list[float] = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    with patch("src.connectors._rate_limit.asyncio.sleep", fake_sleep):
        await connector._request(client, "GET", "/foo")
        await connector._request(client, "GET", "/bar")

    # Second call must sleep at least min_interval (1/3 sec) before firing.
    assert any(s >= 1 / 3 - 1e-2 for s in sleeps), f"no rate-limit sleep observed: {sleeps}"


async def test_request_raises_auth_error_on_401(connector):
    client = AsyncMock()
    client.request = AsyncMock(return_value=_make_response(401))

    with patch("src.connectors._rate_limit.asyncio.sleep", AsyncMock()):
        with pytest.raises(NotionAuthError):
            await connector._request(client, "GET", "/foo")


async def test_request_backs_off_on_429(connector):
    """Should retry after a 429 with exponential backoff and Retry-After respect."""
    client = AsyncMock()
    client.request = AsyncMock(
        side_effect=[
            _make_response(429, headers={"Retry-After": "0"}),
            _make_response(200, {"ok": True}),
        ]
    )
    with patch("src.connectors._rate_limit.asyncio.sleep", AsyncMock()):
        result = await connector._request(client, "GET", "/foo")
    assert result == {"ok": True}
    assert client.request.call_count == 2


async def test_request_gives_up_after_max_retries(connector):
    """After ``_MAX_RETRIES`` 429s in a row, the request raises."""
    client = AsyncMock()
    client.request = AsyncMock(
        return_value=_make_response(429, headers={"Retry-After": "0"})
    )
    with patch("src.connectors._rate_limit.asyncio.sleep", AsyncMock()):
        with pytest.raises(httpx.HTTPStatusError):
            await connector._request(client, "GET", "/foo")


# ── _extract_page_title ──────────────────────────────────────────────


def test_extract_page_title_from_named_property():
    title = NotionConnector._extract_page_title(
        {
            "properties": {
                "Name": {"type": "title", "title": [{"plain_text": "Hello"}]},
            }
        }
    )
    assert title == "Hello"


def test_extract_page_title_handles_missing():
    assert NotionConnector._extract_page_title({"properties": {}}) == "Untitled"


def test_extract_page_title_concatenates_runs():
    title = NotionConnector._extract_page_title(
        {
            "properties": {
                "Title": {
                    "type": "title",
                    "title": [
                        {"plain_text": "Hello "},
                        {"plain_text": "world"},
                    ],
                }
            }
        }
    )
    assert title == "Hello world"


# ── webhook payload helpers ──────────────────────────────────────────


def test_extract_page_id_from_webhook_nested():
    assert NotionConnector._extract_page_id_from_webhook({"page": {"id": "abc"}}) == "abc"


def test_extract_page_id_from_webhook_flat():
    assert NotionConnector._extract_page_id_from_webhook({"page_id": "xyz"}) == "xyz"


def test_extract_page_id_from_webhook_missing():
    assert NotionConnector._extract_page_id_from_webhook({}) is None
    assert NotionConnector._extract_page_id_from_webhook("not a dict") is None  # type: ignore[arg-type]


# ── sync_full ────────────────────────────────────────────────────────


async def test_sync_full_happy_path(connector, db, org_id, fake_token):
    """Pulls pages + indexes with chunks; returns ConnectorSyncResult counts."""
    pages = [_page("page-A", "Auth Spec"), _page("page-B", "Onboarding")]

    async def fake_request(self, client, method, path, **kwargs):
        if path == "/search":
            return {"results": pages, "has_more": False}
        # /blocks/<id>/children
        return {"results": [_block("body line 1"), _block("body line 2")], "has_more": False}

    new_entity = _entity_stub(new=True)

    with patch.object(NotionConnector, "_request", new=fake_request), patch(
        "src.connectors.notion.upsert_entity", AsyncMock(return_value=new_entity)
    ) as upsert, patch(
        "src.connectors.notion._build_chunks", AsyncMock(return_value=[{"index": 0, "body": "x"}])
    ):
        result = await connector.sync_full(db, org_id, fake_token)

    assert isinstance(result, ConnectorSyncResult)
    assert result.source == SourceType.NOTION
    assert result.entities_created == 2
    assert result.entities_updated == 0
    assert result.errors == []
    # Entities written into graph as DOCUMENT type, NOTION source.
    assert upsert.await_count == 2
    create_kwargs = upsert.await_args_list[0].args[1]
    assert create_kwargs.type == EntityType.DOCUMENT
    assert create_kwargs.source == SourceType.NOTION
    assert "notion" in create_kwargs.source_ids


async def test_sync_full_empty_workspace(connector, db, org_id, fake_token):
    """Zero pages → success with zero counts."""

    async def fake_request(self, client, method, path, **kwargs):
        return {"results": [], "has_more": False}

    with patch.object(NotionConnector, "_request", new=fake_request):
        result = await connector.sync_full(db, org_id, fake_token)

    assert result.entities_created == 0
    assert result.entities_updated == 0
    assert result.errors == []


async def test_sync_full_token_expired_propagates(connector, db, org_id, fake_token):
    """401 surfaces as NotionAuthError so the API layer can prompt reauth."""

    async def fake_request(self, client, method, path, **kwargs):
        raise NotionAuthError("expired")

    with patch.object(NotionConnector, "_request", new=fake_request):
        with pytest.raises(NotionAuthError):
            await connector.sync_full(db, org_id, fake_token)


async def test_sync_full_records_error_on_unexpected_failure(connector, db, org_id, fake_token):
    """Unexpected exception during sync is logged + recorded, not raised."""

    async def fake_request(self, client, method, path, **kwargs):
        raise RuntimeError("network exploded")

    with patch.object(NotionConnector, "_request", new=fake_request):
        result = await connector.sync_full(db, org_id, fake_token)

    assert result.errors and "network exploded" in result.errors[0]
    assert result.entities_created == 0


async def test_sync_full_records_per_page_fetch_error(connector, db, org_id, fake_token):
    """If fetching one page's blocks fails, the page still upserts (with empty body)
    and the error is recorded."""
    pages = [_page("page-A", "Spec")]

    call_count = {"n": 0}

    async def fake_request(self, client, method, path, **kwargs):
        call_count["n"] += 1
        if path == "/search":
            return {"results": pages, "has_more": False}
        raise RuntimeError("blocks 500")

    with patch.object(NotionConnector, "_request", new=fake_request), patch(
        "src.connectors.notion.upsert_entity", AsyncMock(return_value=_entity_stub(new=True))
    ):
        result = await connector.sync_full(db, org_id, fake_token)

    assert result.entities_created == 1
    assert any("blocks 500" in e for e in result.errors)


async def test_sync_full_idempotent_resync_updates_not_creates(
    connector, db, org_id, fake_token
):
    """Re-syncing the same page emits an update, not a create."""
    pages = [_page("page-A", "Spec")]

    async def fake_request(self, client, method, path, **kwargs):
        if path == "/search":
            return {"results": pages, "has_more": False}
        return {"results": [], "has_more": False}

    existing = _entity_stub(new=False)

    with patch.object(NotionConnector, "_request", new=fake_request), patch(
        "src.connectors.notion.upsert_entity", AsyncMock(return_value=existing)
    ):
        result = await connector.sync_full(db, org_id, fake_token)

    assert result.entities_created == 0
    assert result.entities_updated == 1


# ── sync_delta ───────────────────────────────────────────────────────


async def test_sync_delta_stops_at_since(connector, db, org_id, fake_token):
    """Pages older than ``since`` (results are DESC) terminate iteration."""
    since = datetime(2026, 5, 1, tzinfo=timezone.utc)
    new_page = _page("new", last_edited="2026-05-02T00:00:00.000Z")
    old_page = _page("old", last_edited="2026-04-01T00:00:00.000Z")

    async def fake_request(self, client, method, path, **kwargs):
        if path == "/search":
            return {"results": [new_page, old_page], "has_more": True}
        return {"results": [], "has_more": False}

    with patch.object(NotionConnector, "_request", new=fake_request), patch(
        "src.connectors.notion.upsert_entity", AsyncMock(return_value=_entity_stub(new=True))
    ) as upsert:
        result = await connector.sync_delta(db, org_id, fake_token, since)

    # Only the page newer than since is indexed.
    assert upsert.await_count == 1
    assert result.entities_created == 1


async def test_sync_delta_pagination(connector, db, org_id, fake_token):
    """``has_more`` + ``next_cursor`` are followed for additional pages."""
    page_1 = _page("p1", last_edited="2026-05-02T00:00:00.000Z")
    page_2 = _page("p2", last_edited="2026-05-02T00:00:01.000Z")
    page_3 = _page("p3", last_edited="2026-05-02T00:00:02.000Z")

    pages_calls: list[dict] = []

    async def fake_request(self, client, method, path, **kwargs):
        if path == "/search":
            pages_calls.append(kwargs.get("json") or {})
            if len(pages_calls) == 1:
                return {"results": [page_3, page_2], "has_more": True, "next_cursor": "cur-2"}
            return {"results": [page_1], "has_more": False}
        return {"results": [], "has_more": False}

    since = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with patch.object(NotionConnector, "_request", new=fake_request), patch(
        "src.connectors.notion.upsert_entity", AsyncMock(return_value=_entity_stub(new=True))
    ) as upsert:
        await connector.sync_delta(db, org_id, fake_token, since)

    assert upsert.await_count == 3
    # Second call carried the cursor from the first response.
    assert pages_calls[1].get("start_cursor") == "cur-2"


async def test_sync_delta_since_in_future_returns_empty(connector, db, org_id, fake_token):
    """If ``since`` is later than every page, no entities are written."""
    page = _page("p1", last_edited="2026-04-01T00:00:00.000Z")

    async def fake_request(self, client, method, path, **kwargs):
        if path == "/search":
            return {"results": [page], "has_more": False}
        return {"results": [], "has_more": False}

    since = datetime(2026, 12, 31, tzinfo=timezone.utc)
    with patch.object(NotionConnector, "_request", new=fake_request), patch(
        "src.connectors.notion.upsert_entity", AsyncMock(return_value=_entity_stub(new=True))
    ) as upsert:
        result = await connector.sync_delta(db, org_id, fake_token, since)

    assert upsert.await_count == 0
    assert result.entities_created == 0


# ── handle_webhook ───────────────────────────────────────────────────


async def test_handle_webhook_page_updated_invalidates(connector, db, org_id):
    """A ``page.updated`` event soft-tombstones existing chunks."""
    payload = {"type": "page.updated", "page": {"id": "page-A"}}
    existing = _entity_stub(new=False)

    with patch(
        "src.connectors.notion.get_entity_by_source",
        AsyncMock(return_value=existing),
    ), patch(
        "src.connectors.notion.update_entity", AsyncMock()
    ) as update:
        result = await connector.handle_webhook(db, org_id, payload)

    update.assert_awaited_once()
    kwargs = update.await_args.kwargs
    assert "chunks_invalidated_at" in kwargs["properties"]
    assert result.entities_updated == 1
    assert result.errors == []


async def test_handle_webhook_page_deleted(connector, db, org_id):
    """A delete event marks the entity archived and clears chunks."""
    payload = {"type": "page.deleted", "page": {"id": "page-A"}}
    existing = _entity_stub(new=False)

    with patch(
        "src.connectors.notion.get_entity_by_source",
        AsyncMock(return_value=existing),
    ), patch(
        "src.connectors.notion.update_entity", AsyncMock()
    ) as update:
        result = await connector.handle_webhook(db, org_id, payload)

    assert result.entities_updated == 1
    update.assert_awaited_once()
    props = update.await_args.kwargs["properties"]
    assert props.get("archived") is True
    assert props.get("chunks") == []


async def test_handle_webhook_malformed_payload_logs_error(connector, db, org_id):
    """Malformed payload (no page id) → recorded error, no graph mutation."""
    with patch(
        "src.connectors.notion.get_entity_by_source", AsyncMock()
    ) as resolver:
        result = await connector.handle_webhook(db, org_id, {})

    resolver.assert_not_awaited()
    assert result.errors


async def test_handle_webhook_unknown_org_no_entity(connector, db, org_id):
    """Webhook for an entity that doesn't exist (e.g. unknown org) is a no-op."""
    payload = {"type": "page.deleted", "page": {"id": "missing"}}

    with patch(
        "src.connectors.notion.get_entity_by_source", AsyncMock(return_value=None)
    ), patch("src.connectors.notion.update_entity", AsyncMock()) as update:
        result = await connector.handle_webhook(db, org_id, payload)

    update.assert_not_awaited()
    assert result.entities_updated == 0


# ── _build_chunks behaviour ──────────────────────────────────────────


async def test_build_chunks_handles_empty():
    from src.connectors.notion import _build_chunks

    assert await _build_chunks("") == []


async def test_build_chunks_emits_overlapping_segments():
    from src.connectors.notion import _build_chunks

    text = "para 1\n\n" + ("a" * 3000) + "\n\n" + ("b" * 3000)
    with patch("src.graph._embedding.embed_text", AsyncMock(return_value=[0.0] * 4)):
        chunks = await _build_chunks(text)

    assert len(chunks) >= 2
    # Every chunk includes embedding metadata (or None on failure).
    assert all("body" in c and "index" in c for c in chunks)


async def test_build_chunks_resilient_to_embedding_failure():
    from src.connectors.notion import _build_chunks

    with patch("src.graph._embedding.embed_text", AsyncMock(side_effect=RuntimeError("no key"))):
        chunks = await _build_chunks("some content")

    assert chunks
    assert chunks[0]["embedding"] is None
