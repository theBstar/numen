"""Add prd_proposals table for agent-proposed PRD/wiki edits with user approval.

Revision ID: b7s8t9u0v1w2
Revises: a6r7s8t9u0v1
Create Date: 2026-05-04

WS1: agents call propose_prd_update(slug, section_anchor, diff_md,
rationale) which writes a row here. The user approves/rejects via the
frontend, which calls the approve/reject REST endpoints. On approve we
re-check base_content_hash against the current WikiFeature.content; if
the wiki has changed since the proposal was filed, we transition status
to 'stale' and require the agent to re-propose with a fresh diff.

Per T1 (autoplan locked decision): we keep WikiFeature.content as a
mutable blob (no wiki_feature_revisions table); race safety comes from
hash-stale rejection plus a partial unique index that prevents two
pending proposals on the same anchor.

Per-statement op.execute() so asyncpg accepts the prepared statements.
"""

from alembic import op

revision = "b7s8t9u0v1w2"
down_revision = "a6r7s8t9u0v1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'prd_proposal_status') THEN
                CREATE TYPE prd_proposal_status AS ENUM
                    ('pending','applied','rejected','stale','expired');
            END IF;
        END $$
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS prd_proposals (
            id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id               UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            proposer_user_id     UUID NULL REFERENCES users(id) ON DELETE SET NULL,
            feature_slug         VARCHAR(256) NOT NULL,
            section_anchor       VARCHAR(256) NOT NULL,
            diff_md              TEXT NOT NULL,
            rationale            TEXT NOT NULL DEFAULT '',
            base_content_hash    CHAR(64) NOT NULL,
            base_updated_at      TIMESTAMPTZ NULL,
            status               prd_proposal_status NOT NULL DEFAULT 'pending',
            decided_by_user_id   UUID NULL REFERENCES users(id) ON DELETE SET NULL,
            decided_at           TIMESTAMPTZ NULL,
            decided_reason       TEXT NULL,
            applied_content_hash CHAR(64) NULL,
            created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at           TIMESTAMPTZ NOT NULL DEFAULT (NOW() + INTERVAL '7 days')
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_prd_proposals_org_status ON prd_proposals (org_id, status, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_prd_proposals_org_slug ON prd_proposals (org_id, feature_slug)"
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_prd_proposals_expiry
            ON prd_proposals (expires_at)
            WHERE status = 'pending'
        """
    )
    # WS1 race-safety: at most one PENDING proposal per (org, slug, anchor).
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_prd_proposals_pending_anchor
            ON prd_proposals (org_id, feature_slug, section_anchor)
            WHERE status = 'pending'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_prd_proposals_pending_anchor")
    op.execute("DROP INDEX IF EXISTS ix_prd_proposals_expiry")
    op.execute("DROP INDEX IF EXISTS ix_prd_proposals_org_slug")
    op.execute("DROP INDEX IF EXISTS ix_prd_proposals_org_status")
    op.execute("DROP TABLE IF EXISTS prd_proposals")
    op.execute("DROP TYPE IF EXISTS prd_proposal_status")
