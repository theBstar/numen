"""wiki feature-centric redesign

Revision ID: t9i0j1k2l3m4
Revises: s8h9i0j1k2l3
Create Date: 2026-04-07
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

# revision identifiers
revision = "t9i0j1k2l3m4"
down_revision = "s8h9i0j1k2l3"
branch_labels = None
depends_on = None

_now = sa.func.now()


def upgrade() -> None:
    # 1. New table: wiki_product_summary
    op.create_table(
        "wiki_product_summary",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("summary", sa.Text, nullable=False, server_default=""),
        sa.Column("feature_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("prd_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("source_hash", sa.String(64), nullable=True),
        sa.Column("prd_hashes", JSONB, nullable=False, server_default="{}"),
        sa.Column("llm_trace", JSONB, nullable=True),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=_now,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=_now,
        ),
    )
    op.create_index(
        "ix_wiki_product_summary_org",
        "wiki_product_summary",
        ["org_id"],
        unique=True,
    )

    # 2. New table: wiki_concepts
    op.create_table(
        "wiki_concepts",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("term", sa.String(256), nullable=False),
        sa.Column("slug", sa.String(256), nullable=False),
        sa.Column("definition", sa.Text, nullable=False, server_default=""),
        sa.Column("prd_references", JSONB, nullable=False, server_default="[]"),
        sa.Column(
            "related_feature_ids",
            JSONB,
            nullable=False,
            server_default="[]",
        ),
        sa.Column("source_hash", sa.String(64), nullable=True),
        sa.Column("llm_trace", JSONB, nullable=True),
        sa.Column(
            "generated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=_now,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=_now,
        ),
    )
    op.create_index(
        "ix_wiki_concepts_org_slug",
        "wiki_concepts",
        ["org_id", "slug"],
        unique=True,
    )
    op.create_index("ix_wiki_concepts_org", "wiki_concepts", ["org_id"])

    # 3. Add new columns to wiki_features
    op.add_column(
        "wiki_features",
        sa.Column("domain_group", sa.String(128), nullable=True),
    )
    op.add_column(
        "wiki_features",
        sa.Column("prd_references", JSONB, nullable=False, server_default="[]"),
    )
    op.add_column(
        "wiki_features",
        sa.Column("concept_ids", JSONB, nullable=False, server_default="[]"),
    )
    op.add_column(
        "wiki_features",
        sa.Column("is_manual", sa.Boolean, nullable=False, server_default="false"),
    )
    op.add_column(
        "wiki_features",
        sa.Column("implementation", JSONB, nullable=False, server_default="{}"),
    )


def downgrade() -> None:
    # Remove wiki_features columns
    op.drop_column("wiki_features", "implementation")
    op.drop_column("wiki_features", "is_manual")
    op.drop_column("wiki_features", "concept_ids")
    op.drop_column("wiki_features", "prd_references")
    op.drop_column("wiki_features", "domain_group")

    # Drop wiki_concepts
    op.drop_index("ix_wiki_concepts_org")
    op.drop_index("ix_wiki_concepts_org_slug")
    op.drop_table("wiki_concepts")

    # Drop wiki_product_summary
    op.drop_index("ix_wiki_product_summary_org")
    op.drop_table("wiki_product_summary")
