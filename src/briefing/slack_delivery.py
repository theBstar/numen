"""Slack DM delivery for Numen daily briefings."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.models import OAuthToken, OrgMember
from src.shared.types import BriefingItem, SourceType
from src.slack.actions import build_item_actions

logger = logging.getLogger(__name__)

_API_BASE = "https://slack.com/api"
_MAX_RETRIES = 3
_BASE_BACKOFF_SECONDS = 1.0

# Scopes that must be present on the bot token for DM delivery to succeed.
# OAuthToken.scopes is the comma-joined string we stored at connect time.
_REQUIRED_BOT_SCOPES = ("chat:write", "im:write", "users:read.email")


def _missing_required_scopes(token: OAuthToken) -> list[str]:
    """Return any required bot scopes that aren't present on the stored token."""
    granted = {s.strip() for s in (token.scopes or "").split(",") if s.strip()}
    return [s for s in _REQUIRED_BOT_SCOPES if s not in granted]


async def _get_slack_token(db: AsyncSession, org_id) -> OAuthToken | None:
    result = await db.execute(
        select(OAuthToken).where(
            OAuthToken.org_id == org_id,
            OAuthToken.connector == SourceType.SLACK,
        )
    )
    return result.scalar_one_or_none()


def _build_blocks(
    member: OrgMember,
    items: list[BriefingItem],
    narrative: str | None,
) -> list[dict]:
    """Build a Block Kit payload for the briefing DM."""
    name = member.display_name or member.email.split("@")[0]
    today = datetime.now(timezone.utc).strftime("%b %-d, %Y")

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"Your Numen Briefing - {today}"},
        },
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"Good morning, {name}."},
            ],
        },
    ]

    if narrative:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": narrative}})

    blocks.append({"type": "divider"})

    for item in items[:10]:
        urgency_pct = int(round(max(0.0, min(1.0, item.urgency_score)) * 100))
        link = ""
        if item.source_links:
            first = item.source_links[0]
            url = first.get("url") if isinstance(first, dict) else None
            if url:
                link = f"\n<{url}|Open in source>"
        text = (
            f"*{item.title}*  `urgency {urgency_pct}`\n"
            f"{item.why_it_matters}"
            f"{link}"
        )
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": text}})
        # Each item is the start of a conversation, not a dead end.
        blocks.append(build_item_actions(item.entity_id, item.title))

    if len(items) > 10:
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"...and {len(items) - 10} more in your dashboard."},
                ],
            }
        )

    return blocks


async def _slack_post(
    client: httpx.AsyncClient,
    method: str,
    *,
    json: dict | None = None,
    params: dict | None = None,
) -> dict:
    """POST/GET a Slack Web API method and return the JSON body. Raises on transport errors."""
    url = f"{_API_BASE}/{method}"
    if json is not None:
        resp = await client.post(url, json=json)
    else:
        resp = await client.get(url, params=params)
    resp.raise_for_status()
    return resp.json()


async def deliver_via_slack(
    db: AsyncSession,
    member: OrgMember,
    items: list[BriefingItem],
    *,
    narrative: str | None = None,
) -> tuple[bool, str | None]:
    """Deliver the briefing as a Slack DM.

    Returns (success, fallback_reason). On failure, ``fallback_reason`` is one
    of ``"no_token"``, ``"missing_scopes"``, ``"user_not_found"``,
    ``"open_dm_failed"``, ``"post_failed"`` so the caller can fall back to
    email and record the reason on the Briefing.
    """
    token = await _get_slack_token(db, member.org_id)
    if token is None:
        return False, "no_token"

    if _missing_required_scopes(token):
        # Token predates the bot-scope change -- user must reconnect Slack.
        return False, "missing_scopes"

    headers = {
        "Authorization": f"Bearer {token.access_token}",
        "Content-Type": "application/json; charset=utf-8",
    }

    async with httpx.AsyncClient(headers=headers, timeout=15.0) as client:
        # 1. Resolve member.email -> Slack user_id
        try:
            lookup = await _slack_post(
                client,
                "users.lookupByEmail",
                params={"email": member.email},
            )
        except Exception:
            logger.warning("slack users.lookupByEmail transport error for member=%s", member.id, exc_info=True)
            return False, "user_not_found"

        if not lookup.get("ok"):
            err = lookup.get("error", "unknown")
            if err == "users_not_found":
                logger.info("slack: no user with email=%s in workspace", member.email)
            else:
                logger.warning("slack users.lookupByEmail error=%s for member=%s", err, member.id)
            return False, "user_not_found"

        slack_user_id = lookup.get("user", {}).get("id")
        if not slack_user_id:
            return False, "user_not_found"

        # 2. Open a DM channel
        try:
            opened = await _slack_post(
                client,
                "conversations.open",
                json={"users": slack_user_id},
            )
        except Exception:
            logger.warning("slack conversations.open transport error for member=%s", member.id, exc_info=True)
            return False, "open_dm_failed"

        if not opened.get("ok"):
            logger.warning("slack conversations.open error=%s for member=%s", opened.get("error"), member.id)
            return False, "open_dm_failed"

        channel_id = opened.get("channel", {}).get("id")
        if not channel_id:
            return False, "open_dm_failed"

        # 3. Post the message with retry on transient errors
        blocks = _build_blocks(member, items, narrative)
        fallback_text = f"Your Numen briefing - {len(items)} updates"

        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                posted = await _slack_post(
                    client,
                    "chat.postMessage",
                    json={
                        "channel": channel_id,
                        "blocks": blocks,
                        "text": fallback_text,
                    },
                )
            except Exception:
                logger.warning(
                    "slack chat.postMessage transport error (attempt %d/%d) member=%s",
                    attempt,
                    _MAX_RETRIES,
                    member.id,
                    exc_info=True,
                )
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(_BASE_BACKOFF_SECONDS * (2 ** (attempt - 1)))
                    continue
                return False, "post_failed"

            if posted.get("ok"):
                logger.info(
                    "Slack briefing delivered to member=%s ts=%s",
                    member.id,
                    posted.get("ts"),
                )
                return True, None

            err = posted.get("error", "unknown")
            # Non-retryable auth errors should fall back immediately.
            if err in {"not_authed", "invalid_auth", "token_revoked", "missing_scope"}:
                logger.warning("slack chat.postMessage non-retryable error=%s member=%s", err, member.id)
                return False, "post_failed"
            logger.warning(
                "slack chat.postMessage error=%s (attempt %d/%d) member=%s",
                err,
                attempt,
                _MAX_RETRIES,
                member.id,
            )
            if attempt < _MAX_RETRIES:
                await asyncio.sleep(_BASE_BACKOFF_SECONDS * (2 ** (attempt - 1)))

    return False, "post_failed"
