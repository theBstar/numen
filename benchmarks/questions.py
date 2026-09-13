"""The question set, and an oracle retrieval plan for each arm.

"Oracle" means both arms are given a *perfect* plan: no wasted calls, no
wrong turns, no re-reads. That removes agent skill from the comparison and
leaves only the structural cost of getting the required facts into context.
It is deliberately generous to the per-tool arm, which in practice would
explore rather than know.

Every plan is written out here so it can be argued with. If a plan is unfair,
the fix is a pull request against this file.

`needs_identity_join` marks questions that cannot be answered without linking
a person across two systems. Those inherit the error rate measured in
experiment 1 - the cost model below assumes the join succeeds, which flatters
the per-tool arm further.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from benchmarks import projections as pj
from benchmarks.identities import BY_KEY

# Convenience slices of the projected sources.
ISSUES = pj.linear_issues()
PULLS = pj.github_pulls()
PROJECTS = pj.linear_projects()
INITIATIVES = pj.linear_initiatives()


def issue(identifier: str) -> dict:
    return next(i for i in ISSUES if i["identifier"] == identifier)


def pulls_for(task_key: str) -> list[dict]:
    """Pull requests carrying a Linear key, matched the way an agent would.

    Case-insensitive across title and branch, because that is the only signal
    GitHub exposes - there is no index on Linear keys.
    """
    k = task_key.lower()
    return [p for p in PULLS
            if k in p["title"].lower() or k in p["head"]["ref"].lower()]


def project_for(task_key: str) -> dict | None:
    return next((p for p in PROJECTS if any(n["identifier"] == task_key
                                            for n in p["issues"]["nodes"])), None)


def initiative(ident: str) -> dict | None:
    return next((g for g in INITIATIVES if g["id"] == ident), None)


def issues_for_person(person_key: str) -> list[dict]:
    handle = BY_KEY[person_key].linear.handle
    return [i for i in ISSUES if i["assignee"]["id"] == handle]


def pulls_by_person(person_key: str) -> list[dict]:
    login = BY_KEY[person_key].github.handle
    return [p for p in PULLS if p["user"]["login"] == login]


@dataclass
class Call:
    source: str
    op: str
    payload: object

    @property
    def bytes(self) -> int:
        return pj.size(self.payload)


@dataclass
class Question:
    qid: str
    hops: int
    text: str
    needs_identity_join: bool
    per_tool: list[Call]
    graph: list[Call]
    note: str = ""
    answer: object = field(default=None)
    #: The exact set of identifiers a correct answer names. Grading for
    #: experiment 3 is set equality against this - no judge model, no partial
    #: credit for prose that sounds right.
    expected_ids: list[str] = field(default_factory=list)
    #: Identifiers that are plausible but wrong. Naming one of these is how a
    #: false identity merge shows up in an answer rather than in a metric.
    distractor_ids: list[str] = field(default_factory=list)


# ── T0: one source, no cross-source hop ───────────────────────────────────

_urgent = [i for i in ISSUES if i["priority"] == "urgent"]

Q1 = Question(
    qid="T0-urgent",
    hops=0,
    text="Which tickets are urgent priority? Return their Linear keys.",
    needs_identity_join=False,
    note="Single source. Linear can filter server side; so can the graph.",
    per_tool=[Call("linear", "issues(filter:{priority:urgent})", _urgent)],
    graph=[Call("numen", "list_tasks(priority=urgent)", _urgent)],
    answer=[i["identifier"] for i in _urgent],
    expected_ids=[i["identifier"] for i in _urgent],
)

_alice_issues = issues_for_person("alice")

Q2 = Question(
    qid="T0-assigned",
    hops=0,
    text="Which tickets is the Linear user alice.chen assigned? Return their Linear keys.",
    needs_identity_join=False,
    note="Asked in Linear's own vocabulary, so no identity work is required.",
    per_tool=[Call("linear", "issues(filter:{assignee:alice.chen})", _alice_issues)],
    graph=[Call("numen", "get_person_tasks(alice)", _alice_issues)],
    answer=[i["identifier"] for i in _alice_issues],
    expected_ids=[i["identifier"] for i in _alice_issues],
)

# ── T1: one cross-source hop ──────────────────────────────────────────────

_t1_task = issue("ENG-4501")
_t1_prs = pulls_for("ENG-4501")

Q3 = Question(
    qid="T1-pr-for-ticket",
    hops=1,
    text="Which pull request implements ENG-4501? Return its number.",
    needs_identity_join=False,
    note=(
        "GitHub has no index on Linear keys, so the per-tool arm must list pull "
        "requests and scan titles and branches locally. The graph stores the edge."
    ),
    per_tool=[
        Call("linear", "issue(ENG-4501)", _t1_task),
        Call("github", "pulls.list(state=all)", PULLS),
    ],
    graph=[Call("numen", "get_task_context(ENG-4501)", {"task": _t1_task, "prs": _t1_prs})],
    answer=[p["number"] for p in _t1_prs],
    expected_ids=[str(p["number"]) for p in _t1_prs],
    distractor_ids=[str(p["number"]) for p in PULLS if p not in _t1_prs][:4],
)

# ── T2: cross-source hop that crosses an identity boundary ────────────────

_t2_prs = pulls_for("ENG-4502")
_t2_author = _t2_prs[0]["user"]["login"] if _t2_prs else None
_t2_other = issues_for_person("igor")

Q4 = Question(
    qid="T2-author-workload",
    hops=2,
    text=(
        "The pull request for ENG-4502 has an author. Which Linear tickets is that "
        "same person assigned? Return only the Linear keys."
    ),
    needs_identity_join=True,
    note=(
        "The PR names a GitHub login; the other tickets are keyed by a Linear user. "
        "Bridging them needs both rosters and a resolution attempt - which experiment 1 "
        "shows fails for this person."
    ),
    per_tool=[
        Call("github", "pulls.list(state=all)", PULLS),
        Call("github", "orgs.listMembers", pj.github_users()),
        Call("linear", "users", pj.linear_users()),
        Call("linear", "issues(filter:{assignee:?})", _t2_other),
    ],
    graph=[Call("numen", "get_person_workload(from pr ENG-4502)",
                {"person": "igor", "prs": _t2_prs, "tasks": _t2_other})],
    answer={"person": "igor", "other_tasks": [i["identifier"] for i in _t2_other]},
    expected_ids=[i["identifier"] for i in _t2_other],
    distractor_ids=[i["identifier"] for i in issues_for_person("julia")][:4],
)

_alice_prs = pulls_by_person("alice")

Q5 = Question(
    qid="T2-review-queue",
    hops=2,
    text=(
        "Which currently open pull requests were authored by Alice Chen? "
        "Return only the pull request numbers."
    ),
    needs_identity_join=True,
    note="Needs the Linear-to-GitHub person link, then a per-ticket PR match.",
    per_tool=[
        Call("linear", "users", pj.linear_users()),
        Call("github", "orgs.listMembers", pj.github_users()),
        Call("linear", "issues(filter:{assignee:alice.chen})", _alice_issues),
        Call("github", "pulls.list(state=open)", [p for p in PULLS if p["state"] == "open"]),
    ],
    graph=[Call("numen", "get_person_prs(alice, state=open)",
                {"tasks": _alice_issues, "prs": _alice_prs})],
    answer=[p["number"] for p in _alice_prs if p["state"] == "open"],
    expected_ids=[str(p["number"]) for p in _alice_prs if p["state"] == "open"],
    distractor_ids=[str(p["number"]) for p in pulls_by_person("andrew")]
    if "andrew" in BY_KEY else [],
)

# ── T3: three hops, ending at a goal ──────────────────────────────────────

_t3_task = issue("ENG-4501")
_t3_project = project_for("ENG-4501")
_t3_nodes = _t3_project["initiatives"]["nodes"] if _t3_project else []
_t3_init = initiative(_t3_nodes[0]["id"]) if _t3_nodes else None

Q6 = Question(
    qid="T3-goal-exposure",
    hops=3,
    text="Which company initiative is exposed if ENG-4501 slips? Return the initiative id.",
    needs_identity_join=False,
    note=(
        "ticket -> project -> initiative -> owner. Linear can nest within itself, but "
        "there is no single query that walks issue to initiative, so the arm pages "
        "projects and initiatives and joins locally."
    ),
    per_tool=[
        Call("linear", "issue(ENG-4501)", _t3_task),
        Call("linear", "projects", PROJECTS),
        Call("linear", "initiatives", INITIATIVES),
    ],
    graph=[Call("numen", "get_goal_progress(via ENG-4501)",
                {"task": _t3_task, "project": _t3_project, "initiative": _t3_init})],
    answer={"initiative": _t3_init["id"] if _t3_init else None},
    expected_ids=[_t3_init["id"]] if _t3_init else [],
    distractor_ids=[g["id"] for g in INITIATIVES if not _t3_init or g["id"] != _t3_init["id"]][:4],
)

_blocked = [i for i in ISSUES if i["state"]["name"] in ("in_review", "in_progress")
            and i["priority"] == "urgent"]

# The initiatives reachable from those tickets, via their projects. This is the
# full three-hop walk the question actually asks for.
_blocked_inits = set()
for _i in _blocked:
    _p = project_for(_i["identifier"])
    for _n in (_p["initiatives"]["nodes"] if _p else []):
        _blocked_inits.add(_n["id"])

Q7 = Question(
    qid="T3-at-risk-owners",
    hops=3,
    text=(
        "Across every urgent in-flight ticket, which company initiatives are exposed? "
        "Return only the initiative ids."
    ),
    needs_identity_join=True,
    note="The widest question in the set: tickets, projects, initiatives, PRs and reviewers.",
    per_tool=[
        Call("linear", "issues(filter:{priority:urgent})", _blocked),
        Call("linear", "projects", PROJECTS),
        Call("linear", "initiatives", INITIATIVES),
        Call("github", "pulls.list(state=all)", PULLS),
        Call("github", "orgs.listMembers", pj.github_users()),
        Call("linear", "users", pj.linear_users()),
    ],
    graph=[Call("numen", "get_delayed_projects()",
                {"tasks": _blocked, "projects": PROJECTS[:3], "initiatives": INITIATIVES[:3]})],
    answer={"initiatives": sorted(_blocked_inits)},
    expected_ids=sorted(_blocked_inits),
)

QUESTIONS: tuple[Question, ...] = (Q1, Q2, Q3, Q4, Q5, Q6, Q7)
