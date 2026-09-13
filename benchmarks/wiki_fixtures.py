"""A product wiki over the same estate: PRD documents and the feature graph.

`src/demo/` seeds people, tickets and pull requests but no product
documentation, so this authors it. The documents are written the way real
PRDs are - prose, a decisions section, some numbers, and the occasional
disagreement with a sibling document that nobody noticed.

The feature graph is what Numen's wiki layer builds on top: each feature
points at the PRD sections it came from and at the tickets, pull requests and
people implementing it. Both arms of experiment 5 are served from this one
source, so the difference measured is the shape of the access, not the
content.

The conflict between PRD-002 and PRD-006 is deliberate and is the only one.
"""

from __future__ import annotations

# ── PRD documents ─────────────────────────────────────────────────────────

DOCS: tuple[dict, ...] = (
    {
        "id": "PRD-001",
        "title": "Safari OAuth: PKCE support",
        "author": "eve",
        "updated": "2026-07-14",
        "body": """# Safari OAuth: PKCE support

## Problem
Sign-in fails for roughly 9% of new workspaces. Every failing report is
Safari, and every one is a workspace whose identity provider requires PKCE.
Safari's Intelligent Tracking Prevention drops the state cookie we use to
carry the verifier across the redirect, so the exchange arrives without it
and the provider rejects it.

## Approach
Stop carrying the verifier in a cookie. Generate the code verifier in the
client, keep it in sessionStorage for the life of the redirect, and send the
challenge on the authorize call. On return, read the verifier back and
exchange it directly.

## Decisions
- We support S256 only. Providers that offer plain are downgraded and we
  refuse rather than fall back.
- The verifier lives in sessionStorage, not localStorage, so a closed tab
  ends the attempt.
- No change to the server session format. This is a client-side fix.

## Out of scope
Native mobile flows. Those never used the cookie and are unaffected.
""",
    },
    {
        "id": "PRD-002",
        "title": "Connector rate limiting",
        "author": "grace",
        "updated": "2026-07-02",
        "body": """# Connector rate limiting

## Problem
Two large workspaces tripped GitHub's secondary limits during their first
sync and were throttled for the rest of the hour. We retry, but our retries
are what pushed them over.

## Approach
A token bucket per connector per organization, refilled on a schedule, with
the bucket sized from the provider's published ceiling rather than guessed.

## Decisions
- **Retry policy: three attempts, exponential backoff starting at one
  second.** After the third failure the sync is abandoned and reported, not
  retried on the next cycle.
- Buckets are per organization, so one noisy tenant cannot starve another.
- 429 responses consume a token. Otherwise a throttled caller spins.

## Numbers
Steady state for GitHub is 5,000 requests per hour per installation. We
target 80% of the ceiling so a burst has somewhere to go.
""",
    },
    {
        "id": "PRD-003",
        "title": "Entity resolution across sources",
        "author": "eve",
        "updated": "2026-08-03",
        "body": """# Entity resolution across sources

## Problem
The same person is three records: a GitHub login, a Linear user, a Slack id.
Until those are one entity, every cross-source question is guesswork, and a
briefing that says "Alice has four things open" is wrong in both directions.

## Approach
Resolve at ingest, not at query time. Each connector reports whatever
identity attributes its API exposes; the resolver clusters them offline with
the whole roster present, and persists the mapping.

## Decisions
- Email is the only high-confidence key. Everything else is a hint.
- We keep an explicit confidence on each link, so a briefing can decline to
  assert something it inferred weakly.
- Manual overrides win permanently and are never re-derived.

## Known weakness
Where no source exposes an email, the resolver falls back to name and handle
similarity, and two people with the same surname can merge. We would rather
under-link than merge, so the threshold is set conservatively.
""",
    },
    {
        "id": "PRD-004",
        "title": "The daily briefing",
        "author": "eve",
        "updated": "2026-08-19",
        "body": """# The daily briefing

## Problem
People do not ask the system questions. They open twelve tabs and guess. The
product has to arrive rather than wait.

## Approach
One message per person per morning. Ranked by urgency, capped at five items,
each carrying why it was surfaced and which goal it connects to.

## Decisions
- Five items maximum. A briefing that lists everything is a dashboard, and
  dashboards get ignored.
- Every item shows provenance. No item appears without a source link.
- Delivery is Slack first. Email is a fallback for people who have not
  connected Slack.

## Open question
Whether a person with nothing urgent gets a short note or no message at all.
Currently no message.
""",
    },
    {
        "id": "PRD-005",
        "title": "Slack thread ingestion",
        "author": "grace",
        "updated": "2026-06-21",
        "body": """# Slack thread ingestion

## Problem
Decisions get made in threads and never leave them. A ticket says "blocked on
the payments decision" and the decision is four days deep in a channel.

## Approach
Ingest public channel messages and thread replies. Attach a thread to the
entities it mentions, so a ticket carries the conversation that shaped it.

## Decisions
- Public channels only. We never read a private channel or a DM, and there is
  no setting that turns this on.
- Threads are attached to entities by explicit mention, not by inference.
- Message bodies are stored. Redaction happens at query time, not ingest.

## Out of scope
Reactions and channel membership.
""",
    },
    {
        "id": "PRD-006",
        "title": "Sync reliability and backoff",
        "author": "frank",
        "updated": "2026-08-28",
        "body": """# Sync reliability and backoff

## Problem
Transient provider failures abandon a whole sync cycle. A single 502 from
Linear during a delta sync loses the window, and the next cycle starts from
the last successful cursor, so nothing is lost but the data is stale for
another fifteen minutes.

## Approach
Make retries survive a cycle. Track attempts against the cursor rather than
the request, so a retry resumes where the failure happened.

## Decisions
- **Retry policy: five attempts with jittered backoff, up to two minutes
  total.** Beyond that the cursor is parked and an operator is paged.
- Cursors are checkpointed after each page, not at the end of a sync.
- A parked cursor blocks that connector only.

## Note
This supersedes the retry guidance in the connector rate limiting document
for sync paths. Webhook paths are unchanged.
""",
    },
)

DOC_BY_ID = {d["id"]: d for d in DOCS}

# ── The feature graph ─────────────────────────────────────────────────────
# What Numen's wiki layer builds: a feature per capability, pointing back at
# the PRD sections it came from and forward at the work implementing it.

FEATURES: tuple[dict, ...] = (
    {
        "slug": "safari-pkce",
        "title": "Safari PKCE sign-in",
        "domain_group": "auth",
        "status": "active",
        "summary": "PKCE-based OAuth so Safari users with ITP can sign in.",
        "prd_references": ["PRD-001"],
        "concepts": ["oauth", "pkce", "safari"],
        "implementation": {"tasks": ["ENG-4501", "ENG-4505"], "prs": [301], "people": ["alice"]},
    },
    {
        "slug": "connector-rate-limiting",
        "title": "Connector rate limiting",
        "domain_group": "ingestion",
        "status": "active",
        "summary": "Per-org token buckets so one tenant cannot exhaust a provider quota.",
        "prd_references": ["PRD-002", "PRD-006"],
        "concepts": ["rate-limit", "retry", "backoff"],
        "implementation": {"tasks": ["ENG-4502", "ENG-4510"], "prs": [302], "people": ["igor"]},
    },
    {
        "slug": "entity-resolution",
        "title": "Cross-source entity resolution",
        "domain_group": "graph",
        "status": "active",
        "summary": "One person across GitHub, Linear and Slack, resolved at ingest.",
        "prd_references": ["PRD-003"],
        "concepts": ["identity", "resolution", "confidence"],
        "implementation": {"tasks": ["ENG-4506", "ENG-4515"], "prs": [303], "people": ["alice"]},
    },
    {
        "slug": "daily-briefing",
        "title": "Daily briefing",
        "domain_group": "briefing",
        "status": "active",
        "summary": "One ranked message per person per morning, capped at five items.",
        "prd_references": ["PRD-004"],
        "concepts": ["briefing", "urgency", "provenance"],
        "implementation": {"tasks": ["ENG-4511", "ENG-4558"], "prs": [], "people": ["hannah", "lisa"]},
    },
    {
        "slug": "slack-threads",
        "title": "Slack thread ingestion",
        "domain_group": "ingestion",
        "status": "active",
        "summary": "Public channel threads attached to the entities they mention.",
        "prd_references": ["PRD-005"],
        "concepts": ["slack", "threads", "privacy"],
        "implementation": {"tasks": ["ENG-4509", "ENG-4557"], "prs": [], "people": ["david"]},
    },
    {
        "slug": "sync-reliability",
        "title": "Sync reliability",
        "domain_group": "ingestion",
        "status": "planned",
        "summary": "Cursor-checkpointed retries so a transient failure does not lose a window.",
        "prd_references": ["PRD-006"],
        "concepts": ["retry", "backoff", "cursor"],
        "implementation": {"tasks": ["ENG-4559", "ENG-4513"], "prs": [], "people": ["igor", "kevin"]},
    },
)

FEATURE_BY_SLUG = {f["slug"]: f for f in FEATURES}

#: Alignment the wiki layer records at ingest. One real disagreement.
CONFLICTS: tuple[dict, ...] = (
    {
        "documents": ["PRD-002", "PRD-006"],
        "topic": "retry policy",
        "detail": ("PRD-002 specifies three attempts with exponential backoff from one "
                   "second. PRD-006 specifies five attempts with jittered backoff up to "
                   "two minutes, and claims to supersede PRD-002 for sync paths without "
                   "PRD-002 being updated."),
    },
)
