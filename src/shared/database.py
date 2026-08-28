import contextvars
from uuid import UUID

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from src.config import settings

_current_org_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_org_id", default=None)

# Superuser engine - used by Alembic migrations and background workers
engine = create_async_engine(settings.database_url, echo=False, pool_size=20, max_overflow=10)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# App engine - numen_app role with RLS enforced
app_engine = create_async_engine(settings.database_app_url, echo=False, pool_size=20, max_overflow=10)
app_async_session = async_sessionmaker(app_engine, class_=AsyncSession, expire_on_commit=False)


@event.listens_for(app_engine.sync_engine, "checkout")
def _set_rls_on_checkout(dbapi_connection, connection_record, connection_proxy):
    """Set the RLS org context every time a connection is checked out.

    Reads the current org_id from contextvars (set by RLSMiddleware).
    This fires on every checkout, so even if the pool recycles connections
    mid-request, each checkout re-applies the correct org_id.
    """
    org_id = _current_org_id.get(None)
    cursor = dbapi_connection.cursor()
    if org_id:
        # SET cannot take a bound parameter, so the value is interpolated.
        # Coercing through UUID first means anything that is not a plain
        # UUID raises here rather than reaching the statement - this string
        # crosses the tenant boundary, so it must never be free text.
        try:
            safe_org_id = UUID(str(org_id))
        except (ValueError, AttributeError, TypeError):
            cursor.close()
            raise ValueError(f"Refusing to set a non-UUID org context: {org_id!r}") from None
        cursor.execute(f"SET app.current_org_id = '{safe_org_id}'")
    else:
        cursor.execute("RESET app.current_org_id")
    cursor.close()


class Base(DeclarativeBase):
    pass


def set_current_org_id(org_id: str | None) -> None:
    """Set the current org_id in the async context for RLS."""
    _current_org_id.set(org_id)


def get_current_org_id() -> str | None:
    """Get the current org_id from the async context."""
    return _current_org_id.get()


async def get_db() -> AsyncSession:
    """Yield a DB session. Uses RLS-enforced engine when org_id is in context."""
    org_id = _current_org_id.get()
    if org_id:
        async with app_async_session() as session:
            yield session
    else:
        async with async_session() as session:
            yield session
