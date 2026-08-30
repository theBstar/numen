# Numen

**Proactive work intelligence for engineering teams. Self-hosted.**

Numen connects to the tools your team already uses, builds a graph of the work
happening across them, and tells each person what deserves their attention today
and why. It reads continuously and surfaces to you - you do not have to ask it
questions.

Search tools answer when you ask. Numen tells you before you ask.

```bash
git clone https://github.com/theBstar/numen.git
cd numen
cp .env.example .env
docker compose up --build
```

Open http://localhost:5173 to connect your tools and watch the graph build.
Everything runs on your infrastructure. The only network egress is to the LLM
endpoint you configure - and that can be a model running on your own hardware.

Then move it to where your team already is:

```
@numen what is blocking the checkout rewrite?

Numen  Three things, most urgent first.
       1. PR #482 has been waiting on review for 4 days. Priya is the only
          reviewer and she is out until Thursday.
       2. ENG-1204 is blocked on the payments schema decision in
          #eng-architecture, which has been open since the 12th.
       3. The Stripe migration doc was edited yesterday and contradicts
          the acceptance criteria on ENG-1198.
       Connected to: Q3 goal "cut checkout drop-off by 15%"
```

That answer joins GitHub, Linear, Slack, and a Google Doc. No single tool could
have produced it, which is the entire point.

[docs/slack-setup.md](docs/slack-setup.md) has a ready-made app manifest and
takes about five minutes.

---

## What it does

**Connects your work tools.** Linear, GitHub, Slack, Jira, Notion, and Google
Docs sync incrementally into one normalized graph of people, tasks, pull
requests, projects, documents, and goals.

**Resolves entities across tools.** The same person in Slack, GitHub, and Linear
becomes one person. A pull request links to the ticket it closes and the goal it
serves.

**Scores urgency per person.** A weighted model over deadlines, blockers, review
latency, and goal linkage decides what actually matters for each individual,
rather than showing everyone the same dashboard.

**Delivers a daily briefing.** Email or Slack DM, ranked by urgency, with every
item annotated by the signals that surfaced it and the goal it connects to.

**Answers wherever you work.** One agent, many front doors: mention it in
Slack, send it a DM, use the web chat, call `/api/ask`, or point any
OpenAI-compatible client at `/api/v1/chat/completions`. The reasoning lives in
one place, so every surface gets the same tools and the same answer.

**Exposes the graph to your own agents.** A built-in MCP server gives Claude
Code, Cursor, and any MCP client tools over the joined graph. Per-tool MCP
servers hand an agent three siloed APIs; this one hands it a graph where the
joins, entity resolution, and urgency scoring are already done.

## Why self-host

Numen reads your team's tickets, code review, and conversations. That is exactly
the kind of data most companies will not send to a third-party SaaS.

- **Your data stays put.** Postgres, Redis, and FalkorDB run in your network.
- **Bring your own model.** Numen speaks the OpenAI wire protocol, so it works
  with OpenAI, Azure, OpenRouter, or a local Ollama or vLLM server. Point
  `LLM_BASE_URL` at localhost and no token leaves your network.
- **Audit it.** The scoring model, the prompts, and every query are in this
  repository.
- **No per-seat pricing.** Run it for five people or five hundred.

## Requirements

- Docker and Docker Compose
- An LLM endpoint: an API key for a hosted provider, or a local server
- Optional, for real data: OAuth apps for the tools you want to connect

## Configuration

All settings live in `.env`. Copy `.env.example` and edit. The essentials:

| Variable | What it does |
|---|---|
| `LLM_API_KEY` | Key for a hosted LLM provider. Leave empty for a local server. |
| `LLM_BASE_URL` | Any OpenAI-compatible endpoint. Empty targets OpenAI. |
| `LLM_MODEL` | Chat model name. |
| `EMBEDDING_MODEL` | Embedding model. Changing it requires reindexing the graph. |
| `ADMIN_EMAILS` | Comma-separated admins. Set this to your own address first. |
| `SECRET_KEY` / `JWT_SECRET_KEY` | Session and token signing. Generate strong values. |

Running fully local with Ollama:

```bash
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=llama3.3
EMBEDDING_MODEL=nomic-embed-text
EMBEDDING_DIMENSIONS=768
```

### Connecting your tools

Each connector needs an OAuth app in the corresponding developer console, since
a self-hosted install authenticates as itself rather than through a shared
vendor app. `.env.example` lists the variables for Linear, GitHub, Slack, Jira,
Notion, and Google. For Slack, [docs/slack-setup.md](docs/slack-setup.md) has a
ready-made app manifest and explains why you create the app yourself.

Webhooks need a publicly reachable `APP_URL`. Without one, connectors fall back
to polling on `SYNC_INTERVAL_SECONDS`, which works fine for a local install.

## Architecture

Five layers, each independently testable:

| Layer | Does |
|---|---|
| Ingestion (`src/connectors/`) | Pull incremental changes over OAuth, normalize to canonical entities |
| Context graph (`src/graph/`) | Entities and typed edges in Postgres and FalkorDB, with entity resolution |
| Inference (`src/inference/`) | Urgency scoring and cross-signal correlation |
| Briefing (`src/briefing/`) | Assemble and deliver personalized briefings |
| Agent (`src/agent/`) | Tool registry, permissions, and the surface-agnostic run loop |
| Surfaces (`src/slack/`, `src/chat/`, `src/mcp/`, `src/api/routes_agent.py`) | Thin adapters that render the agent's events |

Adapters never call the model or a tool themselves. They resolve identity and
threading, then render what the core emits - which is what keeps one agent from
becoming a different agent per surface.

Where you ask changes what the agent may use. An answer posted somewhere other
people can read it, such as a Slack channel, is grounded only on what the tools
return there, never private documents, and cannot change records.

Deeper documentation is in [.agent/](.agent/), which is written for both humans
and coding agents. [`.agent/architecture.md`](.agent/architecture.md) covers the
data model and request flow.

**Design principle: read-only by default.** Numen drafts; humans approve. It
does not write to your source systems without explicit action.

## Development

```bash
pip install -e ".[dev]"          # backend
cd frontend && npm install       # frontend

make verify-graph                # lint + test one module
make verify                      # everything (cross-service changes)

alembic revision --autogenerate -m "description"
alembic upgrade head
```

Tests mirror `src/`. External APIs are always mocked. See
[AGENTS.md](AGENTS.md) for the full command reference and
[.agent/best-practices.md](.agent/best-practices.md) for patterns.

## Status

Numen is beta. The connectors, graph, scoring, briefings, agent, and MCP server
are covered by the test suite, which mocks every external API. The Slack surface
is the newest part and has had the least exposure to real workspaces, so if
something there is wrong for you, a bug report is genuinely useful. Interfaces
may still change between releases; read the changelog before upgrading.

## License

[AGPL-3.0](LICENSE). You can run Numen internally, modify it, and self-host it
without restriction. If you offer a modified Numen to others as a network
service, you must publish your changes under the same license.

The full feature set is in this repository. There is no crippled community
edition: the connectors, context graph, urgency scoring, briefings, chat agent,
and MCP server are free and stay free.
