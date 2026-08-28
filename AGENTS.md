# Numen - Agent Guide

Machine-readable entry point for AI coding agents (Claude Code, Cursor, Copilot, etc.).

## Setup

```bash
# Full stack (Docker)
docker compose up --build

# Backend only (local)
pip install -e ".[dev]"
uvicorn src.main:app --reload

# Frontend only (local)
cd frontend && npm install && npm run dev

# Migrations (auto-run in Docker, or manually)
alembic upgrade head
```

## Verify

Non-interactive commands for lint + test + typecheck.

```bash
# Per-service (fast - run after changing a specific module)
make verify-connectors   # src/connectors/
make verify-graph        # src/graph/
make verify-inference    # src/inference/
make verify-briefing     # src/briefing/
make verify-api          # src/api/
make verify-chat         # src/chat/
make verify-llm          # src/llm/
make verify-workers      # src/workers/
make verify-frontend     # frontend/ (typecheck + lint)

# Full stack (only for cross-service changes)
make verify-backend      # all backend lint + tests
make verify-frontend     # frontend typecheck + lint
make verify              # everything
```

## Secrets Policy

- **NEVER** read `.env` files directly
- Environment variables documented in `.env.example` (structure only, no values)
- When a runtime value is needed, create a `.sh` script that reads and pipes it
- Google OAuth secrets: backend only, never expose to frontend
- JWT tokens: memory + localStorage, never cookies
- See `.env.example` for all required variables

## Layout Map

| Path | What |
|------|------|
| `src/connectors/` | L1: OAuth connectors (Linear, GitHub, Slack) |
| `src/graph/` | L2: Entity/Edge CRUD, resolution, graph queries |
| `src/inference/` | L3: Urgency scoring, caching |
| `src/briefing/` | L4: Briefing assembly, email delivery |
| `src/llm/` | L5: LLM dispatch (OpenAI), prompts |
| `src/chat/` | Chat agent (LangGraph, tools, SSE) |
| `src/api/` | FastAPI routes, auth, schemas, dependencies |
| `src/workers/` | Background schedulers |
| `src/shared/` | Types, DB models, database engine |
| `src/config.py` | Pydantic settings from .env |
| `frontend/src/` | React 19 + Vite + TypeScript + Tailwind |
| `alembic/` | Database migrations |
| `tests/` | Test suites (mirrors src/ structure) |
| `.agent/` | Deep context docs (architecture, services, best practices) |

## Build Order

1. PostgreSQL + Redis (docker compose or local install)
2. Alembic migrations: `alembic upgrade head`
3. Backend: `uvicorn src.main:app --reload`
4. Frontend: `cd frontend && npm run dev`

## Key Files

| When working on... | Read these first |
|---------------------|-----------------|
| Any backend module | `CLAUDE.md` + `.agent/architecture.md` + `.agent/services/<module>.md` |
| Frontend | `CLAUDE.md` + `.agent/services/frontend.md` |
| Adding a connector | `.agent/services/connectors.md` (includes step-by-step guide) |
| Graph / entity logic | `.agent/services/graph.md` |
| API endpoints | `.agent/services/api.md` |
| Urgency scoring | `.agent/services/inference.md` |
| Before writing any code | `.agent/best-practices.md` |

## Access Points

| Service | URL |
|---------|-----|
| Backend API docs | http://localhost:8001/docs |
| Frontend | http://localhost:5173 |
| PostgreSQL | localhost:5499 |
| Redis | localhost:6380 |
