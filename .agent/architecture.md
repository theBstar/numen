# System Architecture

## Overview

Numen is a proactive work intelligence platform. It connects to engineering/product tools (Linear, GitHub, Slack), builds a context graph of entities and relationships, computes urgency scores, and delivers personalized daily briefings.

## 5-Layer Architecture

| Layer | Directory | What it does |
|-------|-----------|-------------|
| L1 Ingestion | `src/connectors/` | OAuth + API connectors for Linear, GitHub, Slack. Poll every 5 min + webhooks. Normalize into canonical entities. |
| L2 Context Graph | `src/graph/` | Entity/Edge CRUD, cross-source entity resolution, recursive CTE graph traversals. |
| L3 Inference | `src/inference/` | Urgency scoring (hardcoded weights v1), Redis cache, batch + delta scoring. |
| L4 Briefings | `src/briefing/` | Per-role briefing assembly, HTML email templates, delivery via Resend. |
| L5 LLM Dispatch | `src/llm/` | OpenAI SDK wrapper, grounded prompts, v1 action: summarize PR diff. |

Supporting modules:

- `src/api/` - REST API (FastAPI routes, OAuth callbacks, webhook receivers)
- `src/workers/` - Background tasks (5-min sync scheduler, daily briefing scheduler)
- `src/shared/` - Types, DB models, database engine
- `src/chat/` - LangGraph-based chat agent with SSE streaming
- `src/demo/` - Demo org data seeding
- `src/config.py` - Pydantic BaseSettings from .env
- `frontend/` - React 19 + Vite + TypeScript + Tailwind + Radix UI

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Backend | Python 3.12, FastAPI, uvicorn |
| ORM | SQLAlchemy 2.0 async + asyncpg |
| Database | PostgreSQL 16 + pgvector |
| Cache | Redis 7 |
| Migrations | Alembic (async) |
| LLM | Anthropic Claude API, OpenAI (chat agent) |
| Frontend | React 19, Vite 6, TypeScript (strict), Tailwind CSS, Radix UI |
| Email | Resend |
| Containers | Docker Compose |

## Project Structure

```
numen/
├── src/
│   ├── main.py
│   ├── config.py
│   ├── shared/
│   │   ├── types.py
│   │   ├── models.py
│   │   ├── database.py
│   │   └── audit.py
│   ├── connectors/
│   │   ├── base.py
│   │   ├── linear.py
│   │   ├── github.py
│   │   ├── slack.py
│   │   └── schemas/
│   ├── graph/
│   │   ├── repository.py
│   │   ├── resolver.py
│   │   ├── resolution.py
│   │   ├── queries.py
│   │   └── task_transitions.py
│   ├── inference/
│   │   ├── urgency.py
│   │   ├── scorer.py
│   │   └── cache.py
│   ├── briefing/
│   │   ├── assembler.py
│   │   ├── templates.py
│   │   └── delivery.py
│   ├── claude/
│   │   ├── client.py
│   │   ├── prompts.py
│   │   ├── actions.py
│   │   └── link_suggester.py
│   ├── chat/
│   │   ├── service.py
│   │   ├── tools.py
│   │   ├── agent.py
│   │   └── router.py
│   ├── api/
│   │   ├── auth.py
│   │   ├── user_auth.py
│   │   ├── routes.py
│   │   ├── routes_goals.py
│   │   ├── routes_projects.py
│   │   ├── routes_tasks.py
│   │   ├── routes_edges.py
│   │   ├── schemas.py
│   │   └── dependencies.py
│   ├── workers/
│   │   ├── sync_scheduler.py
│   │   └── briefing_scheduler.py
│   └── demo/
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   ├── pages/
│   │   ├── components/
│   │   ├── services/api.ts
│   │   ├── hooks/
│   │   ├── contexts/
│   │   └── types/
│   └── package.json
├── alembic/
├── tests/
├── .agent/
├── CLAUDE.md
├── AGENTS.md
└── VISION.md
```

## Data Flow

### Connector Sync Cycle (every 5 min)

```
SyncScheduler.run()
  -> for each OAuthToken (skip demo orgs)
    -> _get_connector(source)  [lazy singleton]
    -> check SyncState (skip if SYNCING)
    -> connector.sync_delta(db, org_id, token, since)
      -> upsert_entity() / upsert_edge()  [graph/repository.py]
    -> detect_person_duplicates()  [graph/resolution.py]
    -> suggest_pr_task_links()  [GitHub only, claude/link_suggester.py]
    -> update SyncState (IDLE, last_sync_at)
```

### Webhook Flow

```
POST /api/webhooks/{connector}
  -> verify_webhook_signature()
  -> connector.handle_webhook(db, org_id, payload)
    -> upsert_entity() / upsert_edge()
    -> propagate_pr_state_to_tasks()  [GitHub PRs]
```

### Briefing Pipeline (daily)

```
BriefingScheduler
  -> for each OrgMember
    -> assemble_briefing(db, member)  [briefing/assembler.py]
      -> get urgency scores (Redis -> DB fallback)
      -> gather role-specific signals
    -> generate_briefing_narrative(items, role)  [claude/actions.py]
    -> render_briefing_email(briefing)  [briefing/templates.py]
    -> send via Resend (3 retries, exponential backoff)
    -> record Briefing in DB
```

### Chat Flow

```
POST /api/orgs/{id}/chat/{conv_id}/message  (SSE stream)
  -> save user message to chat_messages
  -> rebuild conversation history from DB
  -> invoke LangGraph react agent (OpenAI)
    -> tool calls: list_entities, search_entities, get_blocking_chain, etc.
  -> stream events: token, tool_start, tool_end, done
  -> save assistant message to chat_messages
```

## Cross-Module Contracts

- All connectors produce `ConnectorSyncResult` and call `upsert_entity`/`upsert_edge` from `graph.repository`
- `upsert_entity` handles merge chain following - connectors never need to think about merged entities
- Urgency scoring reads from Entity + Edge tables, writes to `urgency_scores` table + Redis sorted sets
- Briefing assembler reads urgency scores via `get_top_urgent` (Redis first, DB fallback)
- Chat agent tools wrap `graph.queries` functions with org_id + db session binding

## Database Schema

### Core Tables

**Entity** (`entities`) - Nodes in the context graph
- UUID primary key, `org_id` (tenant boundary), `type` (EntityType enum), `source` (SourceType enum)
- `source_ids` (JSONB, GIN indexed) - cross-source ID mapping, e.g. `{"linear_id": "...", "email": "..."}`
- `canonical_name`, `properties` (JSONB - schemaless per entity type)
- `merged_into` (nullable FK to self) - soft-delete for entity deduplication
- `embedding` (pgvector 1536) - semantic search
- `core_type`, `domain`, `domain_type` - classification fields
- Indexes: `(org_id, type)`, GIN on `source_ids`, `(org_id, core_type, domain)`, partial on `merged_into`

**Edge** (`edges`) - Typed relationships
- `from_entity_id`, `to_entity_id`, `type` (EdgeType enum) - unique constraint `uq_edge_triple`
- `weight` (float, decays), `confidence` (inferred < 1, confirmed = 1)
- `evidence` (JSONB list), `first_seen_at`, `last_active_at`
- `valid_from`/`valid_until` - temporal validity windows
- `edge_metadata` (JSONB)
- Indexes: `(from_entity_id, type)`, `(to_entity_id, type)`, `valid_from`, `valid_until`

### Entity Types

`PERSON | TASK | COMMIT_PR | DEPLOY | INCIDENT | ERROR_EVENT | METRIC_SNAPSHOT | FEATURE | PROJECT | GOAL | DOCUMENT | DECISION`

### Edge Types

`OWNS | BLOCKS | DEPENDS_ON | AUTHORED | MENTIONED_IN | SHIPS_TO | MEASURES | CAUSED_BY | TAGGED_TO | CONFLICTS_WITH | CONTAINS | PARENT_OF | ASSIGNED_TO | REPORTS_TO | MEMBER_OF | SURFACED_TO | ACTED_ON | DISMISSED | APPROVED_BY | ESCALATED_TO | PRECEDED_BY | REVIEWS | DEPLOYED_BY`

### Supporting Tables

| Table | Purpose | Key Constraints |
|-------|---------|----------------|
| `urgency_scores` | Cached urgency scores per (person, entity) | `uq_score_person_entity` |
| `users` | Google OAuth users | unique `email`, unique `google_id` |
| `organizations` | Tenant orgs | unique `slug`, `is_demo` flag |
| `org_members` | User membership per org | `uq_member_org_email`, has `person_entity_id` FK |
| `briefings` | Generated briefings | indexed on `(org_member_id, generated_at)` |
| `oauth_tokens` | Connector credentials per org | `uq_token_org_connector` |
| `sync_states` | Sync cursor/status per org+connector | `uq_sync_org_connector` |
| `conversations` | Chat conversations | `(org_id, member_id)` |
| `chat_messages` | Chat messages | indexed on `(conversation_id, created_at)` |
| `person_resolutions` | Duplicate person candidates | `uq_resolution_pair`, status: pending/merged/distinct |
| `link_suggestions` | AI-suggested entity links | `uq_suggestion_triple`, status: pending/accepted/dismissed |
| `audit_logs` | Action audit trail | indexed on `(org_id, created_at)` |

## Auth Architecture

### User Authentication
- Google OAuth handled entirely on backend (`src/api/user_auth.py`)
- Frontend never sees `GOOGLE_CLIENT_ID` or secret
- JWT access tokens (30-min expiry) + refresh tokens (30-day expiry)
- Tokens stored in memory + localStorage on frontend, never in cookies

### Auth Chain (per request)
1. `get_current_user(Authorization)` - decode JWT Bearer token, return User or None
2. `get_current_member(org_id, X-Member-Email, user)` - JWT path (primary) or email header (dev/demo fallback)
3. Auto-links `user_id` on OrgMember if matched by email but not yet linked
4. Auto-creates Person entity for member via `ensure_person_entity_for_member()`

### Connector OAuth (separate from user auth)
- Linear, GitHub, Slack each have OAuth flows in `src/api/auth.py`
- Tokens stored in `oauth_tokens` table per org
- State parameter: `{org_id}:{random_token}` stored in session

## Multi-Tenancy

- `org_id` column on Entity, Edge, OrgMember, OAuthToken, SyncState, UrgencyScoreCache
- **All queries MUST scope to org_id** - this is the tenant boundary
- Demo orgs (`is_demo=True`) are excluded from real sync cycles
- Schema-per-tenant in shared PostgreSQL database

## V1 Constraints

- Connectors: Linear + GitHub + Slack only (read-only OAuth)
- Roles: Engineer + PM only (EM/CTO views planned for V2)
- Briefing: Daily email (web dashboard shows history)
- Goals: Manual input only (no OKR tool integration)
- Claude dispatch: Single action (summarize PR diff)
- Scoring: Hardcoded weights (no ML tuning yet)

## Roadmap (V2)

- Datadog, Sentry, PagerDuty integrations (observability layer)
- Anomaly detection (cross-signal correlation)
- Web app as primary surface (replace email)
- EM and CTO role views
- Bug trace and 1:1 brief Claude actions
- Write capabilities with approval flow
