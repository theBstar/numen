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
    return [p for p in PULLS if task_key in p["title"] or task_key in p["head"]["ref"]]


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


# ── T0: one source, no cross-source hop ───────────────────────────────────

_urgent = [i for i in ISSUES if i["priority"] == "urgent"]

Q1 = Question(
    qid="T0-urgent",
    hops=0,
    text="What are the urgent tickets right now?",
    needs_identity_join=False,
    note="Single source. Linear can filter server side; so can the graph.",
    per_tool=[Call("linear", "issues(filter:{priority:urgent})", _urgent)],
    graph=[Call("numen", "list_tasks(priority=urgent)", _urgent)],
    answer=[i["identifier"] for i in _urgent],
)

_alice_issues = issues_for_person("alice")

Q2 = Question(
    qid="T0-assigned",
    hops=0,
    text="Which tickets is the Linear user alice.chen assigned?",
    needs_identity_join=False,
    note="Asked in Linear's own vocabulary, so no identity work is required.",
    per_tool=[Call("linear", "issues(filter:{assignee:alice.chen})", _alice_issues)],
    graph=[Call("numen", "get_person_tasks(alice)", _alice_issues)],
    answer=[i["identifier"] for i in _alice_issues],
)

# ── T1: one cross-source hop ──────────────────────────────────────────────

_t1_task = issue("ENG-4501")
_t1_prs = pulls_for("ENG-4501")

Q3 = Question(
    qid="T1-pr-for-ticket",
    hops=1,
    text="Which pull request implements ENG-4501?",
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
)

# ── T2: cross-source hop that crosses an identity boundary ────────────────

_t2_prs = pulls_for("ENG-4502")
_t2_author = _t2_prs[0]["user"]["login"] if _t2_prs else None
_t2_other = issues_for_person("igor")

Q4 = Question(
    qid="T2-author-workload",
    hops=2,
    text="Who wrote the pull request for ENG-4502, and what else are they carrying?",
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
)

_alice_prs = pulls_by_person("alice")

Q5 = Question(
    qid="T2-review-queue",
    hops=2,
    text="Of Alice's assigned tickets, which have a pull request waiting on review?",
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
)

# ── T3: three hops, ending at a goal ──────────────────────────────────────

_t3_task = issue("ENG-4501")
_t3_project = project_for("ENG-4501")
_t3_nodes = _t3_project["initiatives"]["nodes"] if _t3_project else []
_t3_init = initiative(_t3_nodes[0]["id"]) if _t3_nodes else None

Q6 = Question(
    qid="T3-goal-exposure",
    hops=3,
    text="Which company initiative is exposed by ENG-4501 slipping, and who owns it?",
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
)

_blocked = [i for i in ISSUES if i["state"]["name"] in ("in_review", "in_progress")
            and i["priority"] == "urgent"]

Q7 = Question(
    qid="T3-at-risk-owners",
    hops=3,
    text="Across urgent in-flight work, which initiatives are exposed and who is reviewing?",
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
    answer={"urgent_in_flight": [i["identifier"] for i in _blocked]},
)

QUESTIONS: tuple[Question, ...] = (Q1, Q2, Q3, Q4, Q5, Q6, Q7)
