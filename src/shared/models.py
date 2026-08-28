"""SQLAlchemy table definitions for the Numen context graph."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.types import TypeDecorator

from src.shared.database import Base
from src.shared.encryption import encrypt_token, try_decrypt
from src.shared.types import (
    AgentRuntime,
    CoreType,
    DeliveryStatus,
    EdgeType,
    EntityType,
    LivingMergeStateStatus,
    LivingMergeStrategy,
    LivingPrProvider,
    LivingPrState,
    LivingTaskStatus,
    LivingWorktreeStatus,
    RoleType,
    SourceType,
    SyncStatus,
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EncryptedString(TypeDecorator):
    """Text column encrypted at rest with Fernet.

    On write: always encrypt. On read: try to decrypt, fall back to the raw
    value if it's legacy plaintext (so the rollout is safe before the
    backfill script has run).
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return encrypt_token(value)

    def process_result_value(self, value, dialect):
        return try_decrypt(value)


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


# ── Core graph tables ──────────────────────────────────────────────────


class Entity(Base):
    __tablename__ = "entities"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True)
    type = Column(Enum(EntityType, name="entity_type"), nullable=False, index=True)
    core_type = Column(Enum(CoreType, name="core_type"), nullable=True)
    domain = Column(String(64), nullable=True)
    domain_type = Column(String(64), nullable=True)
    source = Column(Enum(SourceType, name="source_type"), nullable=False)
    source_ids = Column(JSONB, nullable=False, default=dict)
    canonical_name = Column(String(512), nullable=False)
    properties = Column(JSONB, nullable=False, default=dict)
    embedding = Column(Vector(1536), nullable=True)
    merged_into = Column(UUID(as_uuid=True), ForeignKey("entities.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    # Relationships
    organization = relationship("Organization", back_populates="entities")
    edges_from = relationship(
        "Edge", foreign_keys="Edge.from_entity_id", back_populates="from_entity"
    )
    edges_to = relationship("Edge", foreign_keys="Edge.to_entity_id", back_populates="to_entity")

    __table_args__ = (
        Index("ix_entities_org_type", "org_id", "type"),
        Index("ix_entities_source_ids", "source_ids", postgresql_using="gin"),
        Index("ix_entities_org_core_domain", "org_id", "core_type", "domain"),
        Index(
            "ix_entities_merged_into",
            "merged_into",
            postgresql_where=Column("merged_into").isnot(None),
        ),
    )


class Edge(Base):
    __tablename__ = "edges"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True)
    from_entity_id = Column(
        UUID(as_uuid=True), ForeignKey("entities.id"), nullable=False, index=True
    )
    to_entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id"), nullable=False, index=True)
    type = Column(Enum(EdgeType, name="edge_type"), nullable=False, index=True)
    weight = Column(Float, nullable=False, default=1.0)
    confidence = Column(Float, nullable=False, default=1.0)
    evidence = Column(JSONB, nullable=False, default=list)
    first_seen_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    last_active_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    valid_from = Column(DateTime(timezone=True), nullable=True)
    valid_until = Column(DateTime(timezone=True), nullable=True)
    context_at_creation = Column(JSONB, nullable=True)
    edge_metadata = Column("metadata", JSONB, nullable=True, default=dict)

    # Relationships
    from_entity = relationship("Entity", foreign_keys=[from_entity_id], back_populates="edges_from")
    to_entity = relationship("Entity", foreign_keys=[to_entity_id], back_populates="edges_to")

    __table_args__ = (
        UniqueConstraint("from_entity_id", "to_entity_id", "type", name="uq_edge_triple"),
        Index("ix_edges_from_type", "from_entity_id", "type"),
        Index("ix_edges_to_type", "to_entity_id", "type"),
        Index("ix_edges_valid_from", "valid_from"),
        Index("ix_edges_valid_until", "valid_until"),
    )


# ── Inference cache ────────────────────────────────────────────────────


class UrgencyScoreCache(Base):
    __tablename__ = "urgency_scores"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    person_id = Column(UUID(as_uuid=True), ForeignKey("entities.id"), nullable=False)
    entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id"), nullable=False)
    score = Column(Float, nullable=False)
    score_components = Column(JSONB, nullable=False, default=dict)
    goal_ids = Column(ARRAY(UUID(as_uuid=True)), nullable=False, default=list)
    provenance = Column(JSONB, nullable=False, default=list)
    computed_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    valid_until = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("person_id", "entity_id", name="uq_score_person_entity"),
        Index("ix_urgency_org_person", "org_id", "person_id"),
    )


# ── Users ─────────────────────────────────────────────────────────────


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    email = Column(String(320), nullable=False, unique=True)
    display_name = Column(String(256), nullable=True)
    google_id = Column(String(128), nullable=True, unique=True)
    avatar_url = Column(Text, nullable=True)
    hashed_refresh_token = Column(Text, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)


# ── Organization and membership ────────────────────────────────────────


class Organization(Base):
    __tablename__ = "organizations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    name = Column(String(256), nullable=False)
    slug = Column(String(128), nullable=False, unique=True)
    domain = Column(String(256), nullable=True)  # e.g. "acme.com" for business email orgs
    is_demo = Column(Boolean, nullable=False, default=False, server_default="false")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # Relationships
    entities = relationship("Entity", back_populates="organization")
    members = relationship("OrgMember", back_populates="organization")
    oauth_tokens = relationship("OAuthToken", back_populates="organization")
    sync_states = relationship("SyncState", back_populates="organization")


class OrgMember(Base):
    __tablename__ = "org_members"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    person_entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id"), nullable=True)
    role = Column(Enum(RoleType, name="role_type"), nullable=False, default=RoleType.ENGINEER)
    email = Column(String(320), nullable=False)
    display_name = Column(String(256), nullable=True)
    preferences = Column(JSONB, nullable=False, default=dict)
    timezone = Column(String(64), nullable=False, default="America/New_York")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # Relationships
    organization = relationship("Organization", back_populates="members")
    briefings = relationship("Briefing", back_populates="member")

    __table_args__ = (UniqueConstraint("org_id", "email", name="uq_member_org_email"),)


# ── Briefings ──────────────────────────────────────────────────────────


class Briefing(Base):
    __tablename__ = "briefings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    org_member_id = Column(UUID(as_uuid=True), ForeignKey("org_members.id"), nullable=False)
    generated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    content = Column(JSONB, nullable=False, default=dict)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    delivery_status = Column(
        Enum(DeliveryStatus, name="delivery_status"),
        nullable=False,
        default=DeliveryStatus.PENDING,
    )

    # Relationships
    organization = relationship("Organization")
    member = relationship("OrgMember", back_populates="briefings")

    __table_args__ = (
        Index("ix_briefings_member_date", "org_member_id", "generated_at"),
        Index("ix_briefings_org_id", "org_id"),
    )


# ── OAuth tokens ───────────────────────────────────────────────────────


class OAuthToken(Base):
    __tablename__ = "oauth_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    connector = Column(Enum(SourceType, name="source_type", create_type=False), nullable=False)
    access_token = Column(EncryptedString, nullable=False)
    refresh_token = Column(EncryptedString, nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    scopes = Column(String(1024), nullable=True)
    settings = Column(JSONB, nullable=False, default=dict, server_default="{}")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    # Relationships
    organization = relationship("Organization", back_populates="oauth_tokens")

    __table_args__ = (UniqueConstraint("org_id", "connector", name="uq_token_org_connector"),)


# ── Sync state ─────────────────────────────────────────────────────────


class SyncState(Base):
    __tablename__ = "sync_states"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    connector = Column(Enum(SourceType, name="source_type", create_type=False), nullable=False)
    last_sync_at = Column(DateTime(timezone=True), nullable=True)
    cursor = Column(JSONB, nullable=False, default=dict)
    status = Column(
        Enum(SyncStatus, name="sync_status"),
        nullable=False,
        default=SyncStatus.IDLE,
    )
    error_message = Column(Text, nullable=True)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    # Relationships
    organization = relationship("Organization", back_populates="sync_states")

    __table_args__ = (UniqueConstraint("org_id", "connector", name="uq_sync_org_connector"),)


# ── Chat conversations ───────────────────────────────────────────────


class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    member_id = Column(UUID(as_uuid=True), ForeignKey("org_members.id"), nullable=False)
    title = Column(String(512), nullable=True)
    # How a non-web surface addresses this thread, namespaced by surface,
    # e.g. "slack:C123:1690000000.000100". NULL for web conversations.
    external_ref = Column(String(512), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    # Relationships
    organization = relationship("Organization")
    member = relationship("OrgMember")
    messages = relationship(
        "ChatMessage", back_populates="conversation", order_by="ChatMessage.created_at"
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey("conversations.id"), nullable=False)
    role = Column(String(16), nullable=False)  # "user", "assistant", "tool"
    content = Column(Text, nullable=False)
    tool_calls = Column(JSONB, nullable=True)
    referenced_entities = Column(JSONB, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # Relationships
    organization = relationship("Organization")
    conversation = relationship("Conversation", back_populates="messages")

    __table_args__ = (
        Index("ix_chat_messages_conversation_created", "conversation_id", "created_at"),
        Index("ix_chat_messages_org_id", "org_id"),
    )


# ── Person resolution ─────────────────────────────────────────────────


class PersonResolution(Base):
    __tablename__ = "person_resolutions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    candidate_entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id"), nullable=False)
    match_entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id"), nullable=False)
    confidence = Column(Float, nullable=False)
    match_reasons = Column(JSONB, nullable=False, default=list)
    status = Column(String(32), nullable=False, default="pending")
    resolved_by = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # Relationships
    candidate_entity = relationship("Entity", foreign_keys=[candidate_entity_id])
    match_entity = relationship("Entity", foreign_keys=[match_entity_id])

    __table_args__ = (
        UniqueConstraint("candidate_entity_id", "match_entity_id", name="uq_resolution_pair"),
        Index("ix_resolutions_org_status", "org_id", "status"),
    )


# ── Link suggestions ──────────────────────────────────────────────────


class LinkSuggestion(Base):
    __tablename__ = "link_suggestions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    source_entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id"), nullable=False)
    target_entity_id = Column(UUID(as_uuid=True), ForeignKey("entities.id"), nullable=False)
    edge_type = Column(Enum(EdgeType, name="edge_type", create_type=False), nullable=False)
    confidence = Column(Float, nullable=False)
    reasoning = Column(Text, nullable=True)
    status = Column(String(32), nullable=False, default="pending")
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # Relationships
    source_entity = relationship("Entity", foreign_keys=[source_entity_id])
    target_entity = relationship("Entity", foreign_keys=[target_entity_id])

    __table_args__ = (
        UniqueConstraint(
            "source_entity_id", "target_entity_id", "edge_type", name="uq_suggestion_triple"
        ),
        Index("ix_suggestions_org_status", "org_id", "status"),
    )


# ── API keys (MCP auth) ──────────────────────────────────────────────


class ApiKey(Base):
    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    # Bound to the user who created the key. Nullable for legacy org-only keys
    # created before the migration; MCP write tools refuse those.
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    key_hash = Column(String(128), nullable=False, unique=True)
    name = Column(String(256), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    last_used_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    organization = relationship("Organization")

    __table_args__ = (
        Index("ix_api_keys_org", "org_id"),
        Index("ix_api_keys_user", "user_id"),
        Index(
            "ix_api_keys_expires_at",
            "expires_at",
            postgresql_where="expires_at IS NOT NULL",
        ),
    )


# ── Audit logging ────────────────────────────────────────────────────


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    action = Column(String(128), nullable=False)
    resource_type = Column(String(64), nullable=True)
    resource_id = Column(UUID(as_uuid=True), nullable=True)
    details = Column(JSONB, nullable=True)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        Index("ix_audit_org_created", "org_id", "created_at"),
        Index("ix_audit_user_created", "user_id", "created_at"),
    )


# ── Task activity ────────────────────────────────────────────────────


class TaskActivity(Base):
    __tablename__ = "task_activity"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    activity_type = Column(String(50), nullable=False)  # comment, status_change, assignment_change, field_change
    actor_id = Column(UUID(as_uuid=True), nullable=True)
    content = Column(Text, nullable=True)
    details = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        Index("ix_task_activity_entity", "entity_id", "created_at"),
        Index("ix_task_activity_org", "org_id"),
    )


# ── Saved views ──────────────────────────────────────────────────────


class SavedView(Base):
    __tablename__ = "saved_views"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    member_id = Column(UUID(as_uuid=True), ForeignKey("org_members.id"), nullable=False)
    name = Column(String(200), nullable=False)
    entity_type = Column(String(50), nullable=False, default="task")
    filters = Column(JSONB, nullable=False, default=dict)
    sort_config = Column(JSONB, nullable=False, default=dict)
    view_mode = Column(String(20), nullable=True, default="list")
    group_by = Column(String(50), nullable=True)
    is_default = Column(Boolean, nullable=False, default=False)
    is_shared = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (Index("ix_saved_views_org_member", "org_id", "member_id"),)


# ── Kanban settings ──────────────────────────────────────────────────


class KanbanSetting(Base):
    __tablename__ = "kanban_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    project_id = Column(UUID(as_uuid=True), nullable=True)
    column_status = Column(String(50), nullable=False)
    wip_limit = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (UniqueConstraint("org_id", "project_id", "column_status", name="uq_kanban_org_project_status"),)


# ── Task templates ───────────────────────────────────────────────────


class TaskTemplate(Base):
    __tablename__ = "task_templates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    default_properties = Column(JSONB, nullable=False, default=dict)
    subtask_titles = Column(JSONB, nullable=False, default=list)
    created_by = Column(UUID(as_uuid=True), ForeignKey("org_members.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (Index("ix_task_templates_org", "org_id"),)


# ── Notifications ────────────────────────────────────────────────────


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    member_id = Column(UUID(as_uuid=True), ForeignKey("org_members.id"), nullable=False)
    type = Column(String(50), nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=True)
    actor_id = Column(UUID(as_uuid=True), nullable=True)
    title = Column(String(500), nullable=False)
    details = Column(JSONB, nullable=False, default=dict)
    read_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        Index("ix_notifications_member_unread", "org_id", "member_id", "read_at"),
        Index("ix_notifications_member", "org_id", "member_id", "created_at"),
    )


# ── Task attachments ─────────────────────────────────────────────────


class TaskAttachment(Base):
    __tablename__ = "task_attachments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("org_members.id"), nullable=True)
    filename = Column(String(500), nullable=False)
    file_size = Column(BigInteger, nullable=True)
    mime_type = Column(String(200), nullable=True)
    storage_key = Column(String(1000), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (Index("ix_task_attachments_entity", "entity_id"),)


# ── PRD document system ─────────────────────────────────────────────


class PrdBlock(Base):
    """Section/block content for PRD documents. Each block is individually
    addressable for comments, reactions, AI editing, and cross-referencing.
    Content stored as TipTap JSON node format."""

    __tablename__ = "prd_blocks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=False)  # PRD document entity in FalkorDB
    parent_id = Column(UUID(as_uuid=True), ForeignKey("prd_blocks.id"), nullable=True)
    slug = Column(String(128), nullable=False)
    block_type = Column(
        String(32), nullable=False
    )  # heading, paragraph, image, code, table, list, callout, divider, embed
    content = Column(JSONB, nullable=False, default=dict)
    position = Column(Float, nullable=False)  # fractional ordering for O(1) reorder
    heading_level = Column(Integer, nullable=True)  # 1-6 for headings, null otherwise
    created_by = Column(UUID(as_uuid=True), ForeignKey("org_members.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    # Relationships
    parent = relationship("PrdBlock", remote_side="PrdBlock.id")
    comments = relationship("PrdComment", back_populates="block")
    reactions = relationship("PrdReaction", back_populates="block")

    __table_args__ = (
        Index("ix_prd_blocks_entity_pos", "entity_id", "position"),
        UniqueConstraint("entity_id", "slug", name="uq_prd_block_entity_slug"),
        Index("ix_prd_blocks_parent", "parent_id"),
    )


class PrdVersion(Base):
    """Full block snapshot created on status transitions and explicit saves."""

    __tablename__ = "prd_versions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    version = Column(Integer, nullable=False)
    snapshot = Column(JSONB, nullable=False)  # full block tree snapshot
    status_at = Column(String(32), nullable=False)  # PrdStatus value at snapshot time
    created_by = Column(UUID(as_uuid=True), ForeignKey("org_members.id"), nullable=False)
    message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        UniqueConstraint("entity_id", "version", name="uq_prd_version"),
        Index("ix_prd_versions_entity", "entity_id", "created_at"),
    )


class PrdComment(Base):
    """Section-level threaded comments on PRD blocks."""

    __tablename__ = "prd_comments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    block_id = Column(
        UUID(as_uuid=True), ForeignKey("prd_blocks.id"), nullable=True
    )  # null = doc-level
    parent_id = Column(UUID(as_uuid=True), ForeignKey("prd_comments.id"), nullable=True)
    author_id = Column(UUID(as_uuid=True), ForeignKey("org_members.id"), nullable=False)
    content = Column(Text, nullable=False)
    is_resolved = Column(Boolean, nullable=False, default=False)
    resolved_by = Column(UUID(as_uuid=True), ForeignKey("org_members.id"), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    # Relationships
    block = relationship("PrdBlock", back_populates="comments")
    author = relationship("OrgMember", foreign_keys=[author_id])
    replies = relationship("PrdComment", remote_side="PrdComment.parent_id")

    __table_args__ = (
        Index("ix_prd_comments_entity_block", "entity_id", "block_id"),
        Index("ix_prd_comments_parent", "parent_id"),
    )


class PrdReaction(Base):
    """Section-level emoji reactions on PRD blocks."""

    __tablename__ = "prd_reactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    block_id = Column(UUID(as_uuid=True), ForeignKey("prd_blocks.id"), nullable=False)
    member_id = Column(UUID(as_uuid=True), ForeignKey("org_members.id"), nullable=False)
    emoji = Column(String(8), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # Relationships
    block = relationship("PrdBlock", back_populates="reactions")
    member = relationship("OrgMember")

    __table_args__ = (
        UniqueConstraint("block_id", "member_id", "emoji", name="uq_reaction_block_member_emoji"),
        Index("ix_prd_reactions_block", "block_id"),
    )


class PrdReview(Base):
    """Review workflow for PRD documents."""

    __tablename__ = "prd_reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    reviewer_id = Column(UUID(as_uuid=True), ForeignKey("org_members.id"), nullable=False)
    version = Column(Integer, nullable=False)
    status = Column(String(32), nullable=False, default="pending")
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    # Relationships
    reviewer = relationship("OrgMember")

    __table_args__ = (
        UniqueConstraint(
            "entity_id", "reviewer_id", "version", name="uq_review_entity_reviewer_version"
        ),
        Index("ix_prd_reviews_entity_version", "entity_id", "version"),
    )


class PrdMedia(Base):
    """Media upload tracking for PRD documents (images, files stored in S3/R2)."""

    __tablename__ = "prd_media"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    entity_id = Column(UUID(as_uuid=True), nullable=False)
    uploaded_by = Column(UUID(as_uuid=True), ForeignKey("org_members.id"), nullable=False)
    file_name = Column(String(512), nullable=False)
    file_type = Column(String(128), nullable=False)  # MIME type
    file_size = Column(Integer, nullable=False)  # bytes
    storage_key = Column(Text, nullable=False)  # S3/R2 object key
    cdn_url = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    # Relationships
    uploader = relationship("OrgMember")

    __table_args__ = (Index("ix_prd_media_entity", "entity_id"),)


class PrdAlignmentCheck(Base):
    """PR-PRD alignment check results for code-spec mismatch detection."""

    __tablename__ = "prd_alignment_checks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    prd_entity_id = Column(UUID(as_uuid=True), nullable=False)
    pr_entity_id = Column(UUID(as_uuid=True), nullable=False)
    findings = Column(JSONB, nullable=False, default=list)
    coverage_score = Column(Float, nullable=True)
    status = Column(
        String(32), nullable=False, default="pending"
    )  # pending | acknowledged | resolved
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        Index("ix_prd_alignment_org", "org_id", "created_at"),
        Index("ix_prd_alignment_prd", "prd_entity_id"),
    )


class WikiFeature(Base):
    """LLM-generated wiki feature - a product capability extracted from PRDs.

    Each feature represents a discrete product capability synthesized from
    one or more PRDs. Features are flat (grouped by domain_group, not hierarchy).
    Users can manually edit features; manual edits are preserved across regeneration.
    """

    __tablename__ = "wiki_features"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True)
    title = Column(String(512), nullable=False)
    slug = Column(String(256), nullable=False)
    summary = Column(Text, nullable=False, default="")
    content = Column(Text, nullable=False, default="")  # Markdown content (description)
    status = Column(String(32), nullable=False, default="active")  # active | planned | deprecated
    # legacy, unused
    parent_id = Column(UUID(as_uuid=True), ForeignKey("wiki_features.id"), nullable=True)
    position = Column(Float, nullable=False, default=0.0)

    # Feature-centric fields
    domain_group = Column(String(128), nullable=True)  # soft grouping ("core", "notifications")
    # [{entity_id, section_slugs, prd_title, confidence}]
    prd_references = Column(JSONB, nullable=False, default=list)
    concept_ids = Column(JSONB, nullable=False, default=list)  # list of wiki_concept UUIDs
    is_manual = Column(Boolean, nullable=False, default=False)  # True if user manually edited
    implementation = Column(JSONB, nullable=False, default=dict)  # {people: [], tasks: [], prs: []}

    # Provenance
    source_entity_ids = Column(JSONB, nullable=False, default=list)  # Entity IDs used to generate
    source_hash = Column(String(64), nullable=True)  # Hash of source data for change detection
    llm_trace = Column(JSONB, nullable=True)  # LLMTrace dict

    # Metadata
    generated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        Index("ix_wiki_features_org_slug", "org_id", "slug", unique=True),
        Index("ix_wiki_features_parent", "parent_id"),
    )


class WikiProductSummary(Base):
    """AI-generated product summary for the wiki landing page.

    One row per org. Stores the synthesized product summary derived from
    all PRD features, plus per-PRD content hashes for incremental regeneration.
    """

    __tablename__ = "wiki_product_summary"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, unique=True)
    summary = Column(Text, nullable=False, default="")  # Markdown product summary
    feature_count = Column(Integer, nullable=False, default=0)
    prd_count = Column(Integer, nullable=False, default=0)
    source_hash = Column(String(64), nullable=True)  # Overall change detection
    prd_hashes = Column(JSONB, nullable=False, default=dict)  # {entity_id: hash} per-PRD
    llm_trace = Column(JSONB, nullable=True)
    generated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (Index("ix_wiki_product_summary_org", "org_id", unique=True),)


class WikiConcept(Base):
    """Cross-linkable term/role/concept extracted from PRDs.

    Concepts are terms like 'admin', 'owner', 'overdue' that appear across
    features and PRDs. Each concept has a definition and links back to the
    PRD sections that define or reference it.
    """

    __tablename__ = "wiki_concepts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    term = Column(String(256), nullable=False)
    slug = Column(String(256), nullable=False)
    definition = Column(Text, nullable=False, default="")  # Markdown definition
    # [{entity_id, section_slugs, prd_title}]
    prd_references = Column(JSONB, nullable=False, default=list)
    # list of wiki_feature UUIDs
    related_feature_ids = Column(JSONB, nullable=False, default=list)
    source_hash = Column(String(64), nullable=True)
    llm_trace = Column(JSONB, nullable=True)
    generated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        Index("ix_wiki_concepts_org_slug", "org_id", "slug", unique=True),
        Index("ix_wiki_concepts_org", "org_id"),
    )


# ── Living (agent fleet) tables ──────────────────────────────────────


class LivingWorktree(Base):
    """A git worktree spawned for a Living agent task.

    Mirrors the Mac app's local worktree state in the cloud so the orchestrator
    can resume after a crash and the event log keeps a complete history.
    """

    __tablename__ = "living_worktrees"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    # Bidirectional FK with living_tasks.worktree_id; nullable to allow creation
    # before the task row references it.
    task_id = Column(UUID(as_uuid=True), nullable=True)
    fs_path = Column(Text, nullable=False)
    branch_name = Column(String(256), nullable=False)
    process_pid = Column(Integer, nullable=True)
    status = Column(
        Enum(LivingWorktreeStatus, name="living_worktree_status"),
        nullable=False,
        default=LivingWorktreeStatus.PROVISIONING,
    )
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    last_activity_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_living_worktrees_org", "org_id"),
        Index("ix_living_worktrees_task", "task_id"),
    )


class LivingTask(Base):
    """An agent task dispatched via Living."""

    __tablename__ = "living_tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id = Column(UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False)
    name = Column(String(512), nullable=False)
    description = Column(Text, nullable=True)
    runtime = Column(Enum(AgentRuntime, name="agent_runtime"), nullable=False)
    status = Column(
        Enum(LivingTaskStatus, name="living_task_status"),
        nullable=False,
        default=LivingTaskStatus.QUEUED,
    )
    worktree_id = Column(
        UUID(as_uuid=True), ForeignKey("living_worktrees.id"), nullable=True
    )
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    context_fetch_count = Column(Integer, nullable=False, default=0)
    error_msg = Column(Text, nullable=True)

    pull_request = relationship(
        "LivingPullRequest",
        back_populates="task",
        uselist=False,
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_living_tasks_org_status", "org_id", "status"),
        Index("ix_living_tasks_org_created", "org_id", "created_at"),
    )


class LivingPullRequest(Base):
    """A pull request (or local merge) tracking record for a Living task.

    One row per task. Created when ``Push & Open PR`` is clicked (provider=
    github) or the moment a local merge happens (provider=local). Mutates as
    polling discovers new PR state and as the merge button fires.
    """

    __tablename__ = "living_pull_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    task_id = Column(
        UUID(as_uuid=True),
        ForeignKey("living_tasks.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    org_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    branch_name = Column(Text, nullable=False)
    base_branch = Column(Text, nullable=False)
    commit_head_sha = Column(Text, nullable=True)
    provider = Column(
        Enum(LivingPrProvider, name="living_pr_provider"), nullable=False
    )
    pr_number = Column(Integer, nullable=True)
    pr_url = Column(Text, nullable=True)
    pr_state = Column(
        Enum(LivingPrState, name="living_pr_state"),
        nullable=False,
        default=LivingPrState.NONE,
    )
    merge_state_status = Column(
        Enum(LivingMergeStateStatus, name="living_merge_state_status"),
        nullable=False,
        default=LivingMergeStateStatus.UNKNOWN,
    )
    merge_strategy = Column(
        Enum(LivingMergeStrategy, name="living_merge_strategy"), nullable=True
    )
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    updated_at = Column(
        DateTime(timezone=True), nullable=False, default=_utcnow, onupdate=_utcnow
    )
    merged_at = Column(DateTime(timezone=True), nullable=True)

    task = relationship("LivingTask", back_populates="pull_request", uselist=False)

    __table_args__ = (
        Index("ix_living_pull_requests_org_state", "org_id", "pr_state"),
        Index("ix_living_pull_requests_task", "task_id"),
    )



# ── MCP observability (WS5) ────────────────────────────────────────────


class MCPCallLog(Base):
    """One row per MCP tool invocation. No raw args (PII risk) - sizes only.

    Indexed on (org_id, occurred_at) for cheap dashboard queries.
    """

    __tablename__ = "mcp_call_log"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    tool_name = Column(String(128), nullable=False)
    latency_ms = Column(Integer, nullable=False)
    status = Column(String(8), nullable=False)  # 'ok' | 'error'
    error_code = Column(String(64), nullable=True)
    args_size_bytes = Column(Integer, nullable=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    __table_args__ = (
        Index("ix_mcp_call_log_org_ts", "org_id", "occurred_at"),
        Index("ix_mcp_call_log_tool_ts", "tool_name", "occurred_at"),
    )


class MCPUsageDaily(Base):
    """Hourly-aggregated daily counts per (org, day, tool). Read by the
    /api/admin/mcp/usage endpoint."""

    __tablename__ = "mcp_usage_daily"

    org_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    day = Column(Date, primary_key=True)
    tool_name = Column(String(128), primary_key=True)
    call_count = Column(Integer, nullable=False, default=0)
    error_count = Column(Integer, nullable=False, default=0)
    latency_p50_ms = Column(Integer, nullable=True)
    latency_p99_ms = Column(Integer, nullable=True)

    __table_args__ = (
        Index("ix_mcp_usage_daily_org_day", "org_id", "day"),
    )



# ── PRD proposals (WS1) ────────────────────────────────────────────────


class PRDProposal(Base):
    """Agent-proposed edit to a wiki feature. User approval gate.

    The agent calls propose_prd_update(slug, section_anchor, diff_md,
    rationale) -> writes a row here in 'pending'. User reviews via the
    frontend, approves or rejects -> we transition. On approve we re-check
    base_content_hash against the current WikiFeature.content; if it drifted,
    transition to 'stale' (agent must re-propose).
    """

    __tablename__ = "prd_proposals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=_uuid)
    org_id = Column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    proposer_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    feature_slug = Column(String(256), nullable=False)
    section_anchor = Column(String(256), nullable=False)
    diff_md = Column(Text, nullable=False)
    rationale = Column(Text, nullable=False, default="")
    base_content_hash = Column(String(64), nullable=False)
    base_updated_at = Column(DateTime(timezone=True), nullable=True)
    status = Column(String(16), nullable=False, default="pending")
    decided_by_user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    decided_at = Column(DateTime(timezone=True), nullable=True)
    decided_reason = Column(Text, nullable=True)
    applied_content_hash = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_prd_proposals_org_status", "org_id", "status", "created_at"),
        Index("ix_prd_proposals_org_slug", "org_id", "feature_slug"),
        Index(
            "ix_prd_proposals_expiry",
            "expires_at",
            postgresql_where="status = 'pending'",
        ),
        Index(
            "uq_prd_proposals_pending_anchor",
            "org_id", "feature_slug", "section_anchor",
            unique=True,
            postgresql_where="status = 'pending'",
        ),
    )
