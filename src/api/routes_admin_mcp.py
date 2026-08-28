"""Admin: MCP usage dashboard endpoint (WS5).

Aggregated counts per (org, day, tool) for the last 30d. Org admins only
(ADMIN_ROLES). Reads from mcp_usage_daily (rolled up hourly by the
aggregator worker); falls back to live aggregation over mcp_call_log if
the daily table is empty for the requested day.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_db
from src.api.rbac import ADMIN_ROLES, require_role
from src.shared.models import MCPCallLog, MCPUsageDaily, OrgMember

router = APIRouter(prefix="/api/admin/mcp", tags=["admin"])


class UsageRow(BaseModel):
    day: date
    tool_name: str
    call_count: int
    error_count: int
    latency_p50_ms: int | None
    latency_p99_ms: int | None


class UsageResponse(BaseModel):
    org_id: UUID
    from_day: date
    to_day: date
    rows: list[UsageRow]
    source: str  # "daily_table" | "live_aggregation"


@router.get("/usage", response_model=UsageResponse)
async def get_mcp_usage(
    days: int = Query(30, ge=1, le=90),
    member: OrgMember = Depends(require_role(*ADMIN_ROLES)),
    db: AsyncSession = Depends(get_db),
) -> UsageResponse:
    """Per-day, per-tool MCP usage counts for this org over the last N days.

    Reads mcp_usage_daily when available; otherwise live-aggregates over
    mcp_call_log so dashboards work even before the first aggregator run.
    """
    today = datetime.now(timezone.utc).date()
    from_day = today - timedelta(days=days - 1)

    daily_rows = (
        await db.execute(
            select(MCPUsageDaily)
            .where(
                MCPUsageDaily.org_id == member.org_id,
                MCPUsageDaily.day >= from_day,
            )
            .order_by(MCPUsageDaily.day.desc(), MCPUsageDaily.tool_name)
        )
    ).scalars().all()

    if daily_rows:
        return UsageResponse(
            org_id=member.org_id,
            from_day=from_day,
            to_day=today,
            source="daily_table",
            rows=[
                UsageRow(
                    day=r.day,
                    tool_name=r.tool_name,
                    call_count=r.call_count,
                    error_count=r.error_count,
                    latency_p50_ms=r.latency_p50_ms,
                    latency_p99_ms=r.latency_p99_ms,
                )
                for r in daily_rows
            ],
        )

    # Live aggregation fallback
    live = (
        await db.execute(
            select(
                func.date(MCPCallLog.occurred_at).label("day"),
                MCPCallLog.tool_name,
                func.count().label("call_count"),
                func.sum(
                    func.cast(
                        MCPCallLog.status == "error", type_=db.bind.dialect.dbapi.NUMBER if False else None
                    )
                ),
            )
            .where(
                MCPCallLog.org_id == member.org_id,
                MCPCallLog.occurred_at >= datetime.combine(from_day, datetime.min.time(), tzinfo=timezone.utc),
            )
            .group_by(func.date(MCPCallLog.occurred_at), MCPCallLog.tool_name)
            .order_by(func.date(MCPCallLog.occurred_at).desc(), MCPCallLog.tool_name)
        )
    ).all()

    return UsageResponse(
        org_id=member.org_id,
        from_day=from_day,
        to_day=today,
        source="live_aggregation",
        rows=[
            UsageRow(
                day=r[0],
                tool_name=r[1],
                call_count=int(r[2] or 0),
                error_count=int(r[3] or 0),
                latency_p50_ms=None,
                latency_p99_ms=None,
            )
            for r in live
        ],
    )
