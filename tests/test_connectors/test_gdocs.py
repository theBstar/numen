"""Tests for the Google Docs connector.

Coverage policy: full - per the Living spike test plan, every path from
the "Connectors (Notion + GDocs)" section is exercised here.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.connectors.gdocs import GDocsAuthError, GDocsConnector, _flatten_doc_content
from src.shared.types import ConnectorSyncResult, EntityType, SourceType


@pytest.fixture
def connector():
    return GDocsConnector()


@pytest.fixture
def org_id():
    return uuid.UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
def db():
    return AsyncMock()


@pytest.fixture
def fake_token():
    token = MagicMock()
    token.access_token = "g-bearer"
    return token


def _make_response(status: int, json_body: dict | None = None, headers: dict | None = None):
    request = httpx.Request("GET", "https://www.googleapis.com/drive/v3/files")
    return httpx.Response(
        status_code=status,
        json=json_body if json_body is not None else {},
        headers=headers or {},
        request=request,
    )


def _file(file_id: str = "doc-1", name: str = "RFC 47", modified: str = "2026-05-01T12:00:00.000Z"):
    return {
        "id": file_id,
        "name": name,
        "mimeType": "application/vnd.google-apps.document",
        "modifiedTime": modified,
        "createdTime": "2026-04-01T10:00:00.000Z",
        "webViewLink": f"https://docs.google.com/document/d/{file_id}",
        "owners": [{"displayName": "Alice", "emailAddress": "alice@test.com"}],
        "trashed": False,
    }


def _doc_paragraph(text: str) -> dict:
    return {
        "paragraph": {
            "elements": [{"textRun": {"content": text + "\n"}}],
        }
    }


def _entity_stub(*, new: bool = True):
    entity = MagicMock()
    entity.id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    entity.created_at = now
    entity.updated_at = now if new else now + timedelta(seconds=1)
    return entity


# ── identity ─────────────────────────────────────────────────────────


def test_source_type(connector):
    assert connector.source == SourceType.GDOCS


# ── _flatten_doc_content ─────────────────────────────────────────────


def test_flatten_doc_content_paragraphs():
    content = [_doc_paragraph("hello"), _doc_paragraph("world")]
    assert _flatten_doc_content(content) == "hello\nworld"


def test_flatten_doc_content_handles_empty():
    assert _flatten_doc_content([]) == ""


def test_flatten_doc_content_includes_table_text():
    table = {
        "table": {
            "tableRows": [
                {
                    "tableCells": [
                        {"content": [_doc_paragraph("a")]},
                        {"content": [_doc_paragraph("b")]},
                    ]
                }
            ]
        }
    }
    out = _flatten_doc_content([table])
    assert "a" in out and "b" in out


# ── HTTP helper: rate limit, 429, 401 ────────────────────────────────


async def test_request_paces_for_rate_limit(connector):
    """Back-to-back requests should pace at >= ~333ms to honor 3 req/sec."""
    from src.connectors import gdocs as gdocs_mod

    gdocs_mod._LIMITER._next_allowed_at = 0.0

    client = AsyncMock()
    client.request = AsyncMock(return_value=_make_response(200, {"ok": True}))

    sleeps: list[float] = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    with patch("src.connectors._rate_limit.asyncio.sleep", fake_sleep):
        await connector._request(client, "GET", "https://x")
        await connector._request(client, "GET", "https://y")

    assert any(s >= 1 / 3 - 1e-2 for s in sleeps), f"no rate-limit sleep observed: {sleeps}"


async def test_request_401_raises_auth_error(connector):
    client = AsyncMock()
    client.request = AsyncMock(return_value=_make_response(401))
    with patch("src.connectors._rate_limit.asyncio.sleep", AsyncMock()):
        with pytest.raises(GDocsAuthError):
            await connector._request(client, "GET", "https://x")


async def test_request_backs_off_on_429(connector):
    client = AsyncMock()
    client.request = AsyncMock(
        side_effect=[
            _make_response(429, headers={"Retry-After": "0"}),
            _make_response(200, {"ok": True}),
        ]
    )
    with patch("src.connectors._rate_limit.asyncio.sleep", AsyncMock()):
        result = await connector._request(client, "GET", "https://x")
    assert result == {"ok": True}
    assert client.request.call_count == 2


async def test_request_backs_off_on_403_quota(connector):
    """A 403 with a rateLimitExceeded reason is treated as a retryable quota error."""
    quota_body = {"error": {"errors": [{"reason": "rateLimitExceeded"}]}}
    client = AsyncMock()
    client.request = AsyncMock(
        side_effect=[
            _make_response(403, quota_body),
            _make_response(200, {"ok": True}),
        ]
    )
    with patch("src.connectors._rate_limit.asyncio.sleep", AsyncMock()):
        result = await connector._request(client, "GET", "https://x")
    assert result == {"ok": True}


async def test_request_403_non_quota_raises(connector):
    """A 403 that is NOT a quota error propagates immediately."""
    client = AsyncMock()
    client.request = AsyncMock(
        return_value=_make_response(403, {"error": {"message": "forbidden"}})
    )
    with patch("src.connectors._rate_limit.asyncio.sleep", AsyncMock()):
        with pytest.raises(httpx.HTTPStatusError):
            await connector._request(client, "GET", "https://x")


async def test_request_gives_up_after_max_retries(connector):
    client = AsyncMock()
    client.request = AsyncMock(
        return_value=_make_response(429, headers={"Retry-After": "0"})
    )
    with patch("src.connectors._rate_limit.asyncio.sleep", AsyncMock()):
        with pytest.raises(httpx.HTTPStatusError):
            await connector._request(client, "GET", "https://x")


# ── sync_full ────────────────────────────────────────────────────────


async def test_sync_full_happy_path(connector, db, org_id, fake_token):
    """Lists files, fetches their content, and indexes one Document entity per file."""
    files = [_file("doc-A", "Spec A"), _file("doc-B", "Spec B")]

    async def fake_request(self, client, method, url, **kwargs):
        if "/drive/v3/files" in url:
            return {"files": files}
        # /docs/v1/documents/{id}
        return {"body": {"content": [_doc_paragraph("hello")]}}

    with patch.object(GDocsConnector, "_request", new=fake_request), patch(
        "src.connectors.gdocs.upsert_entity", AsyncMock(return_value=_entity_stub(new=True))
    ) as upsert, patch(
        "src.connectors.gdocs._build_chunks", AsyncMock(return_value=[{"index": 0, "body": "x"}])
    ):
        result = await connector.sync_full(db, org_id, fake_token)

    assert isinstance(result, ConnectorSyncResult)
    assert result.source == SourceType.GDOCS
    assert result.entities_created == 2
    assert result.errors == []
    create_kwargs = upsert.await_args_list[0].args[1]
    assert create_kwargs.type == EntityType.DOCUMENT
    assert create_kwargs.source == SourceType.GDOCS
    assert "gdocs" in create_kwargs.source_ids


async def test_sync_full_empty_workspace(connector, db, org_id, fake_token):
    async def fake_request(self, client, method, url, **kwargs):
        return {"files": []}

    with patch.object(GDocsConnector, "_request", new=fake_request):
        result = await connector.sync_full(db, org_id, fake_token)

    assert result.entities_created == 0
    assert result.errors == []


async def test_sync_full_token_expired(connector, db, org_id, fake_token):
    async def fake_request(self, client, method, url, **kwargs):
        raise GDocsAuthError("expired")

    with patch.object(GDocsConnector, "_request", new=fake_request):
        with pytest.raises(GDocsAuthError):
            await connector.sync_full(db, org_id, fake_token)


async def test_sync_full_records_doc_fetch_error(connector, db, org_id, fake_token):
    """When fetching one doc body fails, the file still upserts and the
    error is recorded on the result."""
    files = [_file("doc-A", "Spec A")]

    async def fake_request(self, client, method, url, **kwargs):
        if "/drive/v3/files" in url:
            return {"files": files}
        raise RuntimeError("docs 500")

    with patch.object(GDocsConnector, "_request", new=fake_request), patch(
        "src.connectors.gdocs.upsert_entity", AsyncMock(return_value=_entity_stub(new=True))
    ):
        result = await connector.sync_full(db, org_id, fake_token)

    assert result.entities_created == 1
    assert any("docs 500" in e for e in result.errors)


async def test_sync_full_records_top_level_error(connector, db, org_id, fake_token):
    """Unexpected exception is captured, not raised."""

    async def fake_request(self, client, method, url, **kwargs):
        raise RuntimeError("network exploded")

    with patch.object(GDocsConnector, "_request", new=fake_request):
        result = await connector.sync_full(db, org_id, fake_token)

    assert result.errors and "network exploded" in result.errors[0]


async def test_sync_full_idempotent_resync(connector, db, org_id, fake_token):
    files = [_file("doc-A")]

    async def fake_request(self, client, method, url, **kwargs):
        if "/drive/v3/files" in url:
            return {"files": files}
        return {"body": {"content": []}}

    with patch.object(GDocsConnector, "_request", new=fake_request), patch(
        "src.connectors.gdocs.upsert_entity",
        AsyncMock(return_value=_entity_stub(new=False)),
    ):
        result = await connector.sync_full(db, org_id, fake_token)

    assert result.entities_created == 0
    assert result.entities_updated == 1


# ── sync_delta ───────────────────────────────────────────────────────


async def test_sync_delta_passes_modified_time_query(connector, db, org_id, fake_token):
    files = [_file("doc-A", modified="2026-05-02T00:00:00Z")]
    captured: list[dict] = []

    async def fake_request(self, client, method, url, **kwargs):
        if "/drive/v3/files" in url:
            captured.append(kwargs.get("params") or {})
            return {"files": files}
        return {"body": {"content": []}}

    since = datetime(2026, 5, 1, tzinfo=timezone.utc)
    with patch.object(GDocsConnector, "_request", new=fake_request), patch(
        "src.connectors.gdocs.upsert_entity",
        AsyncMock(return_value=_entity_stub(new=True)),
    ):
        await connector.sync_delta(db, org_id, fake_token, since)

    assert captured
    q = captured[0].get("q", "")
    assert "modifiedTime" in q
    assert "2026-05-01" in q


async def test_sync_delta_pagination(connector, db, org_id, fake_token):
    page_a = [_file("doc-A")]
    page_b = [_file("doc-B")]

    calls: list[dict] = []

    async def fake_request(self, client, method, url, **kwargs):
        if "/drive/v3/files" in url:
            calls.append(kwargs.get("params") or {})
            if len(calls) == 1:
                return {"files": page_a, "nextPageToken": "next-tok"}
            return {"files": page_b}
        return {"body": {"content": []}}

    since = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with patch.object(GDocsConnector, "_request", new=fake_request), patch(
        "src.connectors.gdocs.upsert_entity",
        AsyncMock(return_value=_entity_stub(new=True)),
    ) as upsert:
        await connector.sync_delta(db, org_id, fake_token, since)

    assert upsert.await_count == 2
    assert calls[1].get("pageToken") == "next-tok"


async def test_sync_delta_since_in_future_returns_empty(connector, db, org_id, fake_token):
    """Drive returns no rows when modifiedTime > future timestamp."""

    async def fake_request(self, client, method, url, **kwargs):
        if "/drive/v3/files" in url:
            return {"files": []}
        return {"body": {"content": []}}

    since = datetime(2099, 1, 1, tzinfo=timezone.utc)
    with patch.object(GDocsConnector, "_request", new=fake_request):
        result = await connector.sync_delta(db, org_id, fake_token, since)

    assert result.entities_created == 0
    assert result.errors == []


# ── handle_webhook ───────────────────────────────────────────────────


async def test_handle_webhook_change_invalidates_chunks(connector, db, org_id):
    payload = {"file_id": "doc-A", "change_type": "update"}
    existing = _entity_stub(new=False)

    with patch(
        "src.connectors.gdocs.get_entity_by_source",
        AsyncMock(return_value=existing),
    ), patch("src.connectors.gdocs.update_entity", AsyncMock()) as update:
        result = await connector.handle_webhook(db, org_id, payload)

    update.assert_awaited_once()
    assert "chunks_invalidated_at" in update.await_args.kwargs["properties"]
    assert result.entities_updated == 1


async def test_handle_webhook_trashed(connector, db, org_id):
    payload = {"file_id": "doc-A", "change_type": "trashed"}
    existing = _entity_stub(new=False)

    with patch(
        "src.connectors.gdocs.get_entity_by_source",
        AsyncMock(return_value=existing),
    ), patch("src.connectors.gdocs.update_entity", AsyncMock()) as update:
        result = await connector.handle_webhook(db, org_id, payload)

    props = update.await_args.kwargs["properties"]
    assert props.get("trashed") is True
    assert props.get("chunks") == []
    assert result.entities_updated == 1


async def test_handle_webhook_malformed(connector, db, org_id):
    """Missing file id → recorded error, no graph mutation."""
    with patch(
        "src.connectors.gdocs.get_entity_by_source", AsyncMock()
    ) as resolver, patch("src.connectors.gdocs.update_entity", AsyncMock()) as update:
        result = await connector.handle_webhook(db, org_id, {})

    resolver.assert_not_awaited()
    update.assert_not_awaited()
    assert result.errors


async def test_handle_webhook_unknown_entity_no_op(connector, db, org_id):
    payload = {"file_id": "missing", "change_type": "trashed"}
    with patch(
        "src.connectors.gdocs.get_entity_by_source", AsyncMock(return_value=None)
    ), patch("src.connectors.gdocs.update_entity", AsyncMock()) as update:
        result = await connector.handle_webhook(db, org_id, payload)

    update.assert_not_awaited()
    assert result.entities_updated == 0
