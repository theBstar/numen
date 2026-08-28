FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for asyncpg, pgvector, and weasyprint
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies only (not the package itself)
COPY pyproject.toml .
RUN pip install --no-cache-dir \
    fastapi uvicorn[standard] sqlalchemy[asyncio] asyncpg pgvector alembic \
    httpx anthropic pydantic pydantic-settings python-dotenv itsdangerous \
    redis[hiredis] resend authlib cryptography \
    "pyjwt[crypto]" slowapi \
    langchain langchain-openai langgraph \
    "mcp[cli]>=1.9.0" \
    falkordb \
    aioboto3 weasyprint \
    markdown-it-py beautifulsoup4 pyyaml openai pdfplumber

# Copy application code
COPY alembic.ini .
COPY alembic/ alembic/
COPY src/ src/
COPY scripts/ scripts/

# Ensure src is importable
ENV PYTHONPATH=/app

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
