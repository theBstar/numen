"""FalkorDB graph traversal and analytics queries via Cypher.

Drop-in replacement for ``queries.py`` - identical function signatures.
All functions accept ``db: AsyncSession`` as first arg (ignored - FalkorDB
uses its own connection).

Functions that receive an org_id use it directly to select the FalkorDB graph.
Functions that only receive an entity_id need org context - callers must
ensure org_id is passed via the ``org_id`` keyword argument.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from src.graph.falkor_client import get_org_graph as _get_graph
from src.graph.falkor_repository import (
    GraphEdge,
    _edge_to_dict,
    _node_to_dict,
    _node_to_entity,
)

logger = logging.getLogger(__name__)


# ── Graph neighborhood ────────────────────────────────────────────────


async def get_entity_neighborhood(
    db,
    entity_id: UUID,
    depth: int = 2,
    *,
    org_id: UUID | None = None,
) -> dict:
    """BFS traversal returning entities and edges within N hops."""
    if org_id is None:
        return {"entities": [], "edges": []}
    graph = await _get_graph(org_id)
    eid = str(entity_id)

    center_result = await graph.query(
        "MATCH (n:Entity {id: $id}) RETURN n",
        {"id": eid},
    )
    if not center_result.result_set:
        return {"entities": [], "edges": []}

    center = _node_to_entity(center_result.result_set[0][0])

    neighbor_result = await graph.query(
        f"MATCH (start:Entity {{id: $id}})-[*1..{int(depth)}]-(neighbor:Entity) RETURN DISTINCT neighbor",
        {"id": eid},
    )
    entities = [center]
    entity_ids = {eid}
    for row in neighbor_result.result_set:
        n = _node_to_entity(row[0])
        nid = str(n.id) if n.id else None
        if nid and nid not in entity_ids:
            entities.append(n)
            entity_ids.add(nid)

    all_ids = list(entity_ids)
    edge_result = await graph.query(
        "MATCH (a:Entity)-[r]->(b:Entity) WHERE a.id IN $ids AND b.id IN $ids RETURN r, a.id, b.id, type(r)",
        {"ids": all_ids},
    )
    edges = []
    for row in edge_result.result_set:
        e = _edge_to_dict(row[0])
        e["from_entity_id"] = UUID(row[1]) if isinstance(row[1], str) else row[1]
        e["to_entity_id"] = UUID(row[2]) if isinstance(row[2], str) else row[2]
        e["type"] = row[3].lower() if row[3] else e.get("type", "")
        edges.append(GraphEdge(e))

    return {"entities": entities, "edges": edges}


# ── Blocking chain ────────────────────────────────────────────────────


async def get_blocking_chain(db, task_id: UUID, *, org_id: UUID | None = None) -> list:
    """Follow BLOCKS edges upstream."""
    if org_id is None:
        return []
    graph = await _get_graph(org_id)
    tid = str(task_id)

    result = await graph.query(
        "MATCH path = (task:Task {id: $id})<-[:BLOCKS*]-(blocker) RETURN nodes(path)",
        {"id": tid},
    )

    if not result.result_set:
        task_result = await graph.query(
            "MATCH (n:Entity {id: $id}) RETURN n",
            {"id": tid},
        )
        if task_result.result_set:
            return [_node_to_entity(task_result.result_set[0][0])]
        return []

    seen = set()
    chain = []
    for row in result.result_set:
        for node in row[0]:
            n = _node_to_entity(node)
            nid = n.id
            if nid and nid not in seen:
                seen.add(nid)
                chain.append(n)
    return chain


# ── Person workload ───────────────────────────────────────────────────


async def get_person_workload(db, person_id: UUID, *, org_id: UUID | None = None) -> dict:
    """Count tasks by status for a person."""
    if org_id is None:
        return {"by_status": {}, "total": 0}
    graph = await _get_graph(org_id)
    pid = str(person_id)

    result = await graph.query(
        "MATCH (p:Person {id: $id})-[:OWNS|ASSIGNED_TO]->(t:Task) RETURN t.status AS status, count(t) AS cnt",
        {"id": pid},
    )

    workload: dict[str, int] = {}
    total = 0
    for row in result.result_set:
        status = row[0] or "unknown"
        count = row[1]
        workload[status] = count
        total += count

    return {"by_status": workload, "total": total}


async def get_person_workload_hybrid(
    db,
    person_id: UUID,
    email: str | None = None,
    *,
    org_id: UUID | None = None,
) -> dict:
    """Workload with email fallback."""
    return await get_person_workload(db, person_id, org_id=org_id)


# ── Person tasks and PRs ─────────────────────────────────────────────


async def get_person_tasks(
    db,
    person_id: UUID,
    *,
    since: str | None = None,
    statuses: list[str] | None = None,
    include_authored: bool = False,
    org_id: UUID | None = None,
) -> list:
    """Get tasks for a person via OWNS/ASSIGNED_TO edges."""
    if org_id is None:
        return []
    graph = await _get_graph(org_id)
    pid = str(person_id)

    wheres = []
    params: dict[str, Any] = {"id": pid}

    if since:
        wheres.append("t.updated_at >= $since")
        params["since"] = since
    if statuses:
        wheres.append("t.status IN $statuses")
        params["statuses"] = statuses

    where_clause = f"WHERE {' AND '.join(wheres)}" if wheres else ""

    result = await graph.query(
        f"MATCH (p:Person {{id: $id}})-[:OWNS|ASSIGNED_TO]->(t:Task) "
        f"{where_clause} "
        "RETURN DISTINCT t ORDER BY t.updated_at DESC",
        params,
    )
    tasks = [_node_to_entity(row[0]) for row in result.result_set]

    if include_authored:
        authored_result = await graph.query(
            "MATCH (p:Person {id: $id})-[:AUTHORED]->(pr:CommitPR)-[:SHIPS_TO]->(t:Task) RETURN DISTINCT t",
            {"id": pid},
        )
        seen_ids = {t.id for t in tasks}
        for row in authored_result.result_set:
            t = _node_to_entity(row[0])
            if t.id not in seen_ids:
                tasks.append(t)

    return tasks


async def get_person_prs(
    db,
    person_id: UUID,
    *,
    status: str | None = None,
    role: str | None = None,
    org_id: UUID | None = None,
) -> list:
    """Get PRs for a person via AUTHORED or REVIEWS edges."""
    if org_id is None:
        return []
    graph = await _get_graph(org_id)
    pid = str(person_id)

    if role == "reviewer":
        edge_type = "REVIEWS"
    elif role == "author":
        edge_type = "AUTHORED"
    else:
        edge_type = "AUTHORED|REVIEWS"

    where_clause = ""
    params: dict[str, Any] = {"id": pid}
    if status:
        where_clause = "WHERE pr.status = $status"
        params["status"] = status

    result = await graph.query(
        f"MATCH (p:Person {{id: $id}})-[:{edge_type}]->(pr:CommitPR) "
        f"{where_clause} "
        "RETURN DISTINCT pr ORDER BY pr.updated_at DESC",
        params,
    )
    return [_node_to_entity(row[0]) for row in result.result_set]


# ── Project queries ───────────────────────────────────────────────────


async def get_project_tasks(db, project_id: UUID, *, org_id: UUID | None = None) -> list:
    """Get tasks contained in a project."""
    if org_id is None:
        return []
    graph = await _get_graph(org_id)
    result = await graph.query(
        "MATCH (p:Project {id: $id})-[:CONTAINS]->(t:Task) RETURN t ORDER BY t.updated_at DESC",
        {"id": str(project_id)},
    )
    return [_node_to_entity(row[0]) for row in result.result_set]


async def get_project_stats(db, project_id: UUID, *, org_id: UUID | None = None) -> dict:
    """Get project task statistics."""
    if org_id is None:
        return {
            "total_tasks": 0,
            "completed": 0,
            "blocked": 0,
            "by_status": {},
            "total": 0,
            "done": 0,
        }
    graph = await _get_graph(org_id)
    pid = str(project_id)

    result = await graph.query(
        "MATCH (p:Project {id: $id})-[:CONTAINS]->(t:Task) RETURN t.status AS status, count(t) AS cnt",
        {"id": pid},
    )

    by_status: dict[str, int] = {}
    total = 0
    completed = 0
    for row in result.result_set:
        status = row[0] or "unknown"
        count = row[1]
        by_status[status] = count
        total += count
        if status in ("done", "merged"):
            completed += count

    block_result = await graph.query(
        "MATCH (p:Project {id: $id})-[:CONTAINS]->(t:Task)<-[:BLOCKS]-(b:Task) RETURN count(DISTINCT t) AS cnt",
        {"id": pid},
    )
    blocked = block_result.result_set[0][0] if block_result.result_set else 0

    return {
        "total_tasks": total,
        "completed": completed,
        "blocked": blocked,
        "by_status": by_status,
        "total": total,
        "done": completed,
    }


# ── Goal queries ──────────────────────────────────────────────────────


async def get_goal_coverage(db, org_id: UUID) -> list[dict]:
    """Count tasks/features tagged to goals."""
    graph = await _get_graph(org_id)
    result = await graph.query(
        "MATCH (e:Entity)-[:TAGGED_TO]->(g:Goal) RETURN g.id AS goal_id, count(e) AS cnt",
    )
    return [{"goal_id": row[0], "count": row[1]} for row in result.result_set]


async def get_goal_tree(db, org_id: UUID) -> list[dict]:
    """Build nested goal hierarchy."""
    graph = await _get_graph(org_id)
    result = await graph.query(
        "MATCH (g:Goal) WHERE g.merged_into IS NULL "
        "OPTIONAL MATCH (g)-[:PARENT_OF]->(child:Goal) "
        "WHERE child.merged_into IS NULL "
        "RETURN g, collect(DISTINCT child) AS children "
        "ORDER BY g.canonical_name",
    )

    tree = []
    for row in result.result_set:
        goal = _node_to_dict(row[0])
        children = [_node_to_dict(c) for c in (row[1] or [])]
        goal["children"] = children
        tree.append(goal)
    return tree


async def compute_goal_progress(db, goal_id: UUID, *, org_id: UUID | None = None) -> dict:
    """Compute task completion percentage for a goal."""
    if org_id is None:
        return {"task_completion_pct": 0, "total_tasks": 0, "completed_tasks": 0}
    graph = await _get_graph(org_id)
    gid = str(goal_id)

    result = await graph.query(
        "MATCH (t:Task)-[:TAGGED_TO]->(g:Goal {id: $id}) RETURN t.status AS status, count(t) AS cnt",
        {"id": gid},
    )

    total = 0
    completed = 0
    for row in result.result_set:
        status = row[0] or "unknown"
        count = row[1]
        total += count
        if status in ("done", "merged"):
            completed += count

    pct = (completed / total * 100) if total > 0 else 0
    return {
        "task_completion_pct": round(pct, 1),
        "total_tasks": total,
        "completed_tasks": completed,
    }


# ── Team queries ──────────────────────────────────────────────────────


async def get_team_members(db, goal_id: UUID, *, org_id: UUID | None = None) -> list:
    """Find team members via REPORTS_TO edges."""
    if org_id is None:
        return []
    graph = await _get_graph(org_id)
    result = await graph.query(
        "MATCH (p:Person)-[:REPORTS_TO]->(m:Person {id: $id}) RETURN p",
        {"id": str(goal_id)},
    )
    return [_node_to_entity(row[0]) for row in result.result_set]


async def get_org_workloads(db, org_id: UUID) -> dict:
    """Count tasks by status for every person in the org, in one query.

    Same shape as ``get_person_workload`` but keyed by person id. Callers
    summarising a whole team should use this rather than looping, which
    issues one graph round trip per person.
    """
    graph = await _get_graph(org_id)
    result = await graph.query(
        "MATCH (p:Person)-[:OWNS|ASSIGNED_TO]->(t:Task) "
        "RETURN p.id AS pid, t.status AS status, count(t) AS cnt"
    )

    workloads: dict[str, dict] = {}
    for row in result.result_set:
        person_id, status, count = row[0], row[1] or "unknown", row[2]
        entry = workloads.setdefault(person_id, {"by_status": {}, "total": 0})
        entry["by_status"][status] = count
        entry["total"] += count
    return workloads


async def get_team_workload_summary(db, goal_id: UUID, *, org_id: UUID | None = None) -> dict:
    """Aggregate workload across team members."""
    members = await get_team_members(db, goal_id, org_id=org_id)
    summary: dict[str, dict] = {}
    for member in members:
        mid = member.id
        if mid:
            workload = await get_person_workload(db, mid, org_id=org_id)
            summary[mid] = workload
    return summary


# ── Analytics queries ─────────────────────────────────────────────────


async def get_stalled_prs(db, org_id: UUID, days: int = 7) -> list:
    """Find PRs not updated for N days."""
    graph = await _get_graph(org_id)
    result = await graph.query(
        "MATCH (pr:CommitPR) "
        "WHERE pr.status <> 'merged' AND pr.status <> 'closed' "
        "AND pr.merged_into IS NULL "
        "RETURN pr ORDER BY pr.updated_at ASC",
    )

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    stalled = []
    for row in result.result_set:
        pr = _node_to_entity(row[0])
        updated = pr.get("updated_at", "")
        if isinstance(updated, datetime):
            updated = updated.isoformat()
        if updated and updated < cutoff:
            stalled.append(pr)
    return stalled


async def get_cross_team_blocking(db, org_id: UUID) -> list[dict]:
    """Find cross-team blocking incidents."""
    graph = await _get_graph(org_id)
    result = await graph.query(
        "MATCH (blocker:Task)-[:BLOCKS]->(blocked:Task) "
        "RETURN blocker, count(blocked) AS blocked_count "
        "ORDER BY blocked_count DESC",
    )
    return [{"blocker": _node_to_entity(row[0]), "blocked_count": row[1]} for row in result.result_set]


async def get_unowned_goals(db, org_id: UUID) -> list:
    """Find goals without OWNS edges."""
    graph = await _get_graph(org_id)
    result = await graph.query(
        "MATCH (g:Goal) "
        "WHERE g.merged_into IS NULL AND NOT ((:Person)-[:OWNS]->(g)) "
        "RETURN g ORDER BY g.canonical_name",
    )
    return [_node_to_entity(row[0]) for row in result.result_set]


# ── Full org graph (visualization) ───────────────────────────────────


async def get_org_graph(
    db,
    org_id: UUID,
    entity_types: list | None = None,
    edge_types: list | None = None,
    search: str | None = None,
    limit: int = 500,
    offset: int = 0,
) -> dict:
    """Return a filtered, paginated slice of the org's full context graph."""
    graph = await _get_graph(org_id)

    wheres = []
    params: dict[str, Any] = {"lim": limit, "off": offset}

    if entity_types:
        type_values = [et.value if hasattr(et, "value") else str(et) for et in entity_types]
        wheres.append("n.type IN $etypes")
        params["etypes"] = type_values
    if search:
        wheres.append("toLower(n.canonical_name) CONTAINS toLower($search)")
        params["search"] = search
    wheres.append("n.merged_into IS NULL")

    where_clause = f"WHERE {' AND '.join(wheres)}" if wheres else ""

    count_result = await graph.query(
        f"MATCH (n:Entity) {where_clause} RETURN count(n) AS cnt",
        params,
    )
    total_entities = count_result.result_set[0][0] if count_result.result_set else 0

    entity_result = await graph.query(
        f"MATCH (n:Entity) {where_clause} RETURN n ORDER BY n.updated_at DESC SKIP $off LIMIT $lim",
        params,
    )
    entities = []
    for row in entity_result.result_set:
        e = _node_to_entity(row[0])
        e.org_id = org_id  # Inject org_id (implicit in graph selection)
        entities.append(e)
    entity_ids = [str(e.id) for e in entities if e.id]

    edges: list = []
    total_edges = 0
    if entity_ids:
        edge_params: dict[str, Any] = {"ids": entity_ids}

        edge_type_filter = ""
        if edge_types:
            edge_type_values = [et.value.upper() if hasattr(et, "value") else str(et).upper() for et in edge_types]
            edge_type_filter = f"AND type(r) IN {edge_type_values}"

        edge_count_result = await graph.query(
            f"MATCH (a:Entity)-[r]->(b:Entity) "
            f"WHERE a.id IN $ids AND b.id IN $ids {edge_type_filter} "
            "RETURN count(r) AS cnt",
            edge_params,
        )
        total_edges = edge_count_result.result_set[0][0] if edge_count_result.result_set else 0

        edge_result = await graph.query(
            f"MATCH (a:Entity)-[r]->(b:Entity) "
            f"WHERE a.id IN $ids AND b.id IN $ids {edge_type_filter} "
            "RETURN r, a.id AS from_id, b.id AS to_id, type(r) AS rtype",
            edge_params,
        )
        for row in edge_result.result_set:
            e = _edge_to_dict(row[0])
            e["from_entity_id"] = row[1]
            e["to_entity_id"] = row[2]
            e["type"] = row[3].lower() if row[3] else e.get("type", "")
            edges.append(GraphEdge(e))

    return {
        "entities": entities,
        "edges": edges,
        "total_entities": total_entities,
        "total_edges": total_edges,
        "has_more": (offset + limit) < total_entities,
    }


# ── Entity timeline ──────────────────────────────────────────────────


async def get_entity_timeline(
    db,
    entity_id: UUID,
    limit: int = 50,
    *,
    org_id: UUID | None = None,
) -> list:
    """Chronological edge events for an entity."""
    if org_id is None:
        return []
    graph = await _get_graph(org_id)
    eid = str(entity_id)

    result = await graph.query(
        "MATCH (a:Entity {id: $id})-[r]-(b:Entity) "
        "RETURN r, a.id, b.id, type(r) "
        "ORDER BY r.last_active_at DESC LIMIT $lim",
        {"id": eid, "lim": limit},
    )

    timeline = []
    for row in result.result_set:
        e = _edge_to_dict(row[0])
        e["from_entity_id"] = row[1]
        e["to_entity_id"] = row[2]
        e["type"] = row[3].lower() if row[3] else e.get("type", "")
        timeline.append(GraphEdge(e))
    return timeline


# ── Connected entity search ──────────────────────────────────────────


async def find_connected_entities(
    db,
    entity_id: UUID,
    target_type,
    max_hops: int = 3,
    *,
    org_id: UUID | None = None,
) -> list:
    """Find entities of a specific type within N hops."""
    if org_id is None:
        return []
    graph = await _get_graph(org_id)
    eid = str(entity_id)
    ttype = target_type.value if hasattr(target_type, "value") else str(target_type)

    result = await graph.query(
        f"MATCH (start:Entity {{id: $id}})-[*1..{int(max_hops)}]-(target:Entity) "
        "WHERE target.type = $ttype "
        "RETURN DISTINCT target",
        {"id": eid, "ttype": ttype},
    )
    return [_node_to_entity(row[0]) for row in result.result_set]


# ── PRD (Document) queries ──────────────────────────────────────────


async def get_prd_tree(db, org_id: UUID) -> list[dict]:
    """Get all Document entities and CONTAINS edges to build a folder tree.

    Returns a flat list of dicts, each with ``{id, title, node_type,
    status, parent_id, position, children}`` where ``children`` is a
    nested list of the same shape.  Top-level items have
    ``parent_id=None``.
    """
    graph = await _get_graph(org_id)

    result = await graph.query(
        "MATCH (d:Document) "
        "OPTIONAL MATCH (parent:Document)-[c:CONTAINS]->(d) "
        "RETURN d.id AS id, d.canonical_name AS title, "
        "d.properties AS props, parent.id AS parent_id, c",
    )

    # Build lookup of flat nodes keyed by id
    nodes_by_id: dict[str, dict] = {}
    for row in result.result_set:
        nid = row[0]
        if nid is None or nid in nodes_by_id:
            continue
        props = row[2]
        if isinstance(props, str):
            try:
                props = json.loads(props)
            except (json.JSONDecodeError, TypeError):
                props = {}
        if not isinstance(props, dict):
            props = {}

        edge_props = _edge_to_dict(row[4]) if row[4] else {}
        position = edge_props.get("position")

        nodes_by_id[nid] = {
            "id": nid,
            "title": row[1],
            "node_type": props.get("node_type"),
            "status": props.get("prd_status"),
            "parent_id": row[3],
            "position": position,
            "children": [],
        }

    # Assemble tree: nest children under their parents
    roots: list[dict] = []
    for node in nodes_by_id.values():
        pid = node["parent_id"]
        if pid and pid in nodes_by_id:
            nodes_by_id[pid]["children"].append(node)
        else:
            roots.append(node)

    # Sort children by position (None-safe)
    def _sort_children(items: list[dict]) -> None:
        items.sort(key=lambda n: (n["position"] is None, n["position"] or 0))
        for item in items:
            _sort_children(item["children"])

    _sort_children(roots)
    return roots


async def get_prd_references(
    db,
    entity_id: UUID,
    *,
    org_id: UUID | None = None,
) -> list[dict]:
    """Get all PRDs that reference or are referenced by this PRD.

    Returns a list of dicts with ``{prd_id, prd_title, direction,
    section_slug}`` where direction is ``'outgoing'`` or ``'incoming'``.
    """
    if org_id is None:
        return []
    graph = await _get_graph(org_id)
    eid = str(entity_id)

    # Outgoing references
    out_result = await graph.query(
        "MATCH (d:Document {id: $id})-[r:REFERENCES]->(target:Document) "
        "RETURN target.id AS prd_id, target.canonical_name AS prd_title, r",
        {"id": eid},
    )
    refs: list[dict] = []
    for row in out_result.result_set:
        edge_props = _edge_to_dict(row[2]) if row[2] else {}
        refs.append(
            {
                "prd_id": row[0],
                "prd_title": row[1],
                "direction": "outgoing",
                "section_slug": edge_props.get("section_slug"),
            }
        )

    # Incoming references
    in_result = await graph.query(
        "MATCH (source:Document)-[r:REFERENCES]->(d:Document {id: $id}) "
        "RETURN source.id AS prd_id, source.canonical_name AS prd_title, r",
        {"id": eid},
    )
    for row in in_result.result_set:
        edge_props = _edge_to_dict(row[2]) if row[2] else {}
        refs.append(
            {
                "prd_id": row[0],
                "prd_title": row[1],
                "direction": "incoming",
                "section_slug": edge_props.get("section_slug"),
            }
        )

    return refs


async def get_prd_coverage(
    db,
    entity_id: UUID,
    *,
    org_id: UUID | None = None,
) -> dict:
    """Get implementation coverage for a PRD.

    Returns ``{total_tasks, tasks_done, tasks_in_progress, tasks_todo,
    coverage_pct, linked_prs, has_design}``.
    """
    if org_id is None:
        return {
            "total_tasks": 0,
            "tasks_done": 0,
            "tasks_in_progress": 0,
            "tasks_todo": 0,
            "coverage_pct": 0.0,
            "linked_prs": 0,
            "has_design": False,
        }
    graph = await _get_graph(org_id)
    eid = str(entity_id)

    # Tasks linked via IMPLEMENTS
    task_result = await graph.query(
        "MATCH (t:Task)-[:IMPLEMENTS]->(d:Document {id: $id}) "
        "RETURN t.status AS status, count(t) AS cnt",
        {"id": eid},
    )
    total_tasks = 0
    tasks_done = 0
    tasks_in_progress = 0
    tasks_todo = 0
    for row in task_result.result_set:
        status = row[0] or "unknown"
        count = row[1]
        total_tasks += count
        if status in ("done", "merged"):
            tasks_done += count
        elif status == "in_progress":
            tasks_in_progress += count
        elif status == "todo":
            tasks_todo += count

    coverage_pct = round((tasks_done / total_tasks * 100), 1) if total_tasks > 0 else 0.0

    # PRs linked via IMPLEMENTS
    pr_result = await graph.query(
        "MATCH (pr:CommitPR)-[:IMPLEMENTS]->(d:Document {id: $id}) RETURN count(pr) AS cnt",
        {"id": eid},
    )
    linked_prs = pr_result.result_set[0][0] if pr_result.result_set else 0

    # Design documents linked via DESIGNS_FOR
    design_result = await graph.query(
        "MATCH (any)-[:DESIGNS_FOR]->(d:Document {id: $id}) RETURN count(any) AS cnt",
        {"id": eid},
    )
    has_design = (design_result.result_set[0][0] if design_result.result_set else 0) > 0

    return {
        "total_tasks": total_tasks,
        "tasks_done": tasks_done,
        "tasks_in_progress": tasks_in_progress,
        "tasks_todo": tasks_todo,
        "coverage_pct": coverage_pct,
        "linked_prs": linked_prs,
        "has_design": has_design,
    }


async def get_prd_stakeholders(
    db,
    entity_id: UUID,
    *,
    org_id: UUID | None = None,
) -> list[dict]:
    """Get people connected to a PRD as owners, stakeholders, or reviewers.

    Returns a list of dicts with ``{person_id, person_name, role_type}``
    where role_type is ``'owner'``, ``'stakeholder'``, or ``'reviewer'``.
    """
    if org_id is None:
        return []
    graph = await _get_graph(org_id)
    eid = str(entity_id)

    # Owners
    owner_result = await graph.query(
        "MATCH (p:Person)-[:OWNS]->(d:Document {id: $id}) "
        "RETURN p.id AS person_id, p.canonical_name AS person_name",
        {"id": eid},
    )
    stakeholders: list[dict] = []
    seen: set[str] = set()
    for row in owner_result.result_set:
        key = f"{row[0]}:owner"
        if key not in seen:
            seen.add(key)
            stakeholders.append(
                {
                    "person_id": row[0],
                    "person_name": row[1],
                    "role_type": "owner",
                }
            )

    # Stakeholders
    sh_result = await graph.query(
        "MATCH (p:Person)-[:STAKEHOLDER_OF]->(d:Document {id: $id}) "
        "RETURN p.id AS person_id, p.canonical_name AS person_name",
        {"id": eid},
    )
    for row in sh_result.result_set:
        key = f"{row[0]}:stakeholder"
        if key not in seen:
            seen.add(key)
            stakeholders.append(
                {
                    "person_id": row[0],
                    "person_name": row[1],
                    "role_type": "stakeholder",
                }
            )

    # Reviewers
    rev_result = await graph.query(
        "MATCH (p:Person)-[:REVIEWER_OF]->(d:Document {id: $id}) "
        "RETURN p.id AS person_id, p.canonical_name AS person_name",
        {"id": eid},
    )
    for row in rev_result.result_set:
        key = f"{row[0]}:reviewer"
        if key not in seen:
            seen.add(key)
            stakeholders.append(
                {
                    "person_id": row[0],
                    "person_name": row[1],
                    "role_type": "reviewer",
                }
            )

    return stakeholders


async def get_prds_for_goal(
    db,
    goal_id: UUID,
    *,
    org_id: UUID | None = None,
) -> list[dict]:
    """Get all PRD documents tagged to a goal.

    Returns a list of dicts with ``{id, title, status, node_type}``.
    """
    if org_id is None:
        return []
    graph = await _get_graph(org_id)
    gid = str(goal_id)

    result = await graph.query(
        "MATCH (d:Document)-[:TAGGED_TO]->(g:Goal {id: $id}) "
        "RETURN d.id AS id, d.canonical_name AS title, d.properties AS props",
        {"id": gid},
    )

    prds: list[dict] = []
    for row in result.result_set:
        props = row[2]
        if isinstance(props, str):
            try:
                props = json.loads(props)
            except (json.JSONDecodeError, TypeError):
                props = {}
        if not isinstance(props, dict):
            props = {}
        prds.append(
            {
                "id": row[0],
                "title": row[1],
                "status": props.get("prd_status"),
                "node_type": props.get("node_type"),
            }
        )
    return prds


async def get_prd_impact_graph(
    db,
    entity_id: UUID,
    depth: int = 2,
    *,
    org_id: UUID | None = None,
) -> dict:
    """Get the full neighborhood of a PRD within N hops.

    Returns ``{entities: list, edges: list}`` in the same format as
    :func:`get_entity_neighborhood`, starting from the given Document
    entity and traversing goals, tasks, PRs, designs, and other PRDs.
    """
    if org_id is None:
        return {"entities": [], "edges": []}
    graph = await _get_graph(org_id)
    eid = str(entity_id)

    # Fetch center node (use Document label for specificity)
    center_result = await graph.query(
        "MATCH (n:Document {id: $id}) RETURN n",
        {"id": eid},
    )
    if not center_result.result_set:
        # Fall back to generic Entity label
        center_result = await graph.query(
            "MATCH (n:Entity {id: $id}) RETURN n",
            {"id": eid},
        )
    if not center_result.result_set:
        return {"entities": [], "edges": []}

    center = _node_to_entity(center_result.result_set[0][0])

    # Gather neighbors within depth hops
    neighbor_result = await graph.query(
        "MATCH (start:Entity {id: $id})-[*1..$d]-(neighbor:Entity) RETURN DISTINCT neighbor",
        {"id": eid, "d": depth},
    )
    entities = [center]
    entity_ids = {eid}
    for row in neighbor_result.result_set:
        n = _node_to_entity(row[0])
        nid = n.id
        if nid and nid not in entity_ids:
            entities.append(n)
            entity_ids.add(nid)

    # Collect edges between all discovered entities
    all_ids = list(entity_ids)
    edge_result = await graph.query(
        "MATCH (a:Entity)-[r]->(b:Entity) "
        "WHERE a.id IN $ids AND b.id IN $ids "
        "RETURN r, a.id, b.id, type(r)",
        {"ids": all_ids},
    )
    edges = []
    for row in edge_result.result_set:
        e = _edge_to_dict(row[0])
        e["from_entity_id"] = row[1]
        e["to_entity_id"] = row[2]
        e["type"] = row[3].lower() if row[3] else e.get("type", "")
        edges.append(GraphEdge(e))

    return {"entities": entities, "edges": edges}
