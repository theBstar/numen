"""Drop FK constraints from tables referencing entities/edges.

Entity and edge data now lives in FalkorDB. PostgreSQL tables that
reference entity IDs keep their UUID columns but lose FK constraints
since there's no entities table to reference.

Revision ID: i8d9e0f1a2b3
Revises: h7c8d9e0f1a2
Create Date: 2026-04-05 15:00:00.000000+00:00
"""

from alembic import op

revision = "i8d9e0f1a2b3"
down_revision = "h7c8d9e0f1a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop FK constraints from org_members -> entities
    op.drop_constraint("org_members_person_entity_id_fkey", "org_members", type_="foreignkey")

    # Drop FK constraints from urgency_scores -> entities
    op.drop_constraint("urgency_scores_person_id_fkey", "urgency_scores", type_="foreignkey")
    op.drop_constraint("urgency_scores_entity_id_fkey", "urgency_scores", type_="foreignkey")

    # Drop FK constraints from person_resolutions -> entities
    op.drop_constraint("person_resolutions_candidate_entity_id_fkey", "person_resolutions", type_="foreignkey")
    op.drop_constraint("person_resolutions_match_entity_id_fkey", "person_resolutions", type_="foreignkey")

    # Drop FK constraints from link_suggestions -> entities
    op.drop_constraint("link_suggestions_source_entity_id_fkey", "link_suggestions", type_="foreignkey")
    op.drop_constraint("link_suggestions_target_entity_id_fkey", "link_suggestions", type_="foreignkey")

    # Drop FK constraints from edges -> entities (self-referential)
    op.drop_constraint("edges_from_entity_id_fkey", "edges", type_="foreignkey")
    op.drop_constraint("edges_to_entity_id_fkey", "edges", type_="foreignkey")

    # Drop FK from entities -> entities (merged_into self-ref)
    op.drop_constraint("entities_merged_into_fkey", "entities", type_="foreignkey")

    # Drop FK from entities -> organizations
    op.drop_constraint("entities_org_id_fkey", "entities", type_="foreignkey")

    # Drop FK from edges -> organizations
    op.drop_constraint("edges_org_id_fkey", "edges", type_="foreignkey")

    # Tables kept for now - many callsites still query them via SQLAlchemy.
    # Data lives in FalkorDB; these tables are effectively empty.
    # Will be dropped once all SQLAlchemy queries are migrated to FalkorDB.


def downgrade() -> None:
    # Re-creating the full tables is complex; this is a one-way migration.
    # To downgrade, restore from backup.
    raise NotImplementedError(
        "Downgrade not supported - entity/edge data lives in FalkorDB. Restore from database backup if needed."
    )
