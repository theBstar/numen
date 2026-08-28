"""add user_id to api_keys

Revision ID: v1l2m3n4o5p6
Revises: u0k1l2m3n4o5
Create Date: 2026-05-01
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers
revision = "v1l2m3n4o5p6"
down_revision = "u0k1l2m3n4o5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "api_keys",
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )
    op.create_index("ix_api_keys_user", "api_keys", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_api_keys_user", table_name="api_keys")
    op.drop_column("api_keys", "user_id")
