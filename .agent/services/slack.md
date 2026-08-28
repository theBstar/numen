# Slack Surface

> `src/slack/`, `src/api/routes_slack.py`

Slack is both a data source and a conversational surface. The two are kept
apart on purpose.

| Path | Purpose |
|------|---------|
| `/api/webhooks/slack` | Ingestion. Messages and reactions become graph entities |
| `/api/slack/events` | The agent. Mentions and DMs become answers |
| `/api/slack/interactions` | Buttons on briefing items |

A dropped ingest can be backfilled; a dropped question looks like a broken bot.
One endpoint deciding which is which would give both the worse failure mode.

## Modules

| File | Responsibility |
|------|----------------|
| `client.py` | Thin Slack Web API wrapper; bot token lookup |
| `identity.py` | Slack user -> `Principal` |
| `handler.py` | Routes an event into the agent, renders the reply |
| `actions.py` | Briefing buttons and the feedback they record |

## Identity

Slack users are matched to `OrgMember` by the email on the Slack profile. No
member record means **no principal** - the person is told so ephemerally rather
than being handed org-wide access.

Audience follows the place: a DM or group DM is `PRIVATE`, a channel mention is
`SHARED`. That single value is what withholds document retrieval and writes in
channels.

## Loop prevention

`should_handle()` rejects `bot_id` and bot subtypes **first**. Without that the
agent answers its own posts, forever. It also ignores edits, joins, and empty
text, and in channels only responds to `app_mention`.

## Threading

A Slack thread maps to a `Conversation` via
`external_ref = "slack:{channel}:{thread_ts}"`, so a Slack thread, a web
conversation and a CLI session are one primitive with shared history.

Replies go back on `thread_ts`, so a whole conversation costs one channel slot.

## Timing

Slack retries anything not acknowledged within three seconds, so the route
verifies, acks, and processes in the background on its own session. Retries
carry `X-Slack-Retry-Num` and are dropped: a retry means our ack was slow, not
that the user asked twice.

Signatures are verified with a five-minute window, so a captured request cannot
be replayed.

## Briefing actions

Each briefing item carries **Why this?**, **Snooze** and **Less like this**.
Feedback is written to `UrgencyScoreCache.score_components["feedback"]`, which
the next briefing reads. A feedback button that changes nothing teaches people
that pressing buttons changes nothing.

## Setup

`docs/slack-setup.md` and `docs/slack-app-manifest.yml`. Each workspace creates
its own app: Slack cut `conversations.history` for distributed apps that are not
Marketplace-approved, and internal apps keep the normal limits.
