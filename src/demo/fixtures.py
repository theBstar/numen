"""Static fixture data for the Numen demo organization.

All UUIDs are deterministic via uuid5 so seeding is idempotent - running the
seeder multiple times produces the same data.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

# ── Deterministic UUID helpers ────────────────────────────────────────────

NAMESPACE = uuid.UUID("12345678-1234-5678-1234-567812345678")


def _id(name: str) -> uuid.UUID:
    """Generate a deterministic UUID from a human-readable name."""
    return uuid.uuid5(NAMESPACE, name)


DEMO_ORG_ID = _id("demo-org")

# ── Reference dates ──────────────────────────────────────────────────────
# Fixtures are anchored relative to "now" so they always look fresh.

_NOW = datetime.now(timezone.utc)
_TODAY = _NOW.replace(hour=0, minute=0, second=0, microsecond=0)


def _days_ago(n: int) -> datetime:
    return _NOW - timedelta(days=n)


def _days_from_now(n: int) -> datetime:
    return _NOW + timedelta(days=n)


# ── Persons ──────────────────────────────────────────────────────────────

PERSONS = [
    {
        "key": "alice",
        "name": "Alice Chen",
        "email": "alice@demo.example.com",
        "role": "engineer",
        "title": "Senior Engineer",
        "team": "Platform",
        "github_username": "alice-chen",
        "linear_id": "user-alice",
        "slack_id": "U03ALICE01",
    },
    {
        "key": "bob",
        "name": "Bob Martinez",
        "email": "bob@demo.example.com",
        "role": "engineer",
        "title": "Engineer",
        "team": "Platform",
        "github_username": "bob-martinez",
        "linear_id": "user-bob",
        "slack_id": "U03BOB001",
    },
    {
        "key": "carol",
        "name": "Carol Wu",
        "email": "carol@demo.example.com",
        "role": "engineer",
        "title": "Engineer",
        "team": "Growth",
        "github_username": "carol-wu",
        "linear_id": "user-carol",
        "slack_id": "U03CAROL1",
    },
    {
        "key": "david",
        "name": "David Kim",
        "email": "david@demo.example.com",
        "role": "engineer",
        "title": "Engineer",
        "team": "Growth",
        "github_username": "david-kim",
        "linear_id": "user-david",
        "slack_id": "U03DAVID1",
    },
    {
        "key": "eve",
        "name": "Eve Patel",
        "email": "eve@demo.example.com",
        "role": "pm",
        "title": "Product Manager",
        "team": "Platform",
        "github_username": "eve-patel",
        "linear_id": "user-eve",
        "slack_id": "U03EVE001",
    },
    {
        "key": "frank",
        "name": "Frank Liu",
        "email": "frank@demo.example.com",
        "role": "vp_eng",
        "title": "VP of Engineering",
        "team": "Engineering",
        "github_username": "frank-liu",
        "linear_id": "user-frank",
        "slack_id": "U03FRANK1",
    },
    {
        "key": "grace",
        "name": "Grace Zhang",
        "email": "grace@demo.example.com",
        "role": "cto",
        "title": "CTO",
        "team": "Leadership",
        "github_username": "grace-zhang",
        "linear_id": "user-grace",
        "slack_id": "U03GRACE1",
    },
    {
        "key": "hannah",
        "name": "Hannah Lee",
        "email": "hannah@demo.example.com",
        "role": "designer",
        "title": "Senior Designer",
        "team": "Design",
        "github_username": "hannah-lee",
        "linear_id": "user-hannah",
        "slack_id": "U03HANNA1",
    },
    {
        "key": "igor",
        "name": "Igor Popov",
        "email": "igor@demo.example.com",
        "role": "engineer",
        "title": "Staff Engineer",
        "team": "Infrastructure",
        "github_username": "igor-popov",
        "linear_id": "user-igor",
        "slack_id": "U03IGOR01",
    },
    {
        "key": "julia",
        "name": "Julia Santos",
        "email": "julia@demo.example.com",
        "role": "engineer",
        "title": "Engineer",
        "team": "Infrastructure",
        "github_username": "julia-santos",
        "linear_id": "user-julia",
        "slack_id": "U03JULIA1",
    },
    {
        "key": "kevin",
        "name": "Kevin Nguyen",
        "email": "kevin@demo.example.com",
        "role": "engineer",
        "title": "Engineer",
        "team": "Mobile",
        "github_username": "kevin-nguyen",
        "linear_id": "user-kevin",
        "slack_id": "U03KEVIN1",
    },
    {
        "key": "lisa",
        "name": "Lisa Park",
        "email": "lisa@demo.example.com",
        "role": "engineer",
        "title": "Engineer",
        "team": "Mobile",
        "github_username": "lisa-park",
        "linear_id": "user-lisa",
        "slack_id": "U03LISA01",
    },
]

# Build quick-lookup helpers
PERSON_IDS: dict[str, uuid.UUID] = {p["key"]: _id(f"person-{p['key']}") for p in PERSONS}
PERSON_BY_KEY: dict[str, dict] = {p["key"]: p for p in PERSONS}


# ── Tasks (Linear source) ───────────────────────────────────────────────


def _task(
    num: int,
    title: str,
    assignee: str,
    status: str,
    priority: str,
    labels: list[str] | None = None,
    in_sprint: bool = False,
    due_days: int | None = None,
    created_days_ago: int = 7,
) -> dict:
    return {
        "key": f"ENG-{num}",
        "num": num,
        "title": title,
        "assignee": assignee,
        "status": status,
        "priority": priority,
        "labels": labels or [],
        "in_sprint": in_sprint,
        "due_date": _days_from_now(due_days).date().isoformat() if due_days is not None else None,
        "created_at": _days_ago(created_days_ago).isoformat(),
    }


TASKS = [
    # ── Urgent (5) ─────────────────────────────────────────────────────
    _task(
        4501,
        "Fix OAuth PKCE flow breaking on Safari",
        "alice",
        "in_progress",
        "urgent",
        ["auth", "bug"],
        True,
        1,
        3,
    ),
    _task(
        4502,
        "Hotfix: rate limiter dropping valid requests under load",
        "igor",
        "in_progress",
        "urgent",
        ["infra", "bug"],
        True,
        0,
        1,
    ),
    _task(
        4503,
        "Resolve database connection pool exhaustion in prod",
        "julia",
        "in_review",
        "urgent",
        ["infra", "bug"],
        True,
        1,
        2,
    ),
    _task(
        4504,
        "Critical: webhook delivery failures for Linear events",
        "bob",
        "in_progress",
        "urgent",
        ["integrations", "bug"],
        True,
        2,
        4,
    ),
    _task(
        4505,
        "Fix SSO login redirect loop for enterprise customers",
        "alice",
        "todo",
        "urgent",
        ["auth", "enterprise"],
        True,
        3,
        1,
    ),
    # ── High (12) ──────────────────────────────────────────────────────
    _task(
        4506,
        "Implement batch entity resolution for large orgs",
        "alice",
        "in_progress",
        "high",
        ["graph", "performance"],
        True,
        5,
        10,
    ),
    _task(
        4507,
        "Add GitHub PR review comment ingestion",
        "bob",
        "in_review",
        "high",
        ["integrations", "github"],
        True,
        4,
        8,
    ),
    _task(
        4508,
        "Build urgency score explanation tooltip UI",
        "carol",
        "in_progress",
        "high",
        ["frontend", "ux"],
        True,
        7,
        6,
    ),
    _task(
        4509,
        "Implement Slack thread context extraction",
        "david",
        "in_progress",
        "high",
        ["integrations", "slack"],
        True,
        6,
        12,
    ),
    _task(
        4510,
        "Add Redis cache warming on app startup",
        "igor",
        "in_review",
        "high",
        ["infra", "performance"],
        False,
        5,
        9,
    ),
    _task(
        4511,
        "Design briefing card component for mobile",
        "hannah",
        "in_review",
        "high",
        ["design", "mobile"],
        True,
        8,
        7,
    ),
    _task(
        4512,
        "Implement goal progress auto-calculation from tasks",
        "eve",
        "in_progress",
        "high",
        ["goals", "inference"],
        True,
        10,
        14,
    ),
    _task(
        4513,
        "Add WebSocket support for live urgency updates",
        "kevin",
        "todo",
        "high",
        ["frontend", "infra"],
        False,
        12,
        5,
    ),
    _task(
        4514,
        "Build org-level analytics dashboard",
        "carol",
        "in_progress",
        "high",
        ["frontend", "analytics"],
        True,
        9,
        11,
    ),
    _task(
        4515,
        "Implement cross-source person matching heuristics",
        "alice",
        "in_review",
        "high",
        ["graph", "resolution"],
        False,
        7,
        15,
    ),
    _task(
        4516,
        "Add Alembic migration for audit log table",
        "julia",
        "done",
        "high",
        ["infra", "database"],
        False,
        None,
        18,
    ),
    _task(
        4517,
        "Implement daily briefing email template",
        "lisa",
        "done",
        "high",
        ["briefings", "email"],
        False,
        None,
        20,
    ),
    # ── Medium (18) ────────────────────────────────────────────────────
    _task(4518, "Add pagination to entity list API", "bob", "done", "medium", ["api"], False, None, 21),
    _task(
        4519,
        "Implement edge weight decay over time",
        "alice",
        "in_progress",
        "medium",
        ["graph", "inference"],
        False,
        14,
        16,
    ),
    _task(
        4520,
        "Add Linear label sync to entity properties",
        "david",
        "in_review",
        "medium",
        ["integrations", "linear"],
        False,
        10,
        13,
    ),
    _task(
        4521,
        "Build settings page for notification preferences",
        "carol",
        "todo",
        "medium",
        ["frontend", "settings"],
        False,
        18,
        8,
    ),
    _task(
        4522,
        "Implement org member invitation flow",
        "bob",
        "todo",
        "medium",
        ["auth", "api"],
        False,
        15,
        6,
    ),
    _task(
        4523,
        "Add error boundary to React app shell",
        "kevin",
        "done",
        "medium",
        ["frontend", "reliability"],
        False,
        None,
        22,
    ),
    _task(
        4524,
        "Write integration tests for Linear connector",
        "bob",
        "in_progress",
        "medium",
        ["testing", "integrations"],
        False,
        12,
        10,
    ),
    _task(
        4525,
        "Implement blocking chain visualization in graph view",
        "carol",
        "todo",
        "medium",
        ["frontend", "graph"],
        False,
        20,
        4,
    ),
    _task(
        4526,
        "Add Sentry error tracking to backend",
        "igor",
        "done",
        "medium",
        ["infra", "observability"],
        False,
        None,
        25,
    ),
    _task(
        4527,
        "Build PR diff summary display component",
        "lisa",
        "in_progress",
        "medium",
        ["frontend", "claude"],
        False,
        11,
        9,
    ),
    _task(
        4528,
        "Implement webhook retry with exponential backoff",
        "julia",
        "in_review",
        "medium",
        ["api", "reliability"],
        False,
        8,
        14,
    ),
    _task(
        4529,
        "Add team-level urgency aggregation view",
        "eve",
        "todo",
        "medium",
        ["inference", "views"],
        False,
        16,
        7,
    ),
    _task(
        4530,
        "Implement dark mode for dashboard",
        "hannah",
        "in_progress",
        "medium",
        ["design", "frontend"],
        False,
        21,
        12,
    ),
    _task(
        4531,
        "Add CSV export for entity data",
        "david",
        "todo",
        "medium",
        ["api", "export"],
        False,
        22,
        5,
    ),
    _task(
        4532,
        "Build goal hierarchy tree component",
        "kevin",
        "in_progress",
        "medium",
        ["frontend", "goals"],
        False,
        15,
        11,
    ),
    _task(
        4533,
        "Implement smart notification batching",
        "lisa",
        "in_review",
        "medium",
        ["briefings", "ux"],
        False,
        13,
        16,
    ),
    _task(
        4534,
        "Add GitHub Actions workflow status ingestion",
        "bob",
        "done",
        "medium",
        ["integrations", "github"],
        False,
        None,
        24,
    ),
    _task(
        4535,
        "Implement search across all entity types",
        "alice",
        "done",
        "medium",
        ["api", "search"],
        False,
        None,
        19,
    ),
    # ── Low (15) ───────────────────────────────────────────────────────
    _task(
        4536,
        "Add loading skeletons to dashboard cards",
        "carol",
        "done",
        "low",
        ["frontend", "ux"],
        False,
        None,
        28,
    ),
    _task(
        4537,
        "Write API documentation for webhook endpoints",
        "bob",
        "todo",
        "low",
        ["docs", "api"],
        False,
        30,
        10,
    ),
    _task(
        4538,
        "Implement keyboard shortcuts for navigation",
        "kevin",
        "todo",
        "low",
        ["frontend", "ux"],
        False,
        35,
        7,
    ),
    _task(
        4539,
        "Add Slack bot /numen command for quick status",
        "david",
        "todo",
        "low",
        ["integrations", "slack"],
        False,
        25,
        9,
    ),
    _task(
        4540,
        "Optimize entity list query with covering index",
        "julia",
        "done",
        "low",
        ["infra", "performance"],
        False,
        None,
        30,
    ),
    _task(
        4541,
        "Add avatar upload support for org members",
        "lisa",
        "todo",
        "low",
        ["frontend", "api"],
        False,
        28,
        6,
    ),
    _task(
        4542,
        "Implement entity archive and soft delete",
        "alice",
        "done",
        "low",
        ["api", "graph"],
        False,
        None,
        26,
    ),
    _task(
        4543,
        "Build onboarding checklist component",
        "hannah",
        "in_progress",
        "low",
        ["design", "onboarding"],
        False,
        20,
        15,
    ),
    _task(
        4544,
        "Add Prometheus metrics endpoint",
        "igor",
        "done",
        "low",
        ["infra", "observability"],
        False,
        None,
        32,
    ),
    _task(
        4545,
        "Write runbook for database failover",
        "julia",
        "todo",
        "low",
        ["docs", "infra"],
        False,
        40,
        8,
    ),
    _task(
        4546,
        "Implement email digest frequency settings",
        "lisa",
        "done",
        "low",
        ["briefings", "settings"],
        False,
        None,
        27,
    ),
    _task(
        4547,
        "Add breadcrumb navigation to entity detail",
        "carol",
        "done",
        "low",
        ["frontend", "ux"],
        False,
        None,
        23,
    ),
    _task(
        4548,
        "Implement rate limiting per API key",
        "igor",
        "in_review",
        "low",
        ["api", "security"],
        False,
        18,
        14,
    ),
    _task(
        4549,
        "Add Figma design token sync exploration",
        "hannah",
        "todo",
        "low",
        ["design", "integrations"],
        False,
        45,
        5,
    ),
    _task(
        4550,
        "Write unit tests for urgency scoring formula",
        "eve",
        "done",
        "low",
        ["testing", "inference"],
        False,
        None,
        20,
    ),
    # ── Additional tasks for volume ───────────────────────────────────
    _task(
        4551,
        "Refactor connector base class for plugin architecture",
        "alice",
        "in_progress",
        "medium",
        ["architecture", "connectors"],
        True,
        10,
        6,
    ),
    _task(
        4552,
        "Add retry logic to Anthropic API calls",
        "bob",
        "done",
        "medium",
        ["claude", "reliability"],
        False,
        None,
        17,
    ),
    _task(
        4553,
        "Implement project burndown chart",
        "carol",
        "todo",
        "medium",
        ["frontend", "analytics"],
        False,
        20,
        4,
    ),
    _task(
        4554,
        "Build decision log timeline view",
        "david",
        "in_progress",
        "low",
        ["frontend", "decisions"],
        False,
        25,
        8,
    ),
    _task(
        4555,
        "Add database connection health check endpoint",
        "julia",
        "done",
        "low",
        ["infra", "health"],
        False,
        None,
        22,
    ),
    _task(
        4556,
        "Implement entity merge UI for duplicate resolution",
        "kevin",
        "todo",
        "high",
        ["frontend", "graph"],
        False,
        14,
        3,
    ),
    _task(
        4557,
        "Add Slack channel mapping to team entities",
        "david",
        "in_review",
        "medium",
        ["integrations", "slack"],
        False,
        9,
        11,
    ),
    _task(
        4558,
        "Build mobile-responsive briefing view",
        "lisa",
        "in_progress",
        "high",
        ["frontend", "mobile"],
        True,
        8,
        7,
    ),
    _task(
        4559,
        "Implement async task queue with Redis",
        "igor",
        "in_review",
        "medium",
        ["infra", "architecture"],
        False,
        6,
        13,
    ),
    _task(
        4560,
        "Add end-to-end tests for OAuth flow",
        "alice",
        "todo",
        "medium",
        ["testing", "auth"],
        False,
        15,
        5,
    ),
]

TASK_IDS: dict[str, uuid.UUID] = {t["key"]: _id(f"task-{t['key']}") for t in TASKS}


# ── Pull Requests (GitHub source) ────────────────────────────────────────


def _pr(
    num: int,
    title: str,
    author: str,
    state: str,
    branch: str,
    task_key: str | None = None,
    additions: int = 100,
    deletions: int = 30,
    created_days_ago: int = 5,
    reviewers: list[str] | None = None,
) -> dict:
    return {
        "key": f"PR-{num}",
        "num": num,
        "title": title,
        "author": author,
        "state": state,
        "branch": branch,
        "task_key": task_key,
        "additions": additions,
        "deletions": deletions,
        "sha": f"abc{num:04d}def1234567890abcdef1234567890ab",
        "created_at": _days_ago(created_days_ago).isoformat(),
        "reviewers": reviewers or [],
    }


PRS = [
    # Open (5)
    _pr(
        301,
        "feat: implement OAuth PKCE for Safari",
        "alice",
        "open",
        "feat/oauth-pkce",
        "ENG-4501",
        342,
        28,
        2,
        ["bob", "igor"],
    ),
    _pr(
        302,
        "fix: rate limiter token bucket overflow",
        "igor",
        "open",
        "fix/rate-limiter",
        "ENG-4502",
        89,
        12,
        1,
        ["alice", "julia"],
    ),
    _pr(
        303,
        "feat: batch entity resolution",
        "alice",
        "open",
        "feat/batch-resolution",
        "ENG-4506",
        567,
        43,
        4,
        ["bob"],
    ),
    _pr(
        304,
        "feat: Slack thread context extraction",
        "david",
        "open",
        "feat/slack-threads",
        "ENG-4509",
        234,
        18,
        3,
        ["carol"],
    ),
    _pr(
        305,
        "feat: WebSocket urgency updates",
        "kevin",
        "open",
        "feat/ws-urgency",
        "ENG-4513",
        445,
        56,
        2,
        ["igor"],
    ),
    # Draft (3)
    _pr(
        306,
        "wip: cross-source person matching",
        "alice",
        "draft",
        "feat/person-matching",
        "ENG-4515",
        678,
        89,
        6,
        [],
    ),
    _pr(
        307,
        "wip: dark mode theme tokens",
        "hannah",
        "draft",
        "feat/dark-mode",
        "ENG-4530",
        156,
        23,
        5,
        [],
    ),
    _pr(
        308,
        "wip: connector plugin architecture",
        "alice",
        "draft",
        "refactor/connector-plugins",
        "ENG-4551",
        890,
        234,
        3,
        [],
    ),
    # Merged (10)
    _pr(
        281,
        "feat: add pagination to entity list",
        "bob",
        "merged",
        "feat/entity-pagination",
        "ENG-4518",
        198,
        34,
        22,
        ["alice"],
    ),
    _pr(
        282,
        "feat: audit log table migration",
        "julia",
        "merged",
        "feat/audit-log-migration",
        "ENG-4516",
        87,
        5,
        19,
        ["igor"],
    ),
    _pr(
        283,
        "feat: daily briefing email template",
        "lisa",
        "merged",
        "feat/briefing-email",
        "ENG-4517",
        312,
        45,
        21,
        ["eve", "hannah"],
    ),
    _pr(
        284,
        "fix: add error boundary to app shell",
        "kevin",
        "merged",
        "fix/error-boundary",
        "ENG-4523",
        56,
        8,
        23,
        ["carol"],
    ),
    _pr(
        285,
        "feat: Sentry error tracking setup",
        "igor",
        "merged",
        "feat/sentry-setup",
        "ENG-4526",
        134,
        12,
        26,
        ["julia"],
    ),
    _pr(
        286,
        "feat: entity search across types",
        "alice",
        "merged",
        "feat/entity-search",
        "ENG-4535",
        267,
        78,
        20,
        ["bob"],
    ),
    _pr(
        287,
        "feat: loading skeletons for dashboard",
        "carol",
        "merged",
        "feat/loading-skeletons",
        "ENG-4536",
        145,
        22,
        29,
        ["hannah"],
    ),
    _pr(
        288,
        "fix: entity list covering index",
        "julia",
        "merged",
        "fix/covering-index",
        "ENG-4540",
        23,
        4,
        31,
        ["igor"],
    ),
    _pr(
        289,
        "feat: GitHub Actions status ingestion",
        "bob",
        "merged",
        "feat/gh-actions-ingestion",
        "ENG-4534",
        203,
        38,
        25,
        ["alice"],
    ),
    _pr(
        290,
        "feat: Prometheus metrics endpoint",
        "igor",
        "merged",
        "feat/prometheus-metrics",
        "ENG-4544",
        178,
        15,
        33,
        ["julia"],
    ),
    # Closed without merge (2)
    _pr(
        291,
        "feat: experimental GraphQL API",
        "bob",
        "closed",
        "feat/graphql-api",
        None,
        890,
        120,
        35,
        ["alice"],
    ),
    _pr(
        292,
        "refactor: switch from REST to tRPC",
        "carol",
        "closed",
        "refactor/trpc-migration",
        None,
        1200,
        900,
        30,
        ["david"],
    ),
]

PR_IDS: dict[str, uuid.UUID] = {p["key"]: _id(f"pr-{p['key']}") for p in PRS}


# ── Deploys (GitHub source) ─────────────────────────────────────────────


def _deploy(
    num: int,
    env: str,
    status: str,
    pr_key: str,
    created_days_ago: int = 1,
    duration_seconds: int = 180,
) -> dict:
    return {
        "key": f"deploy-{num}",
        "num": num,
        "environment": env,
        "status": status,
        "pr_key": pr_key,
        "sha": next(p["sha"] for p in PRS if p["key"] == pr_key),
        "duration_seconds": duration_seconds,
        "created_at": _days_ago(created_days_ago).isoformat(),
    }


DEPLOYS = [
    # Production - success (8)
    _deploy(1, "production", "success", "PR-281", 21, 195),
    _deploy(2, "production", "success", "PR-282", 18, 142),
    _deploy(3, "production", "success", "PR-283", 20, 210),
    _deploy(4, "production", "success", "PR-284", 22, 98),
    _deploy(5, "production", "success", "PR-285", 25, 167),
    _deploy(6, "production", "success", "PR-286", 19, 178),
    _deploy(7, "production", "success", "PR-289", 24, 203),
    _deploy(8, "production", "success", "PR-290", 32, 145),
    # Staging - success (6)
    _deploy(9, "staging", "success", "PR-287", 28, 120),
    _deploy(10, "staging", "success", "PR-288", 30, 88),
    _deploy(11, "staging", "success", "PR-301", 1, 156),
    _deploy(12, "staging", "success", "PR-302", 0, 134),
    _deploy(13, "staging", "success", "PR-303", 3, 189),
    _deploy(14, "staging", "success", "PR-304", 2, 145),
    # Failures (2)
    _deploy(15, "production", "failure", "PR-291", 34, 45),
    _deploy(16, "staging", "failure", "PR-292", 29, 67),
    # Pending (2)
    _deploy(17, "staging", "pending", "PR-305", 0, 0),
    _deploy(18, "staging", "pending", "PR-306", 0, 0),
]

DEPLOY_IDS: dict[str, uuid.UUID] = {d["key"]: _id(f"deploy-{d['key']}") for d in DEPLOYS}


# ── Goals ────────────────────────────────────────────────────────────────


def _goal(
    key: str,
    title: str,
    level: str,
    owner: str,
    target_value: float,
    current_value: float,
    parent_key: str | None = None,
    key_results: list[dict] | None = None,
    start_days_ago: int = 90,
    end_days_from_now: int = 0,
) -> dict:
    return {
        "key": key,
        "title": title,
        "level": level,
        "owner": owner,
        "target_value": target_value,
        "current_value": current_value,
        "parent_key": parent_key,
        "key_results": key_results or [],
        "time_bound_start": _days_ago(start_days_ago).isoformat(),
        "time_bound_end": _days_from_now(end_days_from_now).isoformat(),
    }


GOALS = [
    # Company-level (3)
    _goal(
        "goal-retention",
        "Improve user retention by 15%",
        "company",
        "grace",
        15.0,
        8.2,
        None,
        [
            {"title": "Reduce churn rate from 5% to 3%", "target": 3.0, "current": 3.8},
            {"title": "Increase DAU/MAU ratio to 45%", "target": 45.0, "current": 38.0},
            {"title": "Improve onboarding completion to 80%", "target": 80.0, "current": 65.0},
        ],
        90,
        0,
    ),
    _goal(
        "goal-enterprise",
        "Launch enterprise tier by Q2",
        "company",
        "grace",
        100.0,
        45.0,
        None,
        [
            {"title": "Ship SSO and SCIM provisioning", "target": 100.0, "current": 60.0},
            {"title": "Complete SOC 2 Type II audit", "target": 100.0, "current": 30.0},
            {"title": "Sign 3 enterprise design partners", "target": 3.0, "current": 1.0},
        ],
        90,
        60,
    ),
    _goal(
        "goal-latency",
        "Reduce P95 API latency by 40%",
        "company",
        "grace",
        40.0,
        22.0,
        None,
        [
            {"title": "Optimize hot-path DB queries", "target": 100.0, "current": 55.0},
            {"title": "Add Redis caching layer", "target": 100.0, "current": 70.0},
            {"title": "Implement connection pooling tuning", "target": 100.0, "current": 40.0},
        ],
        90,
        0,
    ),
    # Team-level (5)
    _goal(
        "goal-platform-reliability",
        "Achieve 99.9% platform uptime",
        "team",
        "frank",
        99.9,
        99.4,
        "goal-latency",
        [
            {"title": "Deploy redundant load balancers", "target": 100.0, "current": 80.0},
            {
                "title": "Implement circuit breakers for external APIs",
                "target": 100.0,
                "current": 50.0,
            },
        ],
        90,
        0,
    ),
    _goal(
        "goal-growth-activation",
        "Increase activation rate to 60%",
        "team",
        "eve",
        60.0,
        42.0,
        "goal-retention",
        [
            {"title": "Redesign onboarding wizard", "target": 100.0, "current": 75.0},
            {"title": "Add contextual help tooltips", "target": 100.0, "current": 40.0},
        ],
        90,
        0,
    ),
    _goal(
        "goal-integrations",
        "Ship 3 new connector integrations",
        "team",
        "eve",
        3.0,
        1.0,
        "goal-enterprise",
        [
            {"title": "Notion connector", "target": 100.0, "current": 20.0},
            {"title": "Figma connector", "target": 100.0, "current": 0.0},
            {"title": "Datadog connector", "target": 100.0, "current": 0.0},
        ],
        60,
        30,
    ),
    _goal(
        "goal-mobile-experience",
        "Launch mobile-first briefing experience",
        "team",
        "eve",
        100.0,
        35.0,
        "goal-retention",
        [
            {"title": "Responsive briefing cards", "target": 100.0, "current": 50.0},
            {"title": "Push notification delivery", "target": 100.0, "current": 10.0},
        ],
        60,
        30,
    ),
    _goal(
        "goal-infra-cost",
        "Reduce infrastructure cost by 20%",
        "team",
        "frank",
        20.0,
        8.0,
        "goal-latency",
        [
            {"title": "Right-size database instances", "target": 100.0, "current": 60.0},
            {"title": "Implement query result caching", "target": 100.0, "current": 30.0},
        ],
        60,
        0,
    ),
    # Individual-level (6)
    _goal(
        "goal-alice-resolution",
        "Ship entity resolution v2",
        "individual",
        "alice",
        100.0,
        55.0,
        "goal-platform-reliability",
    ),
    _goal(
        "goal-bob-connectors",
        "Complete GitHub connector hardening",
        "individual",
        "bob",
        100.0,
        70.0,
        "goal-integrations",
    ),
    _goal(
        "goal-carol-dashboard",
        "Deliver analytics dashboard MVP",
        "individual",
        "carol",
        100.0,
        40.0,
        "goal-growth-activation",
    ),
    _goal(
        "goal-igor-infra",
        "Migrate to connection pooler and optimize",
        "individual",
        "igor",
        100.0,
        65.0,
        "goal-infra-cost",
    ),
    _goal(
        "goal-kevin-mobile",
        "Build mobile-responsive frontend shell",
        "individual",
        "kevin",
        100.0,
        30.0,
        "goal-mobile-experience",
    ),
    _goal(
        "goal-lisa-briefings",
        "Implement multi-channel briefing delivery",
        "individual",
        "lisa",
        100.0,
        50.0,
        "goal-mobile-experience",
    ),
]

GOAL_IDS: dict[str, uuid.UUID] = {g["key"]: _id(f"goal-{g['key']}") for g in GOALS}


# ── Projects ─────────────────────────────────────────────────────────────


def _project(
    key: str,
    name: str,
    status: str,
    owner: str,
    description: str,
    goal_keys: list[str],
    task_keys: list[str],
    start_days_ago: int = 30,
    end_days_from_now: int = 30,
) -> dict:
    return {
        "key": key,
        "name": name,
        "status": status,
        "owner": owner,
        "description": description,
        "goal_keys": goal_keys,
        "task_keys": task_keys,
        "start_date": _days_ago(start_days_ago).strftime("%Y-%m-%d"),
        "end_date": _days_from_now(end_days_from_now).strftime("%Y-%m-%d"),
    }


PROJECTS = [
    _project(
        "proj-auth-overhaul",
        "Auth System Overhaul",
        "active",
        "alice",
        "Modernize authentication with PKCE, SSO, and secure session management",
        ["goal-enterprise", "goal-platform-reliability"],
        ["ENG-4501", "ENG-4505", "ENG-4522", "ENG-4560"],
        45,
        15,
    ),
    _project(
        "proj-connector-v2",
        "Connector Framework v2",
        "active",
        "bob",
        "Rebuild connector architecture for extensibility and reliability",
        ["goal-integrations", "goal-bob-connectors"],
        [
            "ENG-4504",
            "ENG-4507",
            "ENG-4509",
            "ENG-4520",
            "ENG-4524",
            "ENG-4534",
            "ENG-4551",
            "ENG-4557",
        ],
        30,
        30,
    ),
    _project(
        "proj-dashboard-v2",
        "Dashboard Redesign",
        "active",
        "carol",
        "New analytics-first dashboard with urgency feeds and team views",
        ["goal-growth-activation", "goal-carol-dashboard"],
        [
            "ENG-4508",
            "ENG-4514",
            "ENG-4521",
            "ENG-4525",
            "ENG-4530",
            "ENG-4532",
            "ENG-4536",
            "ENG-4547",
        ],
        35,
        25,
    ),
    _project(
        "proj-infra-perf",
        "Infrastructure Performance",
        "paused",
        "igor",
        "Database optimization, caching, and observability improvements",
        ["goal-latency", "goal-infra-cost", "goal-igor-infra"],
        [
            "ENG-4502",
            "ENG-4503",
            "ENG-4510",
            "ENG-4526",
            "ENG-4540",
            "ENG-4544",
            "ENG-4548",
            "ENG-4559",
        ],
        60,
        0,
    ),
    _project(
        "proj-mobile-briefings",
        "Mobile Briefing Experience",
        "active",
        "lisa",
        "Mobile-first briefing delivery with push notifications",
        ["goal-mobile-experience", "goal-lisa-briefings", "goal-kevin-mobile"],
        ["ENG-4511", "ENG-4517", "ENG-4527", "ENG-4533", "ENG-4541", "ENG-4546", "ENG-4558"],
        25,
        35,
    ),
    _project(
        "proj-entity-resolution",
        "Entity Resolution Engine",
        "completed",
        "alice",
        "Cross-source entity matching and merge pipeline",
        ["goal-alice-resolution"],
        ["ENG-4506", "ENG-4515", "ENG-4535", "ENG-4542"],
        90,
        -10,
    ),
    _project(
        "proj-onboarding",
        "User Onboarding Revamp",
        "planning",
        "hannah",
        "Redesigned first-run experience with guided setup",
        ["goal-growth-activation"],
        ["ENG-4543", "ENG-4549"],
        10,
        50,
    ),
]

PROJECT_IDS: dict[str, uuid.UUID] = {p["key"]: _id(f"project-{p['key']}") for p in PROJECTS}


# ── Decisions ────────────────────────────────────────────────────────────


def _decision(
    key: str,
    dtype: str,
    title: str,
    actor: str,
    trigger: str,
    outcome: str,
    created_days_ago: int = 3,
) -> dict:
    return {
        "key": key,
        "type": dtype,
        "title": title,
        "actor": actor,
        "trigger": trigger,
        "outcome": outcome,
        "created_at": _days_ago(created_days_ago).isoformat(),
    }


DECISIONS = [
    _decision(
        "dec-01",
        "bug_filed",
        "Connection pool exhaustion identified",
        "julia",
        "Datadog alert: connection count spike",
        "Filed ENG-4503, assigned to Julia with urgent priority",
        2,
    ),
    _decision(
        "dec-02",
        "pr_reviewed",
        "Rate limiter PR needs rework",
        "alice",
        "PR-302 review: race condition in token bucket",
        "Requested changes on PR-302, added concurrency test requirement",
        1,
    ),
    _decision(
        "dec-03",
        "spec_written",
        "Entity resolution v2 specification",
        "eve",
        "Multiple orgs reporting duplicate entities",
        "Wrote spec for cross-source matching heuristics, assigned to Alice",
        8,
    ),
    _decision(
        "dec-04",
        "goal_updated",
        "Retention goal progress update",
        "grace",
        "Monthly metrics review - churn dropping faster than expected",
        "Updated current value from 6.5 to 8.2, on track for target",
        5,
    ),
    _decision(
        "dec-05",
        "item_dismissed",
        "GraphQL API exploration deprioritized",
        "frank",
        "Team capacity constraints and REST API meeting needs",
        "Closed PR-291, moved ENG backlog items to icebox",
        14,
    ),
    _decision(
        "dec-06",
        "capacity_allocated",
        "Mobile team expanded for Q2",
        "frank",
        "Mobile briefing experience behind schedule",
        "Moved Kevin from Growth to Mobile team, added Lisa as second mobile eng",
        10,
    ),
    _decision(
        "dec-07",
        "bug_filed",
        "Linear webhook delivery failures",
        "bob",
        "Monitoring alert: 15% webhook drop rate",
        "Filed ENG-4504 as urgent, root cause: payload size exceeds limit",
        4,
    ),
    _decision(
        "dec-08",
        "pr_reviewed",
        "Briefing email template approved",
        "eve",
        "PR-283 review: template matches design spec",
        "Approved and merged PR-283, scheduled staging deployment",
        20,
    ),
    _decision(
        "dec-09",
        "spec_written",
        "WebSocket architecture decision",
        "igor",
        "Real-time urgency updates requirement from PM",
        "ADR: use Socket.IO with Redis pub/sub for horizontal scaling",
        7,
    ),
    _decision(
        "dec-10",
        "goal_updated",
        "Enterprise tier timeline adjusted",
        "grace",
        "SOC 2 audit taking longer than planned",
        "Extended deadline by 30 days, adjusted Q2 launch to mid-Q2",
        12,
    ),
    _decision(
        "dec-11",
        "bug_filed",
        "Safari OAuth redirect failure",
        "alice",
        "Customer report: SSO fails on Safari 17+",
        "Filed ENG-4501, root cause: missing PKCE code_verifier in Safari",
        3,
    ),
    _decision(
        "dec-12",
        "capacity_allocated",
        "Paused infra-perf project",
        "frank",
        "Urgent auth and reliability work taking priority",
        "Paused infra-perf, redirected Igor to rate limiter fix",
        6,
    ),
    _decision(
        "dec-13",
        "pr_reviewed",
        "Entity search implementation approved",
        "bob",
        "PR-286 review: clean implementation, good test coverage",
        "Approved and merged, deployed to production",
        19,
    ),
    _decision(
        "dec-14",
        "item_dismissed",
        "tRPC migration proposal rejected",
        "frank",
        "Team discussion: switching costs outweigh benefits at current scale",
        "Closed PR-292, keeping REST + OpenAPI approach",
        28,
    ),
    _decision(
        "dec-15",
        "spec_written",
        "Notification batching algorithm",
        "eve",
        "Users complaining about too many email notifications",
        "Spec for smart batching: group by urgency tier, max 3 emails/day",
        9,
    ),
    _decision(
        "dec-16",
        "goal_updated",
        "Infrastructure cost reduction progress",
        "igor",
        "Completed database instance right-sizing",
        "Updated goal from 5% to 8% cost reduction achieved",
        4,
    ),
    _decision(
        "dec-17",
        "bug_filed",
        "SSO redirect loop for enterprise",
        "alice",
        "Enterprise customer escalation via support",
        "Filed ENG-4505, linked to auth overhaul project",
        1,
    ),
    _decision(
        "dec-18",
        "pr_reviewed",
        "Connection pool fix needs load testing",
        "igor",
        "PR for ENG-4503: fix looks correct but untested under load",
        "Requested load test results before merge approval",
        2,
    ),
    _decision(
        "dec-19",
        "capacity_allocated",
        "Hannah allocated to onboarding project",
        "frank",
        "Onboarding completion rate below target",
        "Hannah to lead design for onboarding revamp, starting next sprint",
        7,
    ),
    _decision(
        "dec-20",
        "spec_written",
        "Mobile push notification architecture",
        "kevin",
        "Briefing team needs push delivery channel",
        "Spec for FCM/APNs integration via background worker",
        6,
    ),
    _decision(
        "dec-21",
        "goal_updated",
        "Mobile experience sprint progress",
        "eve",
        "Sprint retrospective - responsive cards shipping",
        "Updated mobile goal from 25% to 35%, on track for Q2",
        3,
    ),
    _decision(
        "dec-22",
        "bug_filed",
        "Webhook retry logic missing backoff",
        "julia",
        "Monitoring: webhook retries causing thundering herd",
        "Filed ENG-4528, added exponential backoff requirement",
        14,
    ),
]

DECISION_IDS: dict[str, uuid.UUID] = {d["key"]: _id(f"decision-{d['key']}") for d in DECISIONS}


# ── Edges ────────────────────────────────────────────────────────────────


def _build_edges() -> list[dict]:
    """Build all edges from the fixture data above."""
    edges: list[dict] = []

    def _edge(
        from_key: str,
        from_type: str,
        to_key: str,
        to_type: str,
        edge_type: str,
        weight: float = 1.0,
        confidence: float = 1.0,
    ) -> None:
        id_maps = {
            "person": PERSON_IDS,
            "task": TASK_IDS,
            "pr": PR_IDS,
            "deploy": DEPLOY_IDS,
            "goal": GOAL_IDS,
            "project": PROJECT_IDS,
            "decision": DECISION_IDS,
        }
        edges.append(
            {
                "key": f"{edge_type}-{from_key}-{to_key}",
                "from_entity_id": id_maps[from_type][from_key],
                "to_entity_id": id_maps[to_type][to_key],
                "type": edge_type,
                "weight": weight,
                "confidence": confidence,
            }
        )

    # ── OWNS / ASSIGNED_TO: person -> task ────────────────────────────
    for t in TASKS:
        assignee = t["assignee"]
        _edge(assignee, "person", t["key"], "task", "owns")
        _edge(assignee, "person", t["key"], "task", "assigned_to")

    # ── AUTHORED: person -> PR ────────────────────────────────────────
    for p in PRS:
        _edge(p["author"], "person", p["key"], "pr", "authored")

    # ── REVIEWS: person -> PR ─────────────────────────────────────────
    for p in PRS:
        for reviewer in p.get("reviewers", []):
            _edge(reviewer, "person", p["key"], "pr", "reviews", weight=0.8)

    # ── SHIPS_TO: PR -> deploy ────────────────────────────────────────
    for d in DEPLOYS:
        _edge(d["pr_key"], "pr", d["key"], "deploy", "ships_to")

    # ── CONTAINS: project -> task ─────────────────────────────────────
    for proj in PROJECTS:
        for tk in proj["task_keys"]:
            if tk in TASK_IDS:
                _edge(proj["key"], "project", tk, "task", "contains")

    # ── TAGGED_TO: project -> goal ────────────────────────────────────
    for proj in PROJECTS:
        for gk in proj["goal_keys"]:
            _edge(proj["key"], "project", gk, "goal", "tagged_to")

    # ── TAGGED_TO: task -> goal (some tasks directly linked) ──────────
    task_goal_links = [
        ("ENG-4501", "goal-enterprise"),
        ("ENG-4505", "goal-enterprise"),
        ("ENG-4506", "goal-alice-resolution"),
        ("ENG-4507", "goal-bob-connectors"),
        ("ENG-4508", "goal-carol-dashboard"),
        ("ENG-4509", "goal-integrations"),
        ("ENG-4510", "goal-igor-infra"),
        ("ENG-4512", "goal-retention"),
        ("ENG-4514", "goal-carol-dashboard"),
        ("ENG-4515", "goal-alice-resolution"),
        ("ENG-4517", "goal-lisa-briefings"),
        ("ENG-4527", "goal-lisa-briefings"),
        ("ENG-4532", "goal-carol-dashboard"),
        ("ENG-4533", "goal-lisa-briefings"),
        ("ENG-4551", "goal-integrations"),
        ("ENG-4558", "goal-kevin-mobile"),
    ]
    for tk, gk in task_goal_links:
        _edge(tk, "task", gk, "goal", "tagged_to", weight=0.9)

    # ── PARENT_OF: goal -> goal ───────────────────────────────────────
    for g in GOALS:
        if g["parent_key"]:
            _edge(g["parent_key"], "goal", g["key"], "goal", "parent_of")

    # ── BLOCKS: task -> task ──────────────────────────────────────────
    blocking_pairs = [
        ("ENG-4501", "ENG-4505"),  # OAuth fix blocks SSO fix
        ("ENG-4502", "ENG-4510"),  # Rate limiter blocks cache warming
        ("ENG-4503", "ENG-4506"),  # DB pool fix blocks batch resolution
        ("ENG-4506", "ENG-4515"),  # Batch resolution blocks person matching
        ("ENG-4509", "ENG-4557"),  # Slack threads blocks channel mapping
        ("ENG-4511", "ENG-4558"),  # Briefing card design blocks mobile briefing
        ("ENG-4519", "ENG-4512"),  # Edge weight decay blocks goal auto-calc
        ("ENG-4559", "ENG-4513"),  # Async queue blocks WebSocket updates
    ]
    for blocker, blocked in blocking_pairs:
        _edge(blocker, "task", blocked, "task", "blocks", weight=1.0, confidence=1.0)

    # ── DEPENDS_ON: task -> task ──────────────────────────────────────
    dependency_pairs = [
        ("ENG-4508", "ENG-4512"),  # Urgency tooltip depends on goal progress
        ("ENG-4525", "ENG-4519"),  # Blocking viz depends on edge weight
        ("ENG-4527", "ENG-4552"),  # PR diff display depends on Anthropic retry
        ("ENG-4533", "ENG-4546"),  # Smart batching depends on frequency settings
        ("ENG-4541", "ENG-4522"),  # Avatar upload depends on member flow
        ("ENG-4543", "ENG-4521"),  # Onboarding depends on settings page
    ]
    for dependent, dependency in dependency_pairs:
        _edge(dependent, "task", dependency, "task", "depends_on", weight=0.8, confidence=0.9)

    # ── REPORTS_TO: person -> person (org chart) ──────────────────────
    reports_to = [
        ("alice", "frank"),  # Alice reports to Frank (EM Platform)
        ("bob", "frank"),  # Bob reports to Frank
        ("carol", "frank"),  # Carol reports to Frank (Growth, but same EM)
        ("david", "frank"),  # David reports to Frank
        ("eve", "grace"),  # Eve (PM) reports to Grace (CTO)
        ("frank", "grace"),  # Frank (EM) reports to Grace
        ("hannah", "grace"),  # Hannah (Designer) reports to Grace
        ("igor", "frank"),  # Igor reports to Frank
        ("julia", "frank"),  # Julia reports to Frank
        ("kevin", "frank"),  # Kevin reports to Frank
        ("lisa", "frank"),  # Lisa reports to Frank
    ]
    for report, manager in reports_to:
        _edge(report, "person", manager, "person", "reports_to", weight=1.0, confidence=1.0)

    # ── MENTIONED_IN: task/PR -> slack channel (simulated) ────────────
    # We simulate Slack mention edges pointing to a synthetic "channel" entity
    # For now, these are task-to-task self-references that signal Slack activity
    # These are noted as having recent Slack mentions in properties rather
    # than as edge targets, since we don't have slack channel entities.
    # The inference layer picks up mention_count from entity properties.

    return edges


EDGES = _build_edges()
EDGE_IDS: dict[str, uuid.UUID] = {e["key"]: _id(f"edge-{e['key']}") for e in EDGES}


# ── Org Members ──────────────────────────────────────────────────────────

# The 8 key members who have org accounts (the ones with defined roles
# in the application: engineers, PM, EM, CTO, designer).
ORG_MEMBERS = [
    {"key": "alice", "role": "engineer"},
    {"key": "bob", "role": "engineer"},
    {"key": "carol", "role": "engineer"},
    {"key": "david", "role": "engineer"},
    {"key": "eve", "role": "pm"},
    {"key": "frank", "role": "vp_eng"},
    {"key": "grace", "role": "cto"},
    {"key": "hannah", "role": "designer"},
]

ORG_MEMBER_IDS: dict[str, uuid.UUID] = {m["key"]: _id(f"org-member-{m['key']}") for m in ORG_MEMBERS}


# ── Connector configs ───────────────────────────────────────────────────

CONNECTOR_CONFIGS = [
    {
        "connector": "linear",
        "access_token": "demo-linear-token-not-real",
        "scopes": "read",
        "last_sync_days_ago": 0,
    },
    {
        "connector": "github",
        "access_token": "demo-github-token-not-real",
        "scopes": "repo,read:org",
        "last_sync_days_ago": 0,
    },
    {
        "connector": "slack",
        "access_token": "demo-slack-token-not-real",
        "scopes": "channels:history,users:read",
        "last_sync_days_ago": 0,
    },
]
