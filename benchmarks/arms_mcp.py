"""The two tool surfaces, as in-process MCP servers.

Both are backed by the identical projected fixtures, so any difference in
what the agent does is the shape of the tools, not the data behind them.

The per-tool arm mirrors what the real Linear, GitHub and Slack MCP servers
expose: list endpoints per resource, returning whole objects, with the same
server-side filters those APIs actually support - and with no notion that a
GitHub login and a Linear user might be the same person. Filter parity
matters: an earlier version of this file gave the graph arm filters and left
the per-tool list endpoints argument-less, which made the baseline dump all
sixty issues on every question. That was a strawman, and the numbers it
produced were discarded.

The graph arm mirrors Numen's registry: fewer tools, each answering a joined
question, with people already resolved across sources.
"""

from __future__ import annotations

import json

from claude_agent_sdk import create_sdk_mcp_server, tool

from benchmarks import projections as pj
from benchmarks import questions as q
from benchmarks.identities import BY_KEY

NO_ARGS: dict = {}


def _out(payload) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(payload, separators=(",", ":"))}]}


# ── Per-tool arm ──────────────────────────────────────────────────────────

@tool(
    "linear_list_issues",
    "List Linear issues with assignee, state, priority and labels. "
    "Optional filters: priority (urgent/high/medium/low), status, "
    "assignee (a Linear user id such as alice.chen).",
    {"priority": str, "status": str, "assignee": str},
)
async def linear_list_issues(args):
    rows = pj.linear_issues()
    if args.get("priority"):
        rows = [i for i in rows if i["priority"] == args["priority"]]
    if args.get("status"):
        rows = [i for i in rows if i["state"]["name"] == args["status"]]
    if args.get("assignee"):
        rows = [i for i in rows if i["assignee"]["id"] == args["assignee"]]
    return _out(rows)


@tool("linear_list_projects", "List Linear projects with their issues and initiatives.", NO_ARGS)
async def linear_list_projects(args):
    return _out(pj.linear_projects())


@tool("linear_list_initiatives", "List Linear initiatives (company goals) with owner and progress.", NO_ARGS)
async def linear_list_initiatives(args):
    return _out(pj.linear_initiatives())


@tool("linear_list_users", "List Linear users: id, name, email.", NO_ARGS)
async def linear_list_users(args):
    return _out(pj.linear_users())


@tool(
    "github_list_pulls",
    "List GitHub pull requests with author, branch, state and reviewers. "
    "Optional filters: state (open/closed/merged), author (a GitHub login).",
    {"state": str, "author": str},
)
async def github_list_pulls(args):
    rows = pj.github_pulls()
    if args.get("state"):
        rows = [p for p in rows if p["state"] == args["state"]]
    if args.get("author"):
        rows = [p for p in rows if p["user"]["login"] == args["author"]]
    return _out(rows)


@tool("github_list_members", "List GitHub organization members: login, and name or email where public.", NO_ARGS)
async def github_list_members(args):
    return _out(pj.github_users())


PER_TOOL_SERVER = create_sdk_mcp_server(
    name="pertool",
    tools=[linear_list_issues, linear_list_projects, linear_list_initiatives,
           linear_list_users, github_list_pulls, github_list_members],
)

PER_TOOL_ALLOWED = [
    "mcp__pertool__linear_list_issues",
    "mcp__pertool__linear_list_projects",
    "mcp__pertool__linear_list_initiatives",
    "mcp__pertool__linear_list_users",
    "mcp__pertool__github_list_pulls",
    "mcp__pertool__github_list_members",
]


# ── Graph arm ─────────────────────────────────────────────────────────────
# People are already resolved, so a task carries its PRs and its owner
# carries every account they hold.

def _person_of_linear(handle: str) -> str | None:
    for key, ident in BY_KEY.items():
        if ident.linear and ident.linear.handle == handle:
            return key
    return None


@tool("numen_list_tasks", "List tasks. Optional filter by priority or status.", {"priority": str, "status": str})
async def numen_list_tasks(args):
    rows = q.ISSUES
    if args.get("priority"):
        rows = [i for i in rows if i["priority"] == args["priority"]]
    if args.get("status"):
        rows = [i for i in rows if i["state"]["name"] == args["status"]]
    return _out(rows)


@tool("numen_get_task_context", "Everything joined to one task: its pull requests, project and initiative.",
      {"task": str})
async def numen_get_task_context(args):
    key = (args.get("task") or "").upper()
    try:
        task = q.issue(key)
    except StopIteration:
        return _out({"error": f"no task {key}"})
    project = q.project_for(key)
    nodes = project["initiatives"]["nodes"] if project else []
    return _out({
        "task": task,
        "pull_requests": q.pulls_for(key),
        "project": project,
        "initiative": q.initiative(nodes[0]["id"]) if nodes else None,
    })


@tool("numen_get_person_workload", "Everything one person owns across sources. Accepts any handle they hold.",
      {"who": str})
async def numen_get_person_workload(args):
    who = (args.get("who") or "").strip().lower()
    key = None
    for k, ident in BY_KEY.items():
        handles = {k.lower(), ident.real_name.lower()}
        for src in ("github", "linear", "slack"):
            si = getattr(ident, src)
            if si:
                handles.add(si.handle.lower())
                if si.display_name:
                    handles.add(si.display_name.lower())
        if who in handles:
            key = k
            break
    if key is None:
        return _out({"error": f"no person matching {who!r}"})
    return _out({
        "person": key,
        "name": BY_KEY[key].real_name,
        "tasks": q.issues_for_person(key),
        "pull_requests": q.pulls_by_person(key),
    })


@tool(
    "numen_get_blocking_chain",
    "What a task is holding up: the tasks it blocks, and who owns each of them. "
    "People are already resolved across GitHub, Linear and Slack.",
    {"task": str},
)
async def numen_get_blocking_chain(args):
    key = (args.get("task") or "").upper()
    rel = pj._relations().get(key, [])
    downstream = []
    for r in rel:
        if r["type"] != "blocks":
            continue
        other = r["relatedIssue"]["identifier"]
        try:
            t = q.issue(other)
        except StopIteration:
            continue
        owner = _person_of_linear(t["assignee"]["id"])
        downstream.append({
            "task": other,
            "title": t["title"],
            "owner": {"person": owner,
                      "name": BY_KEY[owner].real_name if owner else None,
                      "linear_id": t["assignee"]["id"]},
        })
    return _out({"task": key, "blocks": downstream})


@tool(
    "numen_get_person_prs",
    "Pull requests a person authored or is requested to review. Accepts any handle "
    "they hold in any system.",
    {"who": str, "role": str},
)
async def numen_get_person_prs(args):
    who = (args.get("who") or "").strip().lower()
    key = None
    for k, ident in BY_KEY.items():
        names = {k.lower(), ident.real_name.lower()}
        for src in ("github", "linear", "slack"):
            si = getattr(ident, src)
            if si:
                names.add(si.handle.lower())
                if si.display_name:
                    names.add(si.display_name.lower())
        if who in names:
            key = k
            break
    if key is None:
        return _out({"error": f"no person matching {who!r}"})
    login = BY_KEY[key].github.handle if BY_KEY[key].github else None
    authored = [p for p in q.PULLS if p["user"]["login"] == login]
    reviewing = [p for p in q.PULLS
                 if any(r["login"] == login for r in p.get("requested_reviewers", []))]
    role = (args.get("role") or "").lower()
    if role == "author":
        reviewing = []
    elif role in ("reviewer", "review"):
        authored = []
    return _out({"person": key, "name": BY_KEY[key].real_name,
                 "authored": authored, "awaiting_their_review": reviewing})


@tool("numen_get_delayed_projects", "Urgent in-flight work with the projects and initiatives it exposes.", NO_ARGS)
async def numen_get_delayed_projects(args):
    urgent = [i for i in q.ISSUES
              if i["priority"] == "urgent" and i["state"]["name"] in ("in_progress", "in_review")]
    return _out({"tasks": urgent, "projects": q.PROJECTS[:3], "initiatives": q.INITIATIVES[:3]})


GRAPH_SERVER = create_sdk_mcp_server(
    name="numen",
    tools=[numen_list_tasks, numen_get_task_context, numen_get_person_workload,
           numen_get_blocking_chain, numen_get_person_prs, numen_get_delayed_projects],
)

GRAPH_ALLOWED = [
    "mcp__numen__numen_list_tasks",
    "mcp__numen__numen_get_task_context",
    "mcp__numen__numen_get_person_workload",
    "mcp__numen__numen_get_blocking_chain",
    "mcp__numen__numen_get_person_prs",
    "mcp__numen__numen_get_delayed_projects",
]

ARMS = {
    # Experiments 3: graph instead of the integrations.
    "per_tool": {"servers": {"pertool": PER_TOOL_SERVER}, "allowed": PER_TOOL_ALLOWED},
    "graph": {"servers": {"numen": GRAPH_SERVER}, "allowed": GRAPH_ALLOWED},
    # Experiment 4: the deployment people actually have. Nobody disconnects
    # their MCP servers when they add a context layer, so the second arm keeps
    # every integration and gains the graph on top. That also lets us measure
    # something the graph-only arm cannot: whether the model reaches for the
    # graph when the raw tools are right there beside it.
    "integrations": {"servers": {"pertool": PER_TOOL_SERVER}, "allowed": PER_TOOL_ALLOWED},
    "integrations_plus_graph": {
        "servers": {"pertool": PER_TOOL_SERVER, "numen": GRAPH_SERVER},
        "allowed": PER_TOOL_ALLOWED + GRAPH_ALLOWED,
    },
}
