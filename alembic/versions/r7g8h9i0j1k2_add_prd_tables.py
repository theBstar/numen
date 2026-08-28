"""Add PRD document system tables.

Creates tables for PRD blocks, versions, comments, reactions,
reviews, media, and alignment checks.

Revision ID: r7g8h9i0j1k2
Revises: q6f7g8h9i0j1
Create Date: 2026-04-06 10:00:00.000000+00:00
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision = "r7g8h9i0j1k2"
down_revision = "q6f7g8h9i0j1"


def upgrade() -> None:
    # ── prd_blocks ──
    op.create_table(
        "prd_blocks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("entity_id", UUID(as_uuid=True), nullable=False),
        sa.Column("parent_id", UUID(as_uuid=True), sa.ForeignKey("prd_blocks.id"), nullable=True),
        sa.Column("slug", sa.String(128), nullable=False),
        sa.Column("block_type", sa.String(32), nullable=False),
        sa.Column("content", JSONB, nullable=False, server_default="{}"),
        sa.Column("position", sa.Float, nullable=False),
        sa.Column("heading_level", sa.Integer, nullable=True),
        sa.Column(
            "created_by", UUID(as_uuid=True), sa.ForeignKey("org_members.id"), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_prd_blocks_entity_pos", "prd_blocks", ["entity_id", "position"])
    op.create_unique_constraint("uq_prd_block_entity_slug", "prd_blocks", ["entity_id", "slug"])
    op.create_index("ix_prd_blocks_parent", "prd_blocks", ["parent_id"])

    # ── prd_versions ──
    op.create_table(
        "prd_versions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("entity_id", UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("snapshot", JSONB, nullable=False),
        sa.Column("status_at", sa.String(32), nullable=False),
        sa.Column(
            "created_by", UUID(as_uuid=True), sa.ForeignKey("org_members.id"), nullable=False
        ),
        sa.Column("message", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_unique_constraint("uq_prd_version", "prd_versions", ["entity_id", "version"])
    op.create_index("ix_prd_versions_entity", "prd_versions", ["entity_id", "created_at"])

    # ── prd_comments ──
    op.create_table(
        "prd_comments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("entity_id", UUID(as_uuid=True), nullable=False),
        sa.Column("block_id", UUID(as_uuid=True), sa.ForeignKey("prd_blocks.id"), nullable=True),
        sa.Column("parent_id", UUID(as_uuid=True), sa.ForeignKey("prd_comments.id"), nullable=True),
        sa.Column("author_id", UUID(as_uuid=True), sa.ForeignKey("org_members.id"), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("is_resolved", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "resolved_by", UUID(as_uuid=True), sa.ForeignKey("org_members.id"), nullable=True
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_prd_comments_entity_block", "prd_comments", ["entity_id", "block_id"])
    op.create_index("ix_prd_comments_parent", "prd_comments", ["parent_id"])

    # ── prd_reactions ──
    op.create_table(
        "prd_reactions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("block_id", UUID(as_uuid=True), sa.ForeignKey("prd_blocks.id"), nullable=False),
        sa.Column("member_id", UUID(as_uuid=True), sa.ForeignKey("org_members.id"), nullable=False),
        sa.Column("emoji", sa.String(8), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_unique_constraint(
        "uq_reaction_block_member_emoji", "prd_reactions", ["block_id", "member_id", "emoji"]
    )
    op.create_index("ix_prd_reactions_block", "prd_reactions", ["block_id"])

    # ── prd_reviews ──
    op.create_table(
        "prd_reviews",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("entity_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "reviewer_id", UUID(as_uuid=True), sa.ForeignKey("org_members.id"), nullable=False
        ),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_unique_constraint(
        "uq_review_entity_reviewer_version", "prd_reviews", ["entity_id", "reviewer_id", "version"]
    )
    op.create_index("ix_prd_reviews_entity_version", "prd_reviews", ["entity_id", "version"])

    # ── prd_media ──
    op.create_table(
        "prd_media",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("entity_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "uploaded_by", UUID(as_uuid=True), sa.ForeignKey("org_members.id"), nullable=False
        ),
        sa.Column("file_name", sa.String(512), nullable=False),
        sa.Column("file_type", sa.String(128), nullable=False),
        sa.Column("file_size", sa.Integer, nullable=False),
        sa.Column("storage_key", sa.Text, nullable=False),
        sa.Column("cdn_url", sa.Text, nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_prd_media_entity", "prd_media", ["entity_id"])

    # ── prd_alignment_checks ──
    op.create_table(
        "prd_alignment_checks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("prd_entity_id", UUID(as_uuid=True), nullable=False),
        sa.Column("pr_entity_id", UUID(as_uuid=True), nullable=False),
        sa.Column("findings", JSONB, nullable=False, server_default="[]"),
        sa.Column("coverage_score", sa.Float, nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_prd_alignment_org", "prd_alignment_checks", ["org_id", "created_at"])
    op.create_index("ix_prd_alignment_prd", "prd_alignment_checks", ["prd_entity_id"])


def downgrade() -> None:
    op.drop_table("prd_alignment_checks")
    op.drop_table("prd_media")
    op.drop_table("prd_reviews")
    op.drop_table("prd_reactions")
    op.drop_table("prd_comments")
    op.drop_table("prd_versions")
    op.drop_table("prd_blocks")
