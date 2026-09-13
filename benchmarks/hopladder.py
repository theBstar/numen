"""Experiment 4 question set - a ladder from one hop to four.

Each rung adds one traversal. The point is to find where a bag of
integrations stops being enough, rather than to assert that it never was.

Rung 1 needs a single integration and no identity work at all. Rung 4 walks
person -> tickets -> blocked tickets -> projects -> initiatives, and crosses
an identity boundary on the way.

Answers are derived from the fixtures rather than typed by hand, so they
cannot drift from the data the tools serve.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from benchmarks import projections as pj
from benchmarks.identities import BY_KEY
from benchmarks.questions import (
    INITIATIVES,
    ISSUES,
    PROJECTS,
    PULLS,
    issues_for_person,
)


def _linear_id(person: str) -> str:
    return BY_KEY[person].linear.handle


def _github_login(person: str) -> str:
    return BY_KEY[person].github.handle


def _blocks_from(person: str) -> list[tuple[str, str]]:
    """(my ticket, ticket it blocks) for every ticket this person owns."""
    rel = pj._relations()
    mine = {i["identifier"] for i in issues_for_person(person)}
    out = []
    for key in mine:
        for r in rel.get(key, []):
            if r["type"] == "blocks":
                out.append((key, r["relatedIssue"]["identifier"]))
    return sorted(out)


def _owner_of(task_key: str) -> str | None:
    row = next((i for i in ISSUES if i["identifier"] == task_key), None)
    if not row:
        return None
    lid = row["assignee"]["id"]
    return next((k for k, v in BY_KEY.items() if v.linear and v.linear.handle == lid), None)


def _prs_awaiting(person: str) -> list[dict]:
    login = _github_login(person)
    return [p for p in PULLS
            if p["state"] == "open"
            and any(r["login"] == login for r in p.get("requested_reviewers", []))]


@dataclass
class HopQ:
    qid: str
    hops: int
    text: str
    why: str
    crosses_identity: bool
    expected_ids: list[str]
    distractor_ids: list[str] = field(default_factory=list)


SUBJECT = "igor"          # personal GitHub account, so identity is genuinely hard
EASY = "carol"            # consistent everywhere, so rung 1 is winnable by anyone

# ── Rung 1: one integration, no identity work ────────────────────────────
_r1 = sorted(i["identifier"] for i in issues_for_person(EASY))

Q1 = HopQ(
    qid="H1-what-are-they-working-on",
    hops=1,
    text=(f"What is {BY_KEY[EASY].real_name} working on? "
          "Return the Linear keys of every ticket assigned to them."),
    why="One source, one filter. A context layer should add nothing here.",
    crosses_identity=False,
    expected_ids=_r1,
)

# ── Rung 2: two sources, one identity hop ────────────────────────────────
_r2_prs = _prs_awaiting(SUBJECT)
_r2 = sorted({p["user"]["login"] for p in _r2_prs})

Q2 = HopQ(
    qid="H2-waiting-on-my-review",
    hops=2,
    text=(f"Whose open pull requests are waiting on {BY_KEY[SUBJECT].real_name} to review? "
          "Return the GitHub logins of the authors."),
    why=("Requires mapping a person named in Linear terms onto a GitHub login. "
         "This subject's GitHub account carries no name signal."),
    crosses_identity=True,
    expected_ids=_r2,
    distractor_ids=[_github_login(SUBJECT)],
)

# ── Rung 3: the real briefing question ───────────────────────────────────
_blocked_pairs = _blocks_from(SUBJECT)
_blocked_people = {_owner_of(b) for _, b in _blocked_pairs} - {SUBJECT, None}
_review_people = {
    next((k for k, v in BY_KEY.items()
          if v.github and v.github.handle == p["user"]["login"]), None)
    for p in _r2_prs
} - {SUBJECT, None}
_r3 = sorted(_linear_id(p) for p in (_blocked_people | _review_people))

Q3 = HopQ(
    qid="H3-am-i-blocking-anyone",
    hops=3,
    text=(f"Is {BY_KEY[SUBJECT].real_name} holding anyone up? Count both tickets blocked "
          "by their tickets and open pull requests waiting on their review. "
          "Return the Linear user ids of the people affected."),
    why=("Two traversals in different systems that have to be unioned on a person, "
         "which only works if that person is the same entity in both."),
    crosses_identity=True,
    expected_ids=_r3,
    distractor_ids=[_linear_id(SUBJECT)],
)

# ── Rung 4: all the way out to the goal ──────────────────────────────────
_r4 = set()
for _, _b in _blocked_pairs:
    for _p in PROJECTS:
        if any(n["identifier"] == _b for n in _p["issues"]["nodes"]):
            _r4.update(n["id"] for n in _p["initiatives"]["nodes"])

Q4 = HopQ(
    qid="H4-initiatives-at-risk",
    hops=4,
    text=(f"Which company initiatives are exposed by the work {BY_KEY[SUBJECT].real_name} "
          "is blocking? Return only the initiative ids."),
    why="person -> tickets -> blocked tickets -> projects -> initiatives.",
    crosses_identity=False,
    expected_ids=sorted(_r4),
    distractor_ids=[g["id"] for g in INITIATIVES if g["id"] not in _r4][:4],
)

LADDER: tuple[HopQ, ...] = (Q1, Q2, Q3, Q4)
