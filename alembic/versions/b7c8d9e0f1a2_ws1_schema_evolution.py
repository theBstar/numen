"""WS1 schema evolution - users, audit, core_type, domain, edge temporal

Revision ID: b7c8d9e0f1a2
Revises: a6f21062cc1b
Create Date: 2026-03-31 12:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, None] = "a6f21062cc1b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # -- New edge_type enum values --
    # ALTER TYPE ... ADD VALUE cannot run inside a transaction in some PG versions,
    # but Alembic's op.execute handles this correctly in migration context.
    op.execute("ALTER TYPE edge_type ADD VALUE IF NOT EXISTS 'reports_to'")
    op.execute("ALTER TYPE edge_type ADD VALUE IF NOT EXISTS 'member_of'")
    op.execute("ALTER TYPE edge_type ADD VALUE IF NOT EXISTS 'surfaced_to'")
    op.execute("ALTER TYPE edge_type ADD VALUE IF NOT EXISTS 'acted_on'")
    op.execute("ALTER TYPE edge_type ADD VALUE IF NOT EXISTS 'dismissed'")
    op.execute("ALTER TYPE edge_type ADD VALUE IF NOT EXISTS 'approved_by'")
    op.execute("ALTER TYPE edge_type ADD VALUE IF NOT EXISTS 'escalated_to'")
    op.execute("ALTER TYPE edge_type ADD VALUE IF NOT EXISTS 'preceded_by'")
    op.execute("ALTER TYPE edge_type ADD VALUE IF NOT EXISTS 'reviews'")
    op.execute("ALTER TYPE edge_type ADD VALUE IF NOT EXISTS 'deployed_by'")

    # -- Create core_type enum --
    core_type_enum = postgresql.ENUM(
        "person",
        "team",
        "goal",
        "decision",
        "document",
        "signal",
        "metric_snapshot",
        "communication",
        "work_item",
        "artifact",
        name="core_type",
        create_type=False,
    )
    op.execute(
        "CREATE TYPE core_type AS ENUM ("
        "'person', 'team', 'goal', 'decision', 'document', "
        "'signal', 'metric_snapshot', 'communication', 'work_item', 'artifact')"
    )

    # -- Create users table --
    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=256), nullable=True),
        sa.Column("google_id", sa.String(length=128), nullable=True),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("hashed_refresh_token", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("google_id"),
    )

    # -- Create audit_logs table --
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.String(length=128), nullable=False),
        sa.Column("resource_type", sa.String(length=64), nullable=True),
        sa.Column("resource_id", sa.UUID(), nullable=True),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_org_created", "audit_logs", ["org_id", "created_at"], unique=False)
    op.create_index("ix_audit_user_created", "audit_logs", ["user_id", "created_at"], unique=False)

    # -- Add columns to entities --
    op.add_column("entities", sa.Column("core_type", core_type_enum, nullable=True))
    op.add_column("entities", sa.Column("domain", sa.String(length=64), nullable=True))
    op.add_column("entities", sa.Column("domain_type", sa.String(length=64), nullable=True))
    op.create_index("ix_entities_org_core_domain", "entities", ["org_id", "core_type", "domain"], unique=False)

    # -- Add columns to edges --
    op.add_column("edges", sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True))
    op.add_column("edges", sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "edges",
        sa.Column("context_at_creation", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column("edges", sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_index("ix_edges_valid_from", "edges", ["valid_from"], unique=False)
    op.create_index("ix_edges_valid_until", "edges", ["valid_until"], unique=False)

    # -- Add is_demo to organizations --
    op.add_column("organizations", sa.Column("is_demo", sa.Boolean(), nullable=False, server_default="false"))

    # -- Add user_id to org_members --
    op.add_column("org_members", sa.Column("user_id", sa.UUID(), nullable=True))
    op.create_foreign_key("fk_org_members_user_id", "org_members", "users", ["user_id"], ["id"])


def downgrade() -> None:
    # -- Remove user_id from org_members --
    op.drop_constraint("fk_org_members_user_id", "org_members", type_="foreignkey")
    op.drop_column("org_members", "user_id")

    # -- Remove is_demo from organizations --
    op.drop_column("organizations", "is_demo")

    # -- Remove edge columns --
    op.drop_index("ix_edges_valid_until", table_name="edges")
    op.drop_index("ix_edges_valid_from", table_name="edges")
    op.drop_column("edges", "metadata")
    op.drop_column("edges", "context_at_creation")
    op.drop_column("edges", "valid_until")
    op.drop_column("edges", "valid_from")

    # -- Remove entity columns --
    op.drop_index("ix_entities_org_core_domain", table_name="entities")
    op.drop_column("entities", "domain_type")
    op.drop_column("entities", "domain")
    op.drop_column("entities", "core_type")

    # -- Drop audit_logs --
    op.drop_index("ix_audit_user_created", table_name="audit_logs")
    op.drop_index("ix_audit_org_created", table_name="audit_logs")
    op.drop_table("audit_logs")

    # -- Drop users --
    op.drop_table("users")

    # -- Drop core_type enum --
    op.execute("DROP TYPE IF EXISTS core_type")

    # Note: PostgreSQL does not support removing values from enum types.
    # The new edge_type values are left in place on downgrade.
