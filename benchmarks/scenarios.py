"""Alternative assumptions about what the source APIs expose.

The headline result depends on an assumption - that GitHub and Slack often do
not hand back an email address. That assumption is doing real work, so it is
worth testing rather than asserting. These scenarios bracket it.
"""

from __future__ import annotations

import dataclasses

from benchmarks.identities import IDENTITIES, SOURCES, Identity


def _map_sources(ident: Identity, fn) -> Identity:
    changes = {}
    for source in SOURCES:
        si = getattr(ident, source)
        if si is not None:
            changes[source] = fn(ident, source, si)
    return dataclasses.replace(ident, **changes)


def as_authored():
    """Realistic: GitHub hides email; Slack exposes it only where set."""
    return IDENTITIES


def email_everywhere():
    """Best case for the baseline: every source returns a corporate email.

    This is the strongest form of the objection 'you rigged it by hiding
    emails'. If the baseline still fails here, the assumption was not load
    bearing.
    """

    def fn(ident, source, si):
        first_last = ident.real_name.lower().replace(" ", ".")
        return dataclasses.replace(si, email=f"{first_last}@demo.example.com")

    return tuple(_map_sources(i, fn) for i in IDENTITIES)


def no_emails():
    """Worst case: no source returns an email at all."""

    def fn(ident, source, si):
        return dataclasses.replace(si, email=None)

    return tuple(_map_sources(i, fn) for i in IDENTITIES)


SCENARIOS = {
    "as_authored": as_authored,
    "email_everywhere": email_everywhere,
    "no_emails": no_emails,
}
