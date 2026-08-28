"""Token verifier for MCP server API key authentication."""

from __future__ import annotations

import logging

from mcp.server.auth.provider import AccessToken, TokenVerifier

from src.mcp.auth import validate_api_key
from src.shared.database import async_session

logger = logging.getLogger(__name__)


# AccessToken.client_id format: "<org_uuid>" for legacy read-only keys,
# "<org_uuid>:<user_uuid>" once a key is bound to a user. The MCP server
# parses this in _get_actor() so write tools can attribute mutations.
def encode_client_id(org_id: str, user_id: str | None) -> str:
    return f"{org_id}:{user_id}" if user_id else org_id


def decode_client_id(client_id: str) -> tuple[str, str | None]:
    if ":" in client_id:
        org_id, user_id = client_id.split(":", 1)
        return org_id, user_id
    return client_id, None


class NumenTokenVerifier(TokenVerifier):
    """Verify Numen API keys as MCP Bearer tokens.

    Delegates to validate_api_key() which checks the SHA-256 hash against
    the api_keys table. On success, packs (org_id, user_id) into
    AccessToken.client_id and grants the read_write scope when the key is
    bound to a user, else read-only.
    """

    async def verify_token(self, token: str) -> AccessToken | None:
        async with async_session() as db:
            validated = await validate_api_key(db, token)
            if validated is None:
                logger.debug("MCP auth failed: invalid or revoked API key")
                return None
            org_id, user_id = validated
            await db.commit()  # persist last_used_at update

            scopes = ["read", "write"] if user_id else ["read"]
            return AccessToken(
                token=token,
                client_id=encode_client_id(str(org_id), str(user_id) if user_id else None),
                scopes=scopes,
            )
