"""One-shot: ensure the demo org exists in this database.

Idempotent. Used by the deploy workflow after alembic upgrade so the
`Numen Demo` org is always present for admin users to drop into on login.

Usage: python -m scripts.seed_demo
"""

from __future__ import annotations

import asyncio
import logging

from src.demo.seeder import seed_demo_org
from src.shared.database import async_session

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("seed_demo")


async def main() -> None:
    async with async_session() as db:
        org_id = await seed_demo_org(db)
        await db.commit()
    logger.info("Demo org ready: %s", org_id)


if __name__ == "__main__":
    asyncio.run(main())
