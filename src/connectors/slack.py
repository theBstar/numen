"""Slack connector -- extracts decisions and entity mentions from conversations."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from src.connectors.base import BaseConnector
from src.connectors.schemas.slack import (
    SlackDecisionProperties,
    SlackMentionProperties,
)
from src.graph import (
    get_entity_by_source,
    resolve_or_create_person,
    track_edge_result,
    upsert_edge,
    upsert_entity,
)
from src.shared.models import OAuthToken
from src.shared.types import (
    ConnectorSyncResult,
    EdgeCreate,
    EdgeType,
    EntityCreate,
    EntityType,
    SourceType,
)

logger = logging.getLogger(__name__)

API_BASE = "https://slack.com/api"

# Patterns that signal a "decision" in a message (bookmarks, specific emoji reactions, etc.)
_DECISION_EMOJI = {
    "white_check_mark",
    "heavy_check_mark",
    "ballot_box_with_check",
    "decision",
    "approved",
}

# Regex patterns for extracting references to entities in other tools
_ENTITY_MENTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # Linear-style issue IDs: ENG-1234, PLAT-42, etc.
    ("linear_issue", re.compile(r"\b([A-Z]{2,10}-\d{1,6})\b")),
    # GitHub PR references: PR #123, #456 (in context)
    ("github_pr", re.compile(r"\bPR\s*#(\d{1,6})\b", re.IGNORECASE)),
    # GitHub repo references: org/repo#123
    ("github_ref", re.compile(r"\b([\w\-]+/[\w\-]+#\d{1,6})\b")),
    # Generic ticket/issue references: TICKET-123, ISSUE-456
    ("ticket", re.compile(r"\b(TICKET|ISSUE|BUG)-(\d{1,6})\b", re.IGNORECASE)),
]


class SlackConnector(BaseConnector):
    source = SourceType.SLACK

    # ── public interface ──────────────────────────────────────────────

    async def sync_full(
        self,
        db: AsyncSession,
        org_id: UUID,
        token: OAuthToken,
    ) -> ConnectorSyncResult:
        result = ConnectorSyncResult(source=self.source)

        async with self._make_http_client(token) as client:
            # Sync users first so message authors can be linked
            await self._sync_users(client, db, org_id, result)

            channels = await self._list_channels(client)

            for channel in channels:
                channel_id = channel["id"]
                channel_name = channel.get("name", channel_id)

                try:
                    messages = await self._fetch_history(client, channel_id, oldest=None)
                    await self._process_messages(db, org_id, result, messages, channel_id, channel_name)
                except Exception as exc:
                    msg = f"slack sync error channel={channel_name}: {exc}"
                    logger.warning(msg)
                    result.errors.append(msg)

        logger.info(
            "slack full sync org=%s entities=%d/%d edges=%d/%d errors=%d",
            org_id,
            result.entities_created,
            result.entities_updated,
            result.edges_created,
            result.edges_updated,
            len(result.errors),
        )
        return result

    async def sync_delta(
        self,
        db: AsyncSession,
        org_id: UUID,
        token: OAuthToken,
        since: datetime,
    ) -> ConnectorSyncResult:
        result = ConnectorSyncResult(source=self.source)
        oldest = str(since.timestamp())

        async with self._make_http_client(token) as client:
            # Sync users first so message authors can be linked
            await self._sync_users(client, db, org_id, result)

            channels = await self._list_channels(client)

            for channel in channels:
                channel_id = channel["id"]
                channel_name = channel.get("name", channel_id)

                try:
                    messages = await self._fetch_history(client, channel_id, oldest=oldest)
                    await self._process_messages(db, org_id, result, messages, channel_id, channel_name)
                except Exception as exc:
                    msg = f"slack delta sync error channel={channel_name}: {exc}"
                    logger.warning(msg)
                    result.errors.append(msg)

        logger.info(
            "slack delta sync org=%s since=%s entities=%d/%d edges=%d/%d",
            org_id,
            since.isoformat(),
            result.entities_created,
            result.entities_updated,
            result.edges_created,
            result.edges_updated,
        )
        return result

    async def handle_webhook(
        self,
        db: AsyncSession,
        org_id: UUID,
        payload: dict,
    ) -> ConnectorSyncResult:
        result = ConnectorSyncResult(source=self.source)
        event = payload.get("event", {})
        event_type = event.get("type")

        try:
            if event_type == "message":
                await self._handle_message_event(db, org_id, event, result)
            elif event_type == "reaction_added":
                await self._handle_reaction_event(db, org_id, event, payload, result)
            else:
                logger.debug("slack webhook: ignoring event type=%s", event_type)
        except Exception as exc:
            msg = f"slack webhook error: {exc}"
            logger.exception(msg)
            result.errors.append(msg)

        # Caller (receive_webhook) commits and emits SyncCompleted.
        return result

    # ── internal: user sync ────────────────────────────────────────────

    async def _sync_users(
        self,
        client: httpx.AsyncClient,
        db: AsyncSession,
        org_id: UUID,
        result: ConnectorSyncResult,
    ) -> dict[str, UUID]:
        """Sync Slack workspace users. Returns mapping of slack_user_id -> entity UUID."""
        person_map: dict[str, UUID] = {}
        cursor: str | None = None

        while True:
            params: dict[str, str] = {"limit": "200"}
            if cursor:
                params["cursor"] = cursor

            resp = await client.get(f"{API_BASE}/users.list", params=params)
            resp.raise_for_status()
            data = resp.json()

            if not data.get("ok"):
                logger.error("slack users.list error: %s", data.get("error"))
                break

            for member in data.get("members", []):
                # Skip bots and Slackbot
                if member.get("is_bot") or member.get("id") == "USLACKBOT":
                    continue
                if member.get("deleted"):
                    continue

                user_id = member["id"]
                profile = member.get("profile", {})
                email = profile.get("email")
                real_name = profile.get("real_name") or member.get("real_name", "")
                display_name = profile.get("display_name") or ""

                # Build source_ids with email for cross-source resolution
                person_source_ids: dict[str, str] = {"slack_id": user_id}
                if email:
                    person_source_ids["email"] = email.lower()

                entity = await resolve_or_create_person(
                    db,
                    org_id=org_id,
                    source=SourceType.SLACK,
                    source_ids=person_source_ids,
                    canonical_name=real_name or display_name or user_id,
                    properties={
                        "email": email,
                        "display_name": display_name,
                        "real_name": real_name,
                        "avatar_url": profile.get("image_72"),
                        "title": profile.get("title"),
                        "timezone": member.get("tz"),
                    },
                )

                was_new = entity.created_at == entity.updated_at
                if was_new:
                    result.entities_created += 1
                else:
                    result.entities_updated += 1
                person_map[user_id] = entity.id

            cursor = data.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        logger.info("slack user sync org=%s users=%d", org_id, len(person_map))
        return person_map

    # ── internal: message processing ──────────────────────────────────

    async def _process_messages(
        self,
        db: AsyncSession,
        org_id: UUID,
        result: ConnectorSyncResult,
        messages: list[dict],
        channel_id: str,
        channel_name: str,
    ) -> None:
        """Scan messages for decision signals and entity mentions."""
        for msg in messages:
            text = msg.get("text", "")
            ts = msg.get("ts", "")
            user = msg.get("user", "")

            # Check if message looks like a decision (has decision-like reactions)
            reactions = msg.get("reactions", [])
            is_decision = any(r.get("name") in _DECISION_EMOJI for r in reactions)

            if is_decision:
                await self._create_decision_entity(db, org_id, result, text, ts, user, channel_id, channel_name)

            # Extract entity mentions regardless of decision status
            mentions = self._extract_entity_mentions(text)
            if mentions:
                await self._link_mentions(db, org_id, result, mentions, ts, channel_id, channel_name)

    async def _create_decision_entity(
        self,
        db: AsyncSession,
        org_id: UUID,
        result: ConnectorSyncResult,
        text: str,
        ts: str,
        user_id: str,
        channel_id: str,
        channel_name: str,
    ) -> None:
        """Create a Decision entity from a message flagged with a decision emoji."""
        source_id = f"{channel_id}/{ts}"
        # Use first 80 chars of text as canonical name
        name = text[:80].replace("\n", " ").strip()
        if len(text) > 80:
            name += "..."

        entity = await upsert_entity(
            db,
            EntityCreate(
                org_id=org_id,
                type=EntityType.DECISION,
                source=SourceType.SLACK,
                source_ids={"slack": source_id},
                canonical_name=f"Decision: {name}",
                properties=SlackDecisionProperties(
                    text=text[:4000],
                    channel_id=channel_id,
                    channel_name=channel_name,
                    user_id=user_id,
                    timestamp=ts,
                    slack_link=f"https://slack.com/archives/{channel_id}/p{ts.replace('.', '')}",
                ).model_dump(exclude_none=True),
            ),
        )
        was_new = entity.created_at == entity.updated_at
        if was_new:
            result.entities_created += 1
        else:
            result.entities_updated += 1

    async def _link_mentions(
        self,
        db: AsyncSession,
        org_id: UUID,
        result: ConnectorSyncResult,
        mentions: list[dict],
        ts: str,
        channel_id: str,
        channel_name: str,
    ) -> None:
        """Create MENTIONED_IN edges for entity references found in message text."""
        for mention in mentions:
            mention_type = mention["type"]
            mention_value = mention["value"]

            # Try to resolve the mention to an existing entity
            target_entity = None

            if mention_type == "linear_issue":
                # Search for a task entity whose canonical_name starts with this identifier
                target_entity = await get_entity_by_source(db, org_id, SourceType.LINEAR, mention_value)

            elif mention_type in ("github_pr", "github_ref"):
                target_entity = await get_entity_by_source(db, org_id, SourceType.GITHUB, mention_value)

            if target_entity is None:
                # Cannot resolve -- skip this mention
                continue

            # Create a stub entity for the Slack message context if we don't have one
            msg_source_id = f"{channel_id}/{ts}"
            msg_entity = await upsert_entity(
                db,
                EntityCreate(
                    org_id=org_id,
                    type=EntityType.DOCUMENT,
                    source=SourceType.SLACK,
                    source_ids={"slack": msg_source_id},
                    canonical_name=f"Slack message in #{channel_name}",
                    properties=SlackMentionProperties(
                        channel_id=channel_id,
                        channel_name=channel_name,
                        timestamp=ts,
                    ).model_dump(exclude_none=True),
                ),
            )

            edge = await upsert_edge(
                db,
                EdgeCreate(
                    org_id=org_id,
                    from_entity_id=target_entity.id,
                    to_entity_id=msg_entity.id,
                    type=EdgeType.MENTIONED_IN,
                    evidence=[
                        {
                            "source": "slack",
                            "channel": channel_name,
                            "mention_type": mention_type,
                            "mention_value": mention_value,
                            "timestamp": ts,
                        }
                    ],
                ),
            )
            track_edge_result(edge, result)

    # ── webhook event handlers ────────────────────────────────────────

    async def _handle_message_event(
        self,
        db: AsyncSession,
        org_id: UUID,
        event: dict,
        result: ConnectorSyncResult,
    ) -> None:
        """Handle a real-time message event from the Slack Events API."""
        # Skip bot messages and message_changed subtypes for now
        if event.get("bot_id") or event.get("subtype") in ("bot_message", "message_deleted"):
            return

        text = event.get("text", "")
        ts = event.get("ts", "")
        channel_id = event.get("channel", "")

        mentions = self._extract_entity_mentions(text)
        if mentions:
            await self._link_mentions(db, org_id, result, mentions, ts, channel_id, channel_id)

    async def _handle_reaction_event(
        self,
        db: AsyncSession,
        org_id: UUID,
        event: dict,
        payload: dict,
        result: ConnectorSyncResult,
    ) -> None:
        """Handle a reaction_added event -- may promote a message to a Decision."""
        reaction = event.get("reaction", "")
        if reaction not in _DECISION_EMOJI:
            return

        item = event.get("item", {})
        if item.get("type") != "message":
            return

        channel_id = item.get("channel", "")
        ts = item.get("ts", "")

        # We don't have the message text from the reaction event alone,
        # so create a placeholder decision that will be enriched on next sync.
        await self._create_decision_entity(
            db,
            org_id,
            result,
            text=f"[Decision marked with :{reaction}: -- full text pending sync]",
            ts=ts,
            user_id=event.get("user", ""),
            channel_id=channel_id,
            channel_name=channel_id,  # We don't have the name from the event
        )

    # ── Slack API helpers ─────────────────────────────────────────────

    @staticmethod
    async def _list_channels(client: httpx.AsyncClient) -> list[dict]:
        """Fetch all public channels the bot is a member of."""
        channels: list[dict] = []
        cursor: str | None = None

        while True:
            params: dict[str, str] = {
                "types": "public_channel",
                "exclude_archived": "true",
                "limit": "200",
            }
            if cursor:
                params["cursor"] = cursor

            resp = await client.get(f"{API_BASE}/conversations.list", params=params)
            resp.raise_for_status()
            data = resp.json()

            if not data.get("ok"):
                logger.error("slack conversations.list error: %s", data.get("error"))
                break

            channels.extend(data.get("channels", []))

            cursor = data.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        return channels

    @staticmethod
    async def _fetch_history(
        client: httpx.AsyncClient,
        channel_id: str,
        oldest: str | None,
        limit: int = 200,
    ) -> list[dict]:
        """Fetch recent message history for a channel."""
        messages: list[dict] = []
        cursor: str | None = None

        while True:
            params: dict[str, str] = {
                "channel": channel_id,
                "limit": str(min(limit - len(messages), 200)),
            }
            if oldest:
                params["oldest"] = oldest
            if cursor:
                params["cursor"] = cursor

            resp = await client.get(f"{API_BASE}/conversations.history", params=params)
            resp.raise_for_status()
            data = resp.json()

            if not data.get("ok"):
                logger.error(
                    "slack conversations.history error channel=%s: %s",
                    channel_id,
                    data.get("error"),
                )
                break

            messages.extend(data.get("messages", []))

            if len(messages) >= limit:
                break

            cursor = data.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        return messages

    # ── text extraction ───────────────────────────────────────────────

    @staticmethod
    def _extract_entity_mentions(text: str) -> list[dict]:
        """Extract references to entities in other tools from message text.

        Recognizes patterns like:
        - Linear issues: ENG-1234, PLAT-42
        - GitHub PRs: PR #123, org/repo#456
        - Generic tickets: TICKET-789, ISSUE-100
        """
        mentions: list[dict] = []
        seen: set[str] = set()

        for mention_type, pattern in _ENTITY_MENTION_PATTERNS:
            for match in pattern.finditer(text):
                value = match.group(0)
                # Deduplicate
                key = f"{mention_type}:{value}"
                if key in seen:
                    continue
                seen.add(key)
                mentions.append({"type": mention_type, "value": value})

        return mentions
