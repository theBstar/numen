"""FastAPI routes for the feature-centric Product Wiki.

The wiki synthesizes N PRDs into coherent product features with cross-linked
concepts, deep PRD section references, and implementation provenance.
All routes scoped by org_id under /api/orgs/{org_id}/wiki.
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_member, get_db
from src.prd.wiki import get_wiki_graph
from src.prd.wiki_generator import (
    generate_wiki,
    get_wiki_concept_by_slug,
    get_wiki_feature_by_slug,
    get_wiki_landing,
    update_wiki_feature,
)
from src.shared.models import OrgMember

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/orgs/{org_id}/wiki", tags=["wiki"])


# ── Response schemas ───────────────────────────────────────────────


class WikiPrdReference(BaseModel):
    entity_id: str
    prd_title: str = ""
    section_slugs: list[str] = Field(default_factory=list)
    confidence: str = "extracted"  # "extracted" | "inferred"


class WikiConceptBrief(BaseModel):
    id: str
    term: str
    slug: str


class WikiImplementation(BaseModel):
    people: list[dict] = Field(default_factory=list)
    tasks: list[dict] = Field(default_factory=list)
    prs: list[dict] = Field(default_factory=list)


class WikiProductSummaryResponse(BaseModel):
    summary: str = ""
    feature_count: int = 0
    prd_count: int = 0
    generated_at: str | None = None


class WikiStatsResponse(BaseModel):
    total_features: int = 0
    active: int = 0
    planned: int = 0
    manual_edits: int = 0
    concept_count: int = 0


class WikiFeatureListItem(BaseModel):
    id: str
    title: str
    slug: str
    description: str = ""
    domain_group: str = ""
    status: str = "active"
    is_manual: bool = False
    prd_count: int = 0


class WikiLandingResponse(BaseModel):
    summary: WikiProductSummaryResponse = Field(default_factory=WikiProductSummaryResponse)
    features: list[dict] = Field(default_factory=list)
    domain_groups: list[str] = Field(default_factory=list)
    stats: WikiStatsResponse = Field(default_factory=WikiStatsResponse)


class WikiFeatureDetailResponse(BaseModel):
    id: str
    title: str
    slug: str
    description: str = ""
    summary: str = ""
    domain_group: str = ""
    status: str = "active"
    is_manual: bool = False
    prd_references: list[WikiPrdReference] = Field(default_factory=list)
    concepts: list[WikiConceptBrief] = Field(default_factory=list)
    related_features: list[WikiFeatureListItem] = Field(default_factory=list)
    implementation: WikiImplementation = Field(default_factory=WikiImplementation)
    prd_count: int = 0
    llm_trace: dict | None = None
    generated_at: str | None = None
    updated_at: str | None = None


class WikiConceptDetailResponse(BaseModel):
    id: str
    term: str
    slug: str
    definition: str = ""
    prd_references: list[WikiPrdReference] = Field(default_factory=list)
    features: list[WikiFeatureListItem] = Field(default_factory=list)
    generated_at: str | None = None


class WikiFeatureUpdateRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    domain_group: str | None = None
    status: str | None = None


class WikiGenerateResponse(BaseModel):
    features: list[dict] = Field(default_factory=list)
    concepts: list[dict] = Field(default_factory=list)
    summary: WikiProductSummaryResponse | None = None
    generated: bool = False
    message: str = ""
    llm_trace: dict | None = None


# Graph schemas (kept from prior version)


class WikiGraphNode(BaseModel):
    id: str
    type: str  # "feature" | "prd" | "concept"
    label: str
    status: str = ""
    domain_group: str | None = None


class WikiGraphEdge(BaseModel):
    source: str
    target: str
    type: str
    label: str = ""


class WikiGraphResponse(BaseModel):
    nodes: list[WikiGraphNode] = Field(default_factory=list)
    edges: list[WikiGraphEdge] = Field(default_factory=list)


# ── Endpoints ──────────────────────────────────────────────────────


@router.get(
    "",
    response_model=WikiLandingResponse,
    summary="Get wiki landing page - summary, features, stats",
)
async def wiki_landing_endpoint(
    org_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Product wiki landing page with AI-generated summary and feature list."""
    data = await get_wiki_landing(db, org_id)
    return data


@router.get(
    "/features/{slug}",
    response_model=WikiFeatureDetailResponse,
    summary="Get a single wiki feature by slug",
)
async def wiki_feature_detail_endpoint(
    org_id: UUID = Path(...),
    slug: str = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Detailed view of a product feature with PRD references and concept links."""
    data = await get_wiki_feature_by_slug(db, org_id, slug)
    if not data:
        raise HTTPException(status_code=404, detail="Feature not found")
    return data


@router.put(
    "/features/{slug}",
    response_model=WikiFeatureDetailResponse,
    summary="Manually edit a wiki feature",
)
async def wiki_feature_update_endpoint(
    body: WikiFeatureUpdateRequest,
    org_id: UUID = Path(...),
    slug: str = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Manually edit a feature. Sets is_manual=True to preserve across regeneration."""
    data = await update_wiki_feature(
        db,
        org_id,
        slug,
        body.model_dump(exclude_none=True),
    )
    if not data:
        raise HTTPException(status_code=404, detail="Feature not found")
    return data


@router.get(
    "/concepts/{slug}",
    response_model=WikiConceptDetailResponse,
    summary="Get a single wiki concept by slug",
)
async def wiki_concept_detail_endpoint(
    org_id: UUID = Path(...),
    slug: str = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Concept detail with definition, PRD references, and linked features."""
    data = await get_wiki_concept_by_slug(db, org_id, slug)
    if not data:
        raise HTTPException(status_code=404, detail="Concept not found")
    return data


@router.post(
    "/generate",
    response_model=WikiGenerateResponse,
    summary="Generate or regenerate wiki from PRDs",
)
async def wiki_generate_endpoint(
    org_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Trigger wiki generation. Extracts features and concepts from PRDs.

    Uses hybrid extraction (deterministic parsing + LLM). Manual edits
    are preserved. Change detection skips regeneration if PRDs haven't changed.
    """
    result = await generate_wiki(db, org_id)
    return result


@router.get(
    "/graph",
    response_model=WikiGraphResponse,
    summary="Get wiki as a feature-centric graph",
)
async def wiki_graph_endpoint(
    org_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    member: OrgMember = Depends(get_current_member),
):
    """Feature-centric graph visualization with features, PRDs, and concepts."""
    data = await get_wiki_graph(db, org_id)
    return data
