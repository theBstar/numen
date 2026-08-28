# L3: Inference (Urgency Scoring)

> `src/inference/`

## Scoring Formula

Six weighted factors, scores normalized to 0-100:

| Factor | Weight | Normalization | Cap | What it measures |
|--------|--------|---------------|-----|-----------------|
| `staleness_days` | 0.25 | days_since_update / cap | 14 days | How stale the item is |
| `is_blocking_others` | 0.35 | binary 1.0 or 0.0 | - | Has outgoing BLOCKS edges |
| `downstream_blocked_count` | 0.15 | chain_length / cap | 10 entities | Transitive BLOCKS chain depth |
| `mention_count_24h` | 0.10 | count / cap | 10 mentions | MENTIONED_IN edges in last 24h |
| `goal_criticality` | 0.10 | max goal gap ratio | 1.0 | (target - current) / target across linked goals |
| `is_in_current_sprint` | 0.05 | binary 1.0 or 0.0 | - | `properties.is_in_current_sprint` |

```
raw_score = sum(factor_value * weight)   // range 0.0 - 1.0
score = raw_score * 100                  // range 0 - 100
```

Scores are personalized - the same PR has different scores for its author, reviewer, and PM.

## Provenance

Every score includes full provenance - a list of dicts, one per factor:

```json
{
  "factor_name": "is_blocking_others",
  "weight": 0.35,
  "raw_value": 1.0,
  "weighted_value": 35.0,
  "explanation": "This item is blocking 3 other item(s)",
  "evidence": [{"blocked_entity_id": "..."}]
}
```

This powers the "Why Numen surfaced this" UI and the urgency trace endpoint.

## Scoring Orchestration (`scorer.py`)

### Scorable Entity Types

Only `TASK`, `COMMIT_PR`, and `INCIDENT` entities are scored.

### Batch Scoring (`compute_batch`)

For each entity in the list, calls `compute_urgency()` sequentially. Used during full org scoring.

### Org-Wide Scoring (`score_org`)

1. For each `OrgMember` with a `person_entity_id`
2. Find all owned entities (TASK/COMMIT_PR/INCIDENT) via OWNS edges
3. Call `compute_batch()` for that person's entities
4. Persist scores to DB + Redis

### Top-N Retrieval (`get_top_urgent`)

1. Check Redis sorted set first (fast: O(log N) + O(K))
2. Fall back to DB `ORDER BY score DESC` if cache empty
3. Return top N items with full provenance

## Redis Cache (`cache.py`)

| Operation | Key Pattern | Description |
|-----------|------------|-------------|
| `cache_scores()` | `urgency:{org_id}:{person_id}` | Pipeline ZADD to sorted set |
| `get_cached_scores()` | `urgency:{org_id}:{person_id}` | ZREVRANGE with WITHSCORES |
| `invalidate_person()` | `urgency:{org_id}:{person_id}` | DELETE key |
| `invalidate_entity()` | `urgency:{org_id}:*` | SCAN + ZREM across all person keys |

## How to Add a New Factor

1. Create an async helper in `src/inference/urgency.py` returning `tuple[float, dict]` (normalized value + provenance)
2. Add the weight to the `WEIGHTS` dict
3. Call it in `compute_urgency()` alongside existing factors
4. Add to `raw_score` sum and `components`/`provenance` dicts
5. Update this doc with the new factor details
