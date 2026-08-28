"""Centralized graph API - the single interface for all entity and edge operations.

ALL code outside ``src/graph/`` MUST use functions exported from this module.
Direct imports of Entity/Edge models or raw SQLAlchemy queries against them
are prohibited outside this package.

Graph data lives exclusively in FalkorDB. PostgreSQL is used only for
relational data (users, orgs, auth, audit logs).
"""

# ── Repository: entity and edge CRUD (FalkorDB) ─────────────────────
# ── Context graph: TrustGraph-inspired extraction ─────────────────────
from src.graph.context import extract_context_graph

# ── Queries: graph traversal and analytics (FalkorDB Cypher) ─────────
from src.graph.falkor_queries import (
    compute_goal_progress,
    find_connected_entities,
    get_blocking_chain,
    get_cross_team_blocking,
    get_entity_neighborhood,
    get_entity_timeline,
    get_goal_coverage,
    get_goal_tree,
    get_org_graph,
    get_org_workloads,
    get_person_prs,
    get_person_tasks,
    get_person_workload,
    get_person_workload_hybrid,
    get_prd_coverage,
    get_prd_stakeholders,
    get_prds_for_goal,
    get_project_stats,
    get_project_tasks,
    get_stalled_prs,
    get_team_members,
    get_team_workload_summary,
    get_unowned_goals,
)
from src.graph.falkor_repository import (
    # Edge writes
    bulk_upsert_edges,
    # Entity reads
    bulk_upsert_entities,
    # Edge reads
    count_edges,
    count_entities,
    delete_edge_by_id,
    delete_edges,
    # Entity writes
    delete_entity,
    delete_org_edges,
    delete_org_entities,
    find_person_by_email,
    get_connected_entity_ids,
    get_edge_by_id,
    get_edge_by_triple,
    get_edges,
    get_entities_by_ids,
    get_entities_via_edge,
    get_entity,
    get_entity_by_source,
    get_entity_or_404,
    list_edges,
    list_entities,
    replace_edges,
    track_edge_result,
    update_entity,
    upsert_edge,
    upsert_entity,
)

# ── Resolution: post-sync duplicate detection ────────────────────────
from src.graph.resolution import detect_person_duplicates

# ── Resolver: cross-source identity resolution ───────────────────────
from src.graph.resolver import (
    find_person,
    find_similar_persons,
    merge_entities,
    resolve_or_create_entity,
    resolve_or_create_person,
    resolve_person,
)

# ── Task transitions: workflow automation ─────────────────────────────
from src.graph.task_transitions import propagate_pr_state_to_tasks

__all__ = [
    # Repository - entity reads
    "get_entity",
    "get_entity_or_404",
    "get_entity_by_source",
    "list_entities",
    "count_entities",
    "get_entities_by_ids",
    "find_person_by_email",
    # Repository - entity writes
    "upsert_entity",
    "bulk_upsert_entities",
    "update_entity",
    "delete_entity",
    "delete_org_entities",
    # Repository - edge reads
    "get_edges",
    "get_edge_by_id",
    "get_edge_by_triple",
    "list_edges",
    "get_connected_entity_ids",
    "get_entities_via_edge",
    "count_edges",
    # Repository - edge writes
    "upsert_edge",
    "bulk_upsert_edges",
    "delete_edge_by_id",
    "delete_edges",
    "replace_edges",
    "delete_org_edges",
    "track_edge_result",
    # Resolver
    "find_person",
    "resolve_person",
    "resolve_or_create_person",
    "resolve_or_create_entity",
    "merge_entities",
    "find_similar_persons",
    # Resolution
    "detect_person_duplicates",
    # Queries
    "get_entity_neighborhood",
    "get_blocking_chain",
    "get_person_prs",
    "get_person_tasks",
    "get_person_workload",
    "get_person_workload_hybrid",
    "get_org_workloads",
    "get_entity_timeline",
    "find_connected_entities",
    "get_project_tasks",
    "get_project_stats",
    "get_goal_coverage",
    "get_goal_tree",
    "compute_goal_progress",
    "get_team_members",
    "get_team_workload_summary",
    "get_stalled_prs",
    "get_cross_team_blocking",
    "get_unowned_goals",
    "get_org_graph",
    # PRD queries
    "get_prd_coverage",
    "get_prd_stakeholders",
    "get_prds_for_goal",
    # Task transitions
    "propagate_pr_state_to_tasks",
    # Context graph
    "extract_context_graph",
]
