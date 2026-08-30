# Contributing to Numen

Thanks for taking the time. This document covers getting set up, what the
project expects from a change, and the few conventions that are load-bearing.

## Getting set up

```bash
git clone https://github.com/theBstar/numen.git
cd numen
cp .env.example .env
docker compose up --build
```

That should be enough: development secrets are generated on first boot, and
migrations run automatically. The app is at http://localhost:5173, the API docs
at http://localhost:8001/docs.

To run the backend outside Docker:

```bash
pip install -e ".[dev]"
uvicorn src.main:app --reload
```

You need an LLM endpoint for anything that reasons. Set `LLM_API_KEY` for a
hosted provider, or point `LLM_BASE_URL` at a local server such as Ollama - see
the README.

## Before you open a pull request

Run the checks for what you touched. They are fast and scoped:

```bash
make verify-agent       # src/agent/
make verify-graph       # src/graph/
make verify-slack       # src/slack/
make verify             # everything, for cross-service changes
```

CI runs lint, the full test suite, a frontend typecheck, and applies every
migration against a real Postgres.

## What the project expects

**Tests first.** Write a failing test, make it pass, then tidy. Test files
mirror `src/`. External services are always mocked - a test must never make a
network call.

**Scope queries by `org_id`.** It is the tenant boundary. A query that forgets
it is a security bug, not a nit.

**Don't add a second tool registry.** Agent tools go in
`src/agent/registry.py`, once, and every surface picks them up. Numen already
had two registries that drifted until the web chat could do less than an
external MCP client; see [.agent/services/agent.md](.agent/services/agent.md).

**Surfaces are adapters.** Slack, web, and the HTTP endpoints resolve identity
and render events. They never build a prompt or call a tool.

**Keep `.agent/` accurate.** When you change how a module works, update
`.agent/services/<module>.md`. Those docs are read by both people and coding
agents.

**Hyphens, not em dashes**, in code, comments and docs.

## Commit messages

Explain what was wrong and why the change is right, not just what you did. If
you fixed a bug, say what broke and how. The git history is the main record of
why this code looks the way it does.

## Reporting bugs

Open an issue with what you expected, what happened, and enough detail to
reproduce it - the failing command and its output is usually enough. Include
your deployment shape if it is relevant: Docker or bare metal, which LLM
endpoint, which connectors.

For anything security-related, do not open an issue. See
[SECURITY.md](SECURITY.md).

## Scope

Numen is a focused product, and not every good idea belongs in it. If you are
planning something substantial, open an issue first so we can agree on the
shape before you spend the time. Changes that are out of scope get told so
plainly and early, which is meant as respect for your time rather than a
dismissal of the idea.

## Licensing

Numen is [AGPL-3.0](LICENSE). By contributing you agree your contribution is
licensed under the same terms.
