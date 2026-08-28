"""Multi-tenant isolation tests for Living MCP + API.

Org A and Org B both have indexed corpora. We assert that:
  - A token scoped to A receives only A's chunks from get_context.
  - A token scoped to A receives 404 for B's living tasks (never 403, never B's data).
  - A token scoped to A cannot ingest events for B's tasks.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies import get_db
from src.api.living import events_router, tasks_router
from src.api.living._deps import LivingPrincipal, get_living_principal
from src.mcp.tools import get_context

ORG_A = uuid.UUID("00000000-0000-0000-0000-00000000000a")
ORG_B = uuid.UUID("00000000-0000-0000-0000-00000000000b")
AGENT_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def _vec_row(node_id, body, score, org_id):
    node = MagicMock()
    node.properties = {
        "id": node_id,
        "type": "document",
        "source": "notion",
        "canonical_name": f"Doc {node_id}",
        "properties": json.dumps(
            {"body": body, "doc_title": f"Doc {node_id}", "parent_doc_id": node_id}
        ),
        "source_ids": "{}",
        "org_id": str(org_id),
    }
    return [node, score]


async def test_get_context_does_not_leak_b_into_a(mock_db):
    """get_context for Org A NEVER returns chunks tagged to Org B, even if a
    bug in the per-org graph routing accidentally returned them."""
    rows = [
        _vec_row(str(uuid.uuid4()), "Org A secret", 0.9, ORG_A),
        _vec_row(str(uuid.uuid4()), "Org B secret", 0.99, ORG_B),
    ]
    graph = MagicMock()

    async def _query(cypher, params=None):
        result = MagicMock()
        if "db.idx.vector.queryNodes" in cypher:
            result.result_set = rows
        else:
            result.result_set = []
        return result

    graph.query = AsyncMock(side_effect=_query)

    with (
        patch(
            "src.graph._embedding.embed_text",
            new=AsyncMock(return_value=[0.1] * 1536),
        ),
        patch(
            "src.graph.falkor_client.get_org_graph",
            new=AsyncMock(return_value=graph),
        ),
        patch("src.mcp.tools.get_entities_by_ids", new=AsyncMock(return_value=[])),
        patch("src.events.bus.bus.emit", new=AsyncMock(return_value=[])),
    ):
        out = json.loads(
            await get_context(mock_db, ORG_A, AGENT_ID, "anything", max_tokens=4000)
        )

    bodies = [c["body"] for c in out["chunks"]]
    assert any("Org A" in b for b in bodies)
    assert all("Org B" not in b for b in bodies), (
        "Cross-org leak: B's chunk surfaced in A's response"
    )


def _row_for(task):
    res = MagicMock()
    res.scalar_one_or_none = MagicMock(return_value=task)
    return res


def test_living_tasks_api_returns_404_for_b_resource_when_a_authed():
    """Org A's token must NEVER receive Org B's task row."""
    app = FastAPI()
    app.include_router(tasks_router)
    app.include_router(events_router)

    async def override_db():
        db = AsyncMock()
        # Simulates the SQL `WHERE org_id = principal.org_id` filter:
        # principal is A but the row exists in B -> the WHERE filters it out.
        db.execute = AsyncMock(return_value=_row_for(None))
        db.commit = AsyncMock()
        db.flush = AsyncMock()
        db.add = MagicMock()
        yield db

    async def override_principal():
        return LivingPrincipal(
            org_id=ORG_A,
            user_id=uuid.UUID("00000000-0000-0000-0000-0000000000c3"),
            via_api_key=True,
        )

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_living_principal] = override_principal

    bs_task_id = uuid.uuid4()  # Belongs to Org B
    with TestClient(app) as c:
        r = c.get(f"/api/living/tasks/{bs_task_id}")
        assert r.status_code == 404, "Org A must not see Org B's task"

        r = c.patch(
            f"/api/living/tasks/{bs_task_id}/status",
            json={"status": "spawning"},
        )
        assert r.status_code == 404

        r = c.post(
            f"/api/living/tasks/{bs_task_id}/events",
            json={"kind": "session_start", "payload": {}},
        )
        assert r.status_code == 404


def test_event_ingest_404_when_task_in_other_org():
    """A's token POSTing an event to B's task -> 404, payload not persisted."""
    app = FastAPI()
    app.include_router(events_router)

    async def override_db():
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_row_for(None))
        db.commit = AsyncMock()
        db.flush = AsyncMock()
        yield db

    async def override_principal():
        return LivingPrincipal(
            org_id=ORG_A,
            user_id=uuid.UUID("00000000-0000-0000-0000-0000000000c3"),
            via_api_key=True,
        )

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_living_principal] = override_principal

    with patch("src.api.living.events.bus.emit", new=AsyncMock()) as emit:
        with TestClient(app) as c:
            r = c.post(
                f"/api/living/tasks/{uuid.uuid4()}/events",
                json={"kind": "session_start", "payload": {}},
            )
    assert r.status_code == 404
    # Critically: bus.emit must NEVER be called for a foreign-org task.
    assert emit.await_count == 0
