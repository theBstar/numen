"""Add mcp_call_log + mcp_usage_daily for MCP tool-call observability.

Revision ID: z5q6r7s8t9u0
Revises: y4p5q6r7s8t9
Create Date: 2026-05-04

mcp_call_log: one row per MCP tool invocation. Small rows (no raw args -
PII risk), indexed on (org_id, ts) for cheap dashboard queries.

mcp_usage_daily: rolled-up counts per (org_id, day, tool_name). The hourly
worker fills this from mcp_call_log. The /api/admin/mcp/usage endpoint
reads from here so the dashboard query is cheap regardless of call volume.

NOTE: each op.execute() must be a single statement - asyncpg rejects
multi-statement prepared statements (see PR #9 for the same fix on
w2m3n4o5p6q7).
"""

from alembic import op

revision = "z5q6r7s8t9u0"
down_revision = "y4p5q6r7s8t9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'mcp_call_status') THEN
                CREATE TYPE mcp_call_status AS ENUM ('ok','error');
            END IF;
        END $$
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mcp_call_log (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id          UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            user_id         UUID NULL REFERENCES users(id) ON DELETE SET NULL,
            tool_name       VARCHAR(128) NOT NULL,
            latency_ms      INTEGER NOT NULL,
            status          mcp_call_status NOT NULL,
            error_code      VARCHAR(64) NULL,
            args_size_bytes INTEGER NULL,
            occurred_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_mcp_call_log_org_ts ON mcp_call_log (org_id, occurred_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_mcp_call_log_tool_ts ON mcp_call_log (tool_name, occurred_at DESC)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS mcp_usage_daily (
            org_id         UUID NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
            day            DATE NOT NULL,
            tool_name      VARCHAR(128) NOT NULL,
            call_count     INTEGER NOT NULL DEFAULT 0,
            error_count    INTEGER NOT NULL DEFAULT 0,
            latency_p50_ms INTEGER NULL,
            latency_p99_ms INTEGER NULL,
            PRIMARY KEY (org_id, day, tool_name)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_mcp_usage_daily_org_day ON mcp_usage_daily (org_id, day DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS mcp_usage_daily")
    op.execute("DROP TABLE IF EXISTS mcp_call_log")
    op.execute("DROP TYPE IF EXISTS mcp_call_status")
