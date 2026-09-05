FROM python:3.12-slim

WORKDIR /app

# System dependencies for asyncpg, pgvector, and weasyprint
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

# Dependencies come from pyproject.toml, which is the single source of truth.
# This file used to carry its own hand-written copy of the list and it drifted:
# the copy's mcp pin had lost the `<2` upper bound, so every image silently
# installed the 2.x rewrite, `from mcp.server.fastmcp import FastMCP` failed,
# and the MCP server never mounted. It also missed posthog and still installed
# anthropic, dropped when the project moved to the OpenAI wire protocol.
#
# The empty package stub keeps the dependency layer cacheable: pip needs a
# buildable tree to read the metadata, but rebuilding every dependency on each
# source change would make development unusable. Real code arrives below.
COPY pyproject.toml LICENSE ./
RUN mkdir -p src && touch src/__init__.py \
    && pip install --no-cache-dir . \
    && rm -rf src

# Application code
COPY alembic.ini .
COPY alembic/ alembic/
COPY src/ src/
COPY scripts/ scripts/

# /app precedes site-packages, so the mounted source wins in development
ENV PYTHONPATH=/app

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
