"""File attachment routes."""

from __future__ import annotations

import logging
import os
from pathlib import Path as FilePath
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.dependencies import get_current_member, get_db
from src.api.schemas import (
    AttachmentListResponse,
    AttachmentResponse,
    ErrorResponse,
)
from src.graph import get_entity_or_404
from src.shared.models import OrgMember, TaskAttachment
from src.shared.types import EntityType

logger = logging.getLogger(__name__)

UPLOAD_BASE_DIR = "uploads"

# Task-scoped routes
task_router = APIRouter(
    prefix="/api/orgs/{org_id}/tasks/{task_id}",
    tags=["attachments"],
    dependencies=[Depends(get_current_member)],
)
# Org-scoped routes for download
attachment_router = APIRouter(
    prefix="/api/orgs/{org_id}/attachments",
    tags=["attachments"],
    dependencies=[Depends(get_current_member)],
)


# ── Helpers ───────────────────────────────────────────────────────────


def _attachment_to_response(a: TaskAttachment) -> AttachmentResponse:
    """Build an AttachmentResponse from a TaskAttachment model."""
    return AttachmentResponse(
        id=a.id,
        entity_id=a.entity_id,
        filename=a.filename,
        file_size=a.file_size,
        mime_type=a.mime_type,
        created_at=a.created_at,
    )


def _get_storage_dir(org_id: UUID, entity_id: UUID) -> FilePath:
    """Get the storage directory for a task's attachments."""
    return FilePath(UPLOAD_BASE_DIR) / str(org_id) / str(entity_id)


# ── Task-scoped routes ───────────────────────────────────────────────


@task_router.post(
    "/attachments",
    response_model=AttachmentResponse,
    status_code=201,
    summary="Upload attachment",
    responses={404: {"model": ErrorResponse}},
)
async def upload_attachment(
    file: UploadFile,
    org_id: UUID = Path(...),
    task_id: UUID = Path(...),
    member: OrgMember = Depends(get_current_member),
    db: AsyncSession = Depends(get_db),
):
    """Upload a file attachment for a task."""
    # Verify task exists in org
    await get_entity_or_404(db, task_id, org_id=org_id, expected_type=EntityType.TASK)

    # Create storage directory
    storage_dir = _get_storage_dir(org_id, task_id)
    storage_dir.mkdir(parents=True, exist_ok=True)

    # Read file content
    content = await file.read()
    file_size = len(content)

    # Write file to disk
    filename = file.filename or "unnamed"
    file_path = storage_dir / filename

    # Avoid overwriting - append counter if file exists
    counter = 1
    original_stem = file_path.stem
    original_suffix = file_path.suffix
    while file_path.exists():
        file_path = storage_dir / f"{original_stem}_{counter}{original_suffix}"
        counter += 1

    with open(file_path, "wb") as f:
        f.write(content)

    # Store metadata in DB
    storage_key = str(file_path)
    attachment = TaskAttachment(
        org_id=org_id,
        entity_id=task_id,
        uploaded_by=member.id,
        filename=filename,
        file_size=file_size,
        mime_type=file.content_type,
        storage_key=storage_key,
    )
    db.add(attachment)
    await db.commit()
    await db.refresh(attachment)

    return _attachment_to_response(attachment)


@task_router.get(
    "/attachments",
    response_model=AttachmentListResponse,
    summary="List attachments",
)
async def list_attachments(
    org_id: UUID = Path(...),
    task_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
):
    """List all attachments for a task."""
    result = await db.execute(
        select(TaskAttachment)
        .where(
            TaskAttachment.org_id == org_id,
            TaskAttachment.entity_id == task_id,
        )
        .order_by(TaskAttachment.created_at.desc())
    )
    attachments = result.scalars().all()

    items = [_attachment_to_response(a) for a in attachments]
    return AttachmentListResponse(items=items)


@task_router.delete(
    "/attachments/{attachment_id}",
    status_code=204,
    summary="Delete attachment",
    responses={404: {"model": ErrorResponse}},
)
async def delete_attachment(
    org_id: UUID = Path(...),
    task_id: UUID = Path(...),
    attachment_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
):
    """Delete a file attachment and remove the file from disk."""
    result = await db.execute(
        select(TaskAttachment).where(
            TaskAttachment.id == attachment_id,
            TaskAttachment.org_id == org_id,
            TaskAttachment.entity_id == task_id,
        )
    )
    attachment = result.scalar_one_or_none()
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")

    # Delete file from disk
    try:
        file_path = FilePath(attachment.storage_key)
        if file_path.exists():
            os.remove(file_path)
    except OSError:
        logger.warning(f"Failed to delete file: {attachment.storage_key}")

    await db.delete(attachment)
    await db.commit()
    return None


# ── Org-scoped download route ────────────────────────────────────────


@attachment_router.get(
    "/{attachment_id}/download",
    summary="Download attachment",
    responses={404: {"model": ErrorResponse}},
)
async def download_attachment(
    org_id: UUID = Path(...),
    attachment_id: UUID = Path(...),
    db: AsyncSession = Depends(get_db),
):
    """Download a file attachment."""
    result = await db.execute(
        select(TaskAttachment).where(
            TaskAttachment.id == attachment_id,
            TaskAttachment.org_id == org_id,
        )
    )
    attachment = result.scalar_one_or_none()
    if not attachment:
        raise HTTPException(status_code=404, detail="Attachment not found")

    file_path = FilePath(attachment.storage_key)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    return FileResponse(
        path=str(file_path),
        filename=attachment.filename,
        media_type=attachment.mime_type or "application/octet-stream",
    )
