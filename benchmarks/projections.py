"""Render the demo fixtures as each source system would actually return them.

`src/demo/fixtures.py` stores the *resolved* world: a task's assignee is the
person key "alice". No real API returns that. Linear returns a Linear user,
GitHub returns a GitHub login, and nothing in either response says they are
the same human.

These projections undo the resolution, so the per-tool arm sees what a
per-tool MCP would really see. Field sets follow the shape of each vendor's
API rather than Numen's internal model, because response size is one of the
things being measured.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from benchmarks.identities import BY_KEY  # noqa: E402
from src.demo.fixtures import GOALS, PROJECTS, PRS, TASKS  # noqa: E402


def _linear_user(person_key: str) -> dict:
    si = BY_KEY[person_key].linear
    return {"id": si.handle, "name": si.display_name, "email": si.email}


def _github_user(person_key: str) -> dict:
    si = BY_KEY[person_key].github
    out = {"login": si.handle}
    if si.display_name:
        out["name"] = si.display_name
    if si.email:
        out["email"] = si.email
    return out


def linear_issues() -> list[dict]:
    """Linear GraphQL `issues` nodes, with assignee nested."""
    return [
        {
            "identifier": t["key"],
            "title": t["title"],
            "state": {"name": t["status"]},
            "priority": t["priority"],
            "labels": {"nodes": [{"name": lbl} for lbl in t["labels"]]},
            "dueDate": t["due_date"],
            "createdAt": t["created_at"],
            "assignee": _linear_user(t["assignee"]),
        }
        for t in TASKS
    ]


def linear_projects() -> list[dict]:
    """Linear projects, carrying their issue membership and initiative links."""
    return [
        {
            "id": p["key"],
            "name": p["name"],
            "state": p["status"],
            "description": p["description"],
            "lead": _linear_user(p["owner"]),
            "issues": {"nodes": [{"identifier": k} for k in p["task_keys"]]},
            "initiatives": {"nodes": [{"id": g} for g in p["goal_keys"]]},
        }
        for p in PROJECTS
    ]


def linear_initiatives() -> list[dict]:
    """Goals, modelled as Linear initiatives rather than a Numen-only concept.

    Modelling them as Linear-native is deliberately generous to the baseline:
    if goals lived only in Numen the per-tool arm could not answer goal
    questions at all, which would prove nothing except that the data is
    somewhere else.
    """
    return [
        {
            "id": g["key"],
            "name": g["title"],
            "targetDate": g["time_bound_end"],
            "owner": _linear_user(g["owner"]),
            "parent": g["parent_key"],
            "progress": {"target": g["target_value"], "current": g["current_value"]},
        }
        for g in GOALS
    ]


def github_pulls() -> list[dict]:
    """GitHub REST pull objects. The task link exists only inside the text."""
    return [
        {
            "number": pr["num"],
            "title": pr["title"],
            "state": pr["state"],
            "user": _github_user(pr["author"]),
            "head": {"ref": pr["branch"]},
            "additions": pr["additions"],
            "deletions": pr["deletions"],
            "created_at": pr["created_at"],
            "requested_reviewers": [_github_user(r) for r in pr["reviewers"]],
        }
        for pr in PRS
    ]


def github_users() -> list[dict]:
    """The org member roster - what you must pull to attempt identity work."""
    return [_github_user(k) for k in BY_KEY]


def linear_users() -> list[dict]:
    return [_linear_user(k) for k in BY_KEY]


def size(payload) -> int:
    """Response size in bytes, as JSON on the wire."""
    return len(json.dumps(payload, separators=(",", ":")).encode())
