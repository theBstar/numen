"""Shared slowapi Limiter.

Single limiter keyed by (user_id from JWT, falling back to IP). Right for
both unauthenticated endpoints (login, webhook — the viewer IP is the
only identity available) and authenticated ones (one authenticated abuser
sharing an IP with legit users shouldn't pin the IP bucket).

slowapi calls the key function before FastAPI dependencies resolve, so we
decode the JWT inline. Decode failures fall back silently to IP.
"""

from __future__ import annotations

import logging

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

logger = logging.getLogger(__name__)


def _key_func(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        try:
            from src.api.user_auth import decode_token

            payload = decode_token(auth[7:])
            sub = payload.get("sub")
            if sub:
                return f"user:{sub}"
        except Exception as exc:  # noqa: BLE001
            logger.debug("limiter JWT decode failed, falling back to IP: %s", exc)
    return f"ip:{get_remote_address(request)}"


limiter = Limiter(key_func=_key_func)
