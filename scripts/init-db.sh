#!/bin/bash
# Postgres docker-entrypoint-initdb.d script - runs once on fresh cluster init.
# Creates the RLS-enforced `numen_app` role using the password supplied via
# $NUMEN_APP_PASSWORD. The `postgres` superuser (set via POSTGRES_PASSWORD)
# is only used for migrations.

set -e

if [ -z "${NUMEN_APP_PASSWORD:-}" ]; then
  echo "ERROR: NUMEN_APP_PASSWORD must be set for init-db.sh" >&2
  exit 1
fi

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'numen_app') THEN
            CREATE ROLE numen_app LOGIN PASSWORD '$NUMEN_APP_PASSWORD';
        ELSE
            ALTER ROLE numen_app WITH PASSWORD '$NUMEN_APP_PASSWORD';
        END IF;
    END
    \$\$;

    GRANT CONNECT ON DATABASE $POSTGRES_DB TO numen_app;
EOSQL
