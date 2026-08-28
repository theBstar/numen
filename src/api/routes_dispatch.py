"""Claude AI dispatch routes."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_member, get_db
from src.api.schemas import ClaudeDispatchRequest, ClaudeDispatchResponse
from src.shared.models import OrgMember

router = APIRouter(prefix="/api", tags=["dispatch"])


@router.post("/orgs/{org_id}/dispatch", response_model=ClaudeDispatchResponse)
async def claude_dispatch(
    req: ClaudeDispatchRequest,
    org_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
    _member: OrgMember = Depends(get_current_member),
):
    if req.action == "summarize_pr_diff":
        from src.llm.actions import summarize_pr_diff

        result = await summarize_pr_diff(db, req.entity_id)
        return ClaudeDispatchResponse(
            action=req.action,
            entity_id=req.entity_id,
            result=result,
            draft=True,
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {req.action}")
