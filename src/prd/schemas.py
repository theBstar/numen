"""Pydantic request/response schemas for the PRD document system."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field

from src.shared.types import PrdNodeType, PrdReviewStatus, PrdStatus, Priority

# ── Request schemas ───────────────────────────────────────────────────


class PrdCreate(BaseModel):
    title: str
    node_type: PrdNodeType = PrdNodeType.DOCUMENT
    parent_id: UUID | None = None
    description: str | None = None
    priority: Priority = Priority.MEDIUM
    target_date: date | None = None
    tags: list[str] = Field(default_factory=list)
    position: float = 0.0


class PrdUpdate(BaseModel):
    title: str | None = None
    status: PrdStatus | None = None
    description: str | None = None
    priority: Priority | None = None
    target_date: date | None = None
    tags: list[str] | None = None
    cover_image_url: str | None = None
    owner_member_id: UUID | None = None


class PrdMoveRequest(BaseModel):
    parent_id: UUID | None = None
    position: float = 0.0


class PrdStatusTransition(BaseModel):
    new_status: PrdStatus


# ── Block request schemas ─────────────────────────────────────────────


class PrdBlockCreate(BaseModel):
    block_type: str
    content: dict = Field(default_factory=dict)
    position: float = 0.0
    heading_level: int | None = None
    parent_id: UUID | None = None


class PrdBlockUpdate(BaseModel):
    content: dict | None = None
    position: float | None = None
    heading_level: int | None = None


class PrdBlockBatchOp(BaseModel):
    op: str  # "create" | "update" | "delete"
    id: UUID | None = None
    block_type: str | None = None
    content: dict | None = None
    position: float | None = None
    heading_level: int | None = None
    parent_id: UUID | None = None


class PrdBlockBatchRequest(BaseModel):
    operations: list[PrdBlockBatchOp]


# ── Upload schemas ────────────────────────────────────────────────────


class UploadUrlRequest(BaseModel):
    file_name: str
    file_type: str


class UploadUrlResponse(BaseModel):
    upload_url: str
    storage_key: str


class UploadConfirmRequest(BaseModel):
    storage_key: str
    file_name: str
    file_type: str
    file_size: int


# ── Response schemas ──────────────────────────────────────────────────


class PrdResponse(BaseModel):
    id: UUID
    title: str
    node_type: PrdNodeType
    status: PrdStatus
    owner: str | None = None
    owner_member_id: UUID | None = None
    description: str | None = None
    priority: Priority = Priority.MEDIUM
    target_date: date | None = None
    tags: list[str] = Field(default_factory=list)
    cover_image_url: str | None = None
    parent_id: UUID | None = None
    block_count: int = 0
    comment_count: int = 0
    version: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PrdTreeNode(BaseModel):
    id: UUID
    title: str
    node_type: PrdNodeType
    status: PrdStatus
    parent_id: UUID | None = None
    position: float = 0.0
    children: list[PrdTreeNode] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class PrdBlockResponse(BaseModel):
    id: UUID
    entity_id: UUID
    parent_id: UUID | None = None
    slug: str
    block_type: str
    content: dict = Field(default_factory=dict)
    position: float
    heading_level: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class PrdVersionResponse(BaseModel):
    id: UUID
    entity_id: UUID
    version: int
    status_at: str
    created_by: UUID
    message: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class PrdVersionDetail(PrdVersionResponse):
    snapshot: dict = Field(default_factory=dict)


class PrdMediaResponse(BaseModel):
    id: UUID
    entity_id: UUID
    file_name: str
    file_type: str
    file_size: int
    cdn_url: str
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Analytics schemas ─────────────────────────────────────────────────


class PrdCoverage(BaseModel):
    total_tasks: int = 0
    tasks_done: int = 0
    tasks_in_progress: int = 0
    tasks_todo: int = 0
    coverage_pct: float = 0.0
    linked_prs: int = 0
    has_design: bool = False


class PrdReference(BaseModel):
    prd_id: UUID
    prd_title: str
    direction: str  # "outgoing" | "incoming"
    section_slug: str | None = None


# ── Comment schemas ──────────────────────────────────────────────────


class CommentCreate(BaseModel):
    block_id: UUID | None = None
    parent_id: UUID | None = None
    content: str


class CommentUpdate(BaseModel):
    content: str


class CommentResponse(BaseModel):
    id: UUID
    entity_id: UUID
    block_id: UUID | None
    parent_id: UUID | None
    author_id: UUID
    author_name: str | None
    content: str
    is_resolved: bool
    resolved_by: UUID | None
    resolved_at: str | None
    replies: list["CommentResponse"]
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class ReactionToggle(BaseModel):
    emoji: str


class ReactionResponse(BaseModel):
    emoji: str
    count: int
    member_ids: list[UUID]


# ── Review workflow schemas ─────────────────────────────────────────


class ReviewerRequest(BaseModel):
    member_id: UUID


class StakeholderRequest(BaseModel):
    member_id: UUID


class ReviewSubmit(BaseModel):
    status: PrdReviewStatus  # approved or changes_requested
    comment: str | None = None


class ReviewResponse(BaseModel):
    id: UUID
    entity_id: UUID
    reviewer_id: UUID
    reviewer_name: str | None = None
    version: int
    status: PrdReviewStatus
    comment: str | None
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


class ReviewSummary(BaseModel):
    total_reviewers: int
    approved_count: int
    changes_requested_count: int
    pending_count: int
    can_approve: bool


class StakeholderResponse(BaseModel):
    person_id: UUID
    person_name: str
    role_type: str  # "owner" | "stakeholder" | "reviewer"
    member_id: UUID | None = None


# ── Import schemas ────────────────────────────────────────────────────


class ImportRequest(BaseModel):
    source: str  # "notion" | "confluence" | "google_docs"
    source_id: str  # page_id or document_id
    parent_folder_id: UUID | None = None
    # Confluence only
    base_url: str | None = None


class ImportBulkRequest(BaseModel):
    source: str
    root_page_id: str
    parent_folder_id: UUID | None = None

    # Confluence only
    base_url: str | None = None


class ImportBulkResponse(BaseModel):
    job_id: str
    status: str = "started"


# ── Export schemas ───────────────────────────────────────────────────


class ExportRequest(BaseModel):
    format: str  # "markdown" | "html" | "pdf" | "notion" | "confluence" | "google_docs"
    options: dict | None = None  # format-specific options


class ExportResponse(BaseModel):
    url: str | None = None
    external_id: str | None = None


# ── AI schemas ───────────────────────────────────────────────────────


class AiCompleteRequest(BaseModel):
    prompt: str


class AiEditSectionRequest(BaseModel):
    block_ids: list[UUID]
    instruction: str


class AiCompletedBlock(BaseModel):
    block_type: str
    content: dict
    heading_level: int | None = None
    position: float = 0.0
    ai_generated: bool = True


class AiSuggestedReviewer(BaseModel):
    member_id: str
    person_name: str
    reason: str
    score: float


# ── Alignment check schemas ─────────────────────────────────────────


class AlignmentFinding(BaseModel):
    type: str  # missing_requirement | label_mismatch | assumption_conflict | scope_drift
    prd_section: str
    detail: str
    severity: str  # high | medium | low


class AlignmentCheckResponse(BaseModel):
    id: UUID
    prd_entity_id: UUID
    prd_title: str | None = None
    pr_entity_id: UUID
    pr_title: str | None = None
    findings: list[dict] = Field(default_factory=list)
    coverage_score: float | None = None
    status: str
    created_at: str

    model_config = {"from_attributes": True}
