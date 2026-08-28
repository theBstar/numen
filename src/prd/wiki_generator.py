"""Hybrid wiki generation: deterministic PRD parsing + LLM semantic extraction.

Pipeline:
  Step 0  - Parse PRD blocks structurally (headings, terms, sections) - no LLM cost
  Step 1  - LLM extracts features + concepts from structured PRD data
  Step 2  - LLM generates product summary from extracted features
  Step 3  - Graph queries resolve implementation provenance (people, tasks, PRs)

Manual edits (is_manual=True) are preserved across regeneration. Per-PRD
content hashing enables incremental change detection.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.graph.context import context_to_text, extract_context_graph
from src.graph.falkor_queries import get_prd_coverage, get_prd_stakeholders
from src.graph.falkor_repository import list_entities
from src.llm.client import call_llm_with_trace
from src.shared.models import PrdBlock, WikiConcept, WikiFeature, WikiProductSummary
from src.shared.types import EntityType

logger = logging.getLogger(__name__)


# ── Deterministic extraction data classes ─────────────────────────────


@dataclass
class PrdSection:
    slug: str
    title: str
    level: int
    text_content: str
    detected_terms: list[str] = field(default_factory=list)


@dataclass
class PrdStructure:
    entity_id: str
    title: str
    sections: list[PrdSection] = field(default_factory=list)
    cross_references: list[str] = field(default_factory=list)


# ── LLM prompts ──────────────────────────────────────────────────────


FEATURE_EXTRACTION_SYSTEM = """\
You are a product documentation expert. \
Analyze the structured PRD data below and extract:

1. FEATURES: Discrete product capabilities. Each feature:
   - title: Clear feature name (e.g., "Todo Management")
   - slug: URL-safe identifier (lowercase, hyphens)
   - description: Full description compiled from ALL relevant PRDs. Include important details.
   - domain_group: Domain category (e.g., "core", "notifications", "admin", "integrations")
   - prd_references: For each PRD section that contributes, include:
     - entity_id: The PRD entity ID
     - section_slugs: Heading slugs from that PRD
     - prd_title: The PRD document title
     - confidence: "extracted" if explicitly stated, "inferred" if deduced from context
   - status: "active" | "planned" | "deprecated"
   - source_entity_ids: All PRD entity IDs that informed this feature

2. CONCEPTS: Important terms, roles, and domain concepts. Each concept:
   - term: The concept name (e.g., "admin", "owner", "overdue")
   - slug: URL-safe identifier
   - definition: What this term means in the product context
   - prd_references: Same format as features - which PRD sections define/describe this
   - related_feature_slugs: Which feature slugs reference this concept

Rules:
- Features must be FLAT - group by domain_group, no parent-child hierarchy
- Synthesize information from ALL PRDs that mention a feature
- section_slugs MUST reference actual [slug:xxx] identifiers from the input
- Concepts are reusable terms that appear across features - roles, states, entities
- Every feature must have at least one prd_reference
- Use hyphens (-) not em dashes

Output ONLY valid JSON with this structure:
{
  "features": [...],
  "concepts": [...]
}"""


SUMMARY_SYSTEM = """\
You are a product documentation expert. Given a list of product \
features, write a concise 2-4 sentence product summary that captures \
what the product does, who it's for, and its key capabilities. \
Use hyphens (-) not em dashes. Output ONLY the summary text, no JSON."""


# ── Main generation function ─────────────────────────────────────────


async def generate_wiki(db: AsyncSession, org_id: UUID) -> dict:
    """Generate or regenerate the wiki for an org.

    Hybrid pipeline:
      0. Parse PRD blocks deterministically
      1. LLM extracts features + concepts
      2. LLM generates product summary
      3. Graph queries for implementation provenance

    Manual features (is_manual=True) are preserved across regeneration.
    """
    # Step 0: Deterministic pre-processing
    prd_structures = await _parse_prd_structures(db, org_id)

    if not prd_structures:
        logger.info("No PRD content found for org=%s", org_id)
        return {
            "features": [],
            "concepts": [],
            "summary": None,
            "generated": False,
            "llm_trace": None,
            "message": "No PRD documents found to generate wiki from",
        }

    # Compute per-PRD hashes for incremental change detection
    prd_hashes = {
        ps.entity_id: hashlib.sha256(
            "".join(s.text_content for s in ps.sections).encode()
        ).hexdigest()[:32]
        for ps in prd_structures
    }
    overall_hash = hashlib.sha256(json.dumps(prd_hashes, sort_keys=True).encode()).hexdigest()[:32]

    # Check existing summary for change detection
    existing_summary = await db.execute(
        select(WikiProductSummary).where(WikiProductSummary.org_id == org_id)
    )
    existing_summary_row = existing_summary.scalar_one_or_none()

    if existing_summary_row and existing_summary_row.source_hash == overall_hash:
        features = await _load_existing_features(db, org_id)
        concepts = await _load_existing_concepts(db, org_id)
        return {
            "features": features,
            "concepts": concepts,
            "summary": {
                "summary": existing_summary_row.summary,
                "feature_count": existing_summary_row.feature_count,
                "prd_count": existing_summary_row.prd_count,
                "generated_at": (
                    str(existing_summary_row.generated_at)
                    if existing_summary_row.generated_at
                    else None
                ),
            },
            "generated": False,
            "llm_trace": None,
            "message": "Wiki is up to date - no changes detected in PRD content",
        }

    # Also gather graph context for richer extraction
    context = await _gather_org_context(db, org_id)
    context_text = await context_to_text(context)

    # Build structured input for LLM
    structured_input = _build_structured_input(prd_structures, context_text)

    logger.info(
        "Wiki generation for org=%s: %d PRDs, %d sections, %d chars input",
        org_id,
        len(prd_structures),
        sum(len(ps.sections) for ps in prd_structures),
        len(structured_input),
    )

    # Step 1: LLM feature + concept extraction
    user_prompt = f"""\
Analyze this structured PRD data and extract all product features \
and concepts.

{structured_input}

Extract all meaningful product features and cross-linkable concepts."""

    llm_response = await call_llm_with_trace(
        system=FEATURE_EXTRACTION_SYSTEM,
        user=user_prompt,
        max_tokens=8192,
    )

    logger.info(
        "Feature extraction LLM response: %d chars, model=%s",
        len(llm_response.text),
        llm_response.model,
    )

    parsed = _parse_extraction_json(llm_response.text)
    raw_features = parsed.get("features", [])
    raw_concepts = parsed.get("concepts", [])

    if not raw_features:
        logger.warning("LLM returned no features for org=%s", org_id)
        return {
            "features": [],
            "concepts": [],
            "summary": None,
            "generated": True,
            "llm_trace": _build_trace(llm_response),
            "message": "No features could be extracted from PRD content",
        }

    # Step 2: LLM product summary
    feature_list_text = "\n".join(
        f"- {f.get('title', 'Untitled')}: {f.get('description', '')[:200]}" for f in raw_features
    )
    summary_response = await call_llm_with_trace(
        system=SUMMARY_SYSTEM,
        user=f"Product features:\n{feature_list_text}",
        max_tokens=1024,
    )
    product_summary = summary_response.text.strip()

    # Step 3: Store everything - preserve manual edits
    trace = _build_trace(llm_response)

    # Load manual features to preserve
    manual_result = await db.execute(
        select(WikiFeature).where(
            WikiFeature.org_id == org_id,
            WikiFeature.is_manual == True,  # noqa: E712
        )
    )
    manual_features = {wf.slug: wf for wf in manual_result.scalars().all()}

    # Delete only auto-generated features
    await db.execute(
        delete(WikiFeature).where(
            WikiFeature.org_id == org_id,
            WikiFeature.is_manual == False,  # noqa: E712
        )
    )

    # Delete old concepts (always regenerated)
    await db.execute(delete(WikiConcept).where(WikiConcept.org_id == org_id))

    # Insert concepts first (need IDs for feature.concept_ids)
    concept_slug_to_id: dict[str, UUID] = {}
    for raw_concept in raw_concepts:
        slug = raw_concept.get("slug", "")
        if not slug:
            continue
        wc = WikiConcept(
            org_id=org_id,
            term=raw_concept.get("term", slug),
            slug=slug,
            definition=raw_concept.get("definition", ""),
            prd_references=raw_concept.get("prd_references", []),
            related_feature_ids=[],  # will populate after features are inserted
            source_hash=overall_hash,
            llm_trace=trace,
        )
        db.add(wc)
        await db.flush()
        concept_slug_to_id[slug] = wc.id

    # Insert features (skip slugs that already exist as manual)
    stored_features = []
    feature_slug_to_id: dict[str, UUID] = {}

    for i, feat in enumerate(raw_features):
        slug = feat.get("slug", f"feature-{i}")

        # If this slug exists as a manual feature, keep the manual version
        if slug in manual_features:
            mf = manual_features[slug]
            feature_slug_to_id[slug] = mf.id
            continue

        # Resolve concept IDs for this feature
        feat_concept_ids = []
        for rc in raw_concepts:
            related_slugs = rc.get("related_feature_slugs", [])
            if slug in related_slugs and rc.get("slug") in concept_slug_to_id:
                feat_concept_ids.append(str(concept_slug_to_id[rc["slug"]]))

        wf = WikiFeature(
            org_id=org_id,
            title=feat.get("title", "Untitled"),
            slug=slug,
            summary=feat.get("description", feat.get("summary", ""))[:500],
            content=feat.get("description", ""),
            status=feat.get("status", "active"),
            position=float(i),
            domain_group=feat.get("domain_group", ""),
            prd_references=feat.get("prd_references", []),
            concept_ids=feat_concept_ids,
            is_manual=False,
            source_entity_ids=feat.get("source_entity_ids", []),
            source_hash=overall_hash,
            llm_trace=trace,
        )
        db.add(wf)
        await db.flush()
        feature_slug_to_id[slug] = wf.id
        stored_features.append(wf)

    # Update concept.related_feature_ids with actual UUIDs
    for rc in raw_concepts:
        cslug = rc.get("slug", "")
        if cslug not in concept_slug_to_id:
            continue
        related_feature_uuids = []
        for fslug in rc.get("related_feature_slugs", []):
            if fslug in feature_slug_to_id:
                related_feature_uuids.append(str(feature_slug_to_id[fslug]))
        if related_feature_uuids:
            await db.execute(
                update(WikiConcept)
                .where(WikiConcept.id == concept_slug_to_id[cslug])
                .values(related_feature_ids=related_feature_uuids)
            )

    # Step 3b: Implementation provenance from graph
    for wf in stored_features:
        impl = await _gather_implementation(db, org_id, wf.prd_references)
        wf.implementation = impl

    # Upsert product summary
    if existing_summary_row:
        existing_summary_row.summary = product_summary
        existing_summary_row.feature_count = len(raw_features) + len(manual_features)
        existing_summary_row.prd_count = len(prd_structures)
        existing_summary_row.source_hash = overall_hash
        existing_summary_row.prd_hashes = prd_hashes
        existing_summary_row.llm_trace = _build_trace(summary_response)
    else:
        ws = WikiProductSummary(
            org_id=org_id,
            summary=product_summary,
            feature_count=len(raw_features) + len(manual_features),
            prd_count=len(prd_structures),
            source_hash=overall_hash,
            prd_hashes=prd_hashes,
            llm_trace=_build_trace(summary_response),
        )
        db.add(ws)

    await db.commit()

    # Return results
    features = await _load_existing_features(db, org_id)
    concepts = await _load_existing_concepts(db, org_id)

    return {
        "features": features,
        "concepts": concepts,
        "summary": {
            "summary": product_summary,
            "feature_count": len(features),
            "prd_count": len(prd_structures),
            "generated_at": None,
        },
        "generated": True,
        "llm_trace": trace,
        "message": (
            f"Generated {len(raw_features)} features and "
            f"{len(raw_concepts)} concepts from "
            f"{len(prd_structures)} PRDs"
        ),
    }


# ── Query helpers ────────────────────────────────────────────────────


async def get_wiki_features(db: AsyncSession, org_id: UUID) -> list[dict]:
    """Get existing wiki features for an org (no generation)."""
    return await _load_existing_features(db, org_id)


async def get_wiki_feature_by_slug(
    db: AsyncSession,
    org_id: UUID,
    slug: str,
) -> dict | None:
    """Get a single wiki feature by slug with full detail."""
    result = await db.execute(
        select(WikiFeature).where(
            WikiFeature.org_id == org_id,
            WikiFeature.slug == slug,
        )
    )
    wf = result.scalar_one_or_none()
    if not wf:
        return None

    # Resolve concept briefs
    concepts = []
    if wf.concept_ids:
        for cid in wf.concept_ids:
            cr = await db.execute(select(WikiConcept).where(WikiConcept.id == cid))
            wc = cr.scalar_one_or_none()
            if wc:
                concepts.append({"id": str(wc.id), "term": wc.term, "slug": wc.slug})

    # Resolve related features (share concepts)
    related = []
    if wf.concept_ids:
        all_features_result = await db.execute(
            select(WikiFeature).where(
                WikiFeature.org_id == org_id,
                WikiFeature.slug != wf.slug,
            )
        )
        for other in all_features_result.scalars().all():
            other_cids = set(other.concept_ids or [])
            if other_cids & set(wf.concept_ids):
                related.append(_feature_to_list_item(other))

    detail = _feature_to_dict(wf)
    detail["concepts"] = concepts
    detail["related_features"] = related
    return detail


async def get_wiki_concept_by_slug(
    db: AsyncSession,
    org_id: UUID,
    slug: str,
) -> dict | None:
    """Get a single wiki concept by slug."""
    result = await db.execute(
        select(WikiConcept).where(
            WikiConcept.org_id == org_id,
            WikiConcept.slug == slug,
        )
    )
    wc = result.scalar_one_or_none()
    if not wc:
        return None

    # Resolve features that reference this concept
    features = []
    for fid in wc.related_feature_ids or []:
        fr = await db.execute(select(WikiFeature).where(WikiFeature.id == fid))
        wf = fr.scalar_one_or_none()
        if wf:
            features.append(_feature_to_list_item(wf))

    return {
        "id": str(wc.id),
        "term": wc.term,
        "slug": wc.slug,
        "definition": wc.definition,
        "prd_references": wc.prd_references or [],
        "features": features,
        "generated_at": str(wc.generated_at) if wc.generated_at else None,
    }


async def get_wiki_landing(db: AsyncSession, org_id: UUID) -> dict:
    """Get wiki landing page data: summary + feature list + stats."""
    # Summary
    sr = await db.execute(select(WikiProductSummary).where(WikiProductSummary.org_id == org_id))
    summary_row = sr.scalar_one_or_none()
    summary = {
        "summary": summary_row.summary if summary_row else "",
        "feature_count": summary_row.feature_count if summary_row else 0,
        "prd_count": summary_row.prd_count if summary_row else 0,
        "generated_at": (
            str(summary_row.generated_at) if summary_row and summary_row.generated_at else None
        ),
    }

    # Features
    features = await _load_existing_features(db, org_id)

    # Domain groups
    domain_groups = sorted({f.get("domain_group", "") for f in features if f.get("domain_group")})

    # Stats
    total = len(features)
    active = sum(1 for f in features if f.get("status") == "active")
    planned = sum(1 for f in features if f.get("status") == "planned")
    manual = sum(1 for f in features if f.get("is_manual"))

    return {
        "summary": summary,
        "features": features,
        "domain_groups": domain_groups,
        "stats": {
            "total_features": total,
            "active": active,
            "planned": planned,
            "manual_edits": manual,
            "concept_count": await _count_concepts(db, org_id),
        },
    }


async def update_wiki_feature(
    db: AsyncSession,
    org_id: UUID,
    slug: str,
    data: dict,
) -> dict | None:
    """Update a wiki feature manually. Sets is_manual=True."""
    result = await db.execute(
        select(WikiFeature).where(
            WikiFeature.org_id == org_id,
            WikiFeature.slug == slug,
        )
    )
    wf = result.scalar_one_or_none()
    if not wf:
        return None

    if "title" in data:
        wf.title = data["title"]
    if "description" in data:
        wf.content = data["description"]
        wf.summary = data["description"][:500]
    if "domain_group" in data:
        wf.domain_group = data["domain_group"]
    if "status" in data:
        wf.status = data["status"]

    wf.is_manual = True
    await db.commit()

    return await get_wiki_feature_by_slug(db, org_id, slug)


# ── Step 0: Deterministic PRD parsing ────────────────────────────────


async def _parse_prd_structures(
    db: AsyncSession,
    org_id: UUID,
) -> list[PrdStructure]:
    """Parse PRD blocks into structured data - no LLM cost.

    Extracts section headings with slugs, text content, and detected terms
    (bolded text, definition patterns, role names).
    """
    from src.prd.wiki import _extract_text_from_content
    from src.shared.types import PrdStatus

    archived_ids: set[str] = set()
    entities = await list_entities(
        db,
        org_id,
        entity_type=EntityType.DOCUMENT,
        limit=10000,
    )
    for entity in entities:
        props = entity.properties
        if isinstance(props, str):
            props = json.loads(props)
        if props.get("prd_status") == PrdStatus.ARCHIVED.value:
            archived_ids.add(str(entity.id))

    query = select(PrdBlock).where(PrdBlock.org_id == org_id)
    if archived_ids:
        query = query.where(~PrdBlock.entity_id.in_([UUID(x) for x in archived_ids]))
    query = query.order_by(PrdBlock.entity_id, PrdBlock.position)

    result = await db.execute(query)
    blocks = result.scalars().all()

    if not blocks:
        return []

    # Group by entity_id
    entity_blocks: dict[str, list] = defaultdict(list)
    for block in blocks:
        entity_blocks[str(block.entity_id)].append(block)

    structures = []
    for entity_id, eblocks in entity_blocks.items():
        prd = PrdStructure(entity_id=entity_id, title="Untitled PRD")
        current_section: PrdSection | None = None

        for block in eblocks:
            text = _extract_text_from_content(block.content)
            if not text:
                continue

            # Detect the document title from h1
            is_h1 = block.block_type == "heading" and block.heading_level == 1
            if is_h1 and prd.title == "Untitled PRD":
                prd.title = text

            # Each heading starts a new section
            if block.block_type == "heading" and block.heading_level and block.slug:
                if current_section:
                    prd.sections.append(current_section)
                current_section = PrdSection(
                    slug=block.slug,
                    title=text,
                    level=block.heading_level,
                    text_content="",
                    detected_terms=_detect_terms_in_content(block.content),
                )
            elif current_section:
                current_section.text_content += f" {text}"
                current_section.detected_terms.extend(_detect_terms_in_content(block.content))
            else:
                # Content before first heading - create an implicit section
                current_section = PrdSection(
                    slug="intro",
                    title="Introduction",
                    level=1,
                    text_content=text,
                    detected_terms=_detect_terms_in_content(block.content),
                )

        if current_section:
            prd.sections.append(current_section)

        # Deduplicate detected terms
        for section in prd.sections:
            section.detected_terms = list(set(section.detected_terms))
            section.text_content = section.text_content.strip()

        if prd.sections:
            structures.append(prd)

    return structures


def _detect_terms_in_content(content: dict | None) -> list[str]:
    """Extract bolded terms and definition-like patterns from TipTap JSON."""
    if not content:
        return []

    terms = []

    # Check for bold marks
    if content.get("type") == "text":
        marks = content.get("marks", [])
        is_bold = any(m.get("type") == "bold" for m in marks)
        if is_bold:
            text = content.get("text", "").strip()
            # Only keep short bold terms (likely definitions/roles)
            if text and len(text.split()) <= 4:
                terms.append(text.lower())

    # Recurse into children
    for child in content.get("content", []):
        if isinstance(child, dict):
            terms.extend(_detect_terms_in_content(child))

    return terms


def _build_structured_input(
    prd_structures: list[PrdStructure],
    context_text: str,
) -> str:
    """Build the structured text input for the LLM from parsed PRD data."""
    parts = ["# Structured PRD Data\n"]

    for prd in prd_structures:
        parts.append(f"\n## PRD: {prd.title} (entity_id: {prd.entity_id})\n")
        for section in prd.sections:
            parts.append(f"### [slug:{section.slug}] {section.title}")
            if section.text_content:
                parts.append(f"  Content: {section.text_content}")
            if section.detected_terms:
                parts.append(f"  Detected terms: [{', '.join(section.detected_terms)}]")
            parts.append("")

    if context_text:
        parts.append("\n# Additional Context (Tasks, PRs, Goals)\n")
        parts.append(context_text)

    return "\n".join(parts)


# ── Implementation provenance from graph ─────────────────────────────


async def _gather_implementation(
    db: AsyncSession,
    org_id: UUID,
    prd_references: list[dict],
) -> dict:
    """Query graph for people, tasks, and PRs related to PRD entities."""
    people_map: dict[str, dict] = {}
    tasks: list[dict] = []
    prs: list[dict] = []

    for ref in prd_references:
        entity_id = ref.get("entity_id")
        if not entity_id:
            continue

        try:
            eid = UUID(entity_id)
        except (ValueError, TypeError):
            continue

        # People (stakeholders)
        try:
            stakeholders = await get_prd_stakeholders(db, eid, org_id=org_id)
            for s in stakeholders:
                pid = s.get("person_id", "")
                if pid and pid not in people_map:
                    people_map[pid] = {
                        "id": pid,
                        "name": s.get("person_name", "Unknown"),
                        "role": s.get("role_type", "stakeholder"),
                    }
        except Exception as e:
            logger.debug("Failed to get stakeholders for %s: %s", entity_id, e)

        # Tasks and PRs (from coverage)
        try:
            coverage = await get_prd_coverage(db, eid, org_id=org_id)
            task_count = coverage.get("total_tasks", 0)
            if task_count > 0:
                tasks.append(
                    {
                        "prd_entity_id": entity_id,
                        "total": task_count,
                        "done": coverage.get("tasks_done", 0),
                        "in_progress": coverage.get("tasks_in_progress", 0),
                    }
                )
            pr_count = coverage.get("linked_prs", 0)
            if pr_count > 0:
                prs.append(
                    {
                        "prd_entity_id": entity_id,
                        "count": pr_count,
                    }
                )
        except Exception as e:
            logger.debug("Failed to get coverage for %s: %s", entity_id, e)

    return {
        "people": list(people_map.values()),
        "tasks": tasks,
        "prs": prs,
    }


# ── Shared helpers ───────────────────────────────────────────────────


async def _gather_org_context(db: AsyncSession, org_id: UUID) -> dict:
    """Gather graph context for the org - tasks, PRs, goals beyond PRDs."""
    try:
        context = await extract_context_graph(
            org_id,
            query="product features capabilities requirements implementation",
            max_entities=100,
            expansion_hops=2,
            vector_k=20,
        )
        if context.get("entities"):
            return context
    except Exception as e:
        logger.warning("Vector search failed: %s, falling back", e)

    # Fallback: list entities directly
    entities = []
    for etype in [EntityType.TASK, EntityType.COMMIT_PR, EntityType.GOAL, EntityType.PROJECT]:
        try:
            import json as _json

            ents = await list_entities(db, org_id, entity_type=etype, limit=200)
            for e in ents:
                props = e.properties
                if isinstance(props, str):
                    try:
                        props = _json.loads(props)
                    except (ValueError, TypeError):
                        props = {}
                if not isinstance(props, dict):
                    props = {}
                entities.append(
                    {
                        "id": str(e.id),
                        "type": etype.value,
                        "canonical_name": e.canonical_name,
                        "properties": props,
                    }
                )
        except Exception as e:
            logger.warning("Failed to list %s entities: %s", etype.value, e)

    return {"entities": entities, "edges": [], "entry_scores": {}}


async def _load_existing_features(db: AsyncSession, org_id: UUID) -> list[dict]:
    """Load all features for an org, ordered by position."""
    result = await db.execute(
        select(WikiFeature).where(WikiFeature.org_id == org_id).order_by(WikiFeature.position)
    )
    return [_feature_to_dict(f) for f in result.scalars().all()]


async def _load_existing_concepts(db: AsyncSession, org_id: UUID) -> list[dict]:
    """Load all concepts for an org."""
    result = await db.execute(
        select(WikiConcept).where(WikiConcept.org_id == org_id).order_by(WikiConcept.term)
    )
    return [_concept_to_dict(c) for c in result.scalars().all()]


async def _count_concepts(db: AsyncSession, org_id: UUID) -> int:
    from sqlalchemy import func

    result = await db.execute(
        select(func.count()).select_from(WikiConcept).where(WikiConcept.org_id == org_id)
    )
    return result.scalar() or 0


def _feature_to_dict(wf: WikiFeature) -> dict:
    """Convert a WikiFeature model to a full response dict."""
    return {
        "id": str(wf.id),
        "title": wf.title,
        "slug": wf.slug,
        "summary": wf.summary,
        "description": wf.content,
        "domain_group": wf.domain_group or "",
        "status": wf.status,
        "is_manual": wf.is_manual,
        "prd_references": wf.prd_references or [],
        "concept_ids": wf.concept_ids or [],
        "implementation": wf.implementation or {},
        "prd_count": len(wf.prd_references) if wf.prd_references else 0,
        "source_entity_ids": wf.source_entity_ids or [],
        "llm_trace": wf.llm_trace,
        "generated_at": str(wf.generated_at) if wf.generated_at else None,
        "updated_at": str(wf.updated_at) if wf.updated_at else None,
    }


def _feature_to_list_item(wf: WikiFeature) -> dict:
    """Convert a WikiFeature to a lightweight list item."""
    return {
        "id": str(wf.id),
        "title": wf.title,
        "slug": wf.slug,
        "description": wf.content[:200] if wf.content else "",
        "domain_group": wf.domain_group or "",
        "status": wf.status,
        "is_manual": wf.is_manual,
        "prd_count": len(wf.prd_references) if wf.prd_references else 0,
    }


def _concept_to_dict(wc: WikiConcept) -> dict:
    """Convert a WikiConcept to a response dict."""
    return {
        "id": str(wc.id),
        "term": wc.term,
        "slug": wc.slug,
        "definition": wc.definition,
        "prd_references": wc.prd_references or [],
        "related_feature_ids": wc.related_feature_ids or [],
        "generated_at": str(wc.generated_at) if wc.generated_at else None,
    }


def _parse_extraction_json(text: str) -> dict:
    """Parse the LLM's JSON response containing features and concepts."""
    # Try direct parse
    try:
        result = json.loads(text)
        if isinstance(result, dict) and "features" in result:
            return result
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code block
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group(1))
            if isinstance(result, dict) and "features" in result:
                return result
        except json.JSONDecodeError:
            pass

    # Try finding object braces
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            result = json.loads(text[start : end + 1])
            if isinstance(result, dict) and "features" in result:
                return result
        except json.JSONDecodeError:
            pass

    # Fallback: try parsing as array (old format compat)
    try:
        arr = json.loads(text)
        if isinstance(arr, list):
            return {"features": arr, "concepts": []}
    except json.JSONDecodeError:
        pass

    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        try:
            arr = json.loads(match.group())
            if isinstance(arr, list):
                return {"features": arr, "concepts": []}
        except json.JSONDecodeError:
            pass

    logger.warning("Failed to parse LLM extraction response")
    return {"features": [], "concepts": []}


def _build_trace(response) -> dict:
    """Build a trace dict from an LLMResponse."""
    return {
        "model": response.model,
        "input_token_count": response.input_token_count,
        "output_token_count": response.output_token_count,
        "latency_ms": response.latency_ms,
    }
