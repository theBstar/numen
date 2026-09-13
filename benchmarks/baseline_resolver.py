"""The identity resolution an agent holding per-tool MCPs can actually do.

An agent with a GitHub MCP, a Linear MCP and a Slack MCP sees three
independent user records and has to decide which refer to the same human. It
has no shared key: it must infer the links from whatever attributes the tool
responses happen to carry.

This module implements that inference *generously*. Four strategies, applied
in descending order of confidence, plus transitive closure over whatever they
find - because a competent agent would chain `github->linear` and
`linear->slack` into `github->slack`. Being charitable to the baseline is the
point: a benchmark that beats a strawman proves nothing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from itertools import combinations

from benchmarks.identities import IDENTITIES, SOURCES, SourceIdentity


def norm_name(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z ]", "", value.lower()).strip()


def norm_handle(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]", "", value.lower())


@dataclass(frozen=True)
class ProposedLink:
    node_a: tuple[str, str]  # (source, handle)
    node_b: tuple[str, str]
    strategy: str


def _initial_surname_forms(display: str | None) -> set[str]:
    """Handle forms a person's display name plausibly maps to.

    "Alice Chen" -> {alicechen, achen, chena, chen}
    """
    n = norm_name(display)
    parts = [p for p in n.split() if p]
    if len(parts) < 2:
        return {norm_handle(n)} if n else set()
    first, last = parts[0], parts[-1]
    return {
        f"{first}{last}",
        f"{first[0]}{last}",
        f"{last}{first[0]}",
        last,
    }


#: Every strategy, including the fuzzy one. What an eager agent does.
AGGRESSIVE = ("email", "display_name", "handle", "handle_name_form")

#: High-confidence strategies only. What a careful agent does - it declines
#: to guess rather than risk merging two people.
CONSERVATIVE = ("email", "display_name", "handle")


def _try_link(
    a: SourceIdentity, b: SourceIdentity, strategies: tuple[str, ...] = AGGRESSIVE
) -> str | None:
    """Return the name of the first enabled strategy linking a and b."""
    # S1 - exact email. The only high-confidence signal there is.
    if "email" in strategies:
        if a.email and b.email and a.email.lower() == b.email.lower():
            return "email"

    # S2 - identical display name.
    if "display_name" in strategies and a.display_name and b.display_name:
        if norm_name(a.display_name) and norm_name(a.display_name) == norm_name(b.display_name):
            return "display_name"

    # S3 - identical handle once punctuation is stripped.
    if "handle" in strategies:
        if norm_handle(a.handle) and norm_handle(a.handle) == norm_handle(b.handle):
            return "handle"

    # S4 - handle looks like a name form of the other side's display name.
    #      This is the aggressive one, and the one that invents false links.
    if "handle_name_form" in strategies:
        if norm_handle(a.handle) in _initial_surname_forms(b.display_name):
            return "handle_name_form"
        if norm_handle(b.handle) in _initial_surname_forms(a.display_name):
            return "handle_name_form"

    return None


def propose_links(identities=None, strategies: tuple[str, ...] = AGGRESSIVE) -> list[ProposedLink]:
    """Every link the baseline strategies propose across the whole estate."""
    identities = IDENTITIES if identities is None else identities
    nodes: list[tuple[str, str, SourceIdentity]] = []
    for ident in identities:
        for source in SOURCES:
            si = getattr(ident, source)
            if si is not None:
                nodes.append((source, si.handle, si))

    proposed: list[ProposedLink] = []
    for (sa, ha, ia), (sb, hb, ib) in combinations(nodes, 2):
        if sa == sb:
            continue  # linking within one source is not the problem
        strategy = _try_link(ia, ib, strategies)
        if strategy:
            proposed.append(ProposedLink((sa, ha), (sb, hb), strategy))
    return proposed


def components(links: list[ProposedLink]) -> list[set[tuple[str, str]]]:
    """Transitive closure - the clusters the agent would end up believing in."""
    parent: dict[tuple[str, str], tuple[str, str]] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry

    for link in links:
        union(link.node_a, link.node_b)

    groups: dict[tuple[str, str], set[tuple[str, str]]] = {}
    for node in list(parent):
        groups.setdefault(find(node), set()).add(node)
    return list(groups.values())


def node_owner(identities=None) -> dict[tuple[str, str], str]:
    """(source, handle) -> the person key that truly owns it."""
    identities = IDENTITIES if identities is None else identities
    owner: dict[tuple[str, str], str] = {}
    for ident in identities:
        for source in SOURCES:
            si = getattr(ident, source)
            if si is not None:
                owner[(source, si.handle)] = ident.key
    return owner
