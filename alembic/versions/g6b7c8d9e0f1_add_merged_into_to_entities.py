"""Add merged_into column to entities for tracking merged duplicates.

Revision ID: g6b7c8d9e0f1
Revises: f5a6b7c8d9e0
Create Date: 2026-04-02 10:00:00.000000+00:00
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "g6b7c8d9e0f1"
down_revision = "f5a6b7c8d9e0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "entities",
        sa.Column(
            "merged_into",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("entities.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_entities_merged_into",
        "entities",
        ["merged_into"],
        postgresql_where=sa.text("merged_into IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_entities_merged_into", table_name="entities")
    op.drop_column("entities", "merged_into")
