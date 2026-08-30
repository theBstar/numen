# Numen MCP — Troubleshooting

Every MCP error returns the same envelope:

```json
{
  "error": {
    "code": "task_not_found",
    "message": "No task with id 1f3a... in this org.",
    "hint": "Use search_entities or find_matching_task to discover task IDs.",
    "retryable": false,
    "suggested_next_tool": "search_entities",
    "docs_url": "https://numen.team/docs/errors#task_not_found"
  }
}
```

Branch on `code` (stable across versions). The agent should generally
follow `suggested_next_tool` before bothering the user.

## Auth & access

### `auth_required`

Missing or malformed `Authorization` header.

**Fix:** Add `Authorization: Bearer numen_<key>` to the MCP transport
config. Mint at `/mcp-setup` if you don't have one.

### `org_mismatch`

You passed an `org_id` that doesn't match your API key's org.

**Fix:** Omit `org_id` from tool calls - the server resolves it from
your key. If you genuinely need to scope to a different org, mint a new
key for that org from `/account/keys`.

### `user_binding_required`

Legacy API key (created before user-bound keys existed) tried to call
a write tool. Read tools work fine.

**Fix:** Mint a fresh key from `/mcp-setup`. New keys auto-bind to the
calling user.

## Org scoping

### `org_id_required`

You're calling in stdio mode (no auth context) and didn't pass `org_id`.

**Fix:** Pass `org_id` explicitly, or switch to the SSE transport with
an API key.

## Input validation

### `invalid_uuid`

A field that should be a UUID isn't one.

**Fix:** Check the message - it includes the offending value. Common
sources: agent hallucinated an ID; ID came from a different system.

### `invalid_argument`

Generic shape error - usually missing required fields for an action
discriminator (e.g. `action="merge"` with no `merge_strategy`).

**Fix:** Read the message; it lists what's missing.

### `invalid_status`, `invalid_priority`, `invalid_level`,
### `invalid_entity_type`, `invalid_source`

Enum value doesn't match the allowed set.

**Fix:** Read the message - it lists valid values.

## Not found

### `task_not_found`

The task ID doesn't exist *in your org*. Cross-org leaks return this
same code (we never confirm which orgs hold which IDs).

**Fix:** Call `list_tasks` or `search_entities` to discover real IDs.

### `wiki_feature_not_found`

The slug doesn't exist in this org.

**Fix:** Call `list_wiki_features` to see valid slugs.

### `proposal_not_found`

The proposal ID doesn't exist (or is in another org / belongs to
another user the API doesn't surface).

**Fix:** Call `list_proposals(only_mine=true)` to find your active
proposals.

### `entity_not_found`, `goal_not_found`, `project_not_found`,
### `person_not_found`, `briefing_not_found`

Same shape as `task_not_found`. Use the corresponding `list_*` or
`search_*` tool to discover IDs.

## Domain rules

### `task_transition_rejected`

Task status changes are forward-only:
`todo -> in_progress -> in_review -> merged -> done`. You tried to
go backward.

**Fix:** Forward-only by design. If the work is genuinely backing up,
talk to the user about cancelling and creating a new task.

### `proposal_stale`

The wiki feature changed between propose and approve. Your diff would
apply against the wrong base.

**Fix:** Call `get_wiki_feature(slug=...)` to fetch current content,
regenerate the diff, then re-propose. The error envelope's `extra`
includes `current_base_hash` so you can verify drift detection.

### `proposal_duplicate_pending`

Another pending proposal already exists for the same `(feature_slug,
section_anchor)`.

**Fix:** Call `list_proposals(status="pending", feature_slug=...)` to
find the existing one. Wait for it to be decided or coordinate with
its proposer.

### `dedupe_blocked`

Reserved for the find_matching_task threshold blocker (post-calibration
eval). Currently advisory only.

## External / upstream

### `upstream_rate_limited`, `upstream_timeout`, `upstream_error`

Notion / GDocs / Linear / GitHub said no. The connector already retries
with exponential backoff + Retry-After honoring (see WS4); these errors
mean retries are exhausted.

**Fix:** `retryable: true` on these - the agent can wait and retry.
Persistent failures usually mean an OAuth token expired - reauthorize
the connector at `/connections`.

## Internal

### `internal_error`

Something on our side. The message has best-effort detail; check the
server logs for the full trace if you have access.

**Fix:** Retry once. If it persists, it's a bug - file at
https://github.com/theBstar/numen/issues with the request you
sent and the time it failed.
