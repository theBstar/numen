#!/usr/bin/env python
"""Create the first organization, admin, and API key.

A fresh install has an empty database and no way in: the only interactive
sign-in is Google OAuth. Run this once after `docker compose up` to get an
admin and a working API key without registering an OAuth app.

    docker compose exec app python scripts/bootstrap_admin.py you@company.com

Safe to run again; it reuses the existing org and user and mints a new key.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from src.bootstrap import BootstrapError, bootstrap_admin
from src.shared.database import async_session


async def _run(email: str, org_name: str | None) -> int:
    async with async_session() as db:
        try:
            result = await bootstrap_admin(db, email=email, org_name=org_name)
        except BootstrapError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

    what = []
    if result.created_org:
        what.append("organization")
    if result.created_user:
        what.append("admin")

    print()
    print(f"  Organization  {result.org_name}  ({result.org_id})")
    print(f"  Admin         {result.email}  ({result.user_id})")
    if what:
        print(f"  Created       {', '.join(what)}")
    else:
        print("  Created       nothing new - reused the existing org and admin")
    print()
    print("  API key (shown once, it is not recoverable):")
    print()
    print(f"    {result.api_key}")
    print()
    print("  Try it:")
    print()
    print("    curl -s http://localhost:8001/api/ask \\")
    print(f'      -H "Authorization: Bearer {result.api_key}" \\')
    print("      -H 'Content-Type: application/json' \\")
    print("      -d '{\"question\": \"what is blocked?\"}'")
    print()
    print("  Or point an MCP client at http://localhost:8001/mcp/ with the same")
    print("  bearer token. See docs/agent-setup.md.")
    print()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create the first organization, admin, and API key."
    )
    parser.add_argument("email", help="Email address for the admin.")
    parser.add_argument(
        "--org",
        dest="org_name",
        default=None,
        help="Organization name. Defaults to the email domain.",
    )
    args = parser.parse_args()
    return asyncio.run(_run(args.email, args.org_name))


if __name__ == "__main__":
    raise SystemExit(main())
