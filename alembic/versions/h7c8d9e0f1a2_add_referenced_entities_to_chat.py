"""Add referenced_entities JSONB column to chat_messages.

Revision ID: h7c8d9e0f1a2
Revises: g6b7c8d9e0f1
Create Date: 2026-04-04 10:00:00.000000+00:00
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "h7c8d9e0f1a2"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "chat_messages",
        sa.Column("referenced_entities", postgresql.JSONB, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("chat_messages", "referenced_entities")
