"""Seed script for Numen demo data.

Creates a 'Numen Test' org with realistic cross-tool data matching
real connector API schemas. Idempotent - safe to re-run.

Entities and edges are written to FalkorDB via the graph API.
Relational data (org, members, tokens, sync state) stays in PostgreSQL.

Usage: python -m scripts.seed
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from src.graph import delete_org_entities, upsert_edge, upsert_entity
from src.graph.falkor_client import close_falkor, get_org_graph
from src.graph.indexes import ensure_indexes
from src.shared.database import async_session
from src.shared.models import (
    Briefing,
    ChatMessage,
    Conversation,
    LinkSuggestion,
    OAuthToken,
    Organization,
    OrgMember,
    PersonResolution,
    SyncState,
    UrgencyScoreCache,
)
from src.shared.types import (
    EdgeCreate,
    EdgeType,
    EntityCreate,
    EntityType,
    RoleType,
    SourceType,
    SyncStatus,
)

# ── Fixed UUIDs for deterministic seeding ─────────────────────────────

ORG_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")

# Person entity IDs (Linear source — primary identity)
P_ALICE = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000001")
P_BOB = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002")
P_CAROL = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000003")
P_DAVID = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000004")
P_EVE = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000005")
P_FRANK = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000006")
P_GRACE = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000007")
P_HANNAH = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000008")

# OrgMember IDs
M_ALICE = uuid.UUID("cccccccc-0000-0000-0000-000000000001")
M_BOB = uuid.UUID("cccccccc-0000-0000-0000-000000000002")
M_CAROL = uuid.UUID("cccccccc-0000-0000-0000-000000000003")
M_DAVID = uuid.UUID("cccccccc-0000-0000-0000-000000000004")
M_EVE = uuid.UUID("cccccccc-0000-0000-0000-000000000005")
M_FRANK = uuid.UUID("cccccccc-0000-0000-0000-000000000006")
M_GRACE = uuid.UUID("cccccccc-0000-0000-0000-000000000007")
M_HANNAH = uuid.UUID("cccccccc-0000-0000-0000-000000000008")

# Task entity IDs
T = {f"t{i}": uuid.UUID(f"dddddddd-0000-0000-0000-{i:012d}") for i in range(1, 16)}

# Feature entity IDs
F = {f"f{i}": uuid.UUID(f"eeeeeeee-0000-0000-0000-{i:012d}") for i in range(1, 4)}

# PR entity IDs
PR = {f"pr{i}": uuid.UUID(f"ffffffff-0000-0000-0000-{i:012d}") for i in range(1, 11)}

# Deploy entity IDs
D = {f"d{i}": uuid.UUID(f"11111111-0000-0000-0000-{i:012d}") for i in range(1, 5)}

# Goal entity IDs
G = {f"g{i}": uuid.UUID(f"22222222-0000-0000-0000-{i:012d}") for i in range(1, 5)}

# Decision entity IDs
DEC = {f"dec{i}": uuid.UUID(f"33333333-0000-0000-0000-{i:012d}") for i in range(1, 6)}

# Slack document IDs
SD = {f"sd{i}": uuid.UUID(f"44444444-0000-0000-0000-{i:012d}") for i in range(1, 5)}

# Notion document IDs
ND = {f"nd{i}": uuid.UUID(f"55555555-0000-0000-0000-{i:012d}") for i in range(1, 5)}

# Datadog metric IDs
DD = {f"dd{i}": uuid.UUID(f"66666666-0000-0000-0000-{i:012d}") for i in range(1, 6)}

# Sentry error IDs
SE = {f"se{i}": uuid.UUID(f"77777777-0000-0000-0000-{i:012d}") for i in range(1, 4)}

# PagerDuty incident IDs
PD = {f"pd{i}": uuid.UUID(f"88888888-0000-0000-0000-{i:012d}") for i in range(1, 3)}

# Amplitude metric IDs
AM = {f"am{i}": uuid.UUID(f"99999999-0000-0000-0000-{i:012d}") for i in range(1, 4)}

# PostHog metric IDs
PH = {f"ph{i}": uuid.UUID(f"aabbccdd-0000-0000-0000-{i:012d}") for i in range(1, 3)}

# Project entity IDs
PJ = {f"pj{i}": uuid.UUID(f"ccddaabb-0000-0000-0000-{i:012d}") for i in range(1, 4)}

# Figma document IDs
FG = {f"fg{i}": uuid.UUID(f"bbaaddcc-0000-0000-0000-{i:012d}") for i in range(1, 3)}

NOW = datetime.now(timezone.utc)
REPO = "numen-team/platform"


def _dt(days_ago: float = 0, hours_ago: float = 0) -> datetime:
    return NOW - timedelta(days=days_ago, hours=hours_ago)


def _iso(days_ago: float = 0, hours_ago: float = 0) -> str:
    return _dt(days_ago, hours_ago).isoformat()


# ── Helpers ───────────────────────────────────────────────────────────


def _entity(eid, etype, source, source_ids, name, props, days_ago_created=5, days_ago_updated=0.5):
    """Return an EntityCreate DTO for FalkorDB upsert.

    The eid is stored in source_ids as '_seed_id' so the graph API can
    match on re-runs (idempotent).
    """
    sids = {**source_ids, "_seed_id": str(eid)}
    return EntityCreate(
        org_id=ORG_ID,
        type=etype,
        source=source,
        source_ids=sids,
        canonical_name=name,
        properties=props,
    )


def _edge(from_id, to_id, etype, evidence, weight=1.0, confidence=1.0, days_ago=3):
    return EdgeCreate(
        org_id=ORG_ID,
        from_entity_id=from_id,
        to_entity_id=to_id,
        type=etype,
        weight=weight,
        confidence=confidence,
        evidence=evidence,
    )


# ── Data builders ─────────────────────────────────────────────────────


def build_persons() -> list[EntityCreate]:
    people = [
        (P_ALICE, "Alice Chen", "alice@example.com", "alice-chen", "lin-alice-001"),
        (P_BOB, "Bob Martinez", "bob@example.com", "bob-martinez", "lin-bob-002"),
        (P_CAROL, "Carol Wu", "carol@example.com", "carol-wu", "lin-carol-003"),
        (P_DAVID, "David Kim", "david@example.com", "david-kim", "lin-david-004"),
        (P_EVE, "Eve Patel", "eve@example.com", "eve-patel", "lin-eve-005"),
        (P_FRANK, "Frank Liu", "frank@example.com", "frank-liu", "lin-frank-006"),
        (P_GRACE, "Grace Zhang", "grace@example.com", "grace-zhang", "lin-grace-007"),
        (P_HANNAH, "Hannah Lee", "hannah@example.com", "hannah-lee", "lin-hannah-008"),
    ]
    return [
        _entity(
            pid,
            EntityType.PERSON,
            SourceType.LINEAR,
            {"linear": lid, "github": gh},
            name,
            {
                "email": email,
                "avatar_url": f"https://avatars.example.com/{gh}.png",
                "active": True,
                "github_login": gh,
                "contributions": 50 + i * 12,
            },
            days_ago_created=60,
            days_ago_updated=0.2,
        )
        for i, (pid, name, email, gh, lid) in enumerate(people)
    ]


def build_members() -> list[OrgMember]:
    return [
        OrgMember(
            id=M_ALICE,
            org_id=ORG_ID,
            person_entity_id=P_ALICE,
            email="alice@example.com",
            display_name="Alice Chen",
            role=RoleType.ENGINEER,
            timezone="America/Los_Angeles",
        ),
        OrgMember(
            id=M_BOB,
            org_id=ORG_ID,
            person_entity_id=P_BOB,
            email="bob@example.com",
            display_name="Bob Martinez",
            role=RoleType.ENGINEER,
            timezone="America/New_York",
        ),
        OrgMember(
            id=M_CAROL,
            org_id=ORG_ID,
            person_entity_id=P_CAROL,
            email="carol@example.com",
            display_name="Carol Wu",
            role=RoleType.ENGINEER,
            timezone="America/Chicago",
        ),
        OrgMember(
            id=M_DAVID,
            org_id=ORG_ID,
            person_entity_id=P_DAVID,
            email="david@example.com",
            display_name="David Kim",
            role=RoleType.ENGINEER,
            timezone="America/New_York",
        ),
        OrgMember(
            id=M_EVE,
            org_id=ORG_ID,
            person_entity_id=P_EVE,
            email="eve@example.com",
            display_name="Eve Patel",
            role=RoleType.PM,
            timezone="America/New_York",
        ),
        OrgMember(
            id=M_FRANK,
            org_id=ORG_ID,
            person_entity_id=P_FRANK,
            email="frank@example.com",
            display_name="Frank Liu",
            role=RoleType.EM,
            timezone="America/Los_Angeles",
        ),
        OrgMember(
            id=M_GRACE,
            org_id=ORG_ID,
            person_entity_id=P_GRACE,
            email="grace@example.com",
            display_name="Grace Zhang",
            role=RoleType.CTO,
            timezone="America/New_York",
        ),
        OrgMember(
            id=M_HANNAH,
            org_id=ORG_ID,
            person_entity_id=P_HANNAH,
            email="hannah@example.com",
            display_name="Hannah Lee",
            role=RoleType.DESIGNER,
            timezone="America/Los_Angeles",
        ),
    ]


def build_features() -> list[EntityCreate]:
    return [
        _entity(
            F["f1"],
            EntityType.FEATURE,
            SourceType.LINEAR,
            {"linear": "proj-auth-v2-001"},
            "User Authentication Revamp",
            {
                "description": "Complete overhaul of auth system to OAuth2 PKCE flow",
                "state": "started",
                "start_date": "2026-03-01",
                "target_date": "2026-04-15",
                "lead_id": "lin-alice-001",
            },
            days_ago_created=25,
            days_ago_updated=1,
        ),
        _entity(
            F["f2"],
            EntityType.FEATURE,
            SourceType.LINEAR,
            {"linear": "proj-observ-002"},
            "Observability Platform",
            {
                "description": "Unified logging, metrics, and tracing for all services",
                "state": "planned",
                "start_date": "2026-04-01",
                "target_date": "2026-05-15",
                "lead_id": "lin-david-004",
            },
            days_ago_created=20,
            days_ago_updated=3,
        ),
        _entity(
            F["f3"],
            EntityType.FEATURE,
            SourceType.LINEAR,
            {"linear": "proj-onboard-003"},
            "Onboarding V2",
            {
                "description": "Redesigned onboarding flow with progressive disclosure",
                "state": "started",
                "start_date": "2026-02-15",
                "target_date": "2026-03-31",
                "lead_id": "lin-carol-003",
            },
            days_ago_created=40,
            days_ago_updated=2,
        ),
    ]


def build_tasks() -> list[EntityCreate]:
    tasks_data = [
        (
            T["t1"],
            "NUM-42",
            "Implement OAuth2 PKCE flow",
            1,
            "In Progress",
            "started",
            P_ALICE,
            ["auth", "backend"],
            6,
            0.5,
        ),
        (
            T["t2"],
            "NUM-43",
            "Add token refresh middleware",
            1,
            "Todo",
            "unstarted",
            P_ALICE,
            ["auth", "backend"],
            5,
            1,
        ),
        (
            T["t3"],
            "NUM-44",
            "Write PKCE integration tests",
            2,
            "Todo",
            "unstarted",
            P_BOB,
            ["auth", "testing"],
            5,
            2,
        ),
        (
            T["t4"],
            "NUM-45",
            "Migrate user sessions to new auth",
            1,
            "Backlog",
            "backlog",
            P_CAROL,
            ["auth", "migration"],
            4,
            1,
        ),
        (
            T["t5"],
            "NUM-46",
            "Update API rate limiter for new tokens",
            2,
            "In Progress",
            "started",
            P_BOB,
            ["auth", "infra"],
            3,
            0.3,
        ),
        (
            T["t6"],
            "NUM-47",
            "Auth V2 load testing",
            3,
            "Todo",
            "unstarted",
            P_DAVID,
            ["auth", "performance"],
            3,
            2,
        ),
        (
            T["t7"],
            "NUM-48",
            "Deploy auth V2 to staging",
            1,
            "Backlog",
            "backlog",
            P_DAVID,
            ["auth", "deploy"],
            2,
            1,
        ),
        (
            T["t8"],
            "NUM-49",
            "Update onboarding email flow",
            2,
            "In Progress",
            "started",
            P_CAROL,
            ["onboarding", "email"],
            8,
            0.5,
        ),
        (
            T["t9"],
            "NUM-50",
            "Fix Slack notification threading",
            3,
            "Done",
            "completed",
            P_DAVID,
            ["slack", "bugfix"],
            10,
            1,
        ),
        (
            T["t10"],
            "NUM-51",
            "Add Datadog APM to auth service",
            2,
            "In Review",
            "started",
            P_DAVID,
            ["observability", "auth"],
            7,
            0.2,
        ),
        (
            T["t11"],
            "NUM-52",
            "Design system token refresh UX",
            2,
            "In Progress",
            "started",
            P_HANNAH,
            ["auth", "design"],
            5,
            0.5,
        ),
        (
            T["t12"],
            "NUM-53",
            "Write auth migration runbook",
            3,
            "Todo",
            "unstarted",
            P_ALICE,
            ["auth", "docs"],
            4,
            3,
        ),
        (
            T["t13"],
            "NUM-54",
            "Capacity planning for Q2",
            2,
            "In Progress",
            "started",
            P_FRANK,
            ["planning"],
            6,
            0.5,
        ),
        (
            T["t14"],
            "NUM-55",
            "Review auth threat model",
            1,
            "Todo",
            "unstarted",
            P_GRACE,
            ["auth", "security"],
            3,
            2,
        ),
        (
            T["t15"],
            "NUM-56",
            "Onboarding analytics events",
            3,
            "Done",
            "completed",
            P_CAROL,
            ["onboarding", "analytics"],
            12,
            2,
        ),
    ]
    return [
        _entity(
            tid,
            EntityType.TASK,
            SourceType.LINEAR,
            {"linear": str(tid)},
            f"{ident}: {title}",
            {
                "identifier": ident,
                "title": title,
                "description": f"Implementation details for {title.lower()}",
                "priority": priority,
                "state": state,
                "state_type": state_type,
                "team_key": "NUM",
                "labels": labels,
                "created_at": _iso(created),
                "updated_at": _iso(updated),
            },
            days_ago_created=created,
            days_ago_updated=updated,
        )
        for tid, ident, title, priority, state, state_type, _assignee, labels, created, updated in tasks_data
    ]


def build_prs() -> list[EntityCreate]:
    prs_data = [
        (
            PR["pr1"],
            142,
            "Add PKCE auth flow",
            "open",
            False,
            False,
            None,
            "feat/pkce-auth",
            342,
            28,
            P_ALICE,
            3,
            0.5,
        ),
        (
            PR["pr2"],
            143,
            "Token refresh middleware",
            "open",
            True,
            False,
            None,
            "feat/token-refresh",
            89,
            12,
            P_ALICE,
            2,
            1,
        ),
        (
            PR["pr3"],
            138,
            "Rate limiter v2",
            "open",
            False,
            False,
            None,
            "fix/rate-limiter-v2",
            156,
            43,
            P_BOB,
            4,
            0.3,
        ),
        (
            PR["pr4"],
            135,
            "Slack notification fix",
            "closed",
            False,
            True,
            _iso(1),
            "fix/slack-threading",
            67,
            8,
            P_DAVID,
            8,
            1,
        ),
        (
            PR["pr5"],
            140,
            "Datadog APM integration",
            "open",
            False,
            False,
            None,
            "feat/datadog-apm",
            234,
            15,
            P_DAVID,
            5,
            0.2,
        ),
        (
            PR["pr6"],
            137,
            "Onboarding email templates",
            "open",
            False,
            False,
            None,
            "feat/onboarding-emails",
            178,
            22,
            P_CAROL,
            6,
            0.5,
        ),
        (
            PR["pr7"],
            141,
            "Auth service deploy pipeline",
            "closed",
            False,
            True,
            _iso(2),
            "infra/auth-deploy",
            45,
            3,
            P_BOB,
            5,
            2,
        ),
        (
            PR["pr8"],
            139,
            "Design system auth components",
            "open",
            False,
            False,
            None,
            "feat/auth-design-tokens",
            312,
            67,
            P_HANNAH,
            4,
            0.5,
        ),
        (
            PR["pr9"],
            136,
            "Onboarding analytics events",
            "closed",
            False,
            True,
            _iso(3),
            "feat/onboarding-analytics",
            92,
            11,
            P_CAROL,
            10,
            3,
        ),
        (
            PR["pr10"],
            144,
            "Auth threat model docs",
            "open",
            True,
            False,
            None,
            "docs/auth-threat-model",
            420,
            0,
            P_GRACE,
            1,
            0.5,
        ),
    ]
    return [
        _entity(
            prid,
            EntityType.COMMIT_PR,
            SourceType.GITHUB,
            {"github": f"{REPO}#{num}"},
            f"PR #{num}: {title}",
            {
                "repo": REPO,
                "number": num,
                "title": title,
                "state": state,
                "draft": draft,
                "merged": merged,
                "merged_at": merged_at,
                "head_branch": branch,
                "base_branch": "main",
                "additions": adds,
                "deletions": dels,
                "created_at": _iso(created),
                "updated_at": _iso(updated),
                "html_url": f"https://github.com/{REPO}/pull/{num}",
            },
            days_ago_created=created,
            days_ago_updated=updated,
        )
        for prid, num, title, state, draft, merged, merged_at, branch, adds, dels, _author, created, updated in prs_data
    ]


def build_deploys() -> list[EntityCreate]:
    deploys_data = [
        (
            D["d1"],
            "production",
            "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2",
            "main",
            "bob-martinez",
            "Production deploy — auth service hotfix",
            1,
            0.5,
        ),
        (
            D["d2"],
            "staging",
            "b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3",
            "feat/pkce-auth",
            "alice-chen",
            "Staging deploy — PKCE auth preview",
            2,
            0.3,
        ),
        (
            D["d3"],
            "production",
            "c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
            "main",
            "bob-martinez",
            "Production deploy — rate limiter + slack fix",
            5,
            0.2,
        ),
        (
            D["d4"],
            "staging",
            "d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5",
            "feat/onboarding-emails",
            "carol-wu",
            "Staging deploy — onboarding flow",
            3,
            1,
        ),
    ]
    return [
        _entity(
            did,
            EntityType.DEPLOY,
            SourceType.GITHUB,
            {"github": f"{REPO}/deploy/{did}"},
            f"Deploy {sha[:12]} to {env}",
            {
                "repo": REPO,
                "environment": env,
                "sha": sha,
                "ref": ref,
                "task": "deploy",
                "description": desc,
                "created_at": _iso(created),
                "creator_login": creator,
            },
            days_ago_created=created,
            days_ago_updated=updated,
        )
        for did, env, sha, ref, creator, desc, created, updated in deploys_data
    ]


def build_goals() -> list[EntityCreate]:
    return [
        _entity(
            G["g1"],
            EntityType.GOAL,
            SourceType.MANUAL,
            {"manual": "goal-ship-auth-v2"},
            "Ship Auth V2 by April 15",
            {
                "level": "company",
                "status": "active",
                "key_results": [
                    {
                        "title": "Complete PKCE implementation",
                        "target_value": 100,
                        "current_value": 35,
                        "unit": "%",
                    },
                    {
                        "title": "Zero auth-related incidents in 30 days",
                        "target_value": 0,
                        "current_value": 2,
                        "unit": "incidents",
                    },
                    {
                        "title": "Auth success rate > 99.9%",
                        "target_value": 99.9,
                        "current_value": 98.2,
                        "unit": "%",
                    },
                ],
                "target_value": 100,
                "current_value": 35,
                "time_bound_start": "2026-03-01T00:00:00Z",
                "time_bound_end": "2026-04-15T00:00:00Z",
                "progress_mode": "manual",
            },
            days_ago_created=25,
            days_ago_updated=1,
        ),
        _entity(
            G["g2"],
            EntityType.GOAL,
            SourceType.MANUAL,
            {"manual": "goal-pkce-impl"},
            "Complete PKCE Implementation",
            {
                "level": "team",
                "status": "active",
                "key_results": [
                    {
                        "title": "Core PKCE flow merged",
                        "target_value": 100,
                        "current_value": 40,
                        "unit": "%",
                    },
                    {
                        "title": "Integration tests passing",
                        "target_value": 100,
                        "current_value": 0,
                        "unit": "%",
                    },
                ],
                "target_value": 100,
                "current_value": 40,
                "time_bound_start": "2026-03-01T00:00:00Z",
                "time_bound_end": "2026-04-01T00:00:00Z",
                "progress_mode": "manual",
            },
            days_ago_created=25,
            days_ago_updated=1,
        ),
        _entity(
            G["g3"],
            EntityType.GOAL,
            SourceType.MANUAL,
            {"manual": "goal-auth-uptime"},
            "Achieve 99.9% Auth Uptime",
            {
                "level": "team",
                "status": "active",
                "key_results": [
                    {
                        "title": "Auth uptime last 30 days",
                        "target_value": 99.9,
                        "current_value": 98.2,
                        "unit": "%",
                    },
                    {
                        "title": "Mean incident resolution < 30min",
                        "target_value": 30,
                        "current_value": 45,
                        "unit": "minutes",
                    },
                ],
                "target_value": 99.9,
                "current_value": 98.2,
                "time_bound_start": "2026-03-01T00:00:00Z",
                "time_bound_end": "2026-06-30T00:00:00Z",
                "progress_mode": "manual",
            },
            days_ago_created=25,
            days_ago_updated=2,
        ),
        _entity(
            G["g4"],
            EntityType.GOAL,
            SourceType.MANUAL,
            {"manual": "goal-auth-migration-guide"},
            "Write Auth Migration Guide",
            {
                "level": "individual",
                "status": "active",
                "key_results": [
                    {
                        "title": "Draft completed",
                        "target_value": 100,
                        "current_value": 20,
                        "unit": "%",
                    },
                ],
                "target_value": 100,
                "current_value": 20,
                "time_bound_start": "2026-03-15T00:00:00Z",
                "time_bound_end": "2026-04-01T00:00:00Z",
                "progress_mode": "manual",
            },
            days_ago_created=11,
            days_ago_updated=3,
        ),
    ]


def build_decisions() -> list[EntityCreate]:
    decisions = [
        (
            DEC["dec1"],
            "C0ENG001",
            "engineering",
            "U_GRACE",
            "1711152000.000100",
            "Decision: We will use PKCE flow instead of implicit grant for all OAuth2 clients. This applies to both web and mobile. No exceptions for internal tools.",  # noqa: E501
            21,
        ),
        (
            DEC["dec2"],
            "C0ENG001",
            "engineering",
            "U_EVE",
            "1711238400.000200",
            "Decision: Auth V2 rollout will use feature flags - 10% canary, then 50%, then 100%. Rollback trigger: auth error rate > 0.5%.",  # noqa: E501
            18,
        ),
        (
            DEC["dec3"],
            "C0ENG001",
            "engineering",
            "U_GRACE",
            "1711497600.000300",
            "Decision: Token refresh will be handled client-side with a 5-minute buffer before expiry. Server-side refresh is out of scope for V2.",  # noqa: E501
            15,
        ),
        (
            DEC["dec4"],
            "C0ARCH001",
            "architecture",
            "U_GRACE",
            "1711756800.000400",
            "RFC: API rate limiting strategy for auth endpoints - awaiting final approval from Grace. Two options proposed: sliding window vs token bucket.",  # noqa: E501
            5,
        ),
        (
            DEC["dec5"],
            "C0PROD001",
            "product",
            "U_EVE",
            "1711843200.000500",
            "Decision: Onboarding V2 will require email verification before first project creation. This changes the existing flow.",  # noqa: E501
            3,
        ),
    ]
    return [
        _entity(
            did,
            EntityType.DECISION,
            SourceType.SLACK,
            {"slack": f"{ch_id}/{ts}"},
            f"Decision: {text[:80]}...",
            {
                "text": text,
                "channel_id": ch_id,
                "channel_name": ch_name,
                "user_id": uid,
                "timestamp": ts,
                "slack_link": f"https://numen-team.slack.com/archives/{ch_id}/p{ts.replace('.', '')}",
            },
            days_ago_created=days_ago,
            days_ago_updated=days_ago,
        )
        for did, ch_id, ch_name, uid, ts, text, days_ago in decisions
    ]


def build_slack_docs() -> list[EntityCreate]:
    docs = [
        (SD["sd1"], "C0ENG001", "engineering", "1711929600.000600", 2),
        (SD["sd2"], "C0ENG001", "engineering", "1712016000.000700", 1),
        (SD["sd3"], "C0PROD001", "product", "1711843200.000800", 3),
        (SD["sd4"], "C0ARCH001", "architecture", "1711756800.000900", 5),
    ]
    return [
        _entity(
            sid,
            EntityType.DOCUMENT,
            SourceType.SLACK,
            {"slack": f"{ch_id}/{ts}"},
            f"Slack message in #{ch_name}",
            {"channel_id": ch_id, "channel_name": ch_name, "timestamp": ts},
            days_ago_created=days_ago,
            days_ago_updated=days_ago,
        )
        for sid, ch_id, ch_name, ts, days_ago in docs
    ]


def build_notion_docs() -> list[EntityCreate]:
    docs = [
        (ND["nd1"], "Auth V2 PRD", "PRD", 3200, 0.80, 9, "page-auth-v2-prd-001"),
        (ND["nd2"], "Rate Limiting RFC", "RFC", 1800, 0.95, 15, "page-rate-limit-rfc-002"),
        (ND["nd3"], "Onboarding V2 Spec", "spec", 2400, 0.65, 4, "page-onboard-spec-003"),
        (ND["nd4"], "Auth Migration Runbook", "runbook", 800, 0.20, 3, "page-auth-runbook-004"),
    ]
    return [
        _entity(
            nid,
            EntityType.DOCUMENT,
            SourceType.NOTION,
            {"notion": page_id},
            title,
            {
                "title": title,
                "type": doc_type,
                "page_url": f"https://notion.so/{page_id}",
                "last_edited": _iso(days_stale),
                "word_count": words,
                "completeness_estimate": completeness,
            },
            days_ago_created=30,
            days_ago_updated=days_stale,
        )
        for nid, title, doc_type, words, completeness, days_stale, page_id in docs
    ]


def build_datadog_metrics() -> list[EntityCreate]:
    metrics = [
        (DD["dd1"], "api.latency.p95", 145.3, "auth-service", False, None, 0.1),
        (DD["dd2"], "api.latency.p95", 312.7, "auth-service", True, None, 1),
        (DD["dd3"], "api.error_rate", 0.8, "auth-service", True, "auth-v2", 1),
        (DD["dd4"], "api.request_count", 45230, "auth-service", False, None, 0.1),
        (DD["dd5"], "deploy.frequency", 3, "platform", False, None, 0.5),
    ]
    return [
        _entity(
            mid,
            EntityType.METRIC_SNAPSHOT,
            SourceType.DATADOG,
            {"datadog": f"metric/{name}/{_iso(hours_ago)}"},
            f"{name} = {value}",
            {
                "metric_name": name,
                "value": value,
                "timestamp": _iso(hours_ago),
                "service": service,
                "anomaly_flag": anomaly,
                "goal_tag": goal_tag,
            },
            days_ago_created=hours_ago,
            days_ago_updated=hours_ago,
        )
        for mid, name, value, service, anomaly, goal_tag, hours_ago in metrics
    ]


def build_sentry_errors() -> list[EntityCreate]:
    errors = [
        (
            SE["se1"],
            "auth-token-expired-001",
            "TokenExpiredError",
            "auth-service",
            1,
            342,
            str(D["d1"]),
        ),
        (
            SE["se2"],
            "null-user-session-002",
            "NullPointerException",
            "auth-service",
            2,
            89,
            str(D["d1"]),
        ),
        (SE["se3"], "rate-limit-overflow-003", "RateLimitError", "api-gateway", 5, 23, None),
    ]
    return [
        _entity(
            sid,
            EntityType.ERROR_EVENT,
            SourceType.SENTRY,
            {"sentry": f"issue/{fp}"},
            f"Sentry: {err_type} in {service}",
            {
                "fingerprint": fp,
                "error_type": err_type,
                "affected_service": service,
                "first_seen": _iso(days_ago),
                "event_count": count,
                "linked_deploy": linked,
            },
            days_ago_created=days_ago,
            days_ago_updated=0.5,
        )
        for sid, fp, err_type, service, days_ago, count, linked in errors
    ]


def build_pagerduty_incidents() -> list[EntityCreate]:
    return [
        _entity(
            PD["pd1"],
            EntityType.INCIDENT,
            SourceType.PAGERDUTY,
            {"pagerduty": "incident/PD-2001"},
            "P2: Auth service elevated error rate",
            {
                "severity": "P2",
                "service": "auth-service",
                "owner_team": "Platform",
                "opened_at": _iso(1, 2),
                "resolved_at": _iso(0, 20),
                "linked_deploy": str(D["d1"]),
            },
            days_ago_created=1,
            days_ago_updated=0.5,
        ),
        _entity(
            PD["pd2"],
            EntityType.INCIDENT,
            SourceType.PAGERDUTY,
            {"pagerduty": "incident/PD-1998"},
            "P3: Intermittent API gateway timeouts",
            {
                "severity": "P3",
                "service": "api-gateway",
                "owner_team": "Platform",
                "opened_at": _iso(5),
                "resolved_at": _iso(4, 18),
                "linked_deploy": None,
            },
            days_ago_created=5,
            days_ago_updated=4,
        ),
    ]


def build_amplitude_metrics() -> list[EntityCreate]:
    return [
        _entity(
            AM["am1"],
            EntityType.METRIC_SNAPSHOT,
            SourceType.AMPLITUDE,
            {"amplitude": f"metric/checkout_funnel_completion/{_iso(1)}"},
            "checkout_funnel_completion = 72.3%",
            {
                "metric_name": "checkout_funnel_completion",
                "value": 72.3,
                "timestamp": _iso(1),
                "goal_tag": "auth-v2",
                "anomaly_flag": True,
            },
            days_ago_created=1,
            days_ago_updated=0.5,
        ),
        _entity(
            AM["am2"],
            EntityType.METRIC_SNAPSHOT,
            SourceType.AMPLITUDE,
            {"amplitude": f"metric/d7_retention/{_iso(1)}"},
            "d7_retention = 34.1%",
            {
                "metric_name": "d7_retention",
                "value": 34.1,
                "timestamp": _iso(1),
                "goal_tag": None,
                "anomaly_flag": False,
            },
            days_ago_created=1,
            days_ago_updated=0.5,
        ),
        _entity(
            AM["am3"],
            EntityType.METRIC_SNAPSHOT,
            SourceType.AMPLITUDE,
            {"amplitude": f"metric/auth_success_rate/{_iso(0.5)}"},
            "auth_success_rate = 98.2%",
            {
                "metric_name": "auth_success_rate",
                "value": 98.2,
                "timestamp": _iso(0.5),
                "goal_tag": "auth-v2",
                "anomaly_flag": False,
            },
            days_ago_created=0.5,
            days_ago_updated=0.2,
        ),
    ]


def build_posthog_metrics() -> list[EntityCreate]:
    return [
        _entity(
            PH["ph1"],
            EntityType.METRIC_SNAPSHOT,
            SourceType.POSTHOG,
            {"posthog": f"metric/feature_adoption_pkce_auth/{_iso(1)}"},
            "feature_adoption_pkce_auth = 0.0%",
            {
                "metric_name": "feature_adoption_pkce_auth",
                "value": 0.0,
                "feature_flag": "pkce-auth-flow",
                "timestamp": _iso(1),
            },
            days_ago_created=1,
            days_ago_updated=0.5,
        ),
        _entity(
            PH["ph2"],
            EntityType.METRIC_SNAPSHOT,
            SourceType.POSTHOG,
            {"posthog": f"metric/feature_adoption_onboarding_v2/{_iso(1)}"},
            "feature_adoption_onboarding_v2 = 12.4%",
            {
                "metric_name": "feature_adoption_onboarding_v2",
                "value": 12.4,
                "feature_flag": "onboarding-v2",
                "timestamp": _iso(1),
            },
            days_ago_created=1,
            days_ago_updated=0.5,
        ),
    ]


def build_figma_docs() -> list[EntityCreate]:
    return [
        _entity(
            FG["fg1"],
            EntityType.DOCUMENT,
            SourceType.FIGMA,
            {"figma": "file/figma-auth-v2-001"},
            "Auth V2 Design Specs",
            {
                "title": "Auth V2 Design Specs",
                "file_url": "https://figma.com/file/figma-auth-v2-001",
                "last_modified": _iso(2),
                "status": "ready_for_handoff",
            },
            days_ago_created=15,
            days_ago_updated=2,
        ),
        _entity(
            FG["fg2"],
            EntityType.DOCUMENT,
            SourceType.FIGMA,
            {"figma": "file/figma-onboard-002"},
            "Onboarding V2 Mockups",
            {
                "title": "Onboarding V2 Mockups",
                "file_url": "https://figma.com/file/figma-onboard-002",
                "last_modified": _iso(4),
                "status": "in_progress",
            },
            days_ago_created=20,
            days_ago_updated=4,
        ),
    ]


def build_projects() -> list[EntityCreate]:
    return [
        _entity(
            PJ["pj1"],
            EntityType.PROJECT,
            SourceType.MANUAL,
            {"manual": "project-auth-v2"},
            "Auth V2",
            {
                "description": "Complete overhaul of authentication system to OAuth2 PKCE",
                "status": "active",
                "owner_email": "alice@example.com",
                "start_date": "2026-03-01",
                "end_date": "2026-04-15",
                "priority": "high",
            },
            days_ago_created=25,
            days_ago_updated=0.5,
        ),
        _entity(
            PJ["pj2"],
            EntityType.PROJECT,
            SourceType.MANUAL,
            {"manual": "project-onboarding-v2"},
            "Onboarding V2",
            {
                "description": "Redesigned onboarding flow with progressive disclosure",
                "status": "active",
                "owner_email": "carol@example.com",
                "start_date": "2026-02-15",
                "end_date": "2026-03-31",
                "priority": "medium",
            },
            days_ago_created=40,
            days_ago_updated=2,
        ),
        _entity(
            PJ["pj3"],
            EntityType.PROJECT,
            SourceType.MANUAL,
            {"manual": "project-observability"},
            "Observability Platform",
            {
                "description": "Unified logging, metrics, and tracing",
                "status": "planning",
                "owner_email": "david@example.com",
                "start_date": "2026-04-01",
                "end_date": "2026-05-15",
                "priority": "medium",
            },
            days_ago_created=20,
            days_ago_updated=3,
        ),
    ]


def build_edges() -> list[EdgeCreate]:
    ev = lambda src, field, **kw: [{"source": src, "field": field, **kw}]  # noqa: E731
    edges = [
        # OWNS: Person → Task (Linear assignee)
        (P_ALICE, T["t1"], EdgeType.OWNS, ev("linear", "assignee", issue="NUM-42")),
        (P_ALICE, T["t2"], EdgeType.OWNS, ev("linear", "assignee", issue="NUM-43")),
        (P_BOB, T["t3"], EdgeType.OWNS, ev("linear", "assignee", issue="NUM-44")),
        (P_CAROL, T["t4"], EdgeType.OWNS, ev("linear", "assignee", issue="NUM-45")),
        (P_BOB, T["t5"], EdgeType.OWNS, ev("linear", "assignee", issue="NUM-46")),
        (P_DAVID, T["t6"], EdgeType.OWNS, ev("linear", "assignee", issue="NUM-47")),
        (P_DAVID, T["t7"], EdgeType.OWNS, ev("linear", "assignee", issue="NUM-48")),
        (P_CAROL, T["t8"], EdgeType.OWNS, ev("linear", "assignee", issue="NUM-49")),
        (P_DAVID, T["t9"], EdgeType.OWNS, ev("linear", "assignee", issue="NUM-50")),
        (P_DAVID, T["t10"], EdgeType.OWNS, ev("linear", "assignee", issue="NUM-51")),
        (P_HANNAH, T["t11"], EdgeType.OWNS, ev("linear", "assignee", issue="NUM-52")),
        (P_ALICE, T["t12"], EdgeType.OWNS, ev("linear", "assignee", issue="NUM-53")),
        (P_FRANK, T["t13"], EdgeType.OWNS, ev("linear", "assignee", issue="NUM-54")),
        (P_GRACE, T["t14"], EdgeType.OWNS, ev("linear", "assignee", issue="NUM-55")),
        (P_CAROL, T["t15"], EdgeType.OWNS, ev("linear", "assignee", issue="NUM-56")),
        # AUTHORED: Person → PR
        (P_ALICE, PR["pr1"], EdgeType.AUTHORED, ev("github", "author", pr="142")),
        (P_ALICE, PR["pr2"], EdgeType.AUTHORED, ev("github", "author", pr="143")),
        (P_BOB, PR["pr3"], EdgeType.AUTHORED, ev("github", "author", pr="138")),
        (P_DAVID, PR["pr4"], EdgeType.AUTHORED, ev("github", "author", pr="135")),
        (P_DAVID, PR["pr5"], EdgeType.AUTHORED, ev("github", "author", pr="140")),
        (P_CAROL, PR["pr6"], EdgeType.AUTHORED, ev("github", "author", pr="137")),
        (P_BOB, PR["pr7"], EdgeType.AUTHORED, ev("github", "author", pr="141")),
        (P_HANNAH, PR["pr8"], EdgeType.AUTHORED, ev("github", "author", pr="139")),
        (P_CAROL, PR["pr9"], EdgeType.AUTHORED, ev("github", "author", pr="136")),
        (P_GRACE, PR["pr10"], EdgeType.AUTHORED, ev("github", "author", pr="144")),
        # MENTIONED_IN: Person → PR (reviewers)
        (P_BOB, PR["pr1"], EdgeType.MENTIONED_IN, ev("github", "reviewer", pr="142")),
        (P_DAVID, PR["pr1"], EdgeType.MENTIONED_IN, ev("github", "reviewer", pr="142")),
        (P_ALICE, PR["pr3"], EdgeType.MENTIONED_IN, ev("github", "reviewer", pr="138")),
        (P_BOB, PR["pr5"], EdgeType.MENTIONED_IN, ev("github", "reviewer", pr="140")),
        (P_FRANK, PR["pr6"], EdgeType.MENTIONED_IN, ev("github", "reviewer", pr="137")),
        (P_ALICE, PR["pr7"], EdgeType.MENTIONED_IN, ev("github", "reviewer", pr="141")),
        (P_EVE, PR["pr8"], EdgeType.MENTIONED_IN, ev("github", "reviewer", pr="139")),
        (P_FRANK, PR["pr10"], EdgeType.MENTIONED_IN, ev("github", "reviewer", pr="144")),
        # BLOCKS: Task → Task
        (T["t1"], T["t4"], EdgeType.BLOCKS, ev("linear", "relation", type="blocks")),
        (T["t4"], T["t7"], EdgeType.BLOCKS, ev("linear", "relation", type="blocks")),
        (T["t5"], T["t1"], EdgeType.BLOCKS, ev("linear", "relation", type="blocks")),
        (T["t11"], T["t2"], EdgeType.BLOCKS, ev("linear", "relation", type="blocks")),
        # TAGGED_TO: Task → Feature
        (T["t1"], F["f1"], EdgeType.TAGGED_TO, ev("linear", "project", project="Auth Revamp")),
        (T["t2"], F["f1"], EdgeType.TAGGED_TO, ev("linear", "project", project="Auth Revamp")),
        (T["t3"], F["f1"], EdgeType.TAGGED_TO, ev("linear", "project", project="Auth Revamp")),
        (T["t4"], F["f1"], EdgeType.TAGGED_TO, ev("linear", "project", project="Auth Revamp")),
        (T["t5"], F["f1"], EdgeType.TAGGED_TO, ev("linear", "project", project="Auth Revamp")),
        (T["t6"], F["f1"], EdgeType.TAGGED_TO, ev("linear", "project", project="Auth Revamp")),
        (T["t7"], F["f1"], EdgeType.TAGGED_TO, ev("linear", "project", project="Auth Revamp")),
        (T["t10"], F["f2"], EdgeType.TAGGED_TO, ev("linear", "project", project="Observability")),
        (T["t8"], F["f3"], EdgeType.TAGGED_TO, ev("linear", "project", project="Onboarding V2")),
        (T["t15"], F["f3"], EdgeType.TAGGED_TO, ev("linear", "project", project="Onboarding V2")),
        # TAGGED_TO: Task → Goal
        (T["t1"], G["g2"], EdgeType.TAGGED_TO, ev("manual", "goal_tag")),
        (T["t2"], G["g2"], EdgeType.TAGGED_TO, ev("manual", "goal_tag")),
        (T["t3"], G["g2"], EdgeType.TAGGED_TO, ev("manual", "goal_tag")),
        (T["t12"], G["g4"], EdgeType.TAGGED_TO, ev("manual", "goal_tag")),
        (T["t14"], G["g3"], EdgeType.TAGGED_TO, ev("manual", "goal_tag")),
        # SHIPS_TO: PR → Deploy
        (PR["pr7"], D["d1"], EdgeType.SHIPS_TO, ev("github", "ref", sha="a1b2c3")),
        (PR["pr1"], D["d2"], EdgeType.SHIPS_TO, ev("github", "ref", sha="b2c3d4")),
        (PR["pr4"], D["d3"], EdgeType.SHIPS_TO, ev("github", "ref", sha="c3d4e5")),
        (PR["pr6"], D["d4"], EdgeType.SHIPS_TO, ev("github", "ref", sha="d4e5f6")),
        # CAUSED_BY: Incident/Error → Deploy
        (PD["pd1"], D["d1"], EdgeType.CAUSED_BY, ev("inferred", "time_correlation")),
        (SE["se1"], D["d1"], EdgeType.CAUSED_BY, ev("inferred", "time_correlation")),
        (SE["se2"], D["d1"], EdgeType.CAUSED_BY, ev("inferred", "time_correlation")),
        # MEASURES: Metric → Goal
        (AM["am1"], G["g1"], EdgeType.MEASURES, ev("inferred", "goal_tag_match")),
        (AM["am3"], G["g3"], EdgeType.MEASURES, ev("inferred", "goal_tag_match")),
        (DD["dd3"], G["g3"], EdgeType.MEASURES, ev("inferred", "service_match")),
        (PH["ph1"], G["g2"], EdgeType.MEASURES, ev("inferred", "feature_flag_match")),
        (PH["ph2"], G["g1"], EdgeType.MEASURES, ev("inferred", "feature_flag_match")),
        # DEPENDS_ON: Task → Decision
        (T["t1"], DEC["dec1"], EdgeType.DEPENDS_ON, ev("slack", "mention_resolved")),
        (T["t5"], DEC["dec3"], EdgeType.DEPENDS_ON, ev("slack", "mention_resolved")),
        (T["t7"], DEC["dec4"], EdgeType.DEPENDS_ON, ev("slack", "mention_unresolved")),
        # MENTIONED_IN: Entity → Slack Document
        (
            T["t1"],
            SD["sd1"],
            EdgeType.MENTIONED_IN,
            ev("slack", "mention", mention_type="linear_issue", mention_value="NUM-42"),
        ),
        (
            PR["pr1"],
            SD["sd2"],
            EdgeType.MENTIONED_IN,
            ev("slack", "mention", mention_type="github_pr", mention_value="142"),
        ),
        (
            T["t5"],
            SD["sd1"],
            EdgeType.MENTIONED_IN,
            ev("slack", "mention", mention_type="linear_issue", mention_value="NUM-46"),
        ),
        (
            G["g1"],
            SD["sd3"],
            EdgeType.MENTIONED_IN,
            ev("slack", "mention", mention_type="goal", mention_value="Auth V2"),
        ),
        # PARENT_OF: Goal hierarchy
        (G["g1"], G["g2"], EdgeType.PARENT_OF, ev("manual", "goal_hierarchy")),
        (G["g1"], G["g3"], EdgeType.PARENT_OF, ev("manual", "goal_hierarchy")),
        (G["g2"], G["g4"], EdgeType.PARENT_OF, ev("manual", "goal_hierarchy")),
        # CONTAINS: Project → Task
        (PJ["pj1"], T["t1"], EdgeType.CONTAINS, ev("manual", "project_task")),
        (PJ["pj1"], T["t2"], EdgeType.CONTAINS, ev("manual", "project_task")),
        (PJ["pj1"], T["t3"], EdgeType.CONTAINS, ev("manual", "project_task")),
        (PJ["pj1"], T["t4"], EdgeType.CONTAINS, ev("manual", "project_task")),
        (PJ["pj1"], T["t5"], EdgeType.CONTAINS, ev("manual", "project_task")),
        (PJ["pj1"], T["t6"], EdgeType.CONTAINS, ev("manual", "project_task")),
        (PJ["pj1"], T["t7"], EdgeType.CONTAINS, ev("manual", "project_task")),
        (PJ["pj1"], T["t12"], EdgeType.CONTAINS, ev("manual", "project_task")),
        (PJ["pj1"], T["t14"], EdgeType.CONTAINS, ev("manual", "project_task")),
        (PJ["pj2"], T["t8"], EdgeType.CONTAINS, ev("manual", "project_task")),
        (PJ["pj2"], T["t15"], EdgeType.CONTAINS, ev("manual", "project_task")),
        (PJ["pj3"], T["t10"], EdgeType.CONTAINS, ev("manual", "project_task")),
        (PJ["pj3"], T["t9"], EdgeType.CONTAINS, ev("manual", "project_task")),
        # TAGGED_TO: Project → Goal
        (PJ["pj1"], G["g1"], EdgeType.TAGGED_TO, ev("manual", "project_goal")),
        (PJ["pj1"], G["g2"], EdgeType.TAGGED_TO, ev("manual", "project_goal")),
        (PJ["pj2"], G["g1"], EdgeType.TAGGED_TO, ev("manual", "project_goal")),
        (PJ["pj3"], G["g3"], EdgeType.TAGGED_TO, ev("manual", "project_goal")),
    ]
    return [_edge(f, t, et, evidence) for f, t, et, evidence in edges]


def build_connectors() -> tuple[list[OAuthToken], list[SyncState]]:
    connectors = [
        SourceType.LINEAR,
        SourceType.GITHUB,
        SourceType.SLACK,
        SourceType.NOTION,
        SourceType.DATADOG,
        SourceType.SENTRY,
        SourceType.PAGERDUTY,
        SourceType.AMPLITUDE,
        SourceType.POSTHOG,
        SourceType.FIGMA,
    ]
    tokens = [
        OAuthToken(org_id=ORG_ID, connector=c, access_token=f"seed-fake-token-{c.value}", scopes="read")
        for c in connectors
    ]
    syncs = [
        SyncState(org_id=ORG_ID, connector=c, last_sync_at=_dt(0, 0.1), status=SyncStatus.IDLE) for c in connectors
    ]
    return tokens, syncs


# ── Main seed function ────────────────────────────────────────────────


async def _upsert_entities(db, entities, label):
    """Upsert a list of EntityCreate DTOs into FalkorDB and track the ID mapping."""
    id_map = {}
    for entity_dto in entities:
        result = await upsert_entity(db, entity_dto)
        seed_id = entity_dto.source_ids.get("_seed_id")
        if seed_id:
            # Store as string - FalkorDB entity IDs are strings
            id_map[uuid.UUID(seed_id)] = str(result.id)
    print(f"  {len(entities)} {label}")
    return id_map


async def _upsert_edges(db, edges, entity_id_map):
    """Upsert a list of EdgeCreate DTOs, remapping old IDs to FalkorDB IDs."""
    count = 0
    skipped = 0
    for edge_dto in edges:
        # Remap from/to IDs to FalkorDB-generated IDs
        raw_from = entity_id_map.get(edge_dto.from_entity_id)
        raw_to = entity_id_map.get(edge_dto.to_entity_id)
        if not raw_from or not raw_to:
            skipped += 1
            continue
        from_id = uuid.UUID(raw_from) if isinstance(raw_from, str) else raw_from
        to_id = uuid.UUID(raw_to) if isinstance(raw_to, str) else raw_to
        remapped = EdgeCreate(
            org_id=edge_dto.org_id,
            from_entity_id=from_id,
            to_entity_id=to_id,
            type=edge_dto.type,
            weight=edge_dto.weight,
            confidence=edge_dto.confidence,
            evidence=edge_dto.evidence,
        )
        await upsert_edge(db, remapped)
        count += 1
    if skipped:
        print(f"  {count} edges ({skipped} skipped - missing entity)")
    else:
        print(f"  {count} edges")


async def seed():
    async with async_session() as db:
        # Clean up existing PostgreSQL relational data (order matters for FKs)
        print("Cleaning existing seed data...")
        # Get all member IDs so we can cascade-delete dependent records
        from sqlalchemy import select

        member_ids_result = await db.execute(select(OrgMember.id).where(OrgMember.org_id == ORG_ID))
        member_ids = [row[0] for row in member_ids_result.fetchall()]
        if member_ids:
            # Delete chat messages via conversations
            conv_ids_result = await db.execute(select(Conversation.id).where(Conversation.member_id.in_(member_ids)))
            conv_ids = [row[0] for row in conv_ids_result.fetchall()]
            if conv_ids:
                await db.execute(delete(ChatMessage).where(ChatMessage.conversation_id.in_(conv_ids)))
            await db.execute(delete(Conversation).where(Conversation.member_id.in_(member_ids)))
            await db.execute(delete(Briefing).where(Briefing.org_member_id.in_(member_ids)))
        await db.execute(delete(UrgencyScoreCache).where(UrgencyScoreCache.org_id == ORG_ID))
        await db.execute(delete(LinkSuggestion).where(LinkSuggestion.org_id == ORG_ID))
        await db.execute(delete(PersonResolution).where(PersonResolution.org_id == ORG_ID))
        await db.execute(delete(SyncState).where(SyncState.org_id == ORG_ID))
        await db.execute(delete(OAuthToken).where(OAuthToken.org_id == ORG_ID))
        await db.execute(delete(OrgMember).where(OrgMember.org_id == ORG_ID))
        await db.execute(delete(Organization).where(Organization.id == ORG_ID))
        await db.commit()

        # Clean up FalkorDB graph for this org
        print("Cleaning FalkorDB graph...")
        await delete_org_entities(db, ORG_ID)

        # Ensure FalkorDB indexes
        graph = await get_org_graph(ORG_ID)
        await ensure_indexes(graph)

        # Create org in PostgreSQL (relational data stays in PG)
        org = Organization(id=ORG_ID, name="Numen Test", slug="numen-test")
        db.add(org)
        await db.flush()

        # Track entity ID mapping: seed UUID -> FalkorDB-generated UUID
        entity_id_map = {}

        # Persons -> FalkorDB
        persons = build_persons()
        id_map = await _upsert_entities(db, persons, "person entities")
        entity_id_map.update(id_map)

        # Members -> PostgreSQL (relational, references person entity IDs)
        members = build_members()
        for m in members:
            # Remap person_entity_id to FalkorDB-generated ID
            if m.person_entity_id and m.person_entity_id in entity_id_map:
                new_id = entity_id_map[m.person_entity_id]
                m.person_entity_id = uuid.UUID(new_id) if isinstance(new_id, str) else new_id
        db.add_all(members)
        await db.flush()
        print(f"  {len(members)} org members")

        # All other entities -> FalkorDB
        for builder, label in [
            (build_features, "feature entities"),
            (build_tasks, "task entities"),
            (build_prs, "PR entities"),
            (build_deploys, "deploy entities"),
            (build_goals, "goal entities"),
            (build_decisions, "decision entities"),
            (build_slack_docs, "slack document entities"),
            (build_notion_docs, "notion document entities"),
            (build_datadog_metrics, "datadog metric entities"),
            (build_sentry_errors, "sentry error entities"),
            (build_pagerduty_incidents, "pagerduty incident entities"),
            (build_amplitude_metrics, "amplitude metric entities"),
            (build_posthog_metrics, "posthog metric entities"),
            (build_figma_docs, "figma document entities"),
            (build_projects, "project entities"),
        ]:
            id_map = await _upsert_entities(db, builder(), label)
            entity_id_map.update(id_map)

        # Edges -> FalkorDB (with ID remapping)
        edges = build_edges()
        await _upsert_edges(db, edges, entity_id_map)

        # Connectors -> PostgreSQL
        tokens, syncs = build_connectors()
        db.add_all(tokens)
        db.add_all(syncs)
        print(f"  {len(tokens)} OAuth tokens, {len(syncs)} sync states")

        await db.commit()

        print(f"\nSeed complete! Org '{org.name}' ({org.id})")
        print(f"  Total: {len(entity_id_map)} entities, {len(edges)} edges (in FalkorDB)")
        print(f"  Connectors: {len(tokens)} connected ({', '.join(t.connector.value for t in tokens)})")

    await close_falkor()


if __name__ == "__main__":
    asyncio.run(seed())
