# L1: Connectors (Ingestion Layer)

> `src/connectors/`

## BaseConnector ABC

All connectors extend `BaseConnector` (`src/connectors/base.py`):

```
class BaseConnector(ABC):
    source: SourceType

    async def sync_full(db, org_id, token) -> ConnectorSyncResult
    async def sync_delta(db, org_id, token, since) -> ConnectorSyncResult
    async def handle_webhook(db, org_id, payload) -> ConnectorSyncResult
```

- **Stateless** - connectors are singleton instances, no per-org state
- **Lazy loaded** - instantiated on first use by `src/connectors/registry.py` to avoid circular imports
- **HTTP client** - `_make_http_client(token)` returns `httpx.AsyncClient` with Bearer auth and 30s timeout
- **Return value** - `ConnectorSyncResult` with counts: `entities_created`, `entities_updated`, `edges_created`, `edges_updated`, `errors`

## The registry

`src/connectors/registry.py` is the single source of truth for which sources can
be ingested. Every caller - the sync scheduler, the manual-sync route, the
webhook route, the connector status list - resolves through it:

```
get_connector(source)      # SourceType  -> BaseConnector (cached singleton)
source_for_slug("github")  # URL segment -> SourceType
spec_for_slug("github")    # URL segment -> ConnectorSpec (slug, label, webhooks)
CONNECTORS                 # the ordered tuple of every registered spec
SUPPORTED_SOURCES          # frozenset of registered SourceTypes
```

There used to be seven hand-maintained copies of this mapping and they drifted:
Jira was missing from the scheduler, so it never delta-synced after the initial
backfill, and Notion and Google Docs were missing from the route maps, so manual
sync returned 400 and their webhooks were dropped. `tests/test_connectors/
test_registry.py` walks `src/connectors/` and fails if a connector exists but is
not registered.

A `SourceType` with no registered connector is not silently skipped: the
scheduler marks that org's `SyncState` as `ERROR` so the connector does not sit
in the UI looking connected while nothing syncs.

## Existing Connectors

### Linear (`src/connectors/linear.py`)
- **API**: GraphQL with cursor-based pagination
- **Entities**: Issues -> TASK, Projects -> PROJECT, Team members -> PERSON
- **Edges**: OWNS, BLOCKS, CONTAINS, ASSIGNED_TO
- **Schemas**: `src/connectors/schemas/linear.py` (Pydantic validation)

### GitHub (`src/connectors/github.py`)
- **API**: REST API with pagination
- **Entities**: PRs -> COMMIT_PR, Contributors -> PERSON
- **Edges**: AUTHORED, SHIPS_TO, REVIEWS
- **Post-sync**: Triggers `propagate_pr_state_to_tasks()` for PR state changes
- **Post-sync**: Triggers `suggest_pr_task_links()` via Claude for AI link suggestions
- **Schemas**: `src/connectors/schemas/github.py`

### Slack (`src/connectors/slack.py`)
- **API**: Slack Web API
- **Entities**: Users -> PERSON, Messages -> (MENTIONED_IN edges)
- **Edges**: MENTIONED_IN

### Jira (`src/connectors/jira.py`)
- **API**: Atlassian REST v3, OAuth 2.0 3LO with `offline_access` refresh
- **Entities**: Issues -> TASK, Epics -> FEATURE
- **Edges**: OWNS, CONTAINS, BLOCKS, TAGGED_TO

### Notion (`src/connectors/notion.py`)
- **API**: Notion REST API
- **Entities**: Pages -> DOCUMENT
- **Webhooks**: none - kept current by the delta sync only

### Google Docs (`src/connectors/gdocs.py`)
- **API**: Drive + Docs REST APIs
- **Entities**: Documents -> DOCUMENT
- **Webhooks**: none - kept current by the delta sync only

## Entity-to-Source Mapping

| Source | Entity Types | Edge Types |
|--------|-------------|-----------|
| Linear | TASK, PROJECT, PERSON | OWNS, BLOCKS, CONTAINS, ASSIGNED_TO |
| GitHub | COMMIT_PR, DEPLOY, PERSON | AUTHORED, SHIPS_TO, REVIEWS |
| Slack | PERSON | MENTIONED_IN |
| Jira | TASK, FEATURE | OWNS, CONTAINS, BLOCKS, TAGGED_TO |
| Notion | DOCUMENT | - |
| Google Docs | DOCUMENT | - |

Together these are the two halves of the org context: GitHub supplies the code
side (pull requests, reviews, deploys) and Linear, Jira, Notion, and Google Docs
supply the product side (tickets, epics, specs, decisions). The value is in the
joins between them, which is what `src/graph/` builds.

## Post-Sync Pipeline

After every `sync_delta` completes:

1. **Person duplicate detection** (`graph/resolution.detect_person_duplicates`) - compares all Person entities cross-source, creates `PersonResolution` records for human review
2. **AI link suggestions** (GitHub only, `claude/link_suggester.suggest_pr_task_links`) - uses Claude to suggest PR-to-task links, creates `LinkSuggestion` records

## Source attribution: MCP-created entities

Tasks, projects, and goals created through the MCP write tools (`src/mcp/tools.py`) use `source=SourceType.MANUAL` with a `source_id` of `mcp:<slug>`. This intentionally shares the `manual` source bucket with REST-created entities and won't collide with Linear (`linear:ABC-123`), GitHub (`github:org/repo#42`), Jira, or other connector-managed `source_ids`. If you ever want to filter "things made by the MCP", check the `source_ids["manual"]` value for the `mcp:` prefix.

## How to Add a New Connector

1. Add `SourceType.NEWSERVICE` to `src/shared/types.py`
2. Create `src/connectors/newservice.py` extending `BaseConnector`
3. Create `src/connectors/schemas/newservice.py` for property validation
4. Register in `src/connectors/registry.py` (one `ConnectorSpec` entry - this is the only place)
5. Add OAuth flow in `src/api/auth.py` (add to `OAUTH_CONFIG` dict)
6. Add webhook verification in `src/api/dependencies.py` `verify_webhook_signature()`
   - Resolve the HMAC key through a helper both registration and verification call,
     as `src/shared/webhook_secrets.py` does for GitHub. Deriving it in two places
     is how GitHub webhooks came to be signed with one key and checked against another.
7. Add webhook endpoint in routes
8. Create Alembic migration if new entity or edge types are needed
9. Update `.agent/services/connectors.md` with the new connector details
