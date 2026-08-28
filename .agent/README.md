# .agent/ - Deep Technical Context

This directory contains detailed technical context for the Numen codebase. It is designed for consumption by AI coding agents.

**Read `CLAUDE.md` for rules and instructions. Read these files for understanding.**

## Reading Order

1. **[architecture.md](architecture.md)** - Start here. System architecture, data flow, DB schema, tech stack.
2. **[services/\<module\>.md](services/)** - Read the specific service file for the area you're working on.
3. **[best-practices.md](best-practices.md)** - Read before writing any code. Patterns, anti-patterns, testing.

## Index

| File | What it covers |
|------|---------------|
| [architecture.md](architecture.md) | System architecture, data flow, cross-module contracts, DB schema, tech stack, project structure |
| [services/connectors.md](services/connectors.md) | L1: Ingestion - BaseConnector ABC, Linear/GitHub/Slack, how to add new connectors |
| [services/graph.md](services/graph.md) | L2: Entity lifecycle, edge semantics, CTE queries, person resolution, task transitions |
| [services/inference.md](services/inference.md) | L3: Urgency scoring formula, weights, caching, orchestration |
| [services/briefing.md](services/briefing.md) | L4: Briefing assembly by role, email delivery, scheduling |
| [services/claude-dispatch.md](services/claude-dispatch.md) | L5: Claude API client, prompts, actions, link suggester |
| [services/chat.md](services/chat.md) | Chat agent - LangGraph, tools, SSE streaming |
| [services/api.md](services/api.md) | FastAPI routes, auth chain, dependency injection, endpoint reference |
| [services/workers.md](services/workers.md) | Background schedulers, sync loop, lifespan management |
| [services/frontend.md](services/frontend.md) | React app - pages, components, data fetching, routing, state |
| [best-practices.md](best-practices.md) | Coding standards, patterns, anti-patterns, testing conventions |

## Related Files

- **[CLAUDE.md](../CLAUDE.md)** - Rules and instructions (what to follow)
- **[AGENTS.md](../AGENTS.md)** - Agent entry point (setup, verify, secrets, layout)
- **[VISION.md](../VISION.md)** - Product vision and strategy
