"""Cross-source person duplicate detection for post-sync resolution.

Entity data is read from FalkorDB. PersonResolution records are stored in PostgreSQL.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.graph.falkor_repository import GraphNode, list_entities
from src.shared.models import PersonResolution
from src.shared.types import EntityType

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Confidence tiers ─────────────────────────────────────────────────

CONFIDENCE_EMAIL = 0.95
CONFIDENCE_GITHUB = 0.85
CONFIDENCE_SLACK = 0.80
CONFIDENCE_EXACT_NAME = 0.60
CONFIDENCE_FUZZY_NAME = 0.40
MIN_CONFIDENCE = 0.35


def _compute_match(candidate: GraphNode, existing: GraphNode) -> tuple[float, list[dict]]:
    """Compute match confidence and reasons between two Person entities.

    Checks source_ids and properties for cross-source identity signals.
    Returns (confidence, match_reasons) where confidence is the max match score.
    """
    reasons: list[dict] = []
    best_confidence = 0.0

    c_ids = candidate.source_ids or {}
    c_props = candidate.properties or {}
    e_ids = existing.source_ids or {}
    e_props = existing.properties or {}

    # Collect all emails from both entities (source_ids + properties)
    c_emails = set()
    e_emails = set()
    for key in ("email", "emails"):
        if key in c_ids:
            c_emails.add(c_ids[key].lower())
        if key in c_props and isinstance(c_props[key], str) and c_props[key]:
            c_emails.add(c_props[key].lower())
        if key in e_ids:
            e_emails.add(e_ids[key].lower())
        if key in e_props and isinstance(e_props[key], str) and e_props[key]:
            e_emails.add(e_props[key].lower())

    # Email match
    shared_emails = c_emails & e_emails
    if shared_emails:
        email = next(iter(shared_emails))
        reasons.append({"type": "email", "value": email})
        best_confidence = max(best_confidence, CONFIDENCE_EMAIL)

    # GitHub numeric ID match (immutable, highest confidence after email)
    c_github_id = c_ids.get("github_id")
    e_github_id = e_ids.get("github_id")
    if c_github_id and e_github_id and c_github_id == e_github_id:
        reasons.append({"type": "github_id", "value": c_github_id})
        best_confidence = max(best_confidence, CONFIDENCE_GITHUB)

    # GitHub username match (source_ids keys: "github", "github_username")
    c_github = (
        c_ids.get("github") or c_ids.get("github_username") or c_props.get("login") or c_props.get("github_username")
    )
    e_github = (
        e_ids.get("github") or e_ids.get("github_username") or e_props.get("login") or e_props.get("github_username")
    )
    if c_github and e_github and c_github.lower() == e_github.lower():
        reasons.append({"type": "github_username", "value": c_github})
        best_confidence = max(best_confidence, CONFIDENCE_GITHUB)

    # Slack ID match
    c_slack = c_ids.get("slack_id") or c_ids.get("slack")
    e_slack = e_ids.get("slack_id") or e_ids.get("slack")
    if c_slack and e_slack and c_slack == e_slack:
        reasons.append({"type": "slack_id", "value": c_slack})
        best_confidence = max(best_confidence, CONFIDENCE_SLACK)

    # Name matching (only if no stronger signal found)
    c_name = (candidate.canonical_name or "").strip().lower()
    e_name = (existing.canonical_name or "").strip().lower()
    if c_name and e_name and c_name != e_name:
        # Exact case-insensitive match
        if c_name == e_name:
            reasons.append({"type": "exact_name", "value": candidate.canonical_name})
            best_confidence = max(best_confidence, CONFIDENCE_EXACT_NAME)
        # Fuzzy: one name contains the other (e.g., "dana" in "dana okafor")
        elif len(c_name) >= 3 and len(e_name) >= 3:
            if c_name in e_name or e_name in c_name:
                reasons.append(
                    {
                        "type": "fuzzy_name",
                        "value": f"{candidate.canonical_name} ~ {existing.canonical_name}",
                    }
                )
                best_confidence = max(best_confidence, CONFIDENCE_FUZZY_NAME)

    return best_confidence, reasons


async def detect_person_duplicates(
    db: AsyncSession,
    org_id: UUID,
    candidate_entity_ids: list[UUID] | None = None,
) -> list[PersonResolution]:
    """Scan Person entities for cross-source duplicates.

    If candidate_entity_ids is provided, only check those entities.
    Otherwise, scan all Person entities in the org.

    Returns list of newly created PersonResolution records.
    """
    # Load all Person entities from FalkorDB
    all_persons = await list_entities(
        None,
        org_id,
        entity_type=EntityType.PERSON,
        limit=10000,
    )
    # Filter out merged entities
    all_persons = [p for p in all_persons if p.get("merged_into") is None]

    if not all_persons:
        return []

    # Filter candidates
    if candidate_entity_ids:
        str_ids = {str(cid) for cid in candidate_entity_ids}
        candidates = [p for p in all_persons if str(p.id) in str_ids]
    else:
        candidates = list(all_persons)

    # Load existing resolution pairs to avoid re-flagging
    existing_pairs = await _get_existing_resolution_pairs(db, org_id)

    new_resolutions: list[PersonResolution] = []

    for candidate in candidates:
        for existing in all_persons:
            c_id = UUID(str(candidate.id)) if not isinstance(candidate.id, UUID) else candidate.id
            e_id = UUID(str(existing.id)) if not isinstance(existing.id, UUID) else existing.id

            # Skip self
            if c_id == e_id:
                continue

            # Skip same-source entities (they are already deduplicated by upsert_entity)
            if candidate.source == existing.source:
                continue

            # Skip already-resolved pairs (in either direction)
            pair = _normalize_pair(c_id, e_id)
            if pair in existing_pairs:
                continue

            confidence, reasons = _compute_match(candidate, existing)

            if confidence < MIN_CONFIDENCE:
                continue

            resolution = PersonResolution(
                org_id=org_id,
                candidate_entity_id=c_id,
                match_entity_id=e_id,
                confidence=confidence,
                match_reasons=reasons,
                status="pending",
            )

            try:
                db.add(resolution)
                await db.flush()
                new_resolutions.append(resolution)
                existing_pairs.add(pair)
            except IntegrityError:
                # Concurrent sync already created this pair
                await db.rollback()
                logger.debug(
                    "Resolution pair already exists: %s <-> %s",
                    c_id,
                    e_id,
                )

    if new_resolutions:
        logger.info(
            "Detected %d potential duplicate person(s) in org %s",
            len(new_resolutions),
            org_id,
        )

    return new_resolutions


async def _get_existing_resolution_pairs(db: AsyncSession, org_id: UUID) -> set[tuple[UUID, UUID]]:
    """Get all existing resolution pairs (regardless of status) to avoid re-flagging."""
    result = await db.execute(
        select(
            PersonResolution.candidate_entity_id,
            PersonResolution.match_entity_id,
        ).where(
            PersonResolution.org_id == org_id,
            PersonResolution.status.in_(["merged", "distinct", "pending"]),
        )
    )
    pairs: set[tuple[UUID, UUID]] = set()
    for row in result.all():
        pairs.add(_normalize_pair(row[0], row[1]))
    return pairs


def _normalize_pair(id_a: UUID, id_b: UUID) -> tuple[UUID, UUID]:
    """Normalize a pair of UUIDs so (A, B) and (B, A) map to the same key."""
    return (min(id_a, id_b), max(id_a, id_b))
