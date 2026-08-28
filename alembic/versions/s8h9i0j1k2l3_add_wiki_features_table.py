"""add wiki_features table

Revision ID: s8h9i0j1k2l3
Revises: r7g8h9i0j1k2
Create Date: 2026-04-06
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

# revision identifiers
revision = "s8h9i0j1k2l3"
down_revision = "r7g8h9i0j1k2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "wiki_features",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("title", sa.String(512), nullable=False),
        sa.Column("slug", sa.String(256), nullable=False),
        sa.Column("summary", sa.Text, nullable=False, server_default=""),
        sa.Column("content", sa.Text, nullable=False, server_default=""),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column(
            "parent_id", UUID(as_uuid=True), sa.ForeignKey("wiki_features.id"), nullable=True
        ),
        sa.Column("position", sa.Float, nullable=False, server_default="0"),
        sa.Column("source_entity_ids", JSONB, nullable=False, server_default="[]"),
        sa.Column("source_hash", sa.String(64), nullable=True),
        sa.Column("llm_trace", JSONB, nullable=True),
        sa.Column(
            "generated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_wiki_features_org_slug", "wiki_features", ["org_id", "slug"], unique=True)
    op.create_index("ix_wiki_features_parent", "wiki_features", ["parent_id"])


def downgrade() -> None:
    op.drop_index("ix_wiki_features_parent")
    op.drop_index("ix_wiki_features_org_slug")
    op.drop_table("wiki_features")
