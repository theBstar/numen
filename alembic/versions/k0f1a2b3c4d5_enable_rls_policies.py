"""Enable Row-Level Security and create tenant isolation policies.

Revision ID: k0f1a2b3c4d5
Revises: j9e0f1a2b3c4
Create Date: 2026-04-10 00:01:00.000000

"""

import os

from alembic import op

# revision identifiers, used by Alembic.
revision = "k0f1a2b3c4d5"
down_revision = "j9e0f1a2b3c4"
branch_labels = None
depends_on = None

# Tables with NOT NULL org_id
_TENANT_TABLES = [
    "entities",
    "edges",
    "urgency_scores",
    "org_members",
    "oauth_tokens",
    "sync_states",
    "conversations",
    "person_resolutions",
    "link_suggestions",
    "api_keys",
    "briefings",
    "chat_messages",
]


def upgrade() -> None:
    # -- Set a safe default so queries without org context return no rows --
    # ALTER DATABASE takes no bind parameter, so the name is resolved at
    # runtime. Hardcoding "numen" broke every install using another name.
    op.execute(
        """
        DO $$
        BEGIN
            EXECUTE format(
                'ALTER DATABASE %I SET app.current_org_id = %L',
                current_database(), ''
            );
        END
        $$
        """
    )

    # -- Create numen_app role if it does not exist --
    # The password comes from NUMEN_APP_PASSWORD so each install gets its
    # own; the literal fallback is what existing installs already have.
    # Existing deployments skip this branch entirely, the role being present.
    app_password = os.environ.get("NUMEN_APP_PASSWORD", "numen_app_password")
    if "'" in app_password or "\\" in app_password:
        raise ValueError("NUMEN_APP_PASSWORD must not contain quotes or backslashes.")

    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'numen_app') THEN
                CREATE ROLE numen_app LOGIN PASSWORD '{app_password}';
            END IF;
        END
        $$
        """
    )

    # -- Grant permissions to numen_app --
    op.execute("GRANT USAGE ON SCHEMA public TO numen_app")
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO numen_app")
    op.execute("GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO numen_app")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO numen_app")
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE ON SEQUENCES TO numen_app")

    # -- Enable RLS and create policies on tenant-scoped tables --
    for table in _TENANT_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation_{table} ON {table} "
            f"FOR ALL TO numen_app "
            f"USING (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid) "
            f"WITH CHECK (org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)"
        )

    # -- audit_logs: nullable org_id - allow own org + NULL org rows --
    op.execute("ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation_audit_logs ON audit_logs "
        "FOR ALL TO numen_app "
        "USING (org_id IS NULL OR org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid) "
        "WITH CHECK (org_id IS NULL OR org_id = NULLIF(current_setting('app.current_org_id', true), '')::uuid)"
    )


def downgrade() -> None:
    # -- Drop policies and disable RLS --
    for table in _TENANT_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.execute("DROP POLICY IF EXISTS tenant_isolation_audit_logs ON audit_logs")
    op.execute("ALTER TABLE audit_logs DISABLE ROW LEVEL SECURITY")

    # -- Revoke privileges (keep the role for safety) --
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM numen_app"
    )
    op.execute("ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE USAGE ON SEQUENCES FROM numen_app")
    op.execute("REVOKE SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public FROM numen_app")
    op.execute("REVOKE USAGE ON ALL SEQUENCES IN SCHEMA public FROM numen_app")
    op.execute("REVOKE USAGE ON SCHEMA public FROM numen_app")

    op.execute("ALTER DATABASE numen RESET app.current_org_id")
