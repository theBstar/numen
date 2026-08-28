"""Add person_resolutions table for cross-source entity deduplication.

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-04-01 12:00:00.000000+00:00
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "e4f5a6b7c8d9"
down_revision = "d3e4f5a6b7c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "person_resolutions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("candidate_entity_id", sa.UUID(), nullable=False),
        sa.Column("match_entity_id", sa.UUID(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("match_reasons", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("resolved_by", sa.UUID(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["candidate_entity_id"], ["entities.id"]),
        sa.ForeignKeyConstraint(["match_entity_id"], ["entities.id"]),
        sa.ForeignKeyConstraint(["resolved_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("candidate_entity_id", "match_entity_id", name="uq_resolution_pair"),
    )
    op.create_index("ix_resolutions_org_status", "person_resolutions", ["org_id", "status"])


def downgrade() -> None:
    op.drop_index("ix_resolutions_org_status", table_name="person_resolutions")
    op.drop_table("person_resolutions")
