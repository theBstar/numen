"""Core REST API routes - org management, people, entities, graph, urgency."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import (
    ensure_person_entity_for_member,
    get_current_member,
    get_current_user,
    get_current_user_required,
    get_db,
    get_org,
    is_admin_user,
)
from src.api.rate_limit import limiter
from src.api.rbac import (
    ADMIN_ROLES,
    require_role,
)
from src.api.rbac import (
    CROSS_BLOCK_ROLES as _CROSS_BLOCK_ROLES,
)
from src.api.rbac import (
    DELAYED_ROLES as _DELAYED_ROLES,
)
from src.api.rbac import (
    GOALS_ROLES as _GOALS_ROLES,
)
from src.api.rbac import (
    INCIDENT_ROLES as _INCIDENT_ROLES,
)
from src.api.rbac import (
    TEAM_ROLES as _TEAM_ROLES,
)
from src.api.schemas import (
    ClaudeDispatchRequest,
    ClaudeDispatchResponse,
    ConnectorListResponse,
    ConnectorSettingsResponse,
    ConnectorSettingsUpdateRequest,
    ConnectorStatusResponse,
    DashboardSummaryResponse,
    DelayedProjectItem,
    EdgeResponse,
    EntityDetailResponse,
    EntityListResponse,
    EntityResponse,
    FullGraphResponse,
    GitHubRepoListResponse,
    GitHubRepoResponse,
    GoalCreateRequest,
    GoalLinkRequest,
    GoalProgressResponse,
    GoalResponse,
    GoalsSummary,
    GoalUpdateRequest,
    GraphNeighborhoodResponse,
    LinkSuggestionCountResponse,
    LinkSuggestionListResponse,
    LinkSuggestionResponse,
    MemberCreateRequest,
    MemberListResponse,
    MemberResponse,
    MemberUpdateRequest,
    OnboardingRequest,
    OrgCreateRequest,
    OrgGraphResponse,
    OrgListResponse,
    OrgResponse,
    PersonCreateRequest,
    PersonResolutionCountResponse,
    PersonResolutionListResponse,
    PersonResolutionResponse,
    ProjectCreateRequest,
    ProjectListResponse,
    ProjectResponse,
    ProjectUpdateRequest,
    ResolutionLinkRequest,
    SyncTriggerResponse,
    TaskCountsResponse,
    TaskCreateRequest,
    TaskResponse,
    TaskUpdateRequest,
    TeamMemberWorkload,
    UrgencyListResponse,
    UrgencyScoreResponse,
)
from src.graph import (
    compute_goal_progress,
    delete_edges,
    delete_entity,
    get_connected_entity_ids,
    get_cross_team_blocking,
    get_entities_by_ids,
    get_entities_via_edge,
    get_entity_neighborhood,
    get_entity_or_404,
    get_goal_coverage,
    get_goal_tree,
    get_org_graph,
    get_person_workload_hybrid,
    get_project_stats,
    get_stalled_prs,
    get_team_members,
    get_team_workload_summary,
    list_edges,
    merge_entities,
    replace_edges,
    upsert_edge,
    upsert_entity,
)
from src.graph import (
    count_entities as graph_count_entities,
)
from src.graph import (
    get_entity as graph_get_entity,
)
from src.graph import (
    list_entities as graph_list_entities,
)
from src.graph import (
    update_entity as graph_update_entity,
)
from src.shared.models import (
    Edge,
    Entity,
    LinkSuggestion,
    OAuthToken,
    Organization,
    OrgMember,
    PersonResolution,
    SyncState,
    UrgencyScoreCache,
    User,
)
from src.shared.types import (
    EdgeCreate,
    EdgeType,
    EntityCreate,
    EntityType,
    GoalLevel,
    PersonResolutionStatus,
    ProgressMode,
    ProjectStatus,
    RoleType,
    SourceType,
    SyncStatus,
    TaskStatus,
)
from src.shared.webhook_secrets import github_webhook_secret

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["api"])


# ── Organization management ────────────────────────────────────────────


@router.get("/orgs", response_model=OrgListResponse)
async def list_orgs(
    user: User | None = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user is None:
        return OrgListResponse(items=[])

    result = await db.execute(
        select(Organization)
        .join(OrgMember, OrgMember.org_id == Organization.id)
        .where(OrgMember.email == user.email)
        .order_by(Organization.created_at.desc())
    )
    orgs = result.scalars().all()
    return OrgListResponse(items=[OrgResponse.model_validate(o) for o in orgs])


@router.post("/orgs", response_model=OrgResponse)
async def create_org(
    req: OrgCreateRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    org = Organization(name=req.name, slug=req.slug)
    db.add(org)
    await db.flush()

    # Auto-create an OrgMember for the creator if email header is present.
    # Dev-only: gated on settings.allow_header_auth (never True in prod).
    from src.config import settings as _settings

    creator_email = request.headers.get("X-Member-Email") if _settings.allow_header_auth else None
    if creator_email:
        member = OrgMember(
            org_id=org.id,
            email=creator_email,
            display_name=creator_email.split("@")[0],
            role=RoleType.ENGINEER,
        )
        db.add(member)
        await db.flush()
        await ensure_person_entity_for_member(db, member)

    await db.commit()
    await db.refresh(org)
    return org


@router.post("/onboarding", tags=["organizations"])
@limiter.limit("5/minute")
async def complete_onboarding(
    request: Request,
    req: OnboardingRequest,
    user: User = Depends(get_current_user_required),
    db: AsyncSession = Depends(get_db),
):
    """Complete onboarding for a new user - update display name, create org, and add membership."""
    # Update user display_name
    user.display_name = req.display_name
    await db.flush()

    # Map role string to RoleType enum
    role_map = {r.value: r for r in RoleType}
    role = role_map.get(req.role.lower(), RoleType.ENGINEER)

    # Create Organization (check slug uniqueness)
    existing = await db.execute(select(Organization).where(Organization.slug == req.org_slug))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=409, detail=f"Organization with slug '{req.org_slug}' already exists"
        )
    org = Organization(name=req.org_name, slug=req.org_slug)
    db.add(org)
    await db.flush()

    # Create OrgMember
    member = OrgMember(
        org_id=org.id,
        user_id=user.id,
        email=user.email,
        display_name=req.display_name,
        role=role,
    )
    db.add(member)
    await db.flush()
    await ensure_person_entity_for_member(db, member)
    await db.commit()
    await db.refresh(org)

    return OrgResponse.model_validate(org)


@router.get("/orgs/{org_id}", response_model=OrgResponse)
async def get_organization(
    org: Organization = Depends(get_org),
    _member: OrgMember = Depends(get_current_member),
):
    return org


@router.get("/orgs/{org_id}/members", response_model=MemberListResponse)
async def list_members(
    org: Organization = Depends(get_org),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    result = await db.execute(select(OrgMember).where(OrgMember.org_id == org.id).order_by(OrgMember.display_name))
    members = result.scalars().all()
    return MemberListResponse(items=[MemberResponse.model_validate(m) for m in members])


@router.post("/orgs/{org_id}/members", response_model=MemberResponse)
async def create_member(
    req: MemberCreateRequest,
    org: Organization = Depends(get_org),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(require_role(*ADMIN_ROLES)),
):
    member = OrgMember(
        org_id=org.id,
        email=req.email,
        display_name=req.display_name,
        role=req.role,
        timezone=req.timezone,
    )
    db.add(member)
    await db.flush()
    await ensure_person_entity_for_member(db, member)
    await db.commit()
    await db.refresh(member)
    return member


@router.get("/orgs/{org_id}/members/{member_id}", response_model=MemberResponse)
async def get_member(
    member_id: UUID = Path(...),
    org: Organization = Depends(get_org),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    result = await db.execute(select(OrgMember).where(OrgMember.id == member_id, OrgMember.org_id == org.id))
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    return member


@router.put("/orgs/{org_id}/members/{member_id}", response_model=MemberResponse)
async def update_member(
    member_id: UUID = Path(...),
    *,
    req: MemberUpdateRequest,
    org: Organization = Depends(get_org),
    user: User = Depends(get_current_user_required),
    _member: OrgMember = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """Update a member's role/profile. Users can update their own profile; admins can update anyone."""
    result = await db.execute(select(OrgMember).where(OrgMember.id == member_id, OrgMember.org_id == org.id))
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    is_self = member.user_id == user.id or member.email == user.email
    if not is_self and not is_admin_user(user):
        raise HTTPException(status_code=403, detail="Only admins can update other members")

    if req.role is not None:
        member.role = req.role
        # Sync role to the linked Person entity
        if member.person_entity_id:
            person_entity = await graph_get_entity(db, member.person_entity_id, org_id=org.id)
            if person_entity:
                props = dict(person_entity.properties) if person_entity.properties else {}
                props["role"] = req.role.value
                await graph_update_entity(db, member.person_entity_id, org_id=org.id, properties=props)
    if req.display_name is not None:
        member.display_name = req.display_name
        # Sync name to the linked Person entity
        if member.person_entity_id:
            await graph_update_entity(db, member.person_entity_id, org_id=org.id, canonical_name=req.display_name)
    if req.timezone is not None:
        member.timezone = req.timezone

    if req.briefing_hour is not None or req.briefing_channel is not None:
        if req.briefing_channel == "slack":
            slack_token = await db.execute(
                select(OAuthToken).where(
                    OAuthToken.org_id == org.id,
                    OAuthToken.connector == SourceType.SLACK,
                )
            )
            if slack_token.scalar_one_or_none() is None:
                raise HTTPException(
                    status_code=400,
                    detail="Slack is not connected for this organization",
                )

        prefs = dict(member.preferences or {})
        if req.briefing_hour is not None:
            prefs["briefing_hour"] = req.briefing_hour
        if req.briefing_channel is not None:
            prefs["briefing_channel"] = req.briefing_channel
        member.preferences = prefs

    await db.commit()
    await db.refresh(member)
    return member


# ── People / Org Graph ────────────────────────────────────────────────


@router.get("/orgs/{org_id}/people/graph")
async def get_people_graph(
    org_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    """Return all people and their REPORTS_TO edges for org tree visualization."""
    # Auto-seed Person entities for any OrgMembers that don't have one yet
    members_result = await db.execute(
        select(OrgMember).where(OrgMember.org_id == org_id, OrgMember.person_entity_id.is_(None))
    )
    unlinked_members = list(members_result.scalars().all())
    for member in unlinked_members:
        await ensure_person_entity_for_member(db, member)
    if unlinked_members:
        await db.flush()

    people = await graph_list_entities(db, org_id, entity_type=EntityType.PERSON)

    edges = await list_edges(db, org_id=org_id, edge_type=EdgeType.REPORTS_TO)
    # Filter edges to only those between people in this set
    people_ids = {p.id for p in people}
    edges = [e for e in edges if e.from_entity_id in people_ids and e.to_entity_id in people_ids]

    return OrgGraphResponse(
        people=[EntityResponse.model_validate(p) for p in people],
        edges=[EdgeResponse.model_validate(e) for e in edges],
    )


@router.post("/orgs/{org_id}/people")
async def create_person(
    org_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
    *,
    req: PersonCreateRequest,
):
    """Create a person entity with optional REPORTS_TO edge to a manager."""
    person = await upsert_entity(
        db,
        EntityCreate(
            org_id=org_id,
            type=EntityType.PERSON,
            source=SourceType.MANUAL,
            source_ids={},
            canonical_name=req.name,
            properties={
                "email": req.email or "",
                "role": req.role.value if hasattr(req.role, "value") else req.role,
                "title": req.title or "",
            },
        ),
    )

    if req.manager_id:
        await upsert_edge(
            db,
            EdgeCreate(
                org_id=org_id,
                from_entity_id=person.id,
                to_entity_id=req.manager_id,
                type=EdgeType.REPORTS_TO,
                weight=1.0,
                confidence=1.0,
                evidence=[{"source": "manual", "note": "Created via org graph"}],
            ),
        )

    await db.commit()
    await db.refresh(person)
    return EntityResponse.model_validate(person)


# ── Person resolution ─────────────────────────────────────────────────


@router.get("/orgs/{org_id}/people/resolutions", response_model=PersonResolutionListResponse)
async def list_person_resolutions(
    org_id: UUID = Path(...),
    status: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    """List person resolution candidates, optionally filtered by status."""
    query = select(PersonResolution).where(PersonResolution.org_id == org_id)
    if status:
        query = query.where(PersonResolution.status == status)
    query = query.order_by(PersonResolution.confidence.desc())

    result = await db.execute(query)
    resolutions = list(result.scalars().all())

    items = []
    for r in resolutions:
        candidate = await graph_get_entity(db, r.candidate_entity_id, org_id=org_id)
        match = await graph_get_entity(db, r.match_entity_id, org_id=org_id)
        if not candidate or not match:
            continue
        if candidate.merged_into is not None or match.merged_into is not None:
            continue
        items.append(
            PersonResolutionResponse(
                id=r.id,
                candidate=EntityResponse.model_validate(candidate),
                match=EntityResponse.model_validate(match),
                confidence=r.confidence,
                match_reasons=r.match_reasons,
                status=r.status,
                created_at=r.created_at,
            )
        )

    return PersonResolutionListResponse(items=items)


@router.get("/orgs/{org_id}/people/resolutions/count", response_model=PersonResolutionCountResponse)
async def count_person_resolutions(
    org_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    """Count pending person resolutions for badge display.

    Excludes stale resolutions where an entity has been merged,
    and auto-marks them so they stop showing up.
    """
    result = await db.execute(
        select(PersonResolution).where(
            PersonResolution.org_id == org_id,
            PersonResolution.status == PersonResolutionStatus.PENDING,
        )
    )
    resolutions = list(result.scalars().all())

    count = 0
    for r in resolutions:
        candidate = await graph_get_entity(db, r.candidate_entity_id, org_id=org_id)
        match_ent = await graph_get_entity(db, r.match_entity_id, org_id=org_id)
        if not candidate or not match_ent or candidate.merged_into is not None or match_ent.merged_into is not None:
            r.status = PersonResolutionStatus.MERGED
            r.resolved_at = datetime.now(timezone.utc)
            continue
        count += 1

    await db.commit()
    return PersonResolutionCountResponse(pending=count)


@router.post(
    "/orgs/{org_id}/people/resolutions/{resolution_id}/merge",
    response_model=PersonResolutionResponse,
)
async def merge_person_resolution(
    org_id: UUID = Path(...),
    resolution_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    """Merge the candidate entity into the match entity."""
    resolution = await db.get(PersonResolution, resolution_id)
    if not resolution or resolution.org_id != org_id:
        raise HTTPException(status_code=404, detail="Resolution not found")
    if resolution.status != PersonResolutionStatus.PENDING:
        raise HTTPException(
            status_code=400, detail=f"Resolution already resolved as '{resolution.status}'"
        )

    # Merge candidate into match (match is the primary/existing entity)
    primary = await merge_entities(db, resolution.match_entity_id, resolution.candidate_entity_id, org_id=org_id)

    resolution.status = PersonResolutionStatus.MERGED
    resolution.resolved_at = datetime.now(timezone.utc)
    await db.commit()

    # After merge, candidate no longer exists - return match as both
    return PersonResolutionResponse(
        id=resolution.id,
        candidate=EntityResponse.model_validate(primary),
        match=EntityResponse.model_validate(primary),
        confidence=resolution.confidence,
        match_reasons=resolution.match_reasons,
        status=resolution.status,
        created_at=resolution.created_at,
    )


@router.post(
    "/orgs/{org_id}/people/resolutions/{resolution_id}/distinct",
    response_model=PersonResolutionResponse,
)
async def mark_resolution_distinct(
    org_id: UUID = Path(...),
    resolution_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    """Mark two entities as distinct people - will never be re-flagged."""
    resolution = await db.get(PersonResolution, resolution_id)
    if not resolution or resolution.org_id != org_id:
        raise HTTPException(status_code=404, detail="Resolution not found")
    if resolution.status != PersonResolutionStatus.PENDING:
        raise HTTPException(
            status_code=400, detail=f"Resolution already resolved as '{resolution.status}'"
        )

    resolution.status = PersonResolutionStatus.DISTINCT
    resolution.resolved_at = datetime.now(timezone.utc)
    await db.commit()

    candidate = await graph_get_entity(db, resolution.candidate_entity_id, org_id=org_id)
    match = await graph_get_entity(db, resolution.match_entity_id, org_id=org_id)
    return PersonResolutionResponse(
        id=resolution.id,
        candidate=EntityResponse.model_validate(candidate),
        match=EntityResponse.model_validate(match),
        confidence=resolution.confidence,
        match_reasons=resolution.match_reasons,
        status=resolution.status,
        created_at=resolution.created_at,
    )


@router.post(
    "/orgs/{org_id}/people/resolutions/{resolution_id}/dismiss",
    response_model=PersonResolutionResponse,
)
async def dismiss_person_resolution(
    org_id: UUID = Path(...),
    resolution_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    """Dismiss a resolution - hides it but can be re-surfaced."""
    resolution = await db.get(PersonResolution, resolution_id)
    if not resolution or resolution.org_id != org_id:
        raise HTTPException(status_code=404, detail="Resolution not found")
    if resolution.status != PersonResolutionStatus.PENDING:
        raise HTTPException(
            status_code=400, detail=f"Resolution already resolved as '{resolution.status}'"
        )

    resolution.status = PersonResolutionStatus.DISMISSED
    resolution.resolved_at = datetime.now(timezone.utc)
    await db.commit()

    candidate = await graph_get_entity(db, resolution.candidate_entity_id, org_id=org_id)
    match = await graph_get_entity(db, resolution.match_entity_id, org_id=org_id)
    return PersonResolutionResponse(
        id=resolution.id,
        candidate=EntityResponse.model_validate(candidate),
        match=EntityResponse.model_validate(match),
        confidence=resolution.confidence,
        match_reasons=resolution.match_reasons,
        status=resolution.status,
        created_at=resolution.created_at,
    )


@router.post(
    "/orgs/{org_id}/people/resolutions/{resolution_id}/link",
    response_model=PersonResolutionResponse,
)
async def link_person_resolution(
    org_id: UUID = Path(...),
    resolution_id: UUID = Path(...),
    req: ResolutionLinkRequest = ...,
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    """Link the candidate to a different person entity instead of the suggested match."""
    resolution = await db.get(PersonResolution, resolution_id)
    if not resolution or resolution.org_id != org_id:
        raise HTTPException(status_code=404, detail="Resolution not found")
    if resolution.status != PersonResolutionStatus.PENDING:
        raise HTTPException(
            status_code=400, detail=f"Resolution already resolved as '{resolution.status}'"
        )

    target = await graph_get_entity(db, req.target_entity_id, org_id=org_id)
    if not target or target.type != EntityType.PERSON:
        raise HTTPException(status_code=404, detail="Target person entity not found")

    # Merge candidate into the user-specified target
    primary = await merge_entities(db, req.target_entity_id, resolution.candidate_entity_id, org_id=org_id)

    resolution.status = PersonResolutionStatus.MERGED
    resolution.resolved_at = datetime.now(timezone.utc)
    await db.commit()

    return PersonResolutionResponse(
        id=resolution.id,
        candidate=EntityResponse.model_validate(primary),
        match=EntityResponse.model_validate(primary),
        confidence=resolution.confidence,
        match_reasons=resolution.match_reasons,
        status=resolution.status,
        created_at=resolution.created_at,
    )


@router.post("/orgs/{org_id}/people/merge")
async def merge_people(
    org_id: UUID = Path(...),
    primary_id: UUID = Query(..., description="The person entity to keep"),
    duplicate_id: UUID = Query(..., description="The person entity to merge into the primary"),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(require_role(*ADMIN_ROLES)),
):
    """Manually merge two person entities. The duplicate is absorbed into the primary."""
    primary = await graph_get_entity(db, primary_id, org_id=org_id)
    duplicate = await graph_get_entity(db, duplicate_id, org_id=org_id)

    if not primary or primary.type != EntityType.PERSON.value:
        raise HTTPException(status_code=404, detail="Primary person entity not found")
    if not duplicate or duplicate.type != EntityType.PERSON.value:
        raise HTTPException(status_code=404, detail="Duplicate person entity not found")
    if primary_id == duplicate_id:
        raise HTTPException(status_code=400, detail="Cannot merge an entity with itself")

    merged = await merge_entities(db, primary_id, duplicate_id, org_id=org_id)
    await db.commit()

    return EntityResponse.model_validate(merged)


# ── Entities ───────────────────────────────────────────────────────────


@router.get("/orgs/{org_id}/entities", response_model=EntityListResponse)
async def list_entities_endpoint(
    org_id: UUID = Path(...),
    type: EntityType | None = Query(None),
    source: SourceType | None = Query(None),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    total = await graph_count_entities(
        db, org_id, entity_type=type, source=source, search=search
    )
    entities = await graph_list_entities(
        db,
        org_id,
        entity_type=type,
        source=source,
        search=search,
        limit=page_size,
        offset=(page - 1) * page_size,
    )

    return EntityListResponse(
        items=[EntityResponse.model_validate(e) for e in entities],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/orgs/{org_id}/entities/{entity_id}", response_model=EntityDetailResponse)
async def get_entity_endpoint(
    org_id: UUID = Path(...),
    entity_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    entity = await get_entity_or_404(db, entity_id, org_id=org_id)

    edges = await list_edges(db, org_id=org_id, entity_id=entity_id, direction="both")

    return EntityDetailResponse(
        entity=EntityResponse.model_validate(entity),
        edges=[EdgeResponse.model_validate(e) for e in edges],
    )


# ── Context graph (full org) ──────────────────────────────────────────


@router.get("/orgs/{org_id}/graph", response_model=FullGraphResponse)
async def get_full_graph(
    org_id: UUID = Path(...),
    entity_types: str | None = Query(None, description="Comma-separated entity types to include"),
    edge_types: str | None = Query(None, description="Comma-separated edge types to include"),
    search: str | None = Query(None, description="Filter entities by name (case-insensitive)"),
    limit: int = Query(500, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    from src.shared.types import EdgeType, EntityType

    parsed_entity_types = None
    if entity_types:
        parsed_entity_types = [EntityType(t.strip()) for t in entity_types.split(",") if t.strip()]

    parsed_edge_types = None
    if edge_types:
        parsed_edge_types = [EdgeType(t.strip()) for t in edge_types.split(",") if t.strip()]

    graph_data = await get_org_graph(
        db,
        org_id,
        entity_types=parsed_entity_types,
        edge_types=parsed_edge_types,
        search=search,
        limit=limit,
        offset=offset,
    )
    return FullGraphResponse(
        entities=[EntityResponse.model_validate(e) for e in graph_data["entities"]],
        edges=[EdgeResponse.model_validate(e) for e in graph_data["edges"]],
        total_entities=graph_data["total_entities"],
        total_edges=graph_data["total_edges"],
        has_more=graph_data["has_more"],
    )


# ── Graph neighborhood ─────────────────────────────────────────────────


@router.get("/orgs/{org_id}/graph/{entity_id}", response_model=GraphNeighborhoodResponse)
async def get_graph_neighborhood(
    org_id: UUID = Path(...),
    entity_id: UUID = Path(...),
    depth: int = Query(2, ge=1, le=4),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    await get_entity_or_404(db, entity_id, org_id=org_id)
    result = await get_entity_neighborhood(db, entity_id, depth=depth, org_id=org_id)
    return GraphNeighborhoodResponse(
        entities=[EntityResponse.model_validate(e) for e in result.get("entities", [])],
        edges=[EdgeResponse.model_validate(e) for e in result.get("edges", [])],
    )


# ── Urgency scores ─────────────────────────────────────────────────────


@router.get("/orgs/{org_id}/urgency", response_model=UrgencyListResponse)
async def get_urgency(
    org_id: UUID = Path(...),
    limit: int = Query(10, ge=1, le=50),
    member: OrgMember = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(UrgencyScoreCache)
        .where(
            UrgencyScoreCache.org_id == org_id,
            UrgencyScoreCache.person_id == member.person_entity_id,
        )
        .order_by(UrgencyScoreCache.score.desc())
        .limit(limit)
    )
    score_caches = result.scalars().all()

    entity_ids = [sc.entity_id for sc in score_caches]
    entities = await get_entities_by_ids(db, entity_ids)
    entity_map = {e.id: e for e in entities}

    items = []
    for score_cache in score_caches:
        entity = entity_map.get(score_cache.entity_id)
        if not entity:
            continue
        items.append(
            UrgencyScoreResponse(
                entity_id=score_cache.entity_id,
                entity_name=entity.canonical_name,
                entity_type=entity.type,
                score=score_cache.score,
                score_components=score_cache.score_components or {},
                goal_ids=score_cache.goal_ids or [],
                provenance=score_cache.provenance or [],
                computed_at=score_cache.computed_at,
            )
        )

    return UrgencyListResponse(items=items, person_id=member.person_entity_id, role=member.role)


# ── Goals ─────────────────────────────────────────────────────────────


def _goal_response(
    entity: Entity,
    child_ids: list[UUID] | None = None,
    project_ids: list[UUID] | None = None,
    computed_progress: float | None = None,
) -> GoalResponse:
    props = entity.properties or {}
    return GoalResponse(
        id=entity.id,
        title=entity.canonical_name,
        level=props.get("level", GoalLevel.TEAM),
        status=props.get("status", ProjectStatus.ACTIVE),
        key_results=props.get("key_results", []),
        target_value=props.get("target_value"),
        current_value=props.get("current_value"),
        computed_progress=computed_progress,
        owner=props.get("owner_email"),
        parent_goal_id=None,  # resolved via edges
        child_goal_ids=child_ids or [],
        linked_project_ids=project_ids or [],
        time_bound_start=props.get("time_bound_start"),
        time_bound_end=props.get("time_bound_end"),
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


@router.get("/orgs/{org_id}/goals")
async def list_goals(
    org_id: UUID = Path(...),
    level: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    goals = await graph_list_entities(db, org_id, entity_type=EntityType.GOAL)

    items = []
    for g in goals:
        props = g.properties or {}
        if props.get("status") == TaskStatus.ARCHIVED:
            continue
        if level and props.get("level") != level:
            continue
        # Get children
        child_ids = await get_connected_entity_ids(
            db, g.id, EdgeType.PARENT_OF, direction="outgoing"
        )
        # Get linked projects
        linked_projects = await get_entities_via_edge(
            db, g.id, EdgeType.TAGGED_TO, direction="incoming", target_type=EntityType.PROJECT
        )
        project_ids = [p.id for p in linked_projects]
        # Compute progress
        progress_data = await compute_goal_progress(db, g.id)
        items.append(
            _goal_response(g, child_ids, project_ids, progress_data.get("computed_progress"))
        )

    return {"items": items}


@router.get("/orgs/{org_id}/goals/tree")
async def get_goal_tree_endpoint(
    org_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    tree = await get_goal_tree(db, org_id)
    return {"items": tree}


@router.get("/orgs/{org_id}/goals/{goal_id}", response_model=GoalResponse)
async def get_goal(
    org_id: UUID = Path(...),
    goal_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    entity = await get_entity_or_404(db, goal_id, org_id=org_id, expected_type=EntityType.GOAL)
    progress_data = await compute_goal_progress(db, goal_id)
    return _goal_response(entity, computed_progress=progress_data.get("computed_progress"))


@router.post("/orgs/{org_id}/goals", response_model=GoalResponse)
async def create_goal(
    req: GoalCreateRequest,
    org_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    import uuid as _uuid

    entity = await upsert_entity(
        db,
        EntityCreate(
            org_id=org_id,
            type=EntityType.GOAL,
            source=SourceType.MANUAL,
            source_ids={"manual": f"goal-{_uuid.uuid4().hex[:8]}"},
            canonical_name=req.title,
            properties={
                "level": req.level,
                "status": ProjectStatus.ACTIVE,
                "key_results": [kr.model_dump() for kr in req.key_results],
                "target_value": req.target_value,
                "current_value": 0,
                "owner_email": req.owner_email,
                "time_bound_start": req.time_bound_start.isoformat()
                if req.time_bound_start
                else None,
                "time_bound_end": req.time_bound_end.isoformat() if req.time_bound_end else None,
                "progress_mode": ProgressMode.MANUAL,
            },
        ),
    )
    if req.parent_goal_id:
        await upsert_edge(
            db,
            EdgeCreate(
                org_id=org_id,
                from_entity_id=req.parent_goal_id,
                to_entity_id=entity.id,
                type=EdgeType.PARENT_OF,
                evidence=[{"source": "manual"}],
            ),
        )
    await db.commit()
    return _goal_response(entity)


@router.put("/orgs/{org_id}/goals/{goal_id}", response_model=GoalResponse)
async def update_goal(
    req: GoalUpdateRequest,
    org_id: UUID = Path(...),
    goal_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    entity = await get_entity_or_404(db, goal_id, org_id=org_id, expected_type=EntityType.GOAL)

    props = dict(entity.properties or {})
    new_name = None
    if req.title is not None:
        new_name = req.title
    for field in ("level", "status", "target_value", "current_value", "owner_email"):
        val = getattr(req, field, None)
        if val is not None:
            if field == "owner_email":
                props["owner_email"] = val
            else:
                props[field] = val
    if req.key_results is not None:
        props["key_results"] = [kr.model_dump() for kr in req.key_results]
    if req.time_bound_start is not None:
        props["time_bound_start"] = req.time_bound_start.isoformat()
    if req.time_bound_end is not None:
        props["time_bound_end"] = req.time_bound_end.isoformat()
    entity = await graph_update_entity(db, goal_id, canonical_name=new_name, properties=props)

    await db.commit()
    return _goal_response(entity)


@router.delete("/orgs/{org_id}/goals/{goal_id}")
async def delete_goal(
    org_id: UUID = Path(...),
    goal_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(require_role(*_GOALS_ROLES)),
):
    entity = await get_entity_or_404(db, goal_id, org_id=org_id, expected_type=EntityType.GOAL)
    # Soft delete
    props = dict(entity.properties or {})
    props["status"] = TaskStatus.ARCHIVED
    await graph_update_entity(db, goal_id, properties=props)
    await db.commit()
    return {"ok": True}


@router.post("/orgs/{org_id}/goals/{goal_id}/links")
async def link_entity_to_goal(
    req: GoalLinkRequest,
    org_id: UUID = Path(...),
    goal_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    await upsert_edge(
        db,
        EdgeCreate(
            org_id=org_id,
            from_entity_id=req.entity_id,
            to_entity_id=goal_id,
            type=EdgeType.TAGGED_TO,
            evidence=[{"source": "manual"}],
        ),
    )
    await db.commit()
    return {"ok": True}


@router.get("/orgs/{org_id}/goals/{goal_id}/progress", response_model=GoalProgressResponse)
async def get_goal_progress(
    org_id: UUID = Path(...),
    goal_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    data = await compute_goal_progress(db, goal_id)
    return GoalProgressResponse(goal_id=goal_id, **data)


# ── Projects ──────────────────────────────────────────────────────────


def _project_response(
    entity: Entity, db_edges: list[Edge] | None = None, all_tasks: list[Entity] | None = None
) -> ProjectResponse:
    """Build a ProjectResponse from a PROJECT entity."""
    props = entity.properties or {}
    task_list = all_tasks or []
    tasks_done = sum(1 for t in task_list if (t.properties or {}).get("status") == TaskStatus.DONE)
    goal_ids = []
    if db_edges:
        goal_ids = [e.to_entity_id for e in db_edges if e.type == EdgeType.TAGGED_TO]
    return ProjectResponse(
        id=entity.id,
        name=entity.canonical_name,
        description=props.get("description"),
        status=props.get("status", "planning"),
        owner=props.get("owner_email"),
        start_date=props.get("start_date"),
        end_date=props.get("end_date"),
        task_count=len(task_list),
        tasks_done=tasks_done,
        goal_ids=goal_ids,
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


@router.get("/orgs/{org_id}/projects", response_model=ProjectListResponse)
async def list_projects(
    org_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    projects = await graph_list_entities(db, org_id, entity_type=EntityType.PROJECT)

    items = []
    for p in projects:
        # Get tasks linked to this project via CONTAINS edges
        tasks = await get_entities_via_edge(
            db, p.id, EdgeType.CONTAINS, direction="outgoing", target_type=EntityType.TASK
        )
        edges = await list_edges(db, from_entity_id=p.id, edge_type=EdgeType.TAGGED_TO)
        items.append(_project_response(p, edges, tasks))

    return ProjectListResponse(items=items, total=len(items))


@router.get("/orgs/{org_id}/projects/{project_id}", response_model=ProjectResponse)
async def get_project(
    org_id: UUID = Path(...),
    project_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    project = await get_entity_or_404(
        db, project_id, org_id=org_id, expected_type=EntityType.PROJECT
    )
    return _project_response(project)


@router.post("/orgs/{org_id}/projects", response_model=ProjectResponse)
async def create_project(
    req: ProjectCreateRequest,
    org_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    entity = await upsert_entity(
        db,
        EntityCreate(
            org_id=org_id,
            type=EntityType.PROJECT,
            source=SourceType.MANUAL,
            source_ids={"manual": f"project-{req.name.lower().replace(' ', '-')}"},
            canonical_name=req.name,
            properties={
                "description": req.description,
                "status": req.status,
                "owner_email": req.owner_email,
                "start_date": req.start_date,
                "end_date": req.end_date,
            },
        ),
    )
    # Link to goals
    for gid in req.goal_ids:
        await upsert_edge(
            db,
            EdgeCreate(
                org_id=org_id,
                from_entity_id=entity.id,
                to_entity_id=gid,
                type=EdgeType.TAGGED_TO,
                evidence=[{"source": "manual"}],
            ),
        )
    await db.commit()
    return _project_response(entity)


@router.put("/orgs/{org_id}/projects/{project_id}", response_model=ProjectResponse)
async def update_project(
    req: ProjectUpdateRequest,
    org_id: UUID = Path(...),
    project_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    entity = await get_entity_or_404(
        db, project_id, org_id=org_id, expected_type=EntityType.PROJECT
    )

    props = dict(entity.properties or {})
    new_name = None
    if req.name is not None:
        new_name = req.name
    for field in ("description", "status", "owner_email", "start_date", "end_date"):
        val = getattr(req, field, None)
        if val is not None:
            props[field] = val
    entity = await graph_update_entity(db, project_id, canonical_name=new_name, properties=props)

    if req.goal_ids is not None:
        await replace_edges(
            db,
            project_id,
            EdgeType.TAGGED_TO,
            "outgoing",
            req.goal_ids,
            org_id,
            evidence=[{"source": "manual"}],
        )

    await db.commit()
    return _project_response(entity)


@router.delete("/orgs/{org_id}/projects/{project_id}")
async def delete_project(
    org_id: UUID = Path(...),
    project_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(require_role(*_GOALS_ROLES)),
):
    await get_entity_or_404(db, project_id, org_id=org_id, expected_type=EntityType.PROJECT)
    await delete_entity(db, project_id, org_id=org_id)
    await db.commit()
    return {"ok": True}


@router.get("/orgs/{org_id}/projects/{project_id}/tasks")
async def get_project_tasks_endpoint(
    org_id: UUID = Path(...),
    project_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    tasks = await get_entities_via_edge(
        db, project_id, EdgeType.CONTAINS, direction="outgoing", target_type=EntityType.TASK
    )
    return {"items": [_task_response(t) for t in tasks]}


# ── Tasks ─────────────────────────────────────────────────────────────


_STATE_TYPE_MAP = {
    "backlog": TaskStatus.BACKLOG,
    "unstarted": TaskStatus.TODO,
    "started": TaskStatus.IN_PROGRESS,
    "completed": TaskStatus.DONE,
    "cancelled": TaskStatus.DONE,
}


def _normalize_task_status(props: dict) -> str:
    """Normalize Linear state/state_type or manual status to standard values."""
    # If there's an explicit status in our format, use it
    status = props.get("status", "")
    if status.lower().replace(" ", "_") in (
        TaskStatus.TODO,
        TaskStatus.IN_PROGRESS,
        TaskStatus.IN_REVIEW,
        TaskStatus.MERGED,
        TaskStatus.DONE,
        TaskStatus.BACKLOG,
    ):
        return status.lower().replace(" ", "_")
    # Fall back to Linear's state_type
    state_type = props.get("state_type", "")
    return _STATE_TYPE_MAP.get(state_type, TaskStatus.TODO)


def _task_response(
    entity: Entity,
    project_id: UUID | None = None,
    goal_ids: list[UUID] | None = None,
) -> TaskResponse:
    """Build a TaskResponse from a TASK entity."""
    props = entity.properties or {}
    return TaskResponse(
        id=entity.id,
        title=props.get("title", entity.canonical_name),
        description=props.get("description"),
        status=_normalize_task_status(props),
        priority=_priority_from_int(props.get("priority", 3)),
        assignee=props.get("assignee_email"),
        due_date=props.get("due_date"),
        source=entity.source,
        project_id=project_id,
        goal_ids=goal_ids or [],
        labels=props.get("labels", []),
        created_at=entity.created_at,
        updated_at=entity.updated_at,
    )


async def _resolve_task_edges(
    db: AsyncSession, task_id: UUID, org_id: UUID
) -> tuple[UUID | None, list[UUID]]:
    """Resolve project_id and goal_ids for a task from edges."""
    # Project: edge where project --CONTAINS--> task
    project_ids = await get_connected_entity_ids(
        db, task_id, EdgeType.CONTAINS, direction="incoming", org_id=org_id
    )
    project_id = project_ids[0] if project_ids else None

    # Goals: edge where task --TAGGED_TO--> goal
    goal_ids = await get_connected_entity_ids(
        db, task_id, EdgeType.TAGGED_TO, direction="outgoing", org_id=org_id
    )

    return project_id, goal_ids


def _priority_from_int(val) -> str:
    """Convert Linear priority int (0-4) or string to standard priority string."""
    if isinstance(val, str):
        return val
    mapping = {0: "none", 1: "urgent", 2: "high", 3: "medium", 4: "low"}
    return mapping.get(val, "medium")


@router.get("/orgs/{org_id}/tasks")
async def list_tasks(
    org_id: UUID = Path(...),
    status: str | None = Query(None),
    priority: str | None = Query(None),
    assignee: str | None = Query(None),
    project_id: UUID | None = Query(None),
    goal_id: UUID | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    tasks = await graph_list_entities(db, org_id, entity_type=EntityType.TASK, limit=100)

    items = []
    for t in tasks:
        pid, gids = await _resolve_task_edges(db, t.id, org_id)
        resp = _task_response(t, project_id=pid, goal_ids=gids)
        # Apply filters on properties
        if status and resp.status != status:
            continue
        if priority and resp.priority != priority:
            continue
        if assignee and resp.assignee != assignee:
            continue
        items.append(resp)

    return {"items": items}


@router.get("/orgs/{org_id}/tasks/{task_id}", response_model=TaskResponse)
async def get_task(
    org_id: UUID = Path(...),
    task_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    entity = await get_entity_or_404(db, task_id, org_id=org_id, expected_type=EntityType.TASK)
    pid, gids = await _resolve_task_edges(db, entity.id, org_id)
    return _task_response(entity, project_id=pid, goal_ids=gids)


@router.post("/orgs/{org_id}/tasks", response_model=TaskResponse)
async def create_task(
    req: TaskCreateRequest,
    org_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    entity = await upsert_entity(
        db,
        EntityCreate(
            org_id=org_id,
            type=EntityType.TASK,
            source=SourceType.MANUAL,
            source_ids={"manual": f"task-{req.title.lower().replace(' ', '-')[:40]}"},
            canonical_name=req.title,
            properties={
                "title": req.title,
                "description": req.description,
                "status": req.status,
                "priority": req.priority,
                "assignee_email": req.assignee_email,
                "due_date": req.due_date.isoformat() if req.due_date else None,
                "labels": req.labels,
            },
        ),
    )
    # Link to project
    if req.project_id:
        await upsert_edge(
            db,
            EdgeCreate(
                org_id=org_id,
                from_entity_id=req.project_id,
                to_entity_id=entity.id,
                type=EdgeType.CONTAINS,
                evidence=[{"source": "manual"}],
            ),
        )
    # Link to goals
    for gid in req.goal_ids:
        await upsert_edge(
            db,
            EdgeCreate(
                org_id=org_id,
                from_entity_id=entity.id,
                to_entity_id=gid,
                type=EdgeType.TAGGED_TO,
                evidence=[{"source": "manual"}],
            ),
        )
    await db.commit()
    pid, gids = await _resolve_task_edges(db, entity.id, org_id)
    return _task_response(entity, project_id=pid, goal_ids=gids)


@router.put("/orgs/{org_id}/tasks/{task_id}", response_model=TaskResponse)
async def update_task(
    req: TaskUpdateRequest,
    org_id: UUID = Path(...),
    task_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    entity = await get_entity_or_404(db, task_id, org_id=org_id, expected_type=EntityType.TASK)

    props = dict(entity.properties or {})
    new_name = None
    if req.title is not None:
        new_name = req.title
        props["title"] = req.title
    for field in ("description", "status", "priority", "assignee_email", "labels"):
        val = getattr(req, field, None)
        if val is not None:
            props[field] = val
    if req.due_date is not None:
        props["due_date"] = req.due_date.isoformat()
    entity = await graph_update_entity(db, task_id, canonical_name=new_name, properties=props)

    # Update project link (CONTAINS edge)
    if req.project_id is not None:
        # Remove existing project edges pointing to this task
        await delete_edges(db, task_id, edge_type=EdgeType.CONTAINS, direction="incoming")
        # Add new project edge if not clearing
        if req.project_id:
            await upsert_edge(
                db,
                EdgeCreate(
                    org_id=org_id,
                    from_entity_id=req.project_id,
                    to_entity_id=task_id,
                    type=EdgeType.CONTAINS,
                    evidence=[{"source": "manual"}],
                ),
            )

    # Update goal links (TAGGED_TO edges)
    if req.goal_ids is not None:
        await replace_edges(
            db,
            task_id,
            EdgeType.TAGGED_TO,
            "outgoing",
            req.goal_ids,
            org_id,
            evidence=[{"source": "manual"}],
        )

    await db.commit()
    pid, gids = await _resolve_task_edges(db, entity.id, org_id)
    return _task_response(entity, project_id=pid, goal_ids=gids)


@router.delete("/orgs/{org_id}/tasks/{task_id}")
async def delete_task(
    org_id: UUID = Path(...),
    task_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    await get_entity_or_404(db, task_id, org_id=org_id, expected_type=EntityType.TASK)
    await delete_entity(db, task_id, org_id=org_id)
    await db.commit()
    return {"ok": True}


# ── Connector status ───────────────────────────────────────────────────


@router.get("/orgs/{org_id}/connectors", response_model=ConnectorListResponse)
async def get_connector_status(
    org_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    v1_connectors = [
        SourceType.LINEAR,
        SourceType.GITHUB,
        SourceType.SLACK,
        SourceType.JIRA,
        SourceType.NOTION,
        SourceType.DATADOG,
        SourceType.SENTRY,
        SourceType.PAGERDUTY,
        SourceType.AMPLITUDE,
        SourceType.POSTHOG,
        SourceType.FIGMA,
    ]

    tokens_result = await db.execute(select(OAuthToken).where(OAuthToken.org_id == org_id))
    tokens = {t.connector: t for t in tokens_result.scalars().all()}

    syncs_result = await db.execute(select(SyncState).where(SyncState.org_id == org_id))
    syncs = {s.connector: s for s in syncs_result.scalars().all()}

    connectors = []
    for source in v1_connectors:
        sync = syncs.get(source)
        token = tokens.get(source)
        granted = {s.strip() for s in (token.scopes or "").split(",") if s.strip()} if token else set()
        needs_reauth = (
            token is not None
            and source == SourceType.SLACK
            and not {"chat:write", "im:write"}.issubset(granted)
        )
        connectors.append(
            ConnectorStatusResponse(
                connector=source,
                connected=token is not None,
                last_sync_at=sync.last_sync_at if sync else None,
                status=sync.status if sync else SyncStatus.IDLE,
                error_message=sync.error_message if sync else None,
                needs_reauth=needs_reauth,
            )
        )

    return ConnectorListResponse(items=connectors)


@router.get("/orgs/{org_id}/connectors/github/repos", response_model=GitHubRepoListResponse)
async def list_github_repos(
    org_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    """List all GitHub repos accessible to the connected token."""
    import httpx

    token_result = await db.execute(
        select(OAuthToken).where(
            OAuthToken.org_id == org_id,
            OAuthToken.connector == SourceType.GITHUB,
        )
    )
    token = token_result.scalar_one_or_none()
    if not token:
        raise HTTPException(status_code=404, detail="GitHub not connected")

    selected = set((token.settings or {}).get("selected_repos", []))

    repos: list[GitHubRepoResponse] = []
    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {token.access_token}", "Accept": "application/json"},
        timeout=httpx.Timeout(30.0, connect=10.0),
    ) as client:
        next_url: str | None = "https://api.github.com/user/repos"
        params: dict[str, str] | None = {"per_page": "100", "sort": "updated"}

        while next_url:
            resp = await client.get(next_url, params=params)
            resp.raise_for_status()
            for r in resp.json():
                repos.append(
                    GitHubRepoResponse(
                        full_name=r["full_name"],
                        name=r["name"],
                        owner=r.get("owner", {}).get("login", ""),
                        private=r.get("private", False),
                        description=r.get("description"),
                        enabled=r["full_name"] in selected,
                    )
                )
            # Follow pagination
            params = None
            next_url = None
            link_header = resp.headers.get("link", "")
            for part in link_header.split(","):
                if 'rel="next"' in part:
                    start = part.index("<") + 1
                    end = part.index(">")
                    next_url = part[start:end]
                    break

    return GitHubRepoListResponse(repos=repos)


@router.put(
    "/orgs/{org_id}/connectors/{connector}/settings", response_model=ConnectorSettingsResponse
)
async def update_connector_settings(
    req: ConnectorSettingsUpdateRequest,
    org_id: UUID = Path(...),
    connector: str = Path(...),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(require_role(*ADMIN_ROLES)),
):
    """Update connector settings (selected repos). Manages webhooks for GitHub."""
    import httpx

    from src.connectors.github import GitHubConnector

    source_map = {
        "github": SourceType.GITHUB,
        "linear": SourceType.LINEAR,
        "slack": SourceType.SLACK,
        "jira": SourceType.JIRA,
    }
    source = source_map.get(connector)
    if not source:
        raise HTTPException(status_code=400, detail=f"Unknown connector: {connector}")

    token_result = await db.execute(
        select(OAuthToken).where(
            OAuthToken.org_id == org_id,
            OAuthToken.connector == source,
        )
    )
    token = token_result.scalar_one_or_none()
    if not token:
        raise HTTPException(status_code=404, detail=f"{connector} not connected")

    old_settings = token.settings or {}
    old_selected = set(old_settings.get("selected_repos", []))
    new_selected = set(req.selected_repos)
    webhook_ids: dict[str, int] = dict(old_settings.get("webhook_ids", {}))

    # Manage GitHub webhooks for added/removed repos
    if connector == "github":
        from src.config import settings

        webhook_url = f"{settings.app_url}/api/webhooks/github"
        webhook_secret = github_webhook_secret(settings)

        added = new_selected - old_selected
        removed = old_selected - new_selected

        async with httpx.AsyncClient(
            headers={"Authorization": f"Bearer {token.access_token}", "Accept": "application/json"},
            timeout=httpx.Timeout(30.0, connect=10.0),
        ) as client:
            # Create webhooks for newly enabled repos
            for repo in added:
                try:
                    hook_id = await GitHubConnector.create_repo_webhook(
                        client,
                        repo,
                        webhook_url,
                        webhook_secret,
                    )
                    webhook_ids[repo] = hook_id
                    logger.info("Created webhook for %s (hook_id=%d)", repo, hook_id)
                except Exception as exc:
                    logger.warning("Failed to create webhook for %s: %s", repo, exc)

            # Delete webhooks for disabled repos
            for repo in removed:
                hook_id = webhook_ids.pop(repo, None)
                if hook_id:
                    try:
                        await GitHubConnector.delete_repo_webhook(client, repo, hook_id)
                        logger.info("Deleted webhook for %s (hook_id=%d)", repo, hook_id)
                    except Exception as exc:
                        logger.warning("Failed to delete webhook for %s: %s", repo, exc)

    token.settings = {
        **old_settings,
        "selected_repos": list(new_selected),
        "webhook_ids": webhook_ids,
    }
    await db.commit()

    return ConnectorSettingsResponse(
        selected_repos=list(new_selected),
        webhook_ids=webhook_ids,
    )


@router.post("/orgs/{org_id}/connectors/{connector}/sync", response_model=SyncTriggerResponse)
@limiter.limit("10/minute")
async def trigger_connector_sync(
    request: Request,
    org_id: UUID = Path(...),
    connector: str = Path(...),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    """Trigger an immediate sync for a connector."""
    source_map = {
        "github": SourceType.GITHUB,
        "linear": SourceType.LINEAR,
        "slack": SourceType.SLACK,
        "jira": SourceType.JIRA,
    }
    source = source_map.get(connector)
    if not source:
        raise HTTPException(status_code=400, detail=f"Unknown connector: {connector}")

    token_result = await db.execute(
        select(OAuthToken).where(
            OAuthToken.org_id == org_id,
            OAuthToken.connector == source,
        )
    )
    token = token_result.scalar_one_or_none()
    if not token:
        raise HTTPException(status_code=404, detail=f"{connector} not connected")

    # Get or create sync state
    sync_result = await db.execute(
        select(SyncState).where(
            SyncState.org_id == org_id,
            SyncState.connector == source,
        )
    )
    sync_state = sync_result.scalar_one_or_none()
    if not sync_state:
        sync_state = SyncState(
            org_id=org_id,
            connector=source,
            status=SyncStatus.IDLE,
        )
        db.add(sync_state)
        await db.flush()

    if sync_state.status == SyncStatus.SYNCING:
        # If stuck syncing for more than 10 minutes, assume the previous sync
        # crashed and reset so the user can retry.
        stuck_threshold = datetime.now(timezone.utc) - timedelta(minutes=10)
        started_at = sync_state.updated_at or datetime.min.replace(tzinfo=timezone.utc)
        if started_at < stuck_threshold:
            sync_state.status = SyncStatus.IDLE
            sync_state.error_message = "Previous sync timed out - reset automatically"
            await db.flush()
        else:
            raise HTTPException(status_code=409, detail="Sync already in progress")

    # Resolve connector instance
    connector_map = {}
    if source == SourceType.GITHUB:
        from src.connectors.github import GitHubConnector

        connector_map[SourceType.GITHUB] = GitHubConnector()
    elif source == SourceType.LINEAR:
        from src.connectors.linear import LinearConnector

        connector_map[SourceType.LINEAR] = LinearConnector()
    elif source == SourceType.SLACK:
        from src.connectors.slack import SlackConnector

        connector_map[SourceType.SLACK] = SlackConnector()
    elif source == SourceType.JIRA:
        from src.connectors.jira import JiraConnector

        connector_map[SourceType.JIRA] = JiraConnector()

    conn = connector_map.get(source)
    if not conn:
        raise HTTPException(status_code=400, detail=f"No connector implementation for {connector}")

    since = sync_state.last_sync_at or datetime(2000, 1, 1, tzinfo=timezone.utc)

    sync_state.status = SyncStatus.SYNCING
    sync_state.error_message = None
    await db.flush()

    try:
        result = await conn.sync_delta(db, org_id, token, since=since)
        sync_state.last_sync_at = datetime.now(timezone.utc)
        sync_state.status = SyncStatus.IDLE
        sync_state.error_message = None

        # Emit SyncCompleted - triggers person detection, link suggestions, etc.
        from src.events import SyncCompleted, bus

        await bus.emit(
            SyncCompleted(
                db=db,
                org_id=org_id,
                source=source,
                result=result,
            )
        )

        await db.commit()

        return SyncTriggerResponse(
            status="ok",
            entities_created=result.entities_created,
            entities_updated=result.entities_updated,
            edges_created=result.edges_created,
            edges_updated=result.edges_updated,
            errors=result.errors[:10],
        )
    except Exception as exc:
        sync_state.status = SyncStatus.ERROR
        sync_state.error_message = str(exc)[:2000]
        await db.commit()
        raise HTTPException(status_code=500, detail=f"Sync failed: {exc}")


# ── Link suggestions ──────────────────────────────────────────────────


@router.get("/orgs/{org_id}/suggestions", response_model=LinkSuggestionListResponse)
async def list_link_suggestions(
    org_id: UUID = Path(...),
    status: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    """List AI-suggested entity links, optionally filtered by status."""
    query = select(LinkSuggestion).where(LinkSuggestion.org_id == org_id)
    if status:
        query = query.where(LinkSuggestion.status == status)
    query = query.order_by(LinkSuggestion.confidence.desc()).limit(limit)

    result = await db.execute(query)
    suggestions = list(result.scalars().all())

    items = []
    for s in suggestions:
        source = await graph_get_entity(db, s.source_entity_id)
        target = await graph_get_entity(db, s.target_entity_id)
        if not source or not target:
            continue
        items.append(
            LinkSuggestionResponse(
                id=s.id,
                source_entity=EntityResponse.model_validate(source),
                target_entity=EntityResponse.model_validate(target),
                edge_type=s.edge_type,
                confidence=s.confidence,
                reasoning=s.reasoning,
                status=s.status,
                created_at=s.created_at,
            )
        )

    return LinkSuggestionListResponse(items=items)


@router.get("/orgs/{org_id}/suggestions/count", response_model=LinkSuggestionCountResponse)
async def count_link_suggestions(
    org_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    """Count pending link suggestions for badge display."""
    result = await db.execute(
        select(func.count())
        .select_from(LinkSuggestion)
        .where(
            LinkSuggestion.org_id == org_id,
            LinkSuggestion.status == "pending",
        )
    )
    count = result.scalar() or 0
    return LinkSuggestionCountResponse(pending=count)


@router.post(
    "/orgs/{org_id}/suggestions/{suggestion_id}/accept", response_model=LinkSuggestionResponse
)
async def accept_link_suggestion(
    org_id: UUID = Path(...),
    suggestion_id: UUID = Path(...),
    skip_auto_transition: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    """Accept a suggestion - creates the actual edge."""
    suggestion = await db.get(LinkSuggestion, suggestion_id)
    if not suggestion or suggestion.org_id != org_id:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    if suggestion.status != "pending":
        raise HTTPException(status_code=400, detail=f"Suggestion already {suggestion.status}")

    await upsert_edge(
        db,
        EdgeCreate(
            org_id=org_id,
            from_entity_id=suggestion.source_entity_id,
            to_entity_id=suggestion.target_entity_id,
            type=suggestion.edge_type,
            weight=1.0,
            confidence=suggestion.confidence,
            evidence=[{"source": "ai_suggestion", "reasoning": suggestion.reasoning}],
        ),
    )

    # Trigger task transitions if a SHIPS_TO edge connects a merged PR to a task
    from src.events import EdgeCreated, bus

    await bus.emit(
        EdgeCreated(
            db=db,
            org_id=org_id,
            from_entity_id=suggestion.source_entity_id,
            to_entity_id=suggestion.target_entity_id,
            edge_type=suggestion.edge_type,
            skip_auto_transition=skip_auto_transition,
        )
    )

    suggestion.status = "accepted"
    await db.commit()

    source = await graph_get_entity(db, suggestion.source_entity_id)
    target = await graph_get_entity(db, suggestion.target_entity_id)
    return LinkSuggestionResponse(
        id=suggestion.id,
        source_entity=EntityResponse.model_validate(source),
        target_entity=EntityResponse.model_validate(target),
        edge_type=suggestion.edge_type,
        confidence=suggestion.confidence,
        reasoning=suggestion.reasoning,
        status=suggestion.status,
        created_at=suggestion.created_at,
    )


@router.post(
    "/orgs/{org_id}/suggestions/{suggestion_id}/dismiss", response_model=LinkSuggestionResponse
)
async def dismiss_link_suggestion(
    org_id: UUID = Path(...),
    suggestion_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    """Dismiss a suggestion."""
    suggestion = await db.get(LinkSuggestion, suggestion_id)
    if not suggestion or suggestion.org_id != org_id:
        raise HTTPException(status_code=404, detail="Suggestion not found")
    if suggestion.status != "pending":
        raise HTTPException(status_code=400, detail=f"Suggestion already {suggestion.status}")

    suggestion.status = "dismissed"
    await db.commit()

    source = await graph_get_entity(db, suggestion.source_entity_id)
    target = await graph_get_entity(db, suggestion.target_entity_id)
    return LinkSuggestionResponse(
        id=suggestion.id,
        source_entity=EntityResponse.model_validate(source),
        target_entity=EntityResponse.model_validate(target),
        edge_type=suggestion.edge_type,
        confidence=suggestion.confidence,
        reasoning=suggestion.reasoning,
        status=suggestion.status,
        created_at=suggestion.created_at,
    )


@router.post("/orgs/{org_id}/suggestions/generate", response_model=LinkSuggestionListResponse)
@limiter.limit("10/minute")
async def generate_link_suggestions(
    request: Request,
    org_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    """Manually trigger AI link suggestion generation."""
    from src.llm.link_suggester import suggest_pr_task_links

    try:
        new_suggestions = await suggest_pr_task_links(db, org_id)
        await db.commit()
    except Exception as exc:
        logger.warning("Link suggestion generation failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"Suggestion generation failed: {exc}")

    items = []
    for s in new_suggestions:
        source = await graph_get_entity(db, s.source_entity_id)
        target = await graph_get_entity(db, s.target_entity_id)
        if source and target:
            items.append(
                LinkSuggestionResponse(
                    id=s.id,
                    source_entity=EntityResponse.model_validate(source),
                    target_entity=EntityResponse.model_validate(target),
                    edge_type=s.edge_type,
                    confidence=s.confidence,
                    reasoning=s.reasoning,
                    status=s.status,
                    created_at=s.created_at,
                )
            )

    return LinkSuggestionListResponse(items=items)


# ── Claude dispatch ────────────────────────────────────────────────────


@router.post("/orgs/{org_id}/dispatch", response_model=ClaudeDispatchResponse)
@limiter.limit("30/minute")
async def claude_dispatch(
    request: Request,
    req: ClaudeDispatchRequest,
    org_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    if req.action == "summarize_pr_diff":
        from src.llm.actions import summarize_pr_diff

        result = await summarize_pr_diff(db, req.entity_id)
        return ClaudeDispatchResponse(
            action=req.action,
            entity_id=req.entity_id,
            result=result,
            draft=True,
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {req.action}")


# ── Dashboard summary ─────────────────────────────────────────────────



@router.get(
    "/orgs/{org_id}/dashboard/summary",
    response_model=DashboardSummaryResponse,
    tags=["dashboard"],
)
async def get_dashboard_summary(
    org: Organization = Depends(get_org),
    member: OrgMember = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """Return a role-aware dashboard summary for the current member."""
    role = member.role
    person_id = member.person_entity_id
    org_id = org.id

    # If the member has no linked person entity, return empty defaults
    if person_id is None:
        return DashboardSummaryResponse(role=role)

    # ── Lazy edge repair: backfill ASSIGNED_TO edges for tasks that
    #    have assignee_email in properties but no edge to this person.
    try:
        orphan_stmt = text("""
            SELECT e.id FROM entities e
            WHERE e.org_id = :org_id
              AND e.type = 'TASK'
              AND e.properties->>'assignee_email' = :email
              AND NOT EXISTS (
                  SELECT 1 FROM edges ed
                  WHERE ed.to_entity_id = e.id
                    AND ed.from_entity_id = :person_id
                    AND ed.type = 'ASSIGNED_TO'
              )
        """)
        orphan_result = await db.execute(
            orphan_stmt,
            {
                "org_id": str(org_id),
                "email": member.email,
                "person_id": str(person_id),
            },
        )
        orphan_task_ids = [row[0] for row in orphan_result.fetchall()]
        if orphan_task_ids:
            for tid in orphan_task_ids:
                await upsert_edge(
                    db,
                    EdgeCreate(
                        org_id=org_id,
                        from_entity_id=person_id,
                        to_entity_id=tid,
                        type=EdgeType.ASSIGNED_TO,
                        weight=1.0,
                        confidence=1.0,
                        evidence=[{"source": "dashboard_edge_repair"}],
                    ),
                )
            await db.commit()
    except Exception:
        logger.warning("Dashboard edge repair failed", exc_info=True)

    # ── Always: my_tasks + pr_reviews_pending ─────────────────────
    workload = await get_person_workload_hybrid(db, person_id, email=member.email)
    my_tasks = TaskCountsResponse(
        active=workload.get("in_progress", 0),
        in_review=workload.get("in_review", 0),
        todo=workload.get("todo", 0),
        blocked=workload.get("blocked", 0),
        total=workload.get("total", 0),
    )

    # Count open PRs where this person is a reviewer.
    # Use text() to avoid edge_type enum casing mismatch (original migration
    # used UPPERCASE, WS1 migration added lowercase values like 'reviews').
    pr_review_stmt = text("""
        SELECT COUNT(*) FROM edges e
        JOIN entities ent ON ent.id = e.to_entity_id
        WHERE e.from_entity_id = :person_id
          AND e.type = 'reviews'
          AND ent.type = 'COMMIT_PR'
          AND ent.properties->>'status' = 'open'
    """)
    try:
        pr_result = await db.execute(pr_review_stmt, {"person_id": str(person_id)})
        pr_reviews_pending = pr_result.scalar_one()
    except Exception:
        await db.rollback()
        pr_reviews_pending = 0

    # ── Goals summary (PM, CTO, VP_ENG, VP_PRODUCT) ──────────────
    goals_summary: GoalsSummary | None = None
    if role in _GOALS_ROLES:
        coverage = await get_goal_coverage(db, org_id)
        total = len(coverage)
        no_coverage = sum(1 for g in coverage if g.get("task_count", 0) == 0)
        on_track = sum(
            1 for g in coverage if g.get("task_count", 0) > 0 and g.get("feature_count", 0) > 0
        )
        at_risk = total - on_track - no_coverage
        goals_summary = GoalsSummary(
            total=total,
            on_track=on_track,
            at_risk=at_risk,
            no_coverage=no_coverage,
        )

    # ── Team workload + stalled PRs (EM, CTO, VP_ENG) ────────────
    team_workload_list: list[TeamMemberWorkload] | None = None
    team_size = 0
    stalled_prs_count = 0
    team_person_ids: list[UUID] = []

    if role in _TEAM_ROLES:
        team_summary = await get_team_workload_summary(db, person_id)
        members_data = team_summary.get("members", {})
        team_workload_list = [
            TeamMemberWorkload(
                person_id=str(pid),
                person_name=data.get("name", ""),
                todo=data.get("todo", 0),
                in_progress=data.get("in_progress", 0),
                in_review=data.get("in_review", 0),
                done=data.get("done", 0),
                total=data.get("total", 0),
            )
            for pid, data in members_data.items()
        ]
        team_size = len(team_workload_list)

        team_members = await get_team_members(db, person_id)
        team_person_ids = [m.id for m in team_members]
        if team_person_ids:
            try:
                stalled = await get_stalled_prs(db, org_id, team_person_ids)
                stalled_prs_count = len(stalled)
            except Exception:
                await db.rollback()
                stalled_prs_count = 0

    # ── Delayed projects (EM, CTO, VP_ENG, VP_PRODUCT) ────────────
    delayed_projects: list[DelayedProjectItem] | None = None
    if role in _DELAYED_ROLES:
        all_projects = await graph_list_entities(
            db, org_id, entity_type=EntityType.PROJECT, limit=500
        )
        now_utc = datetime.now(timezone.utc)

        delayed_items: list[DelayedProjectItem] = []
        for proj in all_projects:
            props = proj.properties or {}
            status = props.get("status", "")
            if status not in ("planning", "active"):
                continue
            end_date_str = props.get("end_date", "")
            if not end_date_str:
                continue
            try:
                end_dt = datetime.strptime(end_date_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue
            if end_dt >= now_utc:
                continue

            days_overdue = (now_utc - end_dt).days
            stats = await get_project_stats(db, proj.id)
            remaining = stats.get("total", 0) - stats.get("done", 0)

            delayed_items.append(
                DelayedProjectItem(
                    id=str(proj.id),
                    name=proj.canonical_name,
                    days_overdue=max(days_overdue, 0),
                    remaining_tasks=max(remaining, 0),
                )
            )
        delayed_projects = delayed_items

    # ── Cross-team blocks (EM, CTO, VP_ENG) ───────────────────────
    cross_team_blocks = 0
    if role in _CROSS_BLOCK_ROLES and team_person_ids:
        blocks = await get_cross_team_blocking(db, org_id, team_person_ids)
        cross_team_blocks = len(blocks)

    # ── Recent incidents (ENGINEER, VP_ENG) ───────────────────────
    recent_incidents_count = 0
    if role in _INCIDENT_ROLES:
        week_ago = datetime.now(timezone.utc) - timedelta(days=7)
        all_incidents = await graph_list_entities(
            db, org_id, entity_type=EntityType.INCIDENT, limit=500
        )
        recent_incidents_count = sum(
            1 for inc in all_incidents if inc.created_at and inc.created_at >= week_ago
        )

    return DashboardSummaryResponse(
        role=role,
        my_tasks=my_tasks,
        pr_reviews_pending=pr_reviews_pending,
        goals_summary=goals_summary,
        team_workload=team_workload_list,
        team_size=team_size,
        delayed_projects=delayed_projects,
        stalled_prs_count=stalled_prs_count,
        cross_team_blocks=cross_team_blocks,
        recent_incidents_count=recent_incidents_count,
    )
