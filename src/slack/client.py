"""Thin Slack Web API client.

Only what the agent adapter needs, so the adapter stays about conversation
rather than HTTP. Every call returns the parsed payload; callers check ``ok``.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.shared.models import OAuthToken
from src.shared.types import SourceType

logger = logging.getLogger(__name__)

API_BASE = "https://slack.com/api"
_TIMEOUT = 15.0

# Beyond the DM-delivery scopes, the agent needs to be addressed and to
# answer where it was addressed.
AGENT_BOT_SCOPES = (
    "app_mentions:read",
    "assistant:write",
    "chat:write",
    "commands",
    "im:history",
    "im:write",
    "users:read",
    "users:read.email",
)


async def get_bot_token(db: AsyncSession, org_id: UUID) -> str | None:
    """The stored Slack bot token for this org, if the connector is linked."""
    result = await db.execute(
        select(OAuthToken).where(
            OAuthToken.org_id == org_id,
            OAuthToken.connector == SourceType.SLACK,
        )
    )
    token = result.scalar_one_or_none()
    return token.access_token if token else None


async def call(token: str, method: str, payload: dict[str, Any]) -> dict:
    """POST to one Slack Web API method."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        response = await client.post(
            f"{API_BASE}/{method}",
            json=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
        )
    body = response.json()
    if not body.get("ok"):
        logger.warning("Slack %s failed: %s", method, body.get("error"))
    return body


async def lookup_slack_email(token: str, slack_user_id: str) -> str | None:
    """The email on a Slack profile, which is how we match Numen members."""
    body = await call(token, "users.info", {"user": slack_user_id})
    if not body.get("ok"):
        return None
    profile = (body.get("user") or {}).get("profile") or {}
    email = profile.get("email")
    return email.lower() if email else None


async def post_message(token: str, channel: str, text: str, thread_ts: str | None = None, blocks=None) -> dict:
    payload: dict[str, Any] = {"channel": channel, "text": text}
    if thread_ts:
        payload["thread_ts"] = thread_ts
    if blocks:
        payload["blocks"] = blocks
    return await call(token, "chat.postMessage", payload)


async def post_ephemeral(token: str, channel: str, user: str, text: str, thread_ts: str | None = None) -> dict:
    """Reply visibly to one person in a channel, invisibly to everyone else."""
    payload: dict[str, Any] = {"channel": channel, "user": user, "text": text}
    if thread_ts:
        payload["thread_ts"] = thread_ts
    return await call(token, "chat.postEphemeral", payload)


async def set_status(token: str, channel: str, thread_ts: str, status: str) -> dict:
    """Show what the agent is doing, in place of streaming tokens.

    Uses the current agent-session API and falls back to the legacy
    assistant-threads method on older workspaces.
    """
    body = await call(
        token,
        "agents.sessions.setStatus",
        {"channel_id": channel, "thread_ts": thread_ts, "status": status},
    )
    if body.get("ok"):
        return body

    return await call(
        token,
        "assistant.threads.setStatus",
        {"channel_id": channel, "thread_ts": thread_ts, "status": status},
    )


async def set_suggested_prompts(token: str, channel: str, thread_ts: str, prompts: list[dict]) -> dict:
    """Seed an empty thread with things worth asking. Slack shows up to four."""
    return await call(
        token,
        "assistant.threads.setSuggestedPrompts",
        {"channel_id": channel, "thread_ts": thread_ts, "prompts": prompts[:4]},
    )
