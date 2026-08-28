# Context Graph - Developer Guide

The context graph is Numen's core data structure. Every connector, scorer, briefing, and UI feature reads from it. **All entity and edge operations MUST go through `src/graph/`** - no direct SQL queries against Entity or Edge models outside this package.

## Data Model

### Entities (nodes)

Each entity represents a work artifact, person, or concept ingested from an external tool or created manually.

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `org_id` | UUID | Tenant isolation (every query must scope to org) |
| `type` | EntityType | Discriminator (PERSON, TASK, COMMIT_PR, etc.) |
| `source` | SourceType | Which connector created it (LINEAR, GITHUB, SLACK, MANUAL) |
| `source_ids` | JSONB | Cross-source identifiers (see "source_ids conventions" below) |
| `canonical_name` | text | Display name (connector-set or user-overridden) |
| `properties` | JSONB | Source-specific data (status, labels, description, etc.) |
| `embedding` | vector(1536) | Optional semantic embedding for future search |
| `merged_into` | UUID or null | Points to canonical entity if this is a merged duplicate |
| `created_at` | datetime | Immutable creation timestamp |
| `updated_at` | datetime | Last modification timestamp |

### Entity Types

| Type | Source(s) | Description |
|------|-----------|-------------|
| PERSON | All | A human. Cross-source resolved via email/username. |
| TASK | Linear, Manual | An issue or work item (Linear issue, manual task). |
| COMMIT_PR | GitHub | A pull request with diff, description, reviewers. |
| DEPLOY | GitHub | A deployment event with status and environment. |
| PROJECT | Linear, Manual | A grouping of tasks. |
| GOAL | Manual | An OKR or objective with key results. |
| FEATURE | Manual | A product feature. |
| DECISION | Slack | A decision extracted from Slack messages. |
| DOCUMENT | Slack | A document mention extracted from Slack. |
| INCIDENT | Future | A production incident (Datadog, PagerDuty). |
| ERROR_EVENT | Future | An error event (Sentry). |
| METRIC_SNAPSHOT | Future | A point-in-time metric reading. |

### Edges (relationships)

Each edge is a typed, directed relationship between two entities.

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Primary key |
| `org_id` | UUID | Tenant isolation |
| `from_entity_id` | UUID | Source entity |
| `to_entity_id` | UUID | Target entity |
| `type` | EdgeType | Relationship type |
| `weight` | float | Strength/relevance (default 1.0) |
| `confidence` | float | 0-1, where 1 = confirmed, <1 = inferred |
| `evidence` | JSONB[] | Provenance - why this edge exists |
| `first_seen_at` | datetime | When the edge was first created |
| `last_active_at` | datetime | When the edge was last refreshed |

**Unique constraint**: `(from_entity_id, to_entity_id, type)` - only one edge of each type between a pair.

### Edge Types

| Type | From -> To | Description |
|------|-----------|-------------|
| ASSIGNED_TO | Task -> Person | Person is assigned to task |
| AUTHORED | Person -> PR/Decision | Person created the artifact |
| BLOCKS | Task -> Task | First task blocks second |
| CONTAINS | Project -> Task | Project contains task |
| PARENT_OF | Goal -> Goal | Goal hierarchy |
| TAGGED_TO | Entity -> Goal | Entity linked to a goal |
| OWNS | Person -> Entity | Person owns/is responsible for entity |
| REPORTS_TO | Person -> Person | Org hierarchy |
| REVIEWS | Person -> PR | Person reviews PR |
| SHIPS_TO | PR -> Task | PR delivers this task |
| DEPLOYED_BY | Deploy -> Person | Person triggered deploy |
| DEPENDS_ON | Task -> Task | Dependency (not blocking) |
| MENTIONED_IN | Entity -> Entity | Cross-reference in text |
| MEASURES | Metric -> Goal | Metric tracks goal progress |
| CAUSED_BY | Incident -> Entity | Root cause link |

## source_ids Conventions

`source_ids` is the JSONB field that stores cross-source identifiers. Standardized keys:

| Key | Source | Stability | Example |
|-----|--------|-----------|---------|
| `email` | Any | Stable | `"alice@company.com"` (always lowercase) |
| `github` | GitHub | Mutable | `"alice-chen"` (login, user can rename) |
| `github_id` | GitHub | Immutable | `"12345678"` (numeric user ID) |
| `linear` | Linear | Immutable | `"d2592a97-..."` (UUID) |
| `slack_id` | Slack | Immutable | `"U03ALICE01"` (member ID) |

**Rules:**
- Email is always lowercase
- Use `slack_id` (not `slack`) for person entities
- Store `github_id` alongside `github` for stability
- After merge, all identifiers from both entities are combined

## Graph API Reference

All functions are async and take `AsyncSession` as first parameter. Import from `src.graph`:

```python
from src.graph import list_entities, upsert_edge, get_entity_or_404
```

### Entity Reads

| Function | Returns | Description |
|----------|---------|-------------|
| `get_entity(db, entity_id)` | `Entity or None` | Fetch by ID |
| `get_entity_or_404(db, entity_id, org_id?, expected_type?)` | `Entity` | Fetch by ID; raises 404 |
| `get_entity_by_source(db, org_id, source, source_id)` | `Entity or None` | Find by source + source_id value |
| `list_entities(db, org_id, entity_type?, search?, status?, limit?, offset?)` | `list[Entity]` | Filtered list with pagination |
| `count_entities(db, org_id, entity_type?, search?, status?)` | `int` | Count matching entities |
| `get_entities_by_ids(db, entity_ids)` | `list[Entity]` | Multi-ID lookup |
| `find_person_by_email(db, org_id, email)` | `Entity or None` | Find person by email in source_ids or properties |

### Entity Writes

| Function | Returns | Description |
|----------|---------|-------------|
| `upsert_entity(db, EntityCreate)` | `Entity` | Insert or update, merge source_ids, follow merged_into chain |
| `bulk_upsert_entities(db, list[EntityCreate])` | `list[Entity]` | Batch upsert |
| `update_entity(db, entity_id, canonical_name?, properties?, merge_properties?)` | `Entity` | Update mutable fields |
| `delete_entity(db, entity_id)` | `None` | Hard delete entity + all edges |
| `delete_org_entities(db, org_id)` | `int` | Bulk delete for org |

### Edge Reads

| Function | Returns | Description |
|----------|---------|-------------|
| `get_edges(db, entity_id, edge_types?, direction?)` | `list[Edge]` | Edges for entity (legacy, use `list_edges` for new code) |
| `get_edge_by_id(db, edge_id)` | `Edge or None` | Single edge by ID |
| `get_edge_by_triple(db, from_id, to_id, type)` | `Edge or None` | Find by unique triple |
| `list_edges(db, org_id?, entity_id?, edge_type?, direction?, from_id?, to_id?)` | `list[Edge]` | Flexible filtered list |
| `get_connected_entity_ids(db, entity_id, edge_type, direction)` | `list[UUID]` | Just IDs via edge |
| `get_entities_via_edge(db, entity_id, edge_type, direction, target_type?)` | `list[Entity]` | Full entities via edge |
| `count_edges(db, entity_id, edge_type, direction)` | `int` | Count edges of type |

### Edge Writes

| Function | Returns | Description |
|----------|---------|-------------|
| `upsert_edge(db, EdgeCreate)` | `Edge` | Insert or update, merge evidence |
| `bulk_upsert_edges(db, list[EdgeCreate])` | `list[Edge]` | Batch upsert |
| `delete_edge_by_id(db, edge_id)` | `bool` | Delete single edge |
| `delete_edges(db, entity_id, edge_type?, direction?)` | `int` | Delete edges by filter |
| `replace_edges(db, entity_id, edge_type, direction, new_target_ids, org_id)` | `list[Edge]` | Atomic delete-and-recreate |
| `delete_org_edges(db, org_id)` | `int` | Bulk delete for org |

### Cross-Source Resolution

| Function | Returns | Description |
|----------|---------|-------------|
| `resolve_person(db, org_id, identifiers)` | `Entity` | Find or create person by email/github/slack/name |
| `resolve_or_create_person(db, org_id, source, source_ids, name, properties)` | `Entity` | Connector-facing wrapper for person resolution |
| `merge_entities(db, primary_id, duplicate_id)` | `Entity` | Merge duplicate into primary |
| `find_similar_persons(db, org_id, name, email?)` | `list[Entity]` | Find potential duplicates for UI |
| `detect_person_duplicates(db, org_id, candidate_ids?)` | `list[PersonResolution]` | Post-sync duplicate scanner |

### Graph Traversal & Analytics

| Function | Returns | Description |
|----------|---------|-------------|
| `get_entity_neighborhood(db, entity_id, depth?)` | `dict` | BFS traversal within N hops |
| `get_blocking_chain(db, task_id)` | `list[Entity]` | Follow BLOCKS edges recursively |
| `get_person_workload(db, person_id)` | `dict` | OWNS edge counts by task status |
| `get_entity_timeline(db, entity_id, since?)` | `list[Edge]` | Edge activity timeline |
| `find_connected_entities(db, entity_id, target_type, max_hops?)` | `list[Entity]` | Find typed entities within hops |
| `get_project_tasks(db, project_id)` | `list[Entity]` | Tasks in project via CONTAINS |
| `get_project_stats(db, project_id)` | `dict` | Task counts by status |
| `get_goal_coverage(db, org_id)` | `list[dict]` | Task/feature counts per goal |
| `get_goal_tree(db, org_id)` | `list[dict]` | Nested goal hierarchy |
| `compute_goal_progress(db, goal_id)` | `dict` | Progress from linked tasks |
| `propagate_pr_state_to_tasks(db, pr_entity_id)` | `list[UUID]` | Advance tasks when PR state changes |

## Person Resolution Flow

### At ingestion time (proactive)

Connectors call `resolve_or_create_person()` instead of `upsert_entity()` for Person entities:

1. Extract identifiers (email, github, slack_id) from source_ids + properties
2. Search existing persons: email (0.95) -> github_id (0.85) -> github (0.85) -> slack_id (0.80) -> name (0.60)
3. If match found: enrich existing entity with new source_ids
4. If no match: create new entity via `upsert_entity()`

### Post-sync (safety net)

`detect_person_duplicates()` runs after each sync cycle:

1. Loads all Person entities for the org
2. Compares cross-source pairs (different sources only)
3. Creates `PersonResolution` records for matches above 0.35 confidence
4. User reviews and merges via the UI

### Merge

`merge_entities()` combines two entities:

1. Combines source_ids (additive)
2. Stores duplicate's properties under `_connector_data[source]`
3. Re-points all edges from duplicate to primary (handles unique constraint conflicts)
4. Sets `merged_into` pointer on duplicate (soft delete)
5. Updates OrgMember references

## Invariants

1. **Org isolation** - Every list/query function filters by `org_id`. Never expose data across orgs.
2. **merged_into filtering** - `list_entities()` and `get_entities_via_edge()` exclude merged entities by default.
3. **Edge uniqueness** - `(from_entity_id, to_entity_id, type)` is unique. `upsert_edge()` handles conflicts.
4. **No direct queries** - Code outside `src/graph/` must not import Entity/Edge from `src.shared.models` or build SQLAlchemy queries against them.
5. **Flush, not commit** - Graph functions call `db.flush()`, not `db.commit()`. The caller (API route) owns the transaction.

## Adding New Entity Types

1. Add to `EntityType` enum in `src/shared/types.py`
2. Add connector logic to emit entities of this type
3. If scorable: add to `_SCORABLE_TYPES` in `src/inference/urgency.py`
4. Add frontend route in `frontend/src/App.tsx`
5. Update this document

## Adding New Edge Types

1. Add to `EdgeType` enum in `src/shared/types.py`
2. Add connector logic to emit edges of this type
3. If used in traversal: update relevant functions in `src/graph/queries.py`
4. Update this document
