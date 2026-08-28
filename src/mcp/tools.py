"""MCP tool definitions - read and write access to Numen's work intelligence.

Read tools have no actor requirement.
Write tools (create_task, update_task_status, append_wiki_note, ...) require
a user-bound API key; callers pass actor_user_id resolved by the MCP server
from AccessToken.client_id.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.graph import (
    compute_goal_progress,
    delete_edges,
    find_person_by_email,
    get_blocking_chain,
    get_edges,
    get_entities_by_ids,
    get_entities_via_edge,
    get_entity,
    get_entity_by_source,
    get_entity_neighborhood,
    get_goal_tree,
    get_person_workload,
    get_project_stats,
    list_entities,
    update_entity,
    upsert_edge,
    upsert_entity,
)
from src.mcp.serializers import edge_to_dict, entity_to_dict, urgency_score_to_dict
from src.shared.audit import log_action_safely
from src.shared.models import Briefing, OrgMember, UrgencyScoreCache, User, WikiFeature
from src.shared.types import (
    TASK_STATUS_PIPELINE,
    EdgeCreate,
    EdgeType,
    EntityCreate,
    EntityType,
    GoalLevel,
    Priority,
    ProgressMode,
    ProjectStatus,
    SourceType,
    TaskStatus,
)

logger = logging.getLogger(__name__)


async def get_context(
    db: AsyncSession,
    org_id: UUID,
    agent_id: UUID,
    task: str,
    task_id: UUID | None = None,
    max_tokens: int = 4000,
) -> str:
    """Living MCP tool: retrieve task-relevant context for an agent.

    Pipeline (locked per Living design doc):
      1. Embed `task` via src/graph/_embedding.py
      2. Vector top-k=20 cosine match on the org's FalkorDB Entity embedding
      3. For each top chunk's parent doc, fetch 1-hop neighborhood (BATCHED)
      4. Token-budget truncate to `max_tokens`. If a single top chunk's body
         exceeds the budget, it is truncated at sentence boundary, never dropped.
      5. Emit ContextFetchEvent via the EventBus.
      6. Return JSON: {chunks, related_entities, total_tokens, fetched_at}.

    Cross-org safety: caller (the MCP server tool wrapper) must already have
    verified that the request's auth token org matches `org_id`. This function
    additionally scopes every graph query by `org_id` so a leak is not possible
    even if the wrapper guard is bypassed.
    """
    from datetime import datetime, timezone

    from src.events import ContextFetchEvent, bus
    from src.graph._embedding import embed_text
    from src.graph.falkor_client import get_org_graph
    from src.graph.falkor_repository import _node_to_dict

    fetched_at = datetime.now(timezone.utc).isoformat()
    top_k = 20

    # Edge case: max_tokens=0 returns immediately (still emit event so the
    # zero-result path is observable).
    if max_tokens <= 0:
        try:
            await bus.emit(
                ContextFetchEvent(
                    db=db,
                    org_id=org_id,
                    task_id=task_id,
                    agent_id=agent_id,
                    task_query=task,
                    top_k_doc_ids=(),
                    total_tokens=0,
                    result_count=0,
                )
            )
        except Exception as exc:
            logger.warning("ContextFetchEvent emit failed: %s", exc)
        return json.dumps(
            {
                "chunks": [],
                "related_entities": [],
                "total_tokens": 0,
                "fetched_at": fetched_at,
            },
            default=str,
        )

    # 1) Embed task. If embedding service is down -> 503-shaped error JSON.
    try:
        query_embedding = await embed_text(task)
    except Exception as exc:
        logger.warning("get_context embed failed: %s", exc)
        return json.dumps(
            {
                "error": "Embedding service unavailable",
                "retry_after_seconds": 5,
                "status": 503,
            }
        )

    # 2) Vector top-k against the org's graph.
    try:
        graph = await get_org_graph(org_id)
        vector_result = await graph.query(
            "CALL db.idx.vector.queryNodes('Entity', 'embedding', $k, vecf32($emb)) "
            "YIELD node, score "
            "RETURN node, score",
            {"emb": query_embedding, "k": top_k},
        )
    except Exception as exc:
        logger.warning("get_context vector query failed: %s", exc)
        return json.dumps(
            {
                "error": "Graph store unavailable",
                "retry_after_seconds": 5,
                "status": 503,
            }
        )

    top_chunks: list[dict] = []
    parent_doc_ids: list[str] = []
    seen_parents: set[str] = set()
    for row in vector_result.result_set:
        node = _node_to_dict(row[0])
        score = float(row[1]) if row[1] is not None else 0.0
        # Cross-org safety: a vector index per-org graph already scopes results,
        # but defensively drop anything whose org_id doesn't match.
        node_org = node.get("org_id")
        if node_org and str(node_org) != str(org_id):
            continue
        props = node.get("properties") or {}
        if isinstance(props, str):
            try:
                props = json.loads(props)
            except (json.JSONDecodeError, TypeError):
                props = {}
        body = props.get("body") or props.get("content") or node.get("canonical_name") or ""
        doc_title = (
            props.get("doc_title")
            or props.get("title")
            or node.get("canonical_name")
            or ""
        )
        doc_url = props.get("doc_url") or props.get("url")
        source = node.get("source") or props.get("source")
        parent_id = props.get("parent_doc_id") or node.get("id")
        if parent_id and parent_id not in seen_parents:
            parent_doc_ids.append(parent_id)
            seen_parents.add(parent_id)
        top_chunks.append(
            {
                "chunk_id": node.get("id"),
                "doc_title": doc_title,
                "doc_url": doc_url,
                "source": source,
                "body": body,
                "score": score,
                "parent_doc_id": parent_id,
            }
        )

    # 3) Batch-fetch parent doc entities + 1-hop neighborhood. Use the graph
    # repository's batched API to avoid N+1.
    related_entities: list[dict] = []
    if parent_doc_ids:
        try:
            parent_uuids: list[UUID] = []
            for pid in parent_doc_ids:
                try:
                    parent_uuids.append(UUID(str(pid)))
                except (ValueError, TypeError):
                    continue
            # Single batched fetch for parent docs.
            parents = await get_entities_by_ids(db, parent_uuids)
            for p in parents:
                if getattr(p, "org_id", None) != org_id:
                    continue
                related_entities.append(
                    {
                        "id": str(p.id),
                        "type": p.type.value if p.type else None,
                        "title": p.canonical_name,
                        "relation_to_task": "parent_doc",
                    }
                )
            # 1-hop neighborhood: do it via a single Cypher query that
            # returns neighbors for ALL parent ids at once (batched).
            id_strs = [str(u) for u in parent_uuids]
            if id_strs:
                hop_result = await graph.query(
                    "MATCH (d:Entity)-[r]-(neighbor:Entity) "
                    "WHERE d.id IN $ids "
                    "RETURN DISTINCT neighbor, type(r) AS rtype, d.id AS parent_id",
                    {"ids": id_strs},
                )
                for row in hop_result.result_set:
                    n = _node_to_dict(row[0])
                    if n.get("org_id") and str(n.get("org_id")) != str(org_id):
                        continue
                    nid = n.get("id")
                    if nid in id_strs:
                        continue
                    related_entities.append(
                        {
                            "id": nid,
                            "type": n.get("type"),
                            "title": n.get("canonical_name"),
                            "relation_to_task": (row[1] or "related_to").lower()
                            if row[1]
                            else "related_to",
                        }
                    )
        except Exception as exc:
            logger.warning("get_context neighborhood expansion failed: %s", exc)

    # 4) Token-budget truncate. We approximate tokens as ceil(len(text)/4)
    # which matches OpenAI's commonly-cited rule of thumb. The exact tokenizer
    # is not required for budget-clamping; recall@k cares about content.
    def _approx_tokens(text: str) -> int:
        if not text:
            return 0
        return max(1, (len(text) + 3) // 4)

    def _truncate_to_tokens(text: str, budget: int) -> str:
        if budget <= 0 or not text:
            return ""
        # Approx: 4 chars/token. Keep sentence boundary if possible.
        max_chars = budget * 4
        if len(text) <= max_chars:
            return text
        # Find the last sentence-ending punctuation within budget.
        slice_ = text[:max_chars]
        for sep in (". ", "! ", "? ", "\n\n", "\n"):
            idx = slice_.rfind(sep)
            if idx > 0 and idx > max_chars // 2:
                return slice_[: idx + len(sep)].rstrip()
        return slice_.rstrip()

    chunks_out: list[dict] = []
    total_tokens = 0
    for ch in top_chunks:
        body = ch.get("body") or ""
        body_tokens = _approx_tokens(body)
        remaining = max_tokens - total_tokens
        if remaining <= 0:
            break
        if body_tokens > remaining:
            # Per spec: truncate the chunk (sentence-boundary), never drop the
            # top chunk just because it exceeds the budget alone.
            truncated = _truncate_to_tokens(body, remaining)
            ch_out = dict(ch)
            ch_out["body"] = truncated
            ch_out["truncated"] = True
            chunks_out.append(ch_out)
            total_tokens += _approx_tokens(truncated)
            break
        chunks_out.append(ch)
        total_tokens += body_tokens

    # 5) Emit ContextFetchEvent. Failure here must not break the response;
    # the EventBus already swallows handler errors but a programmer error
    # (e.g. wrong dataclass shape) would raise here.
    try:
        await bus.emit(
            ContextFetchEvent(
                db=db,
                org_id=org_id,
                task_id=task_id,
                agent_id=agent_id,
                task_query=task,
                top_k_doc_ids=tuple(
                    str(pid) for pid in seen_parents if _safe_uuid(pid) is not None
                ),
                total_tokens=total_tokens,
                result_count=len(chunks_out),
            )
        )
    except Exception as exc:
        logger.warning("ContextFetchEvent emit failed: %s", exc)

    return json.dumps(
        {
            "chunks": chunks_out,
            "related_entities": related_entities,
            "total_tokens": total_tokens,
            "fetched_at": fetched_at,
        },
        default=str,
    )


def _safe_uuid(val) -> UUID | None:
    try:
        return UUID(str(val))
    except (ValueError, TypeError):
        return None


async def search_entities(
    db: AsyncSession, org_id: UUID, query: str, entity_type: str | None = None, limit: int = 20
) -> str:
    """Search entities by name with optional type filter."""
    et = None
    if entity_type:
        try:
            et = EntityType(entity_type.lower())
        except ValueError:
            return json.dumps(
                {"error": f"Unknown type: {entity_type}. Valid: {[t.value for t in EntityType]}"},
                default=str,
            )

    entities = await list_entities(db, org_id, entity_type=et, search=query, limit=limit)
    return json.dumps([entity_to_dict(e) for e in entities], default=str)


async def get_entity_detail(db: AsyncSession, org_id: UUID, entity_id: str) -> str:
    """Get entity details by ID including its edges."""
    try:
        eid = UUID(entity_id)
    except ValueError:
        return json.dumps({"error": f"Invalid UUID: {entity_id}"})

    entity = await get_entity(db, eid)
    if entity is None or entity.org_id != org_id:
        return json.dumps({"error": f"Entity not found: {entity_id}"})

    edges = await get_edges(db, eid, org_id=org_id)
    return json.dumps(
        {"entity": entity_to_dict(entity), "edges": [edge_to_dict(e) for e in edges]},
        default=str,
    )


async def get_entity_graph(db: AsyncSession, org_id: UUID, entity_id: str, depth: int = 2) -> str:
    """Get the neighborhood graph for an entity (up to N hops)."""
    try:
        eid = UUID(entity_id)
    except ValueError:
        return json.dumps({"error": f"Invalid UUID: {entity_id}"})

    neighborhood = await get_entity_neighborhood(db, eid, depth=min(depth, 3), org_id=org_id)
    entities = neighborhood.get("entities", [])
    edges = neighborhood.get("edges", [])
    return json.dumps(
        {
            "entities": [entity_to_dict(e) for e in entities],
            "edges": [edge_to_dict(e) for e in edges],
            "depth": depth,
        },
        default=str,
    )


async def list_tasks(
    db: AsyncSession,
    org_id: UUID,
    status: str | None = None,
    priority: str | None = None,
    assignee: str | None = None,
    project_id: str | None = None,
    limit: int = 50,
) -> str:
    """List tasks with optional filtering."""
    entities = await list_entities(db, org_id, entity_type=EntityType.TASK, limit=limit)

    # Apply property-based filters
    results = []
    for e in entities:
        props = e.properties or {}
        if status and props.get("status") != status:
            continue
        if priority and props.get("priority") != priority:
            continue
        if assignee and assignee.lower() not in (props.get("assignee", "") or "").lower():
            continue
        results.append(entity_to_dict(e))

    return json.dumps(results, default=str)


async def get_task_context(db: AsyncSession, org_id: UUID, task_id: str) -> str:
    """Get rich task context: goals, blocking chain, urgency, related PRs, project."""
    try:
        tid = UUID(task_id)
    except ValueError:
        return json.dumps({"error": f"Invalid UUID: {task_id}"})

    task = await get_entity(db, tid)
    if task is None or task.org_id != org_id or task.type != EntityType.TASK:
        return json.dumps({"error": f"Task not found: {task_id}"})

    result: dict = {"task": entity_to_dict(task)}

    # Linked goals via TAGGED_TO
    goal_entities = await get_entities_via_edge(
        db,
        tid,
        EdgeType.TAGGED_TO,
        direction="outgoing",
        target_type=EntityType.GOAL,
        org_id=org_id,
    )
    goals = []
    for g in goal_entities:
        progress = await compute_goal_progress(db, g.id, org_id=org_id)
        goals.append({"entity": entity_to_dict(g), "progress": progress})
    result["goals"] = goals

    # Blocking chain
    chain = await get_blocking_chain(db, tid, org_id=org_id)
    result["blocking_chain"] = [entity_to_dict(e) for e in chain]

    # Related PRs via SHIPS_TO (incoming - PRs ship to tasks)
    pr_entities = await get_entities_via_edge(
        db,
        tid,
        EdgeType.SHIPS_TO,
        direction="incoming",
        target_type=EntityType.COMMIT_PR,
        org_id=org_id,
    )
    result["related_prs"] = [entity_to_dict(pr) for pr in pr_entities]

    # Project via CONTAINS (incoming - project contains task)
    project_entities = await get_entities_via_edge(
        db,
        tid,
        EdgeType.CONTAINS,
        direction="incoming",
        target_type=EntityType.PROJECT,
        org_id=org_id,
    )
    if project_entities:
        project = project_entities[0]
        stats = await get_project_stats(db, project.id, org_id=org_id)
        result["project"] = {"entity": entity_to_dict(project), "stats": stats}

    # Urgency score
    stmt = select(UrgencyScoreCache).where(UrgencyScoreCache.entity_id == tid).limit(1)
    score_result = await db.execute(stmt)
    score = score_result.scalar_one_or_none()
    if score:
        result["urgency"] = urgency_score_to_dict(score)

    return json.dumps(result, default=str)


async def list_goals(db: AsyncSession, org_id: UUID, level: str | None = None, include_tree: bool = False) -> str:
    """List goals, optionally as a hierarchy tree."""
    if include_tree:
        tree = await get_goal_tree(db, org_id)
        return json.dumps(tree, default=str)

    entities = await list_entities(db, org_id, entity_type=EntityType.GOAL, limit=100)
    results = []
    for e in entities:
        props = e.properties or {}
        if level and props.get("level") != level:
            continue
        results.append(entity_to_dict(e))
    return json.dumps(results, default=str)


async def get_goal_progress(db: AsyncSession, org_id: UUID, goal_id: str) -> str:
    """Get progress for a goal with linked task stats."""
    try:
        gid = UUID(goal_id)
    except ValueError:
        return json.dumps({"error": f"Invalid UUID: {goal_id}"})

    entity = await get_entity(db, gid)
    if entity is None or entity.org_id != org_id:
        return json.dumps({"error": f"Goal not found: {goal_id}"})

    progress = await compute_goal_progress(db, gid, org_id=org_id)
    return json.dumps({"goal": entity_to_dict(entity), "progress": progress}, default=str)


async def get_urgency_scores(db: AsyncSession, org_id: UUID, person_name: str | None = None, limit: int = 10) -> str:
    """Get top urgent items, optionally filtered by person."""
    conditions = [UrgencyScoreCache.org_id == org_id]

    if person_name:
        persons = await list_entities(db, org_id, entity_type=EntityType.PERSON, search=person_name, limit=1)
        if persons:
            conditions.append(UrgencyScoreCache.person_id == persons[0].id)

    stmt = select(UrgencyScoreCache).where(and_(*conditions)).order_by(UrgencyScoreCache.score.desc()).limit(limit)
    result = await db.execute(stmt)
    scores = list(result.scalars().all())

    entity_ids = [s.entity_id for s in scores]
    entities_list = await get_entities_by_ids(db, entity_ids)
    entity_map = {e.id: e for e in entities_list}

    items = []
    for s in scores:
        entity = entity_map.get(s.entity_id)
        items.append(urgency_score_to_dict(s, entity))
    return json.dumps(items, default=str)


async def get_briefing(db: AsyncSession, org_id: UUID, member_email: str) -> str:
    """Get the latest briefing for a member by email."""
    stmt = select(OrgMember).where(OrgMember.org_id == org_id, OrgMember.email == member_email)
    result = await db.execute(stmt)
    member = result.scalar_one_or_none()
    if member is None:
        return json.dumps({"error": f"Member not found: {member_email}"})

    stmt = select(Briefing).where(Briefing.org_member_id == member.id).order_by(Briefing.generated_at.desc()).limit(1)
    result = await db.execute(stmt)
    briefing = result.scalar_one_or_none()
    if briefing is None:
        return json.dumps({"error": "No briefing found for this member"})

    return json.dumps(
        {
            "member_email": member_email,
            "generated_at": briefing.generated_at.isoformat() if briefing.generated_at else None,
            "content": briefing.content,
            "delivery_status": briefing.delivery_status.value if briefing.delivery_status else None,
        },
        default=str,
    )


async def get_person_workload_tool(db: AsyncSession, org_id: UUID, person_name: str) -> str:
    """Get a person's task workload breakdown by name."""
    persons = await list_entities(db, org_id, entity_type=EntityType.PERSON, search=person_name, limit=1)
    if not persons:
        return json.dumps({"error": f"Person not found: {person_name}"})

    person = persons[0]
    workload = await get_person_workload(db, person.id)
    return json.dumps({"person": entity_to_dict(person), "workload": workload}, default=str)


async def search_by_source(db: AsyncSession, org_id: UUID, source: str, source_id: str) -> str:
    """Look up an entity by its source system ID (e.g., Linear issue ID, GitHub PR number)."""
    try:
        src = SourceType(source.lower())
    except ValueError:
        return json.dumps({"error": f"Unknown source: {source}. Valid: {[s.value for s in SourceType]}"})

    entity = await get_entity_by_source(db, org_id, src, source_id)
    if entity is None:
        return json.dumps({"error": f"No entity found for {source}:{source_id}"})
    return json.dumps(entity_to_dict(entity), default=str)


# ── Helpers for write tools ───────────────────────────────────────────


_STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has",
        "have", "in", "is", "it", "of", "on", "or", "that", "the", "this",
        "to", "was", "were", "with", "will", "would", "should", "could", "i",
        "we", "you", "they", "them", "us", "fix", "add", "update", "make",
    }
)


def _extract_keywords(text: str, limit: int = 6) -> list[str]:
    """Pick high-signal words from a free-text description for substring search."""
    words = [w.strip(".,;:!?()[]\"'`").lower() for w in text.split()]
    keywords: list[str] = []
    seen: set[str] = set()
    for w in words:
        if len(w) < 4 or w in _STOPWORDS or w in seen:
            continue
        seen.add(w)
        keywords.append(w)
        if len(keywords) >= limit:
            break
    return keywords


async def _get_actor_email(db: AsyncSession, user_id: UUID) -> str:
    """Resolve a user_id to an email for audit/notes attribution."""
    user = await db.get(User, user_id)
    return user.email if user else f"user:{user_id}"


def _status_rank(status: str) -> int:
    """Index of a status in TASK_STATUS_PIPELINE; -1 if outside the pipeline."""
    try:
        return TASK_STATUS_PIPELINE.index(status)
    except ValueError:
        return -1


# ── Read helper that supports the matching flow ──────────────────────


async def find_matching_task(
    db: AsyncSession,
    org_id: UUID,
    description: str,
    project_hint: str | None = None,
    limit: int = 10,
    recommend_threshold: float | None = 0.85,
) -> str:
    """Find existing tasks that may match a new piece of work.

    Returns a ranked list of candidates with confidence scores. When the
    top match's confidence >= ``recommend_threshold``, the response also
    includes ``recommended_action: "use_existing"`` plus the matched
    task_id - call sites should surface this to the user before creating
    a duplicate. Set ``recommend_threshold=None`` to suppress the
    recommendation (return raw candidates only).

    LLM re-rank is best-effort: if it fails, the response falls back to
    the substring shortlist with confidence=null and no recommendation
    (the threshold is moot without scores).

    Note: confidence is currently the LLM's self-reported score, not a
    cosine similarity. The 0.85 default is conservative and stays
    advisory until a labeled precision eval calibrates it.
    """
    # Substring shortlist over the description's keywords
    keywords = _extract_keywords(description)
    shortlist: list = []
    seen_ids: set[UUID] = set()
    queries = keywords or [description.strip().split()[0] if description.strip() else ""]

    for q in queries:
        if not q:
            continue
        candidates = await list_entities(
            db, org_id, entity_type=EntityType.TASK, search=q, limit=limit
        )
        for c in candidates:
            if c.id in seen_ids:
                continue
            seen_ids.add(c.id)
            shortlist.append(c)
            if len(shortlist) >= limit * 2:
                break
        if len(shortlist) >= limit * 2:
            break

    if not shortlist:
        return json.dumps({"candidates": [], "method": "substring"}, default=str)

    base_dicts = [entity_to_dict(c) for c in shortlist[: limit * 2]]

    # Best-effort LLM re-rank
    try:
        from src.llm.client import call_llm

        candidate_payload = [
            {
                "task_id": d.get("id"),
                "title": d.get("canonical_name") or d.get("name"),
                "status": (d.get("properties") or {}).get("status"),
                "priority": (d.get("properties") or {}).get("priority"),
            }
            for d in base_dicts
        ]
        system = (
            "You match new work descriptions to existing tasks. Output ONLY JSON: "
            '{"matches": [{"task_id": "...", "confidence": 0.0-1.0, "reason": "..."}]} '
            "sorted by confidence descending. Use confidence>=0.8 only if you are sure "
            "it's the same work. Skip tasks with confidence<0.3."
        )
        user = json.dumps(
            {
                "new_work": description,
                "project_hint": project_hint,
                "candidates": candidate_payload,
            },
            default=str,
        )
        raw = await call_llm(system=system, user=user, max_tokens=512)
        parsed = json.loads(raw)
        matches = parsed.get("matches", [])
        # Merge with full entity dicts
        by_id = {d["id"]: d for d in base_dicts}
        ranked = []
        for m in matches[:limit]:
            entity = by_id.get(m.get("task_id"))
            if entity is None:
                continue
            ranked.append(
                {
                    "task": entity,
                    "confidence": m.get("confidence"),
                    "reason": m.get("reason"),
                }
            )
        result: dict = {"candidates": ranked, "method": "llm_rerank"}
        if (
            recommend_threshold is not None
            and ranked
            and isinstance(ranked[0].get("confidence"), (int, float))
            and ranked[0]["confidence"] >= recommend_threshold
        ):
            top = ranked[0]
            result["recommended_action"] = "use_existing"
            result["recommended_task_id"] = top["task"].get("id")
            result["recommended_confidence"] = top["confidence"]
            result["recommend_threshold"] = recommend_threshold
        return json.dumps(result, default=str)
    except Exception as exc:
        logger.warning("find_matching_task LLM re-rank failed, falling back: %s", exc)
        ranked = [
            {"task": d, "confidence": None, "reason": None} for d in base_dicts[:limit]
        ]
        return json.dumps(
            {"candidates": ranked, "method": "substring_fallback"}, default=str
        )


# ── Write tools ──────────────────────────────────────────────────────


async def create_task(
    db: AsyncSession,
    org_id: UUID,
    actor_user_id: UUID,
    title: str,
    description: str | None = None,
    project_id: str | None = None,
    goal_ids: list[str] | None = None,
    assignee_email: str | None = None,
    priority: str = Priority.MEDIUM,
) -> str:
    """Create a task and wire its CONTAINS / TAGGED_TO / ASSIGNED_TO edges.

    Tasks created via MCP use source=manual with a stable mcp:<slug> source_id,
    matching the pattern used by REST manual task creation. status starts at
    todo and advances through the forward-only pipeline.
    """
    if not title.strip():
        return json.dumps({"error": "title is required"})

    try:
        priority_value = Priority(priority).value
    except ValueError:
        return json.dumps(
            {"error": f"Unknown priority: {priority}. Valid: {[p.value for p in Priority]}"}
        )

    properties: dict = {
        "status": TaskStatus.TODO.value,
        "priority": priority_value,
        "labels": [],
    }
    if description:
        properties["description"] = description

    slug = title.lower().replace(" ", "-")[:200]
    entity = await upsert_entity(
        db,
        EntityCreate(
            org_id=org_id,
            type=EntityType.TASK,
            source=SourceType.MANUAL,
            source_ids={"manual": f"mcp:{slug}"},
            canonical_name=title,
            properties=properties,
        ),
    )

    # CONTAINS: project -> task
    if project_id:
        try:
            pid = UUID(project_id)
        except ValueError:
            return json.dumps({"error": f"Invalid project_id: {project_id}"})
        project = await get_entity(db, pid, org_id=org_id)
        if not project or project.type != EntityType.PROJECT:
            return json.dumps({"error": f"Project not found: {project_id}"})
        await upsert_edge(
            db,
            EdgeCreate(
                org_id=org_id,
                from_entity_id=pid,
                to_entity_id=entity.id,
                type=EdgeType.CONTAINS,
                evidence=[{"source": "mcp", "actor_user_id": str(actor_user_id)}],
            ),
        )

    # TAGGED_TO: task -> goal
    for gid_str in goal_ids or []:
        try:
            gid = UUID(gid_str)
        except ValueError:
            return json.dumps({"error": f"Invalid goal_id: {gid_str}"})
        goal = await get_entity(db, gid, org_id=org_id)
        if not goal or goal.type != EntityType.GOAL:
            return json.dumps({"error": f"Goal not found: {gid_str}"})
        await upsert_edge(
            db,
            EdgeCreate(
                org_id=org_id,
                from_entity_id=entity.id,
                to_entity_id=gid,
                type=EdgeType.TAGGED_TO,
                evidence=[{"source": "mcp", "actor_user_id": str(actor_user_id)}],
            ),
        )

    # ASSIGNED_TO: person -> task
    if assignee_email:
        person = await find_person_by_email(db, org_id, assignee_email)
        if person:
            await upsert_edge(
                db,
                EdgeCreate(
                    org_id=org_id,
                    from_entity_id=person.id,
                    to_entity_id=entity.id,
                    type=EdgeType.ASSIGNED_TO,
                    evidence=[{"source": "mcp", "actor_user_id": str(actor_user_id)}],
                ),
            )

    await log_action_safely(
        db,
        org_id=org_id,
        user_id=actor_user_id,
        action="mcp.task.created",
        resource_type="task",
        resource_id=entity.id,
        details={"title": title, "priority": priority_value},
    )
    await db.commit()
    return json.dumps(entity_to_dict(entity), default=str)


async def update_task_status(
    db: AsyncSession,
    org_id: UUID,
    actor_user_id: UUID,
    task_id: str,
    status: str,
) -> str:
    """Move a task forward in the lifecycle (todo -> in_progress -> ... -> done).

    Backward transitions are rejected; the calling AI tool sees the error
    JSON and can surface the rule to the user.
    """
    try:
        tid = UUID(task_id)
    except ValueError:
        return json.dumps({"error": f"Invalid task_id: {task_id}"})

    try:
        target_status = TaskStatus(status).value
    except ValueError:
        return json.dumps(
            {"error": f"Unknown status: {status}. Valid: {[s.value for s in TaskStatus]}"}
        )

    task = await get_entity(db, tid, org_id=org_id)
    if not task or task.type != EntityType.TASK:
        return json.dumps({"error": f"Task not found: {task_id}"})

    current_status = (task.properties or {}).get("status", TaskStatus.TODO.value)
    if target_status == current_status:
        return json.dumps(entity_to_dict(task), default=str)

    target_rank = _status_rank(target_status)
    current_rank = _status_rank(current_status)

    if target_rank == -1 or current_rank == -1:
        return json.dumps(
            {
                "error": (
                    f"Status outside the forward-only pipeline. current={current_status} "
                    f"target={target_status}. Pipeline: {[s.value for s in TASK_STATUS_PIPELINE]}"
                )
            }
        )

    if target_rank <= current_rank:
        return json.dumps(
            {
                "error": (
                    f"Cannot move task backward: {current_status} -> {target_status}. "
                    "Status is forward-only."
                )
            }
        )

    new_props = dict(task.properties or {})
    new_props["status"] = target_status
    updated = await update_entity(db, tid, org_id=org_id, properties=new_props)

    await log_action_safely(
        db,
        org_id=org_id,
        user_id=actor_user_id,
        action="mcp.task.status",
        resource_type="task",
        resource_id=tid,
        details={"old_status": current_status, "new_status": target_status},
    )
    await db.commit()
    return json.dumps(entity_to_dict(updated), default=str)


async def update_task(
    db: AsyncSession,
    org_id: UUID,
    actor_user_id: UUID,
    task_id: str,
    title: str | None = None,
    description: str | None = None,
    priority: str | None = None,
    assignee_email: str | None = None,
) -> str:
    """Patch a task's title/description/priority and optionally re-assign."""
    try:
        tid = UUID(task_id)
    except ValueError:
        return json.dumps({"error": f"Invalid task_id: {task_id}"})

    task = await get_entity(db, tid, org_id=org_id)
    if not task or task.type != EntityType.TASK:
        return json.dumps({"error": f"Task not found: {task_id}"})

    new_props = dict(task.properties or {})
    if description is not None:
        new_props["description"] = description
    if priority is not None:
        try:
            new_props["priority"] = Priority(priority).value
        except ValueError:
            return json.dumps(
                {"error": f"Unknown priority: {priority}. Valid: {[p.value for p in Priority]}"}
            )

    updated = await update_entity(
        db,
        tid,
        org_id=org_id,
        canonical_name=title,
        properties=new_props,
    )

    if assignee_email is not None:
        # Replace existing ASSIGNED_TO edges; empty string clears assignment
        await delete_edges(db, tid, EdgeType.ASSIGNED_TO, direction="incoming")
        if assignee_email:
            person = await find_person_by_email(db, org_id, assignee_email)
            if person:
                await upsert_edge(
                    db,
                    EdgeCreate(
                        org_id=org_id,
                        from_entity_id=person.id,
                        to_entity_id=tid,
                        type=EdgeType.ASSIGNED_TO,
                        evidence=[{"source": "mcp", "actor_user_id": str(actor_user_id)}],
                    ),
                )

    await log_action_safely(
        db,
        org_id=org_id,
        user_id=actor_user_id,
        action="mcp.task.updated",
        resource_type="task",
        resource_id=tid,
        details={
            k: v
            for k, v in {
                "title": title,
                "description": description,
                "priority": priority,
                "assignee_email": assignee_email,
            }.items()
            if v is not None
        },
    )
    await db.commit()
    return json.dumps(entity_to_dict(updated), default=str)


async def link_task(
    db: AsyncSession,
    org_id: UUID,
    actor_user_id: UUID,
    task_id: str,
    project_id: str | None = None,
    goal_ids: list[str] | None = None,
    blocks_task_id: str | None = None,
) -> str:
    """Add CONTAINS / TAGGED_TO / BLOCKS edges to an existing task. Idempotent."""
    try:
        tid = UUID(task_id)
    except ValueError:
        return json.dumps({"error": f"Invalid task_id: {task_id}"})

    task = await get_entity(db, tid, org_id=org_id)
    if not task or task.type != EntityType.TASK:
        return json.dumps({"error": f"Task not found: {task_id}"})

    added: dict[str, list[str]] = {"contains": [], "tagged_to": [], "blocks": []}

    if project_id:
        try:
            pid = UUID(project_id)
        except ValueError:
            return json.dumps({"error": f"Invalid project_id: {project_id}"})
        project = await get_entity(db, pid, org_id=org_id)
        if not project or project.type != EntityType.PROJECT:
            return json.dumps({"error": f"Project not found: {project_id}"})
        await upsert_edge(
            db,
            EdgeCreate(
                org_id=org_id,
                from_entity_id=pid,
                to_entity_id=tid,
                type=EdgeType.CONTAINS,
                evidence=[{"source": "mcp", "actor_user_id": str(actor_user_id)}],
            ),
        )
        added["contains"].append(str(pid))

    for gid_str in goal_ids or []:
        try:
            gid = UUID(gid_str)
        except ValueError:
            return json.dumps({"error": f"Invalid goal_id: {gid_str}"})
        goal = await get_entity(db, gid, org_id=org_id)
        if not goal or goal.type != EntityType.GOAL:
            return json.dumps({"error": f"Goal not found: {gid_str}"})
        await upsert_edge(
            db,
            EdgeCreate(
                org_id=org_id,
                from_entity_id=tid,
                to_entity_id=gid,
                type=EdgeType.TAGGED_TO,
                evidence=[{"source": "mcp", "actor_user_id": str(actor_user_id)}],
            ),
        )
        added["tagged_to"].append(str(gid))

    if blocks_task_id:
        try:
            bid = UUID(blocks_task_id)
        except ValueError:
            return json.dumps({"error": f"Invalid blocks_task_id: {blocks_task_id}"})
        blocked = await get_entity(db, bid, org_id=org_id)
        if not blocked or blocked.type != EntityType.TASK:
            return json.dumps({"error": f"Blocked task not found: {blocks_task_id}"})
        await upsert_edge(
            db,
            EdgeCreate(
                org_id=org_id,
                from_entity_id=tid,
                to_entity_id=bid,
                type=EdgeType.BLOCKS,
                evidence=[{"source": "mcp", "actor_user_id": str(actor_user_id)}],
            ),
        )
        added["blocks"].append(str(bid))

    await log_action_safely(
        db,
        org_id=org_id,
        user_id=actor_user_id,
        action="mcp.task.linked",
        resource_type="task",
        resource_id=tid,
        details=added,
    )
    await db.commit()
    return json.dumps({"task_id": str(tid), "added": added}, default=str)


async def create_project(
    db: AsyncSession,
    org_id: UUID,
    actor_user_id: UUID,
    name: str,
    description: str | None = None,
    status: str = "planning",
    owner_email: str | None = None,
    goal_ids: list[str] | None = None,
) -> str:
    """Create a project and wire OWNS + TAGGED_TO edges. Mirrors POST /projects."""
    if not name.strip():
        return json.dumps({"error": "name is required"})

    try:
        status_value = ProjectStatus(status).value
    except ValueError:
        return json.dumps(
            {"error": f"Unknown status: {status}. Valid: {[s.value for s in ProjectStatus]}"}
        )

    slug = name.lower().replace(" ", "-")
    entity = await upsert_entity(
        db,
        EntityCreate(
            org_id=org_id,
            type=EntityType.PROJECT,
            source=SourceType.MANUAL,
            source_ids={"manual": f"mcp:{slug}"},
            canonical_name=name,
            properties={
                "description": description,
                "status": status_value,
                "owner_email": owner_email,
            },
        ),
    )

    if owner_email:
        owner = await find_person_by_email(db, org_id, owner_email)
        if owner:
            await upsert_edge(
                db,
                EdgeCreate(
                    org_id=org_id,
                    from_entity_id=owner.id,
                    to_entity_id=entity.id,
                    type=EdgeType.OWNS,
                    evidence=[{"source": "mcp", "actor_user_id": str(actor_user_id)}],
                ),
            )

    for gid_str in goal_ids or []:
        try:
            gid = UUID(gid_str)
        except ValueError:
            return json.dumps({"error": f"Invalid goal_id: {gid_str}"})
        goal = await get_entity(db, gid, org_id=org_id)
        if not goal or goal.type != EntityType.GOAL:
            return json.dumps({"error": f"Goal not found: {gid_str}"})
        await upsert_edge(
            db,
            EdgeCreate(
                org_id=org_id,
                from_entity_id=entity.id,
                to_entity_id=gid,
                type=EdgeType.TAGGED_TO,
                evidence=[{"source": "mcp", "actor_user_id": str(actor_user_id)}],
            ),
        )

    await log_action_safely(
        db,
        org_id=org_id,
        user_id=actor_user_id,
        action="mcp.project.created",
        resource_type="project",
        resource_id=entity.id,
        details={"name": name, "status": status_value},
    )
    await db.commit()
    return json.dumps(entity_to_dict(entity), default=str)


async def create_goal(
    db: AsyncSession,
    org_id: UUID,
    actor_user_id: UUID,
    title: str,
    level: str,
    parent_goal_id: str | None = None,
    description: str | None = None,
    target_value: float | None = None,
    owner_email: str | None = None,
) -> str:
    """Create a goal entity, optionally as a child of an existing goal."""
    if not title.strip():
        return json.dumps({"error": "title is required"})

    try:
        level_value = GoalLevel(level).value
    except ValueError:
        return json.dumps(
            {"error": f"Unknown level: {level}. Valid: {[lvl.value for lvl in GoalLevel]}"}
        )

    parent_uuid: UUID | None = None
    if parent_goal_id:
        try:
            parent_uuid = UUID(parent_goal_id)
        except ValueError:
            return json.dumps({"error": f"Invalid parent_goal_id: {parent_goal_id}"})
        parent = await get_entity(db, parent_uuid, org_id=org_id)
        if not parent or parent.type != EntityType.GOAL:
            return json.dumps({"error": f"Parent goal not found: {parent_goal_id}"})
        if (parent.properties or {}).get("status") == ProjectStatus.ARCHIVED.value:
            return json.dumps({"error": "Cannot create a child of an archived goal"})

    properties = {
        "level": level_value,
        "status": ProjectStatus.ACTIVE.value,
        "key_results": [],
        "target_value": target_value,
        "current_value": 0,
        "owner_email": owner_email,
        "description": description,
        "progress_mode": ProgressMode.COMPUTED.value,
    }

    entity = await upsert_entity(
        db,
        EntityCreate(
            org_id=org_id,
            type=EntityType.GOAL,
            source=SourceType.MANUAL,
            source_ids={"manual": f"mcp:{title.lower().replace(' ', '-')}"},
            canonical_name=title,
            properties=properties,
        ),
    )

    if parent_uuid:
        await upsert_edge(
            db,
            EdgeCreate(
                org_id=org_id,
                from_entity_id=parent_uuid,
                to_entity_id=entity.id,
                type=EdgeType.PARENT_OF,
                evidence=[{"source": "mcp", "actor_user_id": str(actor_user_id)}],
            ),
        )

    if owner_email:
        owner = await find_person_by_email(db, org_id, owner_email)
        if owner:
            await upsert_edge(
                db,
                EdgeCreate(
                    org_id=org_id,
                    from_entity_id=owner.id,
                    to_entity_id=entity.id,
                    type=EdgeType.OWNS,
                    evidence=[{"source": "mcp", "actor_user_id": str(actor_user_id)}],
                ),
            )

    await log_action_safely(
        db,
        org_id=org_id,
        user_id=actor_user_id,
        action="mcp.goal.created",
        resource_type="goal",
        resource_id=entity.id,
        details={"title": title, "level": level_value},
    )
    await db.commit()
    return json.dumps(entity_to_dict(entity), default=str)


# ── Wiki tools ───────────────────────────────────────────────────────


_WIKI_NOTES_HEADER = "## Notes from Numen MCP"


async def list_wiki_features(db: AsyncSession, org_id: UUID, status: str | None = None) -> str:
    """List wiki features (slug, title, status) for this org."""
    stmt = select(WikiFeature).where(WikiFeature.org_id == org_id)
    if status:
        stmt = stmt.where(WikiFeature.status == status)
    stmt = stmt.order_by(WikiFeature.position)
    result = await db.execute(stmt)
    rows = list(result.scalars().all())
    return json.dumps(
        [
            {
                "id": str(r.id),
                "slug": r.slug,
                "title": r.title,
                "status": r.status,
                "summary": r.summary,
                "is_manual": r.is_manual,
            }
            for r in rows
        ],
        default=str,
    )


async def get_wiki_feature(db: AsyncSession, org_id: UUID, slug: str) -> str:
    """Fetch a wiki feature by slug, including its Markdown content."""
    stmt = select(WikiFeature).where(
        WikiFeature.org_id == org_id, WikiFeature.slug == slug
    )
    result = await db.execute(stmt)
    wf = result.scalar_one_or_none()
    if wf is None:
        return json.dumps({"error": f"Wiki feature not found: {slug}"})
    return json.dumps(
        {
            "id": str(wf.id),
            "slug": wf.slug,
            "title": wf.title,
            "status": wf.status,
            "summary": wf.summary,
            "content": wf.content,
            "is_manual": wf.is_manual,
        },
        default=str,
    )


async def append_wiki_note(
    db: AsyncSession,
    org_id: UUID,
    actor_user_id: UUID,
    feature_slug: str,
    note_markdown: str,
) -> str:
    """Append a dated, attributed note to a wiki feature.

    The note goes under a stable trailing section "## Notes from Numen MCP"
    so it survives PRD-driven regeneration (which preserves features whose
    is_manual=True). Idempotent on a duplicate consecutive note.
    """
    note = note_markdown.strip()
    if not note:
        return json.dumps({"error": "note_markdown is empty"})

    stmt = select(WikiFeature).where(
        WikiFeature.org_id == org_id, WikiFeature.slug == feature_slug
    )
    result = await db.execute(stmt)
    wf = result.scalar_one_or_none()
    if wf is None:
        return json.dumps({"error": f"Wiki feature not found: {feature_slug}"})

    actor_email = await _get_actor_email(db, actor_user_id)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    bullet = f"- {timestamp} by {actor_email}: {note}"

    content = wf.content or ""
    if _WIKI_NOTES_HEADER in content:
        head, _, tail = content.partition(_WIKI_NOTES_HEADER)
        existing_bullets = [
            line for line in tail.splitlines() if line.strip().startswith("-")
        ]
        if existing_bullets and existing_bullets[-1].strip() == bullet.strip():
            # Idempotent: skip duplicate consecutive note
            return json.dumps(
                {"slug": wf.slug, "appended": False, "reason": "duplicate"},
                default=str,
            )
        new_content = (
            head
            + _WIKI_NOTES_HEADER
            + "\n"
            + "\n".join(existing_bullets + [bullet])
            + "\n"
        )
    else:
        new_content = content.rstrip() + f"\n\n{_WIKI_NOTES_HEADER}\n{bullet}\n"

    wf.content = new_content
    wf.is_manual = True  # ensures the note survives regeneration
    await db.flush()

    await log_action_safely(
        db,
        org_id=org_id,
        user_id=actor_user_id,
        action="mcp.wiki.note_appended",
        resource_type="wiki_feature",
        resource_id=wf.id,
        details={"slug": wf.slug, "note_length": len(note)},
    )
    await db.commit()
    return json.dumps(
        {"slug": wf.slug, "appended": True, "actor": actor_email}, default=str
    )


async def hello_numen(
    db: AsyncSession,
    org_id: UUID,
    user_id: UUID | None = None,
) -> str:
    """First-call WOW tool. Returns org info + sample call so agents orient fast.

    Designed to be the very first MCP call an agent makes after install. The
    response shape is stable - agents can parse `sample_first_call` to
    auto-suggest the next step.
    """
    from sqlalchemy import func, select

    from src.shared.models import Entity, Organization

    org = await db.get(Organization, org_id)
    if org is None:
        from src.mcp.errors import ErrorCode, error_response

        return error_response(
            ErrorCode.AUTH_REQUIRED,
            message="No organization for this API key.",
            hint="Re-mint your API key from the Numen MCP setup page.",
        )

    member_count_stmt = select(func.count(OrgMember.id)).where(OrgMember.org_id == org_id)
    member_count = (await db.execute(member_count_stmt)).scalar() or 0

    entity_count_stmt = (
        select(func.count(Entity.id))
        .where(Entity.org_id == org_id, Entity.merged_into.is_(None))
    )
    entity_count = (await db.execute(entity_count_stmt)).scalar() or 0

    # Latest briefing for the caller (if user_id present and they have one)
    briefing_excerpt: str | None = None
    if user_id is not None:
        briefing_stmt = (
            select(Briefing)
            .join(OrgMember, OrgMember.id == Briefing.org_member_id)
            .where(OrgMember.org_id == org_id, OrgMember.user_id == user_id)
            .order_by(Briefing.generated_at.desc())
            .limit(1)
        )
        b = (await db.execute(briefing_stmt)).scalar_one_or_none()
        if b is not None and isinstance(b.content, dict):
            for k in ("summary", "tldr", "headline"):
                v = b.content.get(k)
                if isinstance(v, str) and v:
                    briefing_excerpt = v[:280]
                    break

    available_tools = {
        "discover_context": ["get_context", "search_entities", "get_entity"],
        "task_lifecycle": [
            "find_matching_task",
            "create_task",
            "update_task_status",
            "update_task",
            "link_task",
        ],
        "planning": [
            "list_tasks",
            "get_task_context",
            "list_goals",
            "get_goal_progress",
            "get_urgency_scores",
        ],
        "wiki": ["list_wiki_features", "get_wiki_feature", "append_wiki_note"],
        "people": ["get_person_workload", "get_briefing"],
        "external": ["search_by_source"],
    }

    payload = {
        "org": {"name": org.name, "slug": org.slug, "id": str(org.id)},
        "member_count": member_count,
        "entity_count": entity_count,
        "user_bound": user_id is not None,
        "available_tools": available_tools,
        "sample_first_call": {
            "tool": "get_context",
            "args": {"task": "What am I working on right now?"},
            "why": "get_context pulls relevant chunks from your wiki + tasks ranked by your task description.",
        },
        "next_steps": [
            "Call get_context with your current task to pull relevant memory.",
            "Before creating a task, call find_matching_task to dedupe.",
            "Use update_task_status to keep state current as work progresses.",
        ],
        "briefing_excerpt": briefing_excerpt,
    }
    return json.dumps(payload, default=str)


# ── PR lifecycle (delegates to src/services/pr_lifecycle) ────────────


def _pr_to_dict(pr) -> dict:
    """Serialize a LivingPullRequest row for MCP responses."""
    return {
        "id": str(pr.id),
        "task_id": str(pr.task_id),
        "org_id": str(pr.org_id),
        "branch_name": pr.branch_name,
        "base_branch": pr.base_branch,
        "commit_head_sha": pr.commit_head_sha,
        "provider": pr.provider.value if pr.provider else None,
        "pr_number": pr.pr_number,
        "pr_url": pr.pr_url,
        "pr_state": pr.pr_state.value if pr.pr_state else None,
        "merge_state_status": (
            pr.merge_state_status.value if pr.merge_state_status else None
        ),
        "merge_strategy": (
            pr.merge_strategy.value if pr.merge_strategy else None
        ),
        "created_at": pr.created_at.isoformat() if pr.created_at else None,
        "updated_at": pr.updated_at.isoformat() if pr.updated_at else None,
        "merged_at": pr.merged_at.isoformat() if pr.merged_at else None,
    }


def _enum_or_error(enum_cls, value: str | None, code, field: str):
    """Coerce string -> enum or return error envelope. None passes through."""
    from src.mcp.errors import error_response

    if value is None:
        return None, None
    try:
        return enum_cls(value), None
    except ValueError:
        valid = [e.value for e in enum_cls]
        return None, error_response(
            code,
            message=f"{field}={value!r} is not valid. Try: {valid}.",
        )


async def update_pr_state(
    db: AsyncSession,
    org_id: UUID,
    task_id_str: str,
    *,
    action: str,
    branch_name: str | None = None,
    base_branch: str | None = None,
    commit_sha: str | None = None,
    commit_head_sha: str | None = None,
    provider: str | None = None,
    pr_number: int | None = None,
    pr_url: str | None = None,
    draft: bool = False,
    pr_state: str | None = None,
    merge_state_status: str | None = None,
    merge_strategy: str | None = None,
    merged_commit_sha: str | None = None,
) -> str:
    """Drive the PR lifecycle for a task. See server.py docstring for action shapes."""
    from src.mcp.errors import ErrorCode, error_response
    from src.services import pr_lifecycle as svc
    from src.shared.types import (
        LivingMergeStateStatus,
        LivingMergeStrategy,
        LivingPrProvider,
        LivingPrState,
    )

    try:
        task_uuid = UUID(task_id_str)
    except (ValueError, TypeError):
        return error_response(
            ErrorCode.INVALID_UUID, message=f"task_id is not a UUID: {task_id_str!r}"
        )

    try:
        if action == "branch_pushed":
            if not branch_name or not commit_sha:
                return error_response(
                    ErrorCode.INVALID_ARGUMENT,
                    message="action=branch_pushed requires branch_name and commit_sha.",
                )
            await svc.record_branch_pushed(
                db, org_id, task_uuid,
                svc.BranchPushedInput(branch_name=branch_name, commit_sha=commit_sha),
            )
            return json.dumps({"ok": True, "action": "branch_pushed"})

        elif action == "link":
            if not branch_name or not base_branch or not provider:
                return error_response(
                    ErrorCode.INVALID_ARGUMENT,
                    message=(
                        "action=link requires branch_name, base_branch, provider."
                    ),
                )
            prov_enum, err = _enum_or_error(
                LivingPrProvider, provider, ErrorCode.INVALID_ARGUMENT, "provider"
            )
            if err:
                return err
            pr = await svc.upsert_pull_request(
                db, org_id, task_uuid,
                svc.PullRequestUpsertInput(
                    branch_name=branch_name,
                    base_branch=base_branch,
                    provider=prov_enum,
                    pr_number=pr_number,
                    pr_url=pr_url,
                    commit_head_sha=commit_head_sha,
                    draft=draft,
                ),
            )
            return json.dumps({"ok": True, "action": "link", "pr": _pr_to_dict(pr)})

        elif action == "patch":
            state_enum, err = _enum_or_error(
                LivingPrState, pr_state, ErrorCode.INVALID_STATUS, "pr_state"
            )
            if err:
                return err
            ms_enum, err = _enum_or_error(
                LivingMergeStateStatus,
                merge_state_status,
                ErrorCode.INVALID_STATUS,
                "merge_state_status",
            )
            if err:
                return err
            pr = await svc.patch_pull_request(
                db, org_id, task_uuid,
                svc.PullRequestPatchInput(
                    pr_state=state_enum,
                    merge_state_status=ms_enum,
                    commit_head_sha=commit_head_sha,
                ),
            )
            return json.dumps({"ok": True, "action": "patch", "pr": _pr_to_dict(pr)})

        elif action == "merge":
            if not merge_strategy or not merged_commit_sha:
                return error_response(
                    ErrorCode.INVALID_ARGUMENT,
                    message=(
                        "action=merge requires merge_strategy and merged_commit_sha."
                    ),
                )
            strat_enum, err = _enum_or_error(
                LivingMergeStrategy,
                merge_strategy,
                ErrorCode.INVALID_ARGUMENT,
                "merge_strategy",
            )
            if err:
                return err
            pr = await svc.record_merge(
                db, org_id, task_uuid,
                svc.MergeRecordInput(
                    merge_strategy=strat_enum,
                    merged_commit_sha=merged_commit_sha,
                ),
            )
            return json.dumps({"ok": True, "action": "merge", "pr": _pr_to_dict(pr)})

        else:
            return error_response(
                ErrorCode.INVALID_ARGUMENT,
                message=(
                    f"action={action!r} unknown. "
                    "Try one of: branch_pushed, link, patch, merge."
                ),
            )
    except svc.PrServiceError as e:
        code_map = {
            "task_not_found": ErrorCode.TASK_NOT_FOUND,
            "pr_not_found": ErrorCode.ENTITY_NOT_FOUND,
        }
        return error_response(
            code_map.get(e.code, ErrorCode.INTERNAL_ERROR),
            message=e.message,
            suggested_next_tool="list_tasks" if e.code == "task_not_found" else None,
        )


async def get_pr_state(
    db: AsyncSession,
    org_id: UUID,
    task_id_str: str,
) -> str:
    """Read the PR row attached to this task, if any."""
    from src.mcp.errors import ErrorCode, error_response
    from src.services import pr_lifecycle as svc

    try:
        task_uuid = UUID(task_id_str)
    except (ValueError, TypeError):
        return error_response(
            ErrorCode.INVALID_UUID, message=f"task_id is not a UUID: {task_id_str!r}"
        )

    try:
        pr = await svc.get_pr_for_task(db, org_id, task_uuid)
    except svc.PrServiceError as e:
        return error_response(ErrorCode.TASK_NOT_FOUND, message=e.message)
    if pr is None:
        return json.dumps({"pr": None, "task_id": task_id_str})
    return json.dumps({"pr": _pr_to_dict(pr)})



# ── PRD proposals (WS1) ───────────────────────────────────────────────


def _proposal_to_dict(p) -> dict:
    return {
        "id": str(p.id),
        "feature_slug": p.feature_slug,
        "section_anchor": p.section_anchor,
        "status": p.status,
        "rationale": p.rationale,
        "diff_md_size": len(p.diff_md or ""),
        "base_content_hash": p.base_content_hash,
        "applied_content_hash": p.applied_content_hash,
        "decided_at": p.decided_at.isoformat() if p.decided_at else None,
        "decided_reason": p.decided_reason,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "expires_at": p.expires_at.isoformat() if p.expires_at else None,
    }


def _translate_proposal_error(e):
    from src.mcp.errors import ErrorCode, error_response
    from src.services.proposals import ProposalErrorCode

    code_map = {
        ProposalErrorCode.FEATURE_NOT_FOUND: ErrorCode.WIKI_FEATURE_NOT_FOUND,
        ProposalErrorCode.DUPLICATE_PENDING: ErrorCode.PROPOSAL_DUPLICATE_PENDING,
        ProposalErrorCode.NOT_FOUND: ErrorCode.PROPOSAL_NOT_FOUND,
        ProposalErrorCode.NOT_PENDING: ErrorCode.PROPOSAL_NOT_FOUND,
        ProposalErrorCode.STALE: ErrorCode.PROPOSAL_STALE,
    }
    hint = None
    suggested = None
    if e.code == ProposalErrorCode.FEATURE_NOT_FOUND:
        hint = "Call list_wiki_features to see valid slugs."
        suggested = "list_wiki_features"
    elif e.code == ProposalErrorCode.STALE:
        hint = "Call get_wiki_feature to fetch current content, regenerate the diff, then re-propose."
        suggested = "get_wiki_feature"
    elif e.code == ProposalErrorCode.DUPLICATE_PENDING:
        hint = "Call list_proposals(status='pending') to find the existing one."
        suggested = "list_proposals"
    return error_response(
        code_map.get(e.code, ErrorCode.INTERNAL_ERROR),
        message=e.message,
        hint=hint,
        suggested_next_tool=suggested,
        extra=e.extra,
    )


async def propose_prd_update(
    db: AsyncSession,
    org_id: UUID,
    proposer_user_id: UUID | None,
    feature_slug: str,
    section_anchor: str,
    diff_md: str,
    rationale: str = "",
    expires_in_days: int = 7,
) -> str:
    """Propose an edit to a wiki feature section, awaiting user approval."""
    from src.services.proposals import ProposalServiceError, ProposeIn
    from src.services.proposals import propose_prd_update as _svc

    if expires_in_days < 1 or expires_in_days > 30:
        from src.mcp.errors import ErrorCode, error_response
        return error_response(
            ErrorCode.INVALID_ARGUMENT,
            message="expires_in_days must be between 1 and 30.",
        )

    try:
        proposal = await _svc(
            db, org_id, proposer_user_id,
            ProposeIn(
                feature_slug=feature_slug,
                section_anchor=section_anchor,
                diff_md=diff_md,
                rationale=rationale,
                expires_in_days=expires_in_days,
            ),
        )
    except ProposalServiceError as e:
        return _translate_proposal_error(e)
    return json.dumps(
        {
            "ok": True,
            "proposal": _proposal_to_dict(proposal),
            "user_action_required": (
                f"Visit /prd-proposals/{proposal.id} to approve or reject."
            ),
        }
    )


async def get_proposal_status(
    db: AsyncSession,
    org_id: UUID,
    proposal_id_str: str,
) -> str:
    """Read a proposal by id (org-scoped)."""
    from src.mcp.errors import ErrorCode, error_response
    from src.services.proposals import ProposalServiceError
    from src.services.proposals import get_proposal as _svc_get

    try:
        proposal_uuid = UUID(proposal_id_str)
    except (ValueError, TypeError):
        return error_response(
            ErrorCode.INVALID_UUID,
            message=f"proposal_id is not a UUID: {proposal_id_str!r}",
        )

    try:
        proposal = await _svc_get(db, org_id, proposal_uuid)
    except ProposalServiceError as e:
        return _translate_proposal_error(e)
    return json.dumps({"proposal": _proposal_to_dict(proposal)})


async def list_proposals_tool(
    db: AsyncSession,
    org_id: UUID,
    *,
    status: str | None = None,
    feature_slug: str | None = None,
    proposer_user_id: UUID | None = None,
    limit: int = 50,
) -> str:
    """List proposals scoped to org with optional filters."""
    from src.services.proposals import list_proposals as _svc_list

    proposals = await _svc_list(
        db, org_id,
        status=status,
        feature_slug=feature_slug,
        proposer_user_id=proposer_user_id,
        limit=limit,
    )
    return json.dumps(
        {"items": [_proposal_to_dict(p) for p in proposals], "count": len(proposals)}
    )
