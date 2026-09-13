"""Realistic cross-source identity fixtures.

`src/demo/fixtures.py` refers to people by a single key ("alice") and gives
each one identifiers that all contain their name - `Alice Chen`,
`alice@demo.example.com`, `alice-chen`, `U03ALICE01`. Real identity data is
not like that, and a benchmark built on it would let naive string matching
score near-perfect on the one dimension a context graph is supposed to win.

So this module re-projects the same ten people onto identifiers that follow
patterns you actually meet in a corporate estate. Every pattern here is
common, and two of the ten are deliberately easy so the per-tool baseline
can win the cases it deserves to win.

Each `Identity` records what each source system *exposes about that person in
its own API responses* - which is the only thing an agent holding a per-tool
MCP connection gets to see.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class SourceIdentity:
    """What one source system exposes about a person.

    `email` is None when that system does not return an email address on the
    objects an agent would fetch - which is the norm for GitHub (users hide
    it by default) and common for Slack (admin scope required).
    """

    handle: str
    display_name: str | None = None
    email: str | None = None


@dataclass(frozen=True)
class Identity:
    key: str
    real_name: str
    note: str
    github: SourceIdentity | None = None
    linear: SourceIdentity | None = None
    slack: SourceIdentity | None = None
    aliases: list[str] = field(default_factory=list)


# ── The estate ────────────────────────────────────────────────────────────
#
# Patterns modelled, and why each is here:
#
#   alice   handle unrelated to display name; GitHub email hidden
#   andrew  near-collision with alice's handle - two Chens, one org
#   bob     changed surname; Slack updated, GitHub handle frozen at old name
#   carol   fully consistent, email everywhere            <- baseline should win
#   david   opaque handle, no name signal at all
#   eve     personal GitHub account, unrelated to real name, email hidden
#   frank   operates a bot that authors commits on his behalf
#   grace   fully consistent, email everywhere            <- baseline should win
#   hannah  handles agree after normalization, no emails   <- baseline should win
#   igor    two GitHub accounts, one personal one work
#   julia   Slack shows a nickname, not the legal name
#   kevin   display name identical everywhere               <- baseline should win
#   lisa    Slack profile is a handle, orphaning that account

IDENTITIES: tuple[Identity, ...] = (
    Identity(
        key="alice",
        real_name="Alice Chen",
        note="handle unrelated to display name; GitHub hides the email",
        github=SourceIdentity(handle="achen", display_name="A. Chen", email=None),
        linear=SourceIdentity(
            handle="alice.chen", display_name="Alice Chen", email="alice.chen@demo.example.com"
        ),
        slack=SourceIdentity(handle="U03ALICE01", display_name="Alice", email=None),
    ),
    Identity(
        key="andrew",
        real_name="Andrew Chen",
        note="near-collision with alice: same surname, adjacent GitHub handle",
        github=SourceIdentity(handle="achen-2", display_name="Andrew Chen", email=None),
        linear=SourceIdentity(
            handle="andrew.chen", display_name="Andrew Chen", email="andrew.chen@demo.example.com"
        ),
        slack=SourceIdentity(handle="U03ANDREW", display_name="Andy C", email=None),
    ),
    Identity(
        key="bob",
        real_name="Bob Okonkwo",
        note="changed surname; Slack and Linear updated, GitHub handle frozen at the old one",
        github=SourceIdentity(handle="bmartinez", display_name="Bob Martinez", email=None),
        linear=SourceIdentity(
            handle="bob.okonkwo", display_name="Bob Okonkwo", email="bob.okonkwo@demo.example.com"
        ),
        slack=SourceIdentity(handle="U03BOB001", display_name="Bob Okonkwo", email=None),
        aliases=["Bob Martinez"],
    ),
    Identity(
        key="carol",
        real_name="Carol Wu",
        note="consistent across every system, email exposed everywhere",
        github=SourceIdentity(
            handle="carol-wu", display_name="Carol Wu", email="carol.wu@demo.example.com"
        ),
        linear=SourceIdentity(
            handle="carol.wu", display_name="Carol Wu", email="carol.wu@demo.example.com"
        ),
        slack=SourceIdentity(
            handle="U03CAROL1", display_name="Carol Wu", email="carol.wu@demo.example.com"
        ),
    ),
    Identity(
        key="david",
        real_name="David Kim",
        note="opaque handle carrying no name signal",
        github=SourceIdentity(handle="dk-eng", display_name=None, email=None),
        linear=SourceIdentity(
            handle="david.kim", display_name="David Kim", email="david.kim@demo.example.com"
        ),
        slack=SourceIdentity(handle="U03DAVID1", display_name="David Kim", email=None),
    ),
    Identity(
        key="eve",
        real_name="Eve Patel",
        note="personal GitHub account, no name signal, email hidden - common for contractors",
        github=SourceIdentity(handle="evilgenius42", display_name=None, email=None),
        linear=SourceIdentity(
            handle="eve.patel", display_name="Eve Patel", email="eve.patel@demo.example.com"
        ),
        slack=SourceIdentity(handle="U03EVE001", display_name="Eve Patel", email=None),
    ),
    Identity(
        key="frank",
        real_name="Frank Liu",
        note="operates a deploy bot that authors commits on his behalf",
        github=SourceIdentity(handle="frank-liu", display_name="Frank Liu", email=None),
        linear=SourceIdentity(
            handle="frank.liu", display_name="Frank Liu", email="frank.liu@demo.example.com"
        ),
        slack=SourceIdentity(handle="U03FRANK1", display_name="Frank Liu", email=None),
        aliases=["deploy-bot"],
    ),
    Identity(
        key="grace",
        real_name="Grace Zhang",
        note="consistent across every system, email exposed everywhere",
        github=SourceIdentity(
            handle="grace-zhang", display_name="Grace Zhang", email="grace.zhang@demo.example.com"
        ),
        linear=SourceIdentity(
            handle="grace.zhang", display_name="Grace Zhang", email="grace.zhang@demo.example.com"
        ),
        slack=SourceIdentity(
            handle="U03GRACE1", display_name="Grace Zhang", email="grace.zhang@demo.example.com"
        ),
    ),
    Identity(
        key="hannah",
        real_name="Hannah Lee",
        note="handles agree once punctuation is stripped; no email anywhere",
        github=SourceIdentity(handle="hannah-lee", display_name=None, email=None),
        linear=SourceIdentity(handle="hannah.lee", display_name="Hannah Lee", email=None),
        slack=SourceIdentity(handle="U03HANNA1", display_name="Hannah Lee", email=None),
    ),
    Identity(
        key="igor",
        real_name="Igor Popov",
        note="two GitHub accounts; the personal one authors most of the work",
        github=SourceIdentity(handle="ipopov-dev", display_name="ip", email=None),
        linear=SourceIdentity(
            handle="igor.popov", display_name="Igor Popov", email="igor.popov@demo.example.com"
        ),
        slack=SourceIdentity(handle="U03IGOR01", display_name="Igor Popov", email=None),
        aliases=["igor-popov-work"],
    ),
    Identity(
        key="kevin",
        real_name="Kevin Nguyen",
        note="display name identical in all three systems; no emails",
        github=SourceIdentity(handle="knguyen", display_name="Kevin Nguyen", email=None),
        linear=SourceIdentity(handle="kevin.nguyen", display_name="Kevin Nguyen", email=None),
        slack=SourceIdentity(handle="U03KEVIN1", display_name="Kevin Nguyen", email=None),
    ),
    Identity(
        key="lisa",
        real_name="Lisa Park",
        note="Slack profile shows a handle rather than a name, orphaning that account",
        github=SourceIdentity(handle="lisa-park", display_name="Lisa Park", email=None),
        linear=SourceIdentity(
            handle="lisa.park", display_name="Lisa Park", email="lisa.park@demo.example.com"
        ),
        slack=SourceIdentity(handle="U03LISA01", display_name="lpark", email=None),
    ),
    Identity(
        key="julia",
        real_name="Julia Santos",
        note="Slack shows a nickname rather than the legal name",
        github=SourceIdentity(handle="jsantos", display_name="Julia Santos", email=None),
        linear=SourceIdentity(
            handle="julia.santos", display_name="Julia Santos", email="julia.santos@demo.example.com"
        ),
        slack=SourceIdentity(handle="U03JULIA1", display_name="Jules", email=None),
    ),
)

BY_KEY: dict[str, Identity] = {i.key: i for i in IDENTITIES}
SOURCES = ("github", "linear", "slack")


def source_identity(key: str, source: str) -> SourceIdentity | None:
    return getattr(BY_KEY[key], source, None)


# ── Ground truth ──────────────────────────────────────────────────────────


def truth_pairs() -> list[tuple[str, str, str, str]]:
    """Every cross-source identity link that is true.

    Returns (person_key, source_a, source_b, reason) for each unordered pair
    of sources where the person appears in both.
    """
    out: list[tuple[str, str, str, str]] = []
    for ident in IDENTITIES:
        present = [s for s in SOURCES if getattr(ident, s) is not None]
        for i, a in enumerate(present):
            for b in present[i + 1 :]:
                out.append((ident.key, a, b, ident.note))
    return out
