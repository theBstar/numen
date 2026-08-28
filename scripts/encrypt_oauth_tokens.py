#!/usr/bin/env python3
"""Backfill: encrypt OAuth tokens that are still stored in plaintext.

The EncryptedString TypeDecorator on OAuthToken.access_token / refresh_token
encrypts on write and `try_decrypt`s on read, so plaintext rows keep working
during rollout. This script runs over the table once, detects any row whose
raw column value is not Fernet ciphertext, and rewrites it encrypted.

Idempotent: already-encrypted rows are skipped.

Usage:
    python scripts/encrypt_oauth_tokens.py --dry-run
    python scripts/encrypt_oauth_tokens.py
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

sys.path.insert(0, ".")

from sqlalchemy import text  # noqa: E402

from src.shared.database import async_session  # noqa: E402
from src.shared.encryption import encrypt_token, is_encrypted  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def run(dry_run: bool) -> int:
    """Encrypt any plaintext access_token / refresh_token rows. Returns updated count."""
    updated = 0
    scanned = 0

    async with async_session() as session:
        # Raw SQL bypasses the TypeDecorator so we see what's actually stored.
        result = await session.execute(
            text("SELECT id, access_token, refresh_token FROM oauth_tokens")
        )
        rows = result.fetchall()

    for row in rows:
        scanned += 1
        token_id, access, refresh = row
        new_access = (
            None if access is None or is_encrypted(access) else encrypt_token(access)
        )
        new_refresh = (
            None if refresh is None or is_encrypted(refresh) else encrypt_token(refresh)
        )

        if new_access is None and new_refresh is None:
            continue

        updated += 1
        if dry_run:
            logger.info("DRY RUN would encrypt token %s", token_id)
            continue

        async with async_session() as session:
            params: dict = {"id": token_id}
            sets = []
            if new_access is not None:
                sets.append("access_token = :access_token")
                params["access_token"] = new_access
            if new_refresh is not None:
                sets.append("refresh_token = :refresh_token")
                params["refresh_token"] = new_refresh
            stmt = text(f"UPDATE oauth_tokens SET {', '.join(sets)} WHERE id = :id")
            await session.execute(stmt, params)
            await session.commit()
            logger.info("Encrypted token %s", token_id)

    logger.info("Done. scanned=%d updated=%d dry_run=%s", scanned, updated, dry_run)
    return updated


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing")
    args = parser.parse_args()
    asyncio.run(run(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
