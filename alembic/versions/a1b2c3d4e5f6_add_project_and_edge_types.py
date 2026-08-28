"""Add project entity type and new edge types.

Revision ID: a1b2c3d4e5f6
Revises: 36be3f852e46
Create Date: 2026-03-25 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "36be3f852e46"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction.
    # Use AUTOCOMMIT isolation level for each statement.
    op.execute("ALTER TYPE entity_type ADD VALUE IF NOT EXISTS 'project'")
    op.execute("ALTER TYPE edge_type ADD VALUE IF NOT EXISTS 'contains'")
    op.execute("ALTER TYPE edge_type ADD VALUE IF NOT EXISTS 'parent_of'")
    op.execute("ALTER TYPE edge_type ADD VALUE IF NOT EXISTS 'assigned_to'")


def downgrade() -> None:
    # PostgreSQL does not support removing values from enum types.
    # To downgrade, you would need to recreate the enum type without these values,
    # which is complex and risky. For v1, we accept this as a one-way migration.
    pass
