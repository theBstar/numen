# Changelog

## [0.2.0] - 2026-05-04 - mvp-v0 (MCP-first release)

The Numen MCP becomes the product surface. Agents on Claude Code,
Conductor, Cursor, Claude Desktop, or Windsurf can now discover and
drive the full Numen task graph + PRD layer over a single MCP
connection. The Mac app stays alive but pauses; new agent surfaces
land via the MCP only.

This release closes the autoplan-reviewed scope C plan against the
~30-user PLG pipeline.

### Cross-cutting MCP DX foundation (WS0)

- **Server-injected `org_id` + `agent_id`.** Every tool wrapper now
  resolves these from the API key auth context. SSE callers omit them
  from the call; stdio mode keeps the explicit args.
- **Stable error envelope.** All MCP errors return
  `{error: {code, message, hint, retryable, suggested_next_tool, docs_url}}`
  via `src/mcp/errors.py`. 24 stable codes; agents branch on `code`.
- **`hello_numen` first-call tool.** Returns org info, available tool
  index grouped by intent, sample first call, briefing excerpt. The
  recommended start of every agent session.

### PRD-update confirmation (WS1)

- **3 new MCP tools:** `propose_prd_update`, `get_proposal_status`,
  `list_proposals`. Race-safe via SHA256 hash snapshot of WikiFeature
  content at propose time + partial unique index that blocks duplicate
  pending proposals on the same anchor.
- **Frontend page:** `/prd-proposals` (list) and `/prd-proposals/:id`
  (review with approve/reject + reason).
- **REST endpoints** for the frontend: `GET/POST /api/prd/proposals`.
- **Worker:** daily expiry sweep transitions stale `pending` rows.
- **Stale-on-approve** detection: if the wiki drifts between propose
  and approve, the proposal moves to `stale`; the agent must re-propose.

### PR-MCP wrappers + service extraction (WS2)

- **2 new MCP tools** (T2 collapse from 4 to 2):
  `update_pr_state(action="branch_pushed"|"link"|"patch"|"merge", ...)`
  and `get_pr_state(task_id)`.
- **`src/services/pr_lifecycle.py`** extracts the body of the existing
  `pull_requests.py` REST handlers. REST and MCP both call into the
  service - one source of truth for the state machine and event
  emission.

### Web SSO + key rotation (WS3)

- `POST /api/living/auth/web?client=claude_code|conductor|cursor|...`
  mints an MCP key for the calling user and returns per-client install
  instructions. Security headers force no-store, no-referrer,
  frame-ancestors none.
- **`/api/account/keys`** REST + frontend page: list, mint with custom
  expiry (1-365 days, default 90), revoke, atomic rotate.
- **`api_keys.expires_at`** column added; `validate_api_key` now treats
  expired keys as revoked. Legacy keys with NULL expires_at stay valid.

### Connector rate-limit util (WS4)

- New `src/connectors/_rate_limit.py`: token bucket + exp backoff +
  Retry-After + circuit breaker. Drop-in for any connector.
- Refactored `notion._request`, `gdocs._request` to delegate (same
  external behavior).
- **Linear** now has rate-limit protection (10 req/s, 4 retries) - it
  had none before.

### MCP observability (WS5)

- New `src/mcp/observability.py`: `track()` async context manager
  records latency, status, error_code, args_size to `mcp_call_log`.
  Per-tool redaction allowlist - sensitive fields (descriptions, diff_md,
  prompts) never persisted.
- Hourly aggregator (`src/workers/mcp_usage_aggregator.py`) rolls
  raw logs into `mcp_usage_daily` (call_count, error_count, p50, p99).
- New admin endpoint: `GET /api/admin/mcp/usage?days=N` for
  ADMIN_ROLES. Live aggregation fallback so dashboards work before the
  first roll-up.
- Currently wired on 5 high-value tools (`hello_numen`, `get_context`,
  `find_matching_task`, `update_pr_state`, `get_pr_state`); the
  pattern is 4 lines per wrapper for the remaining 18.

### Multi-tenant isolation hardening (WS6)

- Closed the `@mcp.resource()` auth gap: all 3 resource handlers
  (`numen://org/{org_id}/overview`, `/goals`, `/urgent`) now call
  `_resolve_org_uuid` before delegating. Cross-org URIs return the same
  `org_mismatch` envelope as cross-org tool calls.
- New `tests/test_mcp/test_isolation.py` includes static guards: any
  new tool or resource that doesn't go through `_resolve_org_uuid` /
  `_verify_org_access` fails the test.
- Reference-leak coverage: PR URL claim attack, slug collision lookup.

### `find_matching_task` recommendation threshold (WS7)

- New `recommend_threshold` parameter (default 0.85). When the top
  match's confidence exceeds the threshold, the response includes
  `recommended_action: "use_existing"` + `recommended_task_id` so the
  agent can surface the duplicate before creating.
- Per-call override and `null` to suppress. Stays advisory until a
  labeled precision eval calibrates it.

### `get_context` recall@10 eval suite (WS8)

- Expanded eval set to 30 queries across 4 categories (feature_lookup,
  task_lookup, cross_doc, negative). Per-category thresholds with
  aggregate floor 0.7. Negative category enforces NEAR-ZERO recall to
  catch retriever false positives.
- A hand-labeled corpus can replace the synthetic `expected_doc_ids`
  when available; harness assertions don't change.
  See `tests/test_evals/README.md`.

### Docs (WS9)

Four new docs in `docs/`:
- **agent-setup.md**: per-client install snippets (Claude Code,
  Conductor, Cursor, Claude Desktop, Windsurf, local stdio).
- **recipes.md**: 6 copy-paste workflows (dedup-before-create, link-PR,
  propose-PRD-edit with stale recovery, debug-task-context, first-call
  onboarding, forward-only status).
- **troubleshooting.md**: every ErrorCode -> cause + fix.
- **system-prompt-cookbook.md**: 7 paste-into-CLAUDE.md snippets.

### Test counts

- Backend (excl. evals): 723 passing (was 638 at start of mvp-v0)
- Eval harness: 4 passing (with 30 queries)
- Frontend: 54 passing (no regressions)

### Migrations included

```
z5q6r7s8t9u0_add_mcp_observability
a6r7s8t9u0v1_add_api_key_expiry
b7s8t9u0v1w2_add_prd_proposals
```

Apply with `alembic upgrade head` after pulling.

### Deferred

- Observability `track()` rollout to remaining 18 MCP tool wrappers
  (4-line pattern; see hello_numen for template).
- Markdown-aware diff renderer in PrdProposals detail view (currently
  shows proposed content as preformatted text).
- Real production exports for the recall eval set.
- `wiki_feature_revisions` table (T1 deferred per autoplan; in-place
  mutation + hash-stale rejection for v0).
