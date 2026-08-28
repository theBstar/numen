"""Media upload management for PRD documents.

Uses S3-compatible storage (AWS S3 or Cloudflare R2) with presigned URLs
for direct browser-to-storage uploads.
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from uuid import UUID

import aioboto3
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.models import PrdMedia

logger = logging.getLogger(__name__)

# Config from environment
S3_BUCKET = os.getenv("NUMEN_S3_BUCKET", "numen-prd-media")
S3_REGION = os.getenv("NUMEN_S3_REGION", "us-east-1")
S3_ENDPOINT = os.getenv("NUMEN_S3_ENDPOINT")  # For R2 compatibility
S3_ACCESS_KEY = os.getenv("NUMEN_S3_ACCESS_KEY", "")
S3_SECRET_KEY = os.getenv("NUMEN_S3_SECRET_KEY", "")
CDN_BASE_URL = os.getenv("NUMEN_CDN_BASE_URL", "")

ALLOWED_TYPES = {
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "image/svg+xml",
    "application/pdf",
    "video/mp4",
    "video/webm",
}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
PRESIGNED_URL_EXPIRY = 900  # 15 minutes


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _build_s3_client_kwargs() -> dict:
    """Build kwargs for the aioboto3 S3 client."""
    if not S3_ACCESS_KEY or not S3_SECRET_KEY:
        raise ValueError(
            "S3 credentials not configured. Set NUMEN_S3_ACCESS_KEY and "
            "NUMEN_S3_SECRET_KEY environment variables."
        )

    kwargs: dict = {
        "service_name": "s3",
        "region_name": S3_REGION,
        "aws_access_key_id": S3_ACCESS_KEY,
        "aws_secret_access_key": S3_SECRET_KEY,
    }
    if S3_ENDPOINT:
        kwargs["endpoint_url"] = S3_ENDPOINT

    return kwargs


def _build_cdn_url(storage_key: str) -> str:
    """Build the public CDN URL for a stored object."""
    if CDN_BASE_URL:
        base = CDN_BASE_URL.rstrip("/")
        return f"{base}/{storage_key}"

    # Fall back to S3 bucket URL
    if S3_ENDPOINT:
        return f"{S3_ENDPOINT.rstrip('/')}/{S3_BUCKET}/{storage_key}"
    return f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{storage_key}"


async def generate_upload_url(
    org_id: UUID,
    entity_id: UUID,
    file_name: str,
    file_type: str,
) -> dict:
    """Generate a presigned PUT URL for direct browser upload.

    Returns ``{"upload_url": str, "storage_key": str}``.

    Raises:
        ValueError: If ``file_type`` is not in ``ALLOWED_TYPES`` or
            S3 credentials are missing.
    """
    if file_type not in ALLOWED_TYPES:
        raise ValueError(
            f"File type '{file_type}' is not allowed. "
            f"Accepted types: {', '.join(sorted(ALLOWED_TYPES))}"
        )

    storage_key = f"orgs/{org_id.hex}/prds/{entity_id.hex}/{uuid.uuid4().hex}/{file_name}"

    client_kwargs = _build_s3_client_kwargs()
    session = aioboto3.Session()

    async with session.client(**client_kwargs) as s3:
        upload_url = await s3.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": S3_BUCKET,
                "Key": storage_key,
                "ContentType": file_type,
            },
            ExpiresIn=PRESIGNED_URL_EXPIRY,
        )

    logger.info(
        "Generated presigned upload URL for org=%s entity=%s file=%s",
        org_id,
        entity_id,
        file_name,
    )

    return {"upload_url": upload_url, "storage_key": storage_key}


async def confirm_upload(
    db: AsyncSession,
    org_id: UUID,
    entity_id: UUID,
    member_id: UUID,
    storage_key: str,
    file_name: str,
    file_type: str,
    file_size: int,
) -> PrdMedia:
    """Confirm a completed upload and create the media record.

    Called by the frontend after a successful direct-to-S3 PUT so that
    the database tracks the uploaded file.

    Raises:
        ValueError: If ``file_size`` exceeds ``MAX_FILE_SIZE``.
    """
    if file_size > MAX_FILE_SIZE:
        raise ValueError(
            f"File size {file_size} bytes exceeds maximum of "
            f"{MAX_FILE_SIZE} bytes ({MAX_FILE_SIZE // (1024 * 1024)}MB)."
        )

    cdn_url = _build_cdn_url(storage_key)

    media = PrdMedia(
        org_id=org_id,
        entity_id=entity_id,
        uploaded_by=member_id,
        file_name=file_name,
        file_type=file_type,
        file_size=file_size,
        storage_key=storage_key,
        cdn_url=cdn_url,
    )
    db.add(media)
    await db.flush()

    logger.info(
        "Confirmed media upload id=%s org=%s entity=%s file=%s (%d bytes)",
        media.id,
        org_id,
        entity_id,
        file_name,
        file_size,
    )

    return media


async def list_media(
    db: AsyncSession,
    org_id: UUID,
    entity_id: UUID,
) -> list[PrdMedia]:
    """List all media for a PRD document, most recent first."""
    stmt = (
        select(PrdMedia)
        .where(PrdMedia.org_id == org_id, PrdMedia.entity_id == entity_id)
        .order_by(PrdMedia.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
