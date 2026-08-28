"""Add link_suggestions table for AI-suggested entity links.

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-04-01 14:00:00.000000+00:00
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "f5a6b7c8d9e0"
down_revision = "e4f5a6b7c8d9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "link_suggestions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("source_entity_id", sa.UUID(), nullable=False),
        sa.Column("target_entity_id", sa.UUID(), nullable=False),
        sa.Column(
            "edge_type", postgresql.ENUM(name="edge_type", create_type=False), nullable=False
        ),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("reasoning", sa.Text(), nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["source_entity_id"], ["entities.id"]),
        sa.ForeignKeyConstraint(["target_entity_id"], ["entities.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_entity_id", "target_entity_id", "edge_type", name="uq_suggestion_triple"
        ),
    )
    op.create_index("ix_suggestions_org_status", "link_suggestions", ["org_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_suggestions_org_status", table_name="link_suggestions")
    op.drop_table("link_suggestions")
