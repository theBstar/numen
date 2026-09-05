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

# Create the first org, admin, and API key. The web app signs in through
# Google OAuth, so this is how you get in before configuring one.
docker compose exec app python scripts/bootstrap_admin.py you@company.com
```

That prints an API key which works immediately:

```bash
curl -s http://localhost:8001/api/ask \
  -H "Authorization: Bearer numen_..." \
  -H 'Content-Type: application/json' \
  -d '{"question": "what is blocked?"}'
```

The same key connects any MCP client to `http://localhost:8001/mcp/` - the
trailing slash is required. See [docs/agent-setup.md](docs/agent-setup.md).

Open http://localhost:5173 for the web app; signing in there needs
`GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` in `.env`. Everything runs on your
infrastructure. The only network egress is to the LLM endpoint you configure -
and that can be a model running on your own hardware.

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

## Rolling it out

The quick start gives you a running instance with an empty graph. Three steps
turn it into something your team uses.

**1. Connect a tool.** Each connector needs its own OAuth app in that vendor's
developer console, because a self-hosted install authenticates as itself rather
than through a shared vendor app. Start with one - GitHub or Linear gives the
fastest signal. Put the client id and secret in `.env`, restart, then connect it
from the web app under Connections, or by visiting
`/auth/<connector>/connect?org_id=<your-org-id>`. `.env.example` lists the
variables for all six, and [docs/slack-setup.md](docs/slack-setup.md) has a
ready-made manifest for Slack.

**2. Wait for the first sync.** The initial backfill runs on connect; after that
a delta sync runs every `SYNC_INTERVAL_SECONDS` (300 by default). Webhooks make
it near-immediate but need a publicly reachable `APP_URL`; without one Numen
falls back to polling, which is fine for an internal install. Watch progress
with `docker compose logs -f app`. Connector status, including the last sync
time and any error, is on the Connections page and at
`GET /api/orgs/{org_id}/connectors`.

**3. Ask it something.** Once one connector has synced, the same API key from
the bootstrap step answers questions over real data:

```bash
curl -s http://localhost:8001/api/ask \
  -H "Authorization: Bearer numen_..." \
  -H 'Content-Type: application/json' \
  -d '{"question": "what changed in the last day?"}'
```

Add more connectors from there. The value compounds: one tool is a search box,
three is a graph that can tell you a PR is blocked on a decision in Slack.

### Who can sign in

`SIGNUP_MODE` decides who gets an account. The default is the permissive one,
which is usually wrong for a company:

| Mode | Who gets in |
|---|---|
| `open` (default) | Anyone with an email at a domain that already has an org. Suits a hosted product; on your own instance it admits anyone sharing your email domain. |
| `domain` | Only addresses in `ALLOWED_EMAIL_DOMAINS`, and only into an org that exists. The usual choice. Exact match - `example.com` does not admit `sub.example.com`. |
| `invite` | Nobody joins automatically. Members are added first. |

Set `SIGNUP_MODE=domain` and `ALLOWED_EMAIL_DOMAINS=yourcompany.com` before you
put this anywhere reachable.

## Running it for your team

`docker-compose.yml` is for evaluation: it reloads on source changes, runs the
frontend through a dev server, and binds the datastores to loopback.
`docker-compose.prod.yml` is the one to deploy - built images, no reload, the
frontend compiled to static assets, and Caddy as the only service on the
network.

```bash
# In .env:
#   NUMEN_DOMAIN=numen.yourcompany.com
#   APP_URL=https://numen.yourcompany.com
#   ENVIRONMENT=production
#   POSTGRES_PASSWORD / NUMEN_APP_PASSWORD / SECRET_KEY / JWT_SECRET_KEY / ENCRYPTION_KEY
docker compose -f docker-compose.prod.yml up --build -d
docker compose -f docker-compose.prod.yml exec app python scripts/bootstrap_admin.py you@company.com
```

Caddy obtains a Let's Encrypt certificate for `NUMEN_DOMAIN` automatically,
provided ports 80 and 443 reach the host. Leave `NUMEN_DOMAIN` unset only if
something in front already terminates TLS.

`APP_URL` must match the hostname people actually use. It is not cosmetic: the
MCP server validates the `Host` header against it, so a mismatch makes agent
connections fail with `421 Invalid Host header`.

Startup refuses to run with `ENVIRONMENT=production` while any secret or
database password is still a shipped default.

**Backups.** Numen's state is two volumes, `numen-postgres` and
`numen-falkordb`. Back them up together - the graph references rows in Postgres,
so a mismatched pair restores inconsistent. Redis holds only cache and is
disposable.

**Upgrades.** Pull, rebuild, restart; migrations run on boot.

```bash
git pull && docker compose -f docker-compose.prod.yml up --build -d
```

Read [CHANGELOG.md](CHANGELOG.md) first. Interfaces still change between
releases, and a migration is not reversible - take a backup before upgrading.

**Sizing.** The six services idle at roughly 340 MB of RAM in total, most of it
the app and FalkorDB. Growth is driven by how much history you ingest rather
than by how many people use it, so size the host against your graph, and give
FalkorDB room - it holds the graph in memory.

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
