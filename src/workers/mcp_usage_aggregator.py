"""Hourly aggregator: rolls mcp_call_log into mcp_usage_daily.

Reads the last completed hour's call logs, computes per-(org, day, tool)
totals + error counts + p50/p99 latency, upserts into mcp_usage_daily.
Designed to run on a cron/celery beat schedule; for in-process scheduling,
call `aggregate_recent_hours()` from a periodic task.
"""

from __future__ import annotations

import logging
import statistics
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.shared.models import MCPCallLog, MCPUsageDaily

logger = logging.getLogger(__name__)


async def aggregate_recent_hours(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    hours_back: int = 25,
) -> dict[str, int]:
    """Aggregate logs from the last `hours_back` hours into mcp_usage_daily.

    Idempotent: re-running over the same window produces the same result
    (UPSERT semantics on (org_id, day, tool_name)).

    Returns {"upserted_rows": N, "source_logs": M, "days_covered": D}.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    upserted = 0
    log_count = 0
    days: set[date] = set()

    async with session_factory() as db:
        rows = (
            await db.execute(
                select(MCPCallLog).where(MCPCallLog.occurred_at >= cutoff)
            )
        ).scalars().all()
        log_count = len(rows)

        # Group: (org_id, day, tool_name) -> list[MCPCallLog]
        buckets: dict[tuple[UUID, date, str], list[MCPCallLog]] = {}
        for r in rows:
            day = r.occurred_at.date()
            days.add(day)
            buckets.setdefault((r.org_id, day, r.tool_name), []).append(r)

        for (org_id, day, tool_name), logs in buckets.items():
            latencies = sorted(r.latency_ms for r in logs)
            err_count = sum(1 for r in logs if r.status == "error")
            p50 = int(statistics.median(latencies)) if latencies else None
            # 99th percentile (handle small N gracefully)
            if latencies:
                p99_idx = max(0, int(len(latencies) * 0.99) - 1)
                p99 = latencies[min(p99_idx, len(latencies) - 1)]
            else:
                p99 = None

            stmt = (
                pg_insert(MCPUsageDaily)
                .values(
                    org_id=org_id,
                    day=day,
                    tool_name=tool_name,
                    call_count=len(logs),
                    error_count=err_count,
                    latency_p50_ms=p50,
                    latency_p99_ms=p99,
                )
                .on_conflict_do_update(
                    index_elements=["org_id", "day", "tool_name"],
                    set_={
                        "call_count": len(logs),
                        "error_count": err_count,
                        "latency_p50_ms": p50,
                        "latency_p99_ms": p99,
                    },
                )
            )
            await db.execute(stmt)
            upserted += 1

        await db.commit()

    logger.info(
        "mcp_usage aggregator: upserted=%d source_logs=%d days=%d",
        upserted, log_count, len(days),
    )
    return {
        "upserted_rows": upserted,
        "source_logs": log_count,
        "days_covered": len(days),
    }


async def trim_old_call_logs(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    keep_days: int = 14,
) -> int:
    """Delete mcp_call_log rows older than `keep_days`. Aggregates are
    preserved indefinitely in mcp_usage_daily."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
    async with session_factory() as db:
        result = await db.execute(
            delete(MCPCallLog).where(MCPCallLog.occurred_at < cutoff)
        )
        await db.commit()
        deleted = result.rowcount or 0
    logger.info("mcp_call_log trim: deleted=%d (older than %dd)", deleted, keep_days)
    return deleted
