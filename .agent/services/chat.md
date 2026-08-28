# Web Chat Surface

> `src/chat/`

The web app's front door to the agent. The run loop lives in
[`src/agent/`](agent.md); this module stores conversations and frames events as
SSE.

## Modules

| File | Responsibility |
|------|----------------|
| `service.py` | Conversation and message storage; `converse()` |
| `router.py` | The five HTTP endpoints; SSE framing |
| `safety.py` | Output redaction patterns |

There is no `tools.py` or `agent.py` here any more. Both were duplicates of
`src/agent/`; see [agent.md](agent.md).

## Endpoints

Prefix `/api/orgs/{org_id}/chat`, all requiring `get_current_member`.

| Method | Path | Notes |
|--------|------|-------|
| POST | `/conversations` | Create |
| GET | `/conversations` | List for the current member |
| GET | `/conversations/{id}/messages` | History, tool calls redacted |
| POST | `/conversations/{id}/messages` | Send. SSE stream, **30/minute** |
| DELETE | `/conversations/{id}` | Delete with its messages |

The send endpoint is rate limited because it is the most expensive route in the
app - one call can fan out into several model and tool round trips.

## converse()

`converse()` persists the user message, loads history scoped by `org_id`, runs
the agent, and stores the reply. It yields the core's typed events; `router.py`
turns them into SSE frames with `to_sse()`.

What gets stored is the **sanitized** reply when redaction changed it, not what
streamed.

`get_messages()` takes `org_id` with no default. It is the tenant boundary, and
omitting it once crashed every send.

## External conversations

`get_or_create_external_conversation()` looks a conversation up by
`external_ref`, so Slack threads and CLI sessions reuse this same storage.

## Frontend

`frontend/src/hooks/useChat.ts` handles the event types. `sanitized` replaces
`streamingContent` wholesale - the tokens already rendered contained something
that had to be redacted.
