"""Slack events for the agent.

Kept separate from ``/api/webhooks/slack``, which feeds the ingestion
pipeline. Overloading that route would mean one endpoint deciding whether a
message is data to store or a question to answer, and the two have different
failure modes: a dropped ingest can be backfilled, a dropped question looks
like a broken bot.

Slack retries anything not acknowledged within three seconds, so this route
verifies, acknowledges, and does the work in the background.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from sqlalchemy import select

from src.config import settings
from src.shared.database import async_session
from src.shared.models import OAuthToken
from src.shared.types import SourceType
from src.slack.handler import handle_slack_event

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/slack", tags=["slack"])

# Slack signs with a timestamp; anything older is a replay.
_MAX_SKEW_SECONDS = 60 * 5


async def _verify_signature(request: Request, body: bytes) -> None:
    if not settings.slack_signing_secret:
        raise HTTPException(status_code=503, detail="Slack signing secret is not configured.")

    timestamp = request.headers.get("X-Slack-Request-Timestamp", "")
    signature = request.headers.get("X-Slack-Signature", "")
    if not timestamp or not signature:
        raise HTTPException(status_code=401, detail="Missing Slack signature headers.")

    try:
        age = abs(time.time() - int(timestamp))
    except ValueError:
        raise HTTPException(status_code=401, detail="Malformed Slack timestamp.") from None
    if age > _MAX_SKEW_SECONDS:
        raise HTTPException(status_code=401, detail="Slack request is too old.")

    expected = (
        "v0="
        + hmac.new(
            settings.slack_signing_secret.encode(),
            f"v0:{timestamp}:{body.decode()}".encode(),
            hashlib.sha256,
        ).hexdigest()
    )
    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="Invalid Slack signature.")


async def _org_for_team(team_id: str) -> UUID | None:
    """Which org installed the app in this Slack workspace."""
    if not team_id:
        return None
    async with async_session() as db:
        result = await db.execute(select(OAuthToken).where(OAuthToken.connector == SourceType.SLACK))
        for token in result.scalars().all():
            if (token.settings or {}).get("workspace_id") == team_id:
                return token.org_id
    return None


async def _process(team_id: str, event: dict) -> None:
    """Run one event on its own session, after the ack has gone back."""
    org_id = await _org_for_team(team_id)
    if org_id is None:
        logger.warning("Slack event from unknown workspace %s", team_id)
        return

    from src.shared.database import set_current_org_id

    set_current_org_id(str(org_id))
    try:
        async with async_session() as db:
            await handle_slack_event(db, org_id, event)
    except Exception:
        logger.exception("Slack event processing failed for org %s", org_id)
    finally:
        set_current_org_id(None)


async def _process_action(team_id: str, payload: dict) -> None:
    """Handle one button press on its own session."""
    from src.shared.database import set_current_org_id
    from src.slack.actions import handle_block_action

    org_id = await _org_for_team(team_id)
    if org_id is None:
        logger.warning("Slack interaction from unknown workspace %s", team_id)
        return

    set_current_org_id(str(org_id))
    try:
        async with async_session() as db:
            await handle_block_action(db, org_id, payload)
    except Exception:
        logger.exception("Slack interaction failed for org %s", org_id)
    finally:
        set_current_org_id(None)


@router.post("/interactions", summary="Slack interactive components")
async def slack_interactions(request: Request, background: BackgroundTasks):
    """Receive button presses from briefings.

    Slack sends these form-encoded with the payload as a JSON string, which
    is why this does not simply read the JSON body.
    """
    body = await request.body()
    await _verify_signature(request, body)

    form = await request.form()
    raw = form.get("payload")
    if not raw:
        raise HTTPException(status_code=400, detail="Missing interaction payload.")

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Malformed interaction payload.") from None

    if payload.get("type") == "block_actions":
        team_id = (payload.get("team") or {}).get("id", "")
        background.add_task(_process_action, team_id, payload)

    return {"ok": True}


@router.post("/events", summary="Slack Events API endpoint for the agent")
async def slack_events(request: Request, background: BackgroundTasks):
    body = await request.body()
    await _verify_signature(request, body)

    payload = await request.json()

    # Slack proves it owns the endpoint by asking us to echo a challenge.
    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge", "")}

    # A retry means our ack was late, not that the user asked twice.
    if request.headers.get("X-Slack-Retry-Num"):
        logger.info("Ignoring Slack retry %s", request.headers.get("X-Slack-Retry-Num"))
        return {"ok": True}

    if payload.get("type") == "event_callback":
        background.add_task(_process, payload.get("team_id", ""), payload.get("event") or {})

    return {"ok": True}
