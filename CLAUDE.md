# Numen - Instructions

## What is Numen?

Numen is a proactive work intelligence platform. It connects to engineering/product tools (Linear, GitHub, Slack), builds a context graph of entities and relationships, computes urgency scores, and delivers personalized daily briefings. Read [VISION.md](VISION.md) for the full product vision.

## Quick Start

```bash
cp .env.example .env          # Edit with your API keys
docker compose up --build     # Start all services
# Backend: http://localhost:8001/docs  |  Frontend: http://localhost:5173
```

## Rules

### Routing
- All backend routes MUST be under `/api/` - no exceptions
- Never create a backend route that conflicts with a frontend route
- Vite proxy forwards `/api/*` to backend only

### API Contracts
- List: `{ items: T[] }` - never bare arrays
- Paginated: `{ items, total, page, page_size }`
- Single by ID: `T` or 404 `{ detail: "..." }`
- Latest: `T | null` with 200, not 404
- Errors: `{ detail: "Human-readable message" }`

### Agent surfaces
- One agent core in `src/agent/`. Surfaces are adapters: they resolve identity and threading, then render the events `run_agent()` yields
- An adapter must never build a prompt or call a tool - that is how the tool registries drifted before
- Add tools to `src/agent/registry.py` only. Never define a second registry
- Permissions come from `Principal`: a shared audience (a channel) gets no writes and no private-document retrieval

### Backend
- `async/await` everywhere - never block the event loop
- Always scope DB queries by `org_id` - it's the tenant boundary
- `source_ids` are additive-only in upserts - never remove keys
- JSONB properties: always `.get()` with defaults
- Task status is forward-only: `todo -> in_progress -> in_review -> merged -> done`
- Use `RoleType.ENGINEER` (uppercase) for SQLAlchemy enums
- Use hyphens (-) not em dashes in all content
- Demo org data from `src/demo/` seeder only

### Frontend
- TanStack React Query for data fetching (not legacy `useApi` hooks)
- TypeScript strict - no `any` types
- Tailwind CSS only - no CSS modules or styled-components
- Radix UI + CVA for component variants
- Query keys must include `orgId` for cache isolation
- Mutations must invalidate related queries on success

### Security
- Never read `.env` files - use `.env.example` for structure only
- When a runtime value is needed, create a `.sh` script that reads and pipes it
- Google OAuth secrets: backend only - frontend never sees them
- JWT: memory + localStorage, never cookies

### Testing
- Follow red/green TDD: write a failing test first, then implement code to make it pass, then refactor
- Test files mirror `src/` structure
- Use `conftest.py` fixtures (`mock_db`, `mock_entity`, etc.)
- Mock external APIs, never call them in tests
- After changes, run `make verify-<service>` for the affected module (e.g. `make verify-graph`)
- Only run `make verify` for cross-service changes

### Documentation
- When changing a module's internals, update `.agent/services/<module>.md`
- Keep `.agent/` docs accurate - they are consumed by AI agents

## Design Principles

1. **Read-only in v1** - LLM dispatch always returns drafts. Never acts on source systems without human approval.
2. **Signal provenance** - Every briefing item shows "Why Numen surfaced this" with source links.
3. **Goal-connected** - Every item annotated with the business goal it connects to.
4. **Modular** - Each module (connectors, graph, inference, briefing, llm, api, workers) is independently testable.
5. **Cross-signal reasoning** - The value comes from connecting signals across tools, not from any single integration.

## Development

```bash
# Backend (local)
pip install -e ".[dev]"
uvicorn src.main:app --reload

# Frontend (local)
cd frontend && npm install && npm run dev

# Tests + lint (per-service)
make verify-graph            # or verify-api, verify-inference, etc.

# New migration
alembic revision --autogenerate -m "description"
alembic upgrade head
```

## Deep Context

For architecture details, service internals, data model, and patterns - read the `.agent/` directory. See [AGENTS.md](AGENTS.md) for setup, verify commands, secrets policy, and layout map.

| File | What it covers |
|------|---------------|
| [.agent/architecture.md](.agent/architecture.md) | System architecture, data flow, DB schema, tech stack |
| [.agent/services/connectors.md](.agent/services/connectors.md) | L1: Ingestion connectors |
| [.agent/services/graph.md](.agent/services/graph.md) | L2: Context graph, entity resolution, queries |
| [.agent/services/inference.md](.agent/services/inference.md) | L3: Urgency scoring formula and caching |
| [.agent/services/briefing.md](.agent/services/briefing.md) | L4: Briefing assembly and delivery |
| [.agent/services/claude-dispatch.md](.agent/services/claude-dispatch.md) | L5: LLM dispatch (OpenAI), prompts, actions |
| [.agent/services/agent.md](.agent/services/agent.md) | Agent core: events, principal, tool registry (start here) |
| [.agent/services/chat.md](.agent/services/chat.md) | Web chat surface: conversation storage, SSE |
| [.agent/services/slack.md](.agent/services/slack.md) | Slack surface: identity, threading, briefing actions |
| [.agent/services/api.md](.agent/services/api.md) | FastAPI routes, auth chain, endpoint reference |
| [.agent/services/workers.md](.agent/services/workers.md) | Background schedulers |
| [.agent/services/frontend.md](.agent/services/frontend.md) | React app, components, data fetching |
| [.agent/best-practices.md](.agent/best-practices.md) | Patterns, anti-patterns, testing |
