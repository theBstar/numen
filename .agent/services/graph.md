# L2: Context Graph

> `src/graph/`

## Entity Lifecycle

### Creation / Upsert (`repository.py:upsert_entity`)

1. **Match** - finds existing entity by `(org_id, source, source_ids overlap)` using GIN index on JSONB
2. **Merge chain** - if found entity has `merged_into` set, follows the chain (max 5 hops via `_resolve_merged_chain`) to the canonical entity
3. **Update rules**:
   - **Normal upsert** (no merge): full property update, name update, additive `source_ids` merge
   - **Merged entity**: connector data stored under `_connector_data[source]` namespace to preserve user-set name on canonical entity
4. **Create** - if no match, creates new Entity with provided fields

Key invariants:
- `source_ids` are **additive-only** - keys are never removed during upsert
- `_find_matching_entity` searches including merged stubs so connectors don't re-create duplicates
- Prefers non-merged entities over merged stubs when multiple candidates match

### Entity Merge (`resolver.py:merge_entities`)

Merges a duplicate into a primary entity:

1. Combine `source_ids` (additive)
2. Store duplicate's properties under `_connector_data[source]`
3. Re-point all edges from duplicate to primary (handle unique constraint conflicts by deleting duplicate edges)
4. Skip self-loops (both ends point to primary after merge)
5. Re-point `OrgMember.person_entity_id` references
6. Mark pending `PersonResolution` records as "merged"
7. Delete `LinkSuggestion` records referencing the duplicate
8. Set `duplicate.merged_into = primary_id` (soft-delete, not hard delete)

### Entity Query

- Always filter `merged_into IS NULL` for canonical entities
- Use `get_entity_by_source()` for source-specific lookups (scans source_ids values)

## Edge Semantics

Direction matters. The convention is `from -> to`:

| Edge Type | From | To | Meaning |
|-----------|------|-----|---------|
| OWNS | person | task/feature | Person owns the work item |
| BLOCKS | taskA | taskB | A blocks B |
| DEPENDS_ON | taskA | taskB | A depends on B |
| AUTHORED | person | commit_pr | Person authored the PR |
| SHIPS_TO | commit_pr | task | PR ships to (delivers) a task |
| REVIEWS | person | commit_pr | Person reviews the PR |
| MENTIONED_IN | entity | entity | Entity mentioned in another |
| MEASURES | metric | goal | Metric measures a goal |
| TAGGED_TO | task/feature | goal | Work item tagged to a goal |
| CONTAINS | project | task | Project contains a task |
| PARENT_OF | parent_goal | child_goal | Goal hierarchy |
| ASSIGNED_TO | task | person | Task assigned to person |
| REPORTS_TO | person | person | Reporting chain |

### Edge Upsert (`repository.py:upsert_edge`)

Matches on unique constraint `(from_entity_id, to_entity_id, type)`. On conflict: updates weight, confidence, refreshes `last_active_at`, merges evidence (append new items, avoid exact duplicates).

## Recursive CTE Queries (`queries.py`)

Raw SQL queries must use parameterized enum values via `.name` (e.g., `EdgeType.BLOCKS.name` yields `"BLOCKS"`) instead of hardcoded strings. The DB stores uppercase enum member names, not the lowercase `.value`.

| Function | What it does | When to use |
|----------|-------------|-------------|
| `get_entity_neighborhood(entity_id, max_hops)` | BFS traversal, returns entities + edges within N hops | Graph visualization, context loading |
| `get_blocking_chain(entity_id)` | Follows BLOCKS edges upstream | Urgency scoring, briefing items |
| `get_person_workload(person_id)` | Counts OWNS + ASSIGNED_TO edges grouped by all task statuses | Dashboard stats, workload view |
| `get_person_tasks(person_id, since?, statuses?, include_authored?)` | Tasks via OWNS/ASSIGNED_TO + AUTHORED->PR->SHIPS_TO path | Chat "what did X do", person detail |
| `get_person_prs(person_id, status?, role?)` | PRs via AUTHORED/REVIEWS edges, optional status + role filter | Chat "show X's PRs", PR queries |
| `find_connected_entities(entity_id, target_type, max_hops)` | Finds entities of a specific type within N hops | Cross-reference lookups |
| `get_project_tasks(project_id)` | CONTAINS edges from project to tasks | Project detail page |
| `get_goal_coverage(goal_id)` | Counts tasks/features TAGGED_TO a goal | Goal progress tracking |
| `get_goal_tree(org_id)` | Builds nested tree from PARENT_OF edges | Goal hierarchy view |
| `compute_goal_progress(goal_id)` | Task completion % + key results progress | Goal detail page |

## Person Resolution

### Resolver (`resolver.py:resolve_person`)

Priority cascade when matching identifiers to an existing Person entity:

1. **Email** - exact match in `source_ids` JSONB
2. **GitHub username** - match in `source_ids`
3. **Slack ID** - match in `source_ids`
4. **Name** - case-insensitive exact match on `canonical_name`
5. **Create new** - if no match, creates Person with source=MANUAL

On match, enriches the entity with any new identifiers (`_enrich_entity`).

### Duplicate Detection (`resolution.py:detect_person_duplicates`)

Post-sync scan comparing Person entities cross-source:

**Confidence tiers:**
| Signal | Confidence |
|--------|-----------|
| Shared email | 0.95 |
| GitHub username match | 0.85 |
| Slack ID match | 0.80 |
| Exact name (case-insensitive) | 0.60 |
| Fuzzy name (one contains the other, min 3 chars) | 0.40 |
| Minimum threshold | 0.35 |

- Skips same-source entities (already deduplicated by upsert_entity)
- Skips already-resolved pairs (any status: pending/merged/distinct)
- Normalizes pairs `(min(a,b), max(a,b))` to avoid directional duplicates
- Handles concurrent detection via IntegrityError catch on unique constraint

Results stored in `person_resolutions` table for human review in the UI.

## Task Status Transitions (`task_transitions.py`)

Forward-only status pipeline:

```
todo -> in_progress -> in_review -> merged -> done
```

**Never moves backward.** Rank comparison via `_STATUS_ORDER` index.

### PR State -> Task Status Rules

| PR State | Target Task Status |
|----------|-------------------|
| Opened (not draft) | at least `in_progress` |
| Has review activity or requested reviewers | at least `in_review` |
| Merged | `merged` |
| Closed without merge | no change |

Transitions are logged in `audit_logs` with full details (old/new status, trigger, PR info).

Linked tasks found via SHIPS_TO edges (either direction).
