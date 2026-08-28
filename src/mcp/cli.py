"""CLI entry point for running the Numen MCP server in stdio mode.

Usage (Claude Desktop / Cursor):
    numen-mcp

Or directly:
    python -m src.mcp.cli
"""

from __future__ import annotations

from src.mcp.server import create_mcp_server


def main():
    """Run the MCP server with stdio transport (no auth required)."""
    mcp = create_mcp_server(with_auth=False)
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
