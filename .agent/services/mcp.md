# MCP Server (L6)

Exposes Numen's work intelligence to external AI agents (Claude Code, Claude Desktop, Cursor, Windsurf, ...) via the Model Context Protocol. Supports both read tools (org-scoped, no actor required) and write tools (require an API key bound to a user).

## Module: `src/mcp/`

| File | Purpose |
|------|---------|
| `server.py` | FastMCP instance, lifespan, tool/resource registration, actor + write-auth helpers |
| `tools.py` | Tool implementations (read + write) |
| `resources.py` | Resource implementations (org overview, goals, urgent) |
| `auth.py` | API key creation, validation, revocation - keys may be user-bound |
| `token_verifier.py` | Bearer-token verifier; encodes (org_id, user_id) into AccessToken.client_id |
| `serializers.py` | Entity/Edge/Score to dict helpers |
| `cli.py` | stdio entry point for `numen-mcp` CLI |

## Transport

- **SSE / Streamable HTTP**: Mounted on FastAPI at `/mcp` (controlled by `MCP_ENABLED` env var)
- **stdio**: `numen-mcp` CLI command registered in `pyproject.toml`

## Authentication and the actor model

API keys are SHA-256 hashed in the `api_keys` table. Each key now optionally binds to a `user_id` (added in migration `v1l2m3n4o5p6_add_user_id_to_api_keys`):

- Keys created via `POST /api/orgs/{org_id}/api-keys` automatically inherit the calling member's `user_id`.
- Legacy keys (created before the migration) have `user_id = NULL`. They keep working for **read tools** but are refused by write tools with a clear error message ("This API key is not bound to a user. Generate a new key from the Numen MCP Setup page...").
- `NumenTokenVerifier` packs `(org_id, user_id)` into `AccessToken.client_id` as `"<org>:<user>"` (legacy: just `"<org>"`). The MCP server unpacks via `_get_actor()` and gates writes via `_require_write()`.

### Management endpoints

- `POST /api/orgs/{org_id}/api-keys` - Create key (returns plaintext once, bound to caller)
- `GET /api/orgs/{org_id}/api-keys` - List keys (metadata only)
- `DELETE /api/orgs/{org_id}/api-keys/{key_id}` - Revoke key

## Read tools

| Tool | Description |
|------|-------------|
| `search_entities` | Search by type + keyword |
| `get_entity` | Get entity by ID with edges |
| `get_entity_graph` | 2-hop neighborhood traversal |
| `list_tasks` | Filter by status/priority/assignee/project |
| `get_task_context` | Rich task context (goals + blocking + urgency + PRs) |
| `list_goals` | Goals with optional tree view |
| `get_goal_progress` | Progress with linked task stats |
| `get_urgency_scores` | Top urgent items for a person |
| `get_briefing` | Latest briefing for a member |
| `get_person_workload` | Task distribution by status |
| `search_by_source` | Look up by Linear/GitHub/Slack/Jira ID |
| `find_matching_task` | Substring shortlist + LLM re-rank to find existing tasks matching a free-text description; falls back to substring on LLM failure |
| `list_wiki_features` | List wiki features (slug, title, status) |
| `get_wiki_feature` | Fetch a wiki feature by slug, with Markdown content |

## Write tools (require user-bound key)

| Tool | Description |
|------|-------------|
| `create_task` | Create a task in `todo` with optional CONTAINS / TAGGED_TO / ASSIGNED_TO edges |
| `update_task_status` | Move forward in the lifecycle; backward transitions are rejected |
| `update_task` | Patch title / description / priority / assignee |
| `link_task` | Add CONTAINS / TAGGED_TO / BLOCKS edges (idempotent) |
| `create_project` | Create a project + OWNS / TAGGED_TO edges |
| `create_goal` | Create a goal entity, optionally as a child of an existing goal |
| `append_wiki_note` | Append a dated, attributed bullet to a wiki feature's "## Notes from Numen MCP" trailing section |

### Intended flow (from server `instructions=`)

1. `find_matching_task(description)` - surface candidates for the user to confirm.
2. If no match: `create_task(...)`.
3. Drive forward: `update_task_status(task_id, "in_progress")`, etc.
4. `link_task` to attach to project / goals / blockers.
5. `append_wiki_note` for durable learnings against existing wiki features.

### Forward-only task pipeline

`todo -> in_progress -> in_review -> merged -> done`. `update_task_status` checks `_status_rank()` against `TASK_STATUS_PIPELINE` and returns an error JSON on backward transitions. Statuses outside the pipeline (`backlog`, `archived`) are rejected by the same guard.

### Wiki note convention

Notes append under a stable Markdown header `## Notes from Numen MCP` as bullets `- <YYYY-MM-DD HH:MM UTC> by <user.email>: <text>`. Idempotent on duplicate consecutive bullets. The append flips `WikiFeature.is_manual = True`, which the existing wiki regenerator (`src/prd/wiki_generator.py`) already preserves across PRD-driven regenerations - no generator changes were needed.

### Audit trail

Every write tool emits `mcp.<resource>.<action>` (e.g. `mcp.task.created`, `mcp.task.status`, `mcp.wiki.note_appended`) into `audit_logs` with the actor `user_id`.

## Resources

| URI | Description |
|-----|-------------|
| `numen://org/{org_id}/overview` | Org summary |
| `numen://org/{org_id}/goals` | Goal tree + coverage |
| `numen://org/{org_id}/urgent` | Top 20 urgent tasks |

## Client setup

The setup page at `/mcp-setup` (frontend `src/pages/McpSetup.tsx`) renders one of these for whichever client the user picks:

- **Claude Code (default)** - one shell command:
  ```
  claude mcp add --transport http numen https://<host>/mcp --header "Authorization: Bearer <key>"
  ```
- **Claude Desktop / Cursor / Windsurf** - JSON config with `url` + `Authorization: Bearer` header.
- **CLI (stdio)** - JSON config with `command: numen-mcp` and `NUMEN_API_KEY` env var.

## Dependencies

- `mcp[cli]>=1.9.0` (Python MCP SDK)
- Reuses `src/graph/`, `src/inference/`, `src/llm/` (find_matching_task re-rank), `src/shared/`

## Testing

```bash
make verify-mcp
```
