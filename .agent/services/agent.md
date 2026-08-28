# Agent Core

> `src/agent/`

The surface-agnostic agent. Every conversational front door - web chat, Slack,
the HTTP endpoints, and in time the CLI - runs through this and renders what it
emits.

## The rule

**Adapters consume events. They never call the model and never call a tool.**

Breaking this is how a product ends up with a different agent per channel. It
already happened once here: `src/chat/tools.py` held twelve read-only LangChain
tools while `src/mcp/tools.py` held twenty-eight, so a user in Claude Desktop
could create a task and a user in Numen's own chat panel could not. Both are now
one registry.

## Modules

| File | Responsibility |
|------|----------------|
| `events.py` | The event vocabulary and SSE framing helper |
| `principal.py` | Who is asking, and what the surface permits |
| `registry.py` | The single tool registry, and permission filtering |
| `resolvers.py` | Name to entity, with ambiguity reported back |
| `prompts.py` | System prompt, assembled per surface |
| `core.py` | `run_agent()` and `run_agent_to_text()` |

## Events

`run_agent()` yields typed events, never wire strings:

| Event | Meaning |
|-------|---------|
| `status` | Human-readable progress, e.g. "Checking Linear" |
| `token` | A chunk of reply text |
| `tool_start` / `tool_end` | Tool boundaries |
| `citation` | Entities the answer drew on |
| `elicitation` | The agent asking a question. Not a failure |
| `sanitized` | Replaces text already emitted, after redaction |
| `error` | Something failed. Always followed by `done` |
| `done` | Terminal. Always emitted |

`run_agent()` never raises: failures arrive as `error` so every adapter renders
them the same way. The underlying exception goes to the log, never to the
caller, because it can carry connection strings.

Tokens stream raw because the safety patterns in `src/chat/safety.py` span chunk
boundaries and cannot be applied per token. When redaction changes the text, a
`sanitized` event carries the clean version and adapters replace what they
rendered.

## Principal

```python
Principal(org_id, user_id, email, surface, audience, name, member_id)
```

Two permissions derive from it, and both exist to close the same leak - an
answer read by people who may not have access to the records behind it:

- `can_write` requires a bound user **and** a private audience.
- `can_access_private_data` requires a private audience.

`Audience.PRIVATE` is a web session, a DM, or an ephemeral reply.
`Audience.SHARED` is a channel. Surfaces set this; the core enforces it.

## Registry

`TOOL_SPECS` is the single source of truth. Handlers delegate to
`src.mcp.tools`, so query logic lives in one place, and add what a conversation
needs: resolution by name rather than UUID.

`tools_for(principal)` filters by `writes` and `needs_private_audience`.
`build_langchain_tools(ctx)` renders the permitted set for LangGraph. A raising
handler becomes JSON the model can read, not an exception that aborts the run.

Write handlers re-check `can_write` themselves. The filtering already excludes
them, so this is defence in depth.

## Adding a tool

1. Add the query to `src/mcp/tools.py` if it does not exist.
2. Add an args model and a handler in `registry.py`; delegate, do not reimplement.
3. Append a `ToolSpec`. Set `writes=True` for mutations, and
   `needs_private_audience=True` for anything reading private documents.
4. Add a label to `_TOOL_LABELS` in `core.py` so surfaces can show progress.

The tool appears on every surface at once. Nothing else needs editing.
