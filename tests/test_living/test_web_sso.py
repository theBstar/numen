"""Tests for the WS3 web SSO endpoint and /api/account/keys routes."""

from __future__ import annotations

from src.api.living.auth import _install_snippet, _web_sso_response_headers


def test_install_snippet_claude_code_returns_cli():
    snip = _install_snippet("claude_code", "numen_secretkey", "https://numen.team/mcp")
    assert snip["kind"] == "cli"
    assert "claude mcp add numen" in snip["command"]
    assert "Authorization: Bearer numen_secretkey" in snip["command"]
    assert "https://numen.team/mcp" in snip["command"]


def test_install_snippet_conductor_returns_cli():
    snip = _install_snippet("conductor", "numen_x", "https://numen.team/mcp")
    assert snip["kind"] == "cli"
    assert "conductor mcp add numen" in snip["command"]


def test_install_snippet_cursor_returns_config_file():
    snip = _install_snippet("cursor", "numen_x", "https://numen.team/mcp")
    assert snip["kind"] == "config_file"
    assert "config_path" in snip
    assert snip["config_json"]["mcpServers"]["numen"]["url"] == "https://numen.team/mcp"
    assert snip["config_json"]["mcpServers"]["numen"]["headers"]["Authorization"] == "Bearer numen_x"


def test_install_snippet_claude_desktop_returns_config_file():
    snip = _install_snippet("claude_desktop", "numen_x", "https://numen.team/mcp")
    assert snip["kind"] == "config_file"
    assert "Application Support/Claude" in snip["config_path"]


def test_install_snippet_unknown_client_falls_back():
    snip = _install_snippet("future_client", "numen_x", "https://numen.team/mcp")
    assert snip["kind"] == "manual"
    assert "Authorization: Bearer numen_x" in snip["raw_header"]


def test_security_headers_block_caching_and_framing():
    h = _web_sso_response_headers()
    assert "no-store" in h["Cache-Control"]
    assert h["Referrer-Policy"] == "no-referrer"
    assert h["X-Frame-Options"] == "DENY"
    assert "frame-ancestors 'none'" in h["Content-Security-Policy"]
    assert h["Pragma"] == "no-cache"
