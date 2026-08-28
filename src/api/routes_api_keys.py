"""API key management endpoints for MCP authentication."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_member, get_db
from src.api.schemas import (
    ApiKeyCreateRequest,
    ApiKeyCreateResponse,
    ApiKeyListResponse,
    ApiKeyResponse,
)
from src.mcp.auth import create_api_key, list_api_keys, revoke_api_key
from src.shared.models import OrgMember

router = APIRouter(
    prefix="/api/orgs/{org_id}",
    tags=["mcp"],
    dependencies=[Depends(get_current_member)],
)


@router.post("/api-keys", response_model=ApiKeyCreateResponse, status_code=201)
async def create_key(
    body: ApiKeyCreateRequest,
    org_id: UUID = Path(...),
    member: OrgMember = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """Create a new API key for MCP access. The plaintext key is returned only once."""
    plaintext, api_key = await create_api_key(db, org_id, body.name, user_id=member.user_id)
    await db.commit()
    return ApiKeyCreateResponse(
        id=api_key.id,
        name=api_key.name,
        key=plaintext,
        created_at=api_key.created_at,
    )


@router.get("/api-keys", response_model=ApiKeyListResponse)
async def list_keys(
    org_id: UUID = Path(...),
    member: OrgMember = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """List all API keys for this organization (keys are never returned)."""
    keys = await list_api_keys(db, org_id)
    return ApiKeyListResponse(items=[ApiKeyResponse.model_validate(k) for k in keys])


@router.delete("/api-keys/{key_id}", status_code=204)
async def delete_key(
    key_id: UUID = Path(...),
    org_id: UUID = Path(...),
    member: OrgMember = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """Revoke an API key."""
    revoked = await revoke_api_key(db, key_id, org_id)
    if not revoked:
        raise HTTPException(status_code=404, detail="API key not found")
    await db.commit()
