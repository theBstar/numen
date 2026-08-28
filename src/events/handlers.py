"""All reactive event handlers - the single source of truth for graph triggers.

Every "when X happens, do Y" rule lives here. Adding a new connector
(GitLab, Jira) requires zero changes to this file - the connector just
emits the same event types and handlers fire automatically.
"""

from __future__ import annotations

import logging
import re

from src.events.bus import bus
from src.events.types import (
    LIVING_EVENT_KINDS,
    LIVING_EVENT_TYPES,
    BriefingRequested,
    EdgeCreated,
    EntityUpserted,
    PrdContentChanged,
    PrdStatusChanged,
    SyncCompleted,
)
from src.shared.types import EdgeType, EntityType, SourceType

logger = logging.getLogger(__name__)

# Pattern for Linear-style task identifiers: ENG-123, PLAT-42, etc.
_TASK_ID_PATTERN = re.compile(r"\b([A-Z]{2,10}-\d{1,6})\b")


# ── EntityUpserted handlers ──────────────────────────────────────────


async def on_pr_auto_link(event: EntityUpserted) -> None:
    """Auto-create SHIPS_TO edges by matching PR title/branch to task identifiers.

    Extracts patterns like ENG-123 from PR title and branch name, looks up
    matching Task entities, and creates SHIPS_TO edges so that
    propagate_pr_state_to_tasks can advance them.
    """
    if event.entity_type != EntityType.COMMIT_PR:
        return

    from src.graph import get_entity_by_source, upsert_edge
    from src.shared.types import EdgeCreate, EdgeType

    props = event.properties
    title = props.get("title", "")
    branch = props.get("head_branch", "")
    commit_msgs = props.get("commit_messages", []) or []
    text = f"{title} {branch} {' '.join(commit_msgs)}"

    identifiers = set(_TASK_ID_PATTERN.findall(text))
    if not identifiers:
        return

    for identifier in identifiers:
        task = await get_entity_by_source(event.db, event.org_id, SourceType.LINEAR, identifier)
        if task and task.type == EntityType.TASK:
            await upsert_edge(
                event.db,
                EdgeCreate(
                    org_id=event.org_id,
                    from_entity_id=event.entity_id,
                    to_entity_id=task.id,
                    type=EdgeType.SHIPS_TO,
                    evidence=[
                        {
                            "source": "auto_link",
                            "identifier": identifier,
                            "connector": event.source.value,
                        }
                    ],
                ),
            )
            logger.info(
                "Auto-linked PR %s to task %s via identifier %s",
                event.entity_id,
                task.id,
                identifier,
            )


async def on_pr_author_link(event: EntityUpserted) -> None:
    """Create AUTHORED edge between PR author and PR entity.

    Uses resolve_or_create_person so the person entity is always
    created/found, regardless of which connector produced the PR.
    """
    if event.entity_type != EntityType.COMMIT_PR:
        return

    author_login = event.properties.get("author")
    if not author_login:
        return

    from src.connectors.schemas.github import GitHubContributorProperties
    from src.graph import resolve_or_create_person, upsert_edge
    from src.shared.types import EdgeCreate, EdgeType

    person = await resolve_or_create_person(
        event.db,
        org_id=event.org_id,
        source=event.source,
        source_ids={event.source.value: author_login},
        canonical_name=author_login,
        properties=GitHubContributorProperties(
            login=author_login,
        ).model_dump(exclude_none=True),
    )

    await upsert_edge(
        event.db,
        EdgeCreate(
            org_id=event.org_id,
            from_entity_id=person.id,
            to_entity_id=event.entity_id,
            type=EdgeType.AUTHORED,
            evidence=[{"source": event.source.value, "field": "author"}],
        ),
    )


async def on_pr_task_transitions(event: EntityUpserted) -> None:
    """Propagate PR state changes to linked tasks."""
    if event.entity_type != EntityType.COMMIT_PR:
        return

    from src.graph.task_transitions import propagate_pr_state_to_tasks

    await propagate_pr_state_to_tasks(event.db, event.entity_id)


# ── EdgeCreated handlers ─────────────────────────────────────────────


async def on_edge_task_transitions(event: EdgeCreated) -> None:
    """Propagate PR state to tasks when a SHIPS_TO edge is created via API.

    Handles the case where a PR is already merged when the link is
    established (e.g. accepting an AI suggestion or manual linking).

    When skip_auto_transition is True (set by frontend-initiated flows),
    the handler skips propagation so the frontend can show a confirmation
    dialog and apply the transition explicitly.
    """
    if event.edge_type != EdgeType.SHIPS_TO:
        return
    if event.skip_auto_transition:
        return

    from src.graph.task_transitions import propagate_pr_state_to_tasks

    # Try both directions - one is a PR, the other is a task.
    # propagate_pr_state_to_tasks returns [] for non-PR entities (safe).
    await propagate_pr_state_to_tasks(event.db, event.from_entity_id)
    await propagate_pr_state_to_tasks(event.db, event.to_entity_id)


# ── SyncCompleted handlers ───────────────────────────────────────────


async def on_sync_person_detection(event: SyncCompleted) -> None:
    """Detect cross-source person duplicates after any sync."""
    from src.graph.resolution import detect_person_duplicates

    new_resolutions = await detect_person_duplicates(event.db, event.org_id)
    if new_resolutions:
        logger.info(
            "Found %d person duplicate(s) for org=%s after %s sync",
            len(new_resolutions),
            event.org_id,
            event.source.value,
        )


async def on_sync_link_suggestions(event: SyncCompleted) -> None:
    """Suggest PR-task links after sync if entities changed.

    Not gated on source type - any connector that produces COMMIT_PR
    entities benefits from link suggestions.
    """
    if event.result.entities_created + event.result.entities_updated == 0:
        return

    from src.llm.link_suggester import suggest_pr_task_links

    new_links = await suggest_pr_task_links(event.db, event.org_id)
    if new_links:
        logger.info(
            "Created %d link suggestion(s) for org=%s after %s sync",
            len(new_links),
            event.org_id,
            event.source.value,
        )


async def on_sync_check_prd_alignment(event: SyncCompleted) -> None:
    """Check PR-PRD alignment after GitHub sync.

    Only runs for GitHub syncs that created or updated entities.
    Finds recently synced COMMIT_PR entities and checks them against
    linked PRDs for spec gaps.
    """
    if event.source != SourceType.GITHUB:
        return
    if event.result.entities_created + event.result.entities_updated == 0:
        return

    from uuid import UUID as _UUID

    from src.graph.falkor_client import get_org_graph
    from src.prd.alignment import check_alignment_for_sync

    # Find recently synced PR entities from the graph
    try:
        graph = await get_org_graph(event.org_id)
        result = await graph.query(
            "MATCH (pr:CommitPR) RETURN pr.id ORDER BY pr.updated_at DESC LIMIT 50",
        )
        pr_ids = []
        for row in result.result_set:
            if row[0]:
                try:
                    pr_ids.append(_UUID(row[0]))
                except (ValueError, AttributeError):
                    continue

        if not pr_ids:
            return

        findings = await check_alignment_for_sync(event.db, event.org_id, pr_ids)
        if findings:
            logger.info(
                "PRD alignment check found %d finding(s) for org=%s after %s sync",
                len(findings),
                event.org_id,
                event.source.value,
            )
    except Exception:
        logger.exception(
            "Failed to run PRD alignment check for org=%s after %s sync",
            event.org_id,
            event.source.value,
        )


# ── BriefingRequested handlers ───────────────────────────────────────


async def on_briefing_scoring(event: BriefingRequested) -> None:
    """Recompute urgency scores before assembling a briefing."""
    from src.inference.scorer import score_org

    await score_org(event.db, event.org_id)


# ── PrdContentChanged handlers ──────────────────────────────────────


async def on_prd_content_mention_extraction(event: PrdContentChanged) -> None:
    """Extract cross-PRD mentions from changed blocks and upsert REFERENCES edges.

    Walks the TipTap JSON content of every changed block, finds prdMention
    nodes, and creates REFERENCES edges from the current PRD to each
    mentioned PRD. Edges are additive-only - removed mentions are not
    automatically deleted.
    """
    from uuid import UUID as _UUID

    from sqlalchemy import select

    from src.graph import list_edges, upsert_edge
    from src.shared.models import PrdBlock
    from src.shared.types import EdgeCreate

    # 1. Load changed blocks
    stmt = select(PrdBlock).where(PrdBlock.id.in_(event.changed_block_ids))
    result = await event.db.execute(stmt)
    blocks = result.scalars().all()

    # 2. Extract prdMention nodes from TipTap JSON content
    mentioned_prd_ids: set[_UUID] = set()
    for block in blocks:
        _extract_mentions_from_content(block.content, mentioned_prd_ids)

    if not mentioned_prd_ids:
        logger.debug(
            "No PRD mentions found in %d changed block(s) for entity=%s",
            len(blocks),
            event.entity_id,
        )
        return

    # 3. Get existing REFERENCES edges from this PRD
    existing_edges = await list_edges(
        event.db,
        org_id=event.org_id,
        entity_id=event.entity_id,
        edge_type=EdgeType.REFERENCES,
        direction="outgoing",
    )
    existing_target_ids = {
        _UUID(e.to_entity_id) if isinstance(e.to_entity_id, str) else e.to_entity_id
        for e in existing_edges
    }

    # 4. Upsert edges for new mentions
    new_count = 0
    for prd_id in mentioned_prd_ids - existing_target_ids:
        await upsert_edge(
            event.db,
            EdgeCreate(
                org_id=event.org_id,
                from_entity_id=event.entity_id,
                to_entity_id=prd_id,
                type=EdgeType.REFERENCES,
                evidence=[
                    {
                        "source": "prd_mention",
                        "changed_by": str(event.changed_by),
                    }
                ],
            ),
        )
        new_count += 1

    # 5. Edges are additive-only - we do NOT delete removed mentions.
    #    Manual cleanup can be done by the user via the references UI.

    logger.info(
        "PRD mention extraction: entity=%s found %d mention(s), created %d new edge(s)",
        event.entity_id,
        len(mentioned_prd_ids),
        new_count,
    )

    # Invalidate wiki cache since PRD content/references changed
    from src.prd.wiki import invalidate_wiki_cache

    await invalidate_wiki_cache(event.org_id)


def _extract_mentions_from_content(
    content: dict | None,
    mentioned_ids: set,
) -> None:
    """Recursively extract prdMention node attrs from TipTap JSON content.

    TipTap stores mention nodes as:
      { "type": "prdMention", "attrs": { "prdId": "uuid-string", ... } }

    This walks the content tree and collects all referenced PRD UUIDs.
    """
    from uuid import UUID as _UUID

    if not content:
        return

    node_type = content.get("type")
    if node_type == "prdMention":
        attrs = content.get("attrs", {})
        prd_id = attrs.get("prdId")
        if prd_id:
            try:
                mentioned_ids.add(_UUID(str(prd_id)))
            except (ValueError, AttributeError):
                pass

    # Recurse into child nodes
    for child in content.get("content", []):
        if isinstance(child, dict):
            _extract_mentions_from_content(child, mentioned_ids)


# ── PrdStatusChanged handlers ──────────────────────────────────────


async def on_prd_status_update_graph(event: PrdStatusChanged) -> None:
    """Update the PRD entity's prd_status property in FalkorDB."""
    from src.graph import update_entity

    await update_entity(
        event.db,
        event.entity_id,
        org_id=event.org_id,
        properties={"prd_status": event.new_status},
        merge_properties=True,
    )
    logger.info(
        "Updated FalkorDB prd_status for entity=%s: %s -> %s",
        event.entity_id,
        event.old_status,
        event.new_status,
    )

    # Invalidate wiki cache since PRD status changed
    from src.prd.wiki import invalidate_wiki_cache

    await invalidate_wiki_cache(event.org_id)


async def on_prd_status_create_version(event: PrdStatusChanged) -> None:
    """Create a version snapshot when a PRD transitions status.

    Captures the full block tree at the moment of transition so that
    reviewers can compare versions.
    """
    from sqlalchemy import func, select

    from src.shared.models import PrdBlock, PrdVersion

    # Fetch current blocks for the PRD
    stmt = (
        select(PrdBlock)
        .where(
            PrdBlock.org_id == event.org_id,
            PrdBlock.entity_id == event.entity_id,
        )
        .order_by(PrdBlock.position)
    )
    result = await event.db.execute(stmt)
    blocks = result.scalars().all()

    snapshot = [
        {
            "id": str(block.id),
            "slug": block.slug,
            "block_type": block.block_type,
            "content": block.content,
            "position": block.position,
            "heading_level": block.heading_level,
            "parent_id": str(block.parent_id) if block.parent_id else None,
        }
        for block in blocks
    ]

    # Determine the next version number
    max_version_stmt = select(func.coalesce(func.max(PrdVersion.version), 0)).where(
        PrdVersion.entity_id == event.entity_id
    )
    max_result = await event.db.execute(max_version_stmt)
    current_max = max_result.scalar_one()
    next_version = current_max + 1

    version = PrdVersion(
        org_id=event.org_id,
        entity_id=event.entity_id,
        version=next_version,
        snapshot=snapshot,
        status_at=event.new_status,
        created_by=event.changed_by,
        message=f"Auto-snapshot on status transition: {event.old_status} -> {event.new_status}",
    )
    event.db.add(version)
    await event.db.flush()

    logger.info(
        "Created version %d for PRD entity=%s on status transition %s -> %s",
        next_version,
        event.entity_id,
        event.old_status,
        event.new_status,
    )


# ── Living event persistence ─────────────────────────────────────────


class LivingEventPersistenceHandler:
    """Persists every Living event into the ``living_event`` table.

    Subscribes to the full set of Living event dataclasses
    (``ContextFetchEvent`` ... ``AgentInterventionEvent``) and writes one
    row per emit. Bus contract is preserved: a DB write failure is logged
    and swallowed, never propagated to the emitter.

    Uses raw SQL via the event's already-attached ``AsyncSession`` so the
    write joins the same transaction as the emitter. This avoids forking
    a SQLAlchemy ORM model into ``src/shared/models.py`` for the spike.
    """

    TABLE = "living_event"

    async def handle(self, event: object) -> None:
        try:
            await self._persist(event)
        except Exception as exc:  # noqa: BLE001
            # Preserve the existing bus handler contract: log and continue.
            logger.warning(
                "LivingEventPersistenceHandler write failed: %s",
                exc,
                exc_info=True,
            )

    async def _persist(self, event: object) -> None:
        from sqlalchemy import text

        kind = LIVING_EVENT_KINDS.get(type(event))
        if kind is None:
            return  # not a Living event; ignore defensively.

        payload = self._build_payload(event)
        worktree_id = getattr(event, "worktree_id", None)
        ts = getattr(event, "ts", None)

        stmt = text(
            f"""
            INSERT INTO {self.TABLE}
                (org_id, kind, task_id, worktree_id, agent_id, payload, ts)
            VALUES
                (:org_id, :kind, :task_id, :worktree_id, :agent_id,
                 CAST(:payload AS JSONB), :ts)
            """
        )

        import json as _json

        await event.db.execute(  # type: ignore[attr-defined]
            stmt,
            {
                "org_id": event.org_id,  # type: ignore[attr-defined]
                "kind": kind,
                "task_id": event.task_id,  # type: ignore[attr-defined]
                "worktree_id": worktree_id,
                "agent_id": event.agent_id,  # type: ignore[attr-defined]
                "payload": _json.dumps(payload, default=str),
                "ts": ts,
            },
        )

    @staticmethod
    def _build_payload(event: object) -> dict:
        """Project event fields (minus the bus-internal ones) into a JSONB dict."""
        # Everything except db / org_id / task_id / agent_id / ts / worktree_id
        # is treated as event-specific payload.
        skip = {"db", "org_id", "task_id", "agent_id", "ts", "worktree_id"}
        payload: dict = {}
        # dataclasses with slots expose __slots__ with field names.
        names: list[str] = []
        for klass in type(event).__mro__:
            for slot in getattr(klass, "__slots__", ()) or ():
                if slot not in names:
                    names.append(slot)
        for name in names:
            if name in skip:
                continue
            value = getattr(event, name, None)
            # Be defensive: tuples / UUIDs / datetimes serialize via default=str later.
            if isinstance(value, tuple):
                value = list(value)
            payload[name] = value
        return payload


# Module-level singleton: callers that want to emit a Living event simply
# do ``await bus.emit(ContextFetchEvent(...))`` and persistence is automatic.
living_event_persistence_handler = LivingEventPersistenceHandler()


# ── Registration ─────────────────────────────────────────────────────


def register_all() -> None:
    """Register all event handlers. Called once at app startup."""
    bus.subscribe(EntityUpserted, on_pr_auto_link, priority=5, name="auto_link_pr_to_tasks")
    bus.subscribe(EntityUpserted, on_pr_author_link, priority=8, name="author_link")
    bus.subscribe(EntityUpserted, on_pr_task_transitions, priority=10, name="pr_task_transitions")
    bus.subscribe(EdgeCreated, on_edge_task_transitions, priority=10, name="edge_task_transitions")
    bus.subscribe(SyncCompleted, on_sync_person_detection, priority=10, name="person_detection")
    bus.subscribe(SyncCompleted, on_sync_link_suggestions, priority=20, name="link_suggestions")
    bus.subscribe(BriefingRequested, on_briefing_scoring, priority=10, name="urgency_scoring")
    bus.subscribe(
        PrdContentChanged,
        on_prd_content_mention_extraction,
        priority=10,
        name="prd_mention_extraction",
    )
    bus.subscribe(
        PrdStatusChanged,
        on_prd_status_update_graph,
        priority=5,
        name="prd_status_update_graph",
    )
    bus.subscribe(
        PrdStatusChanged,
        on_prd_status_create_version,
        priority=10,
        name="prd_status_create_version",
    )
    bus.subscribe(
        SyncCompleted,
        on_sync_check_prd_alignment,
        priority=25,
        name="prd_alignment_check",
    )

    # Living spike: persist every living event to ``living_event``.
    for living_event_type in LIVING_EVENT_TYPES:
        bus.subscribe(
            living_event_type,
            living_event_persistence_handler.handle,
            priority=50,
            name=f"living_event_persistence:{LIVING_EVENT_KINDS[living_event_type]}",
        )

    logger.info("Registered %d event handlers", 11 + len(LIVING_EVENT_TYPES))
