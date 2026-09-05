"""The MCP Host allowlist has to cover how the server is actually reached.

Behind a reverse proxy on :80 or :443 the Host header carries no port, but the
allowlist only held port-qualified forms (`localhost:*`, and the netloc of
APP_URL). Running the production stack, an authenticated MCP call returned
421 Misdirected Request with "Invalid Host header: localhost" - so the MCP
server, a headline feature, did not work in any proxied deployment.
"""

from __future__ import annotations

import pytest

from src.mcp.server import _build_transport_security


@pytest.fixture
def app_url(monkeypatch):
    def _set(url: str):
        monkeypatch.setattr("src.mcp.server.settings.app_url", url)
    return _set


def test_the_configured_host_is_allowed_with_its_port(app_url):
    app_url("http://numen.internal:8000")
    assert "numen.internal:8000" in _build_transport_security().allowed_hosts


def test_the_configured_host_is_also_allowed_without_a_port(app_url):
    """A proxy on 80 or 443 sends a bare Host, so the port-stripped form must
    be allowed even when APP_URL carries an explicit port."""
    app_url("http://numen.internal:8000")
    assert "numen.internal" in _build_transport_security().allowed_hosts


def test_a_portless_app_url_still_works(app_url):
    app_url("https://numen.company.com")
    hosts = _build_transport_security().allowed_hosts
    assert "numen.company.com" in hosts


def test_bare_localhost_is_allowed(app_url):
    """The regression: Caddy on :80 forwards Host: localhost, no port."""
    app_url("http://localhost:8000")
    hosts = _build_transport_security().allowed_hosts
    assert "localhost" in hosts
    assert "127.0.0.1" in hosts


def test_port_wildcards_are_kept_for_local_development(app_url):
    app_url("http://localhost:8000")
    hosts = _build_transport_security().allowed_hosts
    assert "localhost:*" in hosts
    assert "127.0.0.1:*" in hosts


def test_the_apex_form_is_allowed_for_a_www_host(app_url):
    app_url("https://www.numen.company.com")
    hosts = _build_transport_security().allowed_hosts
    assert "numen.company.com" in hosts


def test_rebinding_protection_stays_on(app_url):
    """The allowlist is widened, not disabled."""
    app_url("https://numen.company.com")
    assert _build_transport_security().enable_dns_rebinding_protection is True


def test_no_duplicate_entries(app_url):
    app_url("http://localhost:8000")
    hosts = _build_transport_security().allowed_hosts
    assert len(hosts) == len(set(hosts))
