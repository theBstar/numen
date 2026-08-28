# Numen in Slack

Numen answers in Slack: mention it in a channel, or send it a direct message.
The daily briefing arrives as a DM whose items you can act on in place.

## Create the app

You create the Slack app in your own workspace rather than installing a shared
one. Two reasons, both practical:

- **Rate limits.** Slack cut `conversations.history` to roughly one request a
  minute for distributed apps that are not Marketplace-approved. Apps a
  workspace creates for itself keep the normal limits, which is what Numen's
  ingestion needs.
- **Your tokens stay yours.** The bot token is issued to your workspace and
  stored in your database.

Steps:

1. Go to https://api.slack.com/apps and choose **Create New App** ->
   **From an app manifest**.
2. Pick your workspace, then paste [slack-app-manifest.yml](slack-app-manifest.yml),
   replacing `YOUR-NUMEN-HOST` with your Numen hostname.
3. Install to the workspace when prompted.
4. From **Basic Information**, copy the **Signing Secret**, and from **OAuth &
   Permissions** copy the **Bot User OAuth Token**.

## Configure Numen

```bash
SLACK_CLIENT_ID=...
SLACK_CLIENT_SECRET=...
SLACK_SIGNING_SECRET=...
```

Then connect Slack from **Connections** in the Numen web app, which stores the
bot token and records your workspace id so incoming events route to the right
organisation.

## Reachability

Slack delivers events over HTTPS, so it must be able to reach
`https://YOUR-NUMEN-HOST/api/slack/events`. If Numen runs somewhere Slack
cannot reach:

- Ingestion still works. Connectors fall back to polling every
  `SYNC_INTERVAL_SECONDS`.
- Briefings still arrive. Numen calls Slack, not the other way round.
- The agent will not answer in Slack, because it never receives the message.

For a local trial, a tunnel (`ngrok http 8001` or similar) is enough. Put the
tunnel hostname in both request URLs in the manifest.

## What Numen can see and do, by place

Where you ask changes what the answer may draw on. A channel is readable by
people who may not have access to the records behind an answer, so:

| | Direct message | Channel |
|---|---|---|
| Answers from the work graph | Yes | Yes |
| Retrieves private documents | Yes | No |
| Creates or updates records | Yes | No |

Someone with no Numen account gets a private note telling them so, rather than
an answer, and never a public one.

## The daily briefing

Each item carries three buttons:

- **Why this?** asks the agent to explain the item, answering in the thread.
- **Snooze** leaves it out of tomorrow's briefing.
- **Less like this** feeds back into ranking, so the signal actually changes
  what you get.

Replies in a briefing thread go to the agent, so the briefing is the start of a
conversation rather than a notification you have to leave.

## Troubleshooting

**Numen does not respond to a mention.** Check that the event request URL is
verified in the Slack app settings, and that `SLACK_SIGNING_SECRET` matches the
signing secret. Numen rejects unsigned and stale requests.

**"I could not find a Numen account for you."** Slack users are matched to
Numen members by the email on the Slack profile. Add that person to the
organisation with the same address.

**Buttons do nothing.** Interactivity has to be switched on in the Slack app,
with its request URL pointing at `/api/slack/interactions`.
