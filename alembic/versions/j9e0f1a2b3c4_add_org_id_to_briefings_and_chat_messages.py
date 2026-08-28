"""Add org_id to briefings and chat_messages for RLS support.

Revision ID: j9e0f1a2b3c4
Revises: i8d9e0f1a2b3
Create Date: 2026-04-10 00:00:00.000000

"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision = "j9e0f1a2b3c4"
down_revision = "i8d9e0f1a2b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- briefings: add org_id, backfill from org_members, make NOT NULL --
    op.add_column("briefings", sa.Column("org_id", UUID(as_uuid=True), nullable=True))

    op.execute(
        """
        UPDATE briefings b
        SET org_id = om.org_id
        FROM org_members om
        WHERE b.org_member_id = om.id
        """
    )

    op.alter_column("briefings", "org_id", nullable=False)

    op.create_foreign_key("fk_briefings_org_id", "briefings", "organizations", ["org_id"], ["id"])
    op.create_index("ix_briefings_org_id", "briefings", ["org_id"])

    # -- chat_messages: add org_id, backfill from conversations, make NOT NULL --
    op.add_column("chat_messages", sa.Column("org_id", UUID(as_uuid=True), nullable=True))

    op.execute(
        """
        UPDATE chat_messages cm
        SET org_id = c.org_id
        FROM conversations c
        WHERE cm.conversation_id = c.id
        """
    )

    op.alter_column("chat_messages", "org_id", nullable=False)

    op.create_foreign_key("fk_chat_messages_org_id", "chat_messages", "organizations", ["org_id"], ["id"])
    op.create_index("ix_chat_messages_org_id", "chat_messages", ["org_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_messages_org_id", table_name="chat_messages")
    op.drop_constraint("fk_chat_messages_org_id", "chat_messages", type_="foreignkey")
    op.drop_column("chat_messages", "org_id")

    op.drop_index("ix_briefings_org_id", table_name="briefings")
    op.drop_constraint("fk_briefings_org_id", "briefings", type_="foreignkey")
    op.drop_column("briefings", "org_id")
