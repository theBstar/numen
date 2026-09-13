"""Experiment 5 tool surfaces: raw documents versus documents plus a wiki graph.

Arm one is what a team has today - their integrations, plus a Notion or Google
Docs MCP server that can search and fetch pages. Arm two adds Numen's wiki
layer on top, which is a graph: a feature per capability, pointing back at the
PRD sections it came from and forward at the tickets, pull requests and people
implementing it.

Both are served from `wiki_fixtures.py`. Deliberately absent is any tool that
lists conflicts. The wiki layer does record alignment at ingest, but exposing
that as a tool would answer the conflict question outright and measure
nothing. What the wiki arm gets instead is structural: it can see that two
documents describe one feature. Noticing they disagree is still the model's
job in both arms.
"""

from __future__ import annotations

import json
import re

from claude_agent_sdk import create_sdk_mcp_server, tool

from benchmarks import projections as pj
from benchmarks import questions as q
from benchmarks.arms_mcp import (
    PER_TOOL_ALLOWED,
    PER_TOOL_SERVER,
)
from benchmarks.identities import BY_KEY
from benchmarks.wiki_fixtures import DOC_BY_ID, DOCS, FEATURE_BY_SLUG, FEATURES

_WORD = re.compile(r"[a-z0-9]+")


def _out(payload) -> dict:
    return {"content": [{"type": "text", "text": json.dumps(payload, separators=(",", ":"))}]}


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


# ── Document arm ──────────────────────────────────────────────────────────

@tool("docs_list", "List every product document: id, title, author, last updated.", {})
async def docs_list(args):
    return _out([{k: d[k] for k in ("id", "title", "author", "updated")} for d in DOCS])


@tool(
    "docs_search",
    "Full-text search over product documents. Returns the best matches with a "
    "snippet around the strongest hit.",
    {"query": str, "limit": int},
)
async def docs_search(args):
    terms = _tokens(args.get("query") or "")
    limit = int(args.get("limit") or 3)
    scored = []
    for d in DOCS:
        body = d["body"]
        hits = _tokens(body) & terms
        if not hits:
            continue
        # crude frequency weighting - what a naive search endpoint does
        score = sum(body.lower().count(t) for t in hits)
        first = min((body.lower().find(t) for t in hits if body.lower().find(t) >= 0),
                    default=0)
        scored.append({
            "id": d["id"], "title": d["title"], "author": d["author"],
            "score": score,
            "snippet": body[max(0, first - 120): first + 280].strip(),
        })
    scored.sort(key=lambda r: -r["score"])
    return _out(scored[:limit])


@tool("docs_get", "Fetch one product document in full by id, for example PRD-002.", {"id": str})
async def docs_get(args):
    d = DOC_BY_ID.get((args.get("id") or "").upper())
    return _out(d or {"error": f"no document {args.get('id')!r}"})


DOCS_SERVER = create_sdk_mcp_server(name="docs", tools=[docs_list, docs_search, docs_get])
DOCS_ALLOWED = ["mcp__docs__docs_list", "mcp__docs__docs_search", "mcp__docs__docs_get"]


# ── Wiki graph arm ────────────────────────────────────────────────────────

def _resolve_people(keys: list[str]) -> list[dict]:
    out = []
    for k in keys:
        ident = BY_KEY.get(k)
        if not ident:
            continue
        out.append({
            "person": k,
            "name": ident.real_name,
            "linear_id": ident.linear.handle if ident.linear else None,
            "github_login": ident.github.handle if ident.github else None,
        })
    return out


def _feature_payload(f: dict) -> dict:
    impl = f["implementation"]
    tasks = []
    for key in impl["tasks"]:
        row = next((i for i in q.ISSUES if i["identifier"] == key), None)
        if row:
            tasks.append({"identifier": key, "title": row["title"],
                          "state": row["state"]["name"], "assignee": row["assignee"]})
    return {
        "slug": f["slug"], "title": f["title"], "status": f["status"],
        "domain_group": f["domain_group"], "summary": f["summary"],
        "documents": f["prd_references"],
        "concepts": f["concepts"],
        "implementation": {"tasks": tasks, "pull_requests": impl["prs"],
                           "people": _resolve_people(impl["people"])},
    }


@tool(
    "wiki_list_features",
    "List product features. Each names the documents it was built from and its "
    "implementation status.",
    {},
)
async def wiki_list_features(args):
    return _out([{"slug": f["slug"], "title": f["title"], "status": f["status"],
                  "domain_group": f["domain_group"], "summary": f["summary"],
                  "documents": f["prd_references"]} for f in FEATURES])


@tool(
    "wiki_get_feature",
    "One feature in full: its source documents, concepts, and the tickets, pull "
    "requests and people implementing it, with people already resolved across systems.",
    {"slug": str},
)
async def wiki_get_feature(args):
    f = FEATURE_BY_SLUG.get((args.get("slug") or "").lower())
    return _out(_feature_payload(f) if f else {"error": f"no feature {args.get('slug')!r}"})


@tool(
    "wiki_feature_for_document",
    "Which feature a product document belongs to. A feature may be built from "
    "several documents.",
    {"document_id": str},
)
async def wiki_feature_for_document(args):
    did = (args.get("document_id") or "").upper()
    hits = [_feature_payload(f) for f in FEATURES if did in f["prd_references"]]
    return _out(hits or {"error": f"no feature references {did}"})


@tool(
    "wiki_trace_to_goals",
    "Walk a feature out to the company initiatives its implementation work serves.",
    {"slug": str},
)
async def wiki_trace_to_goals(args):
    f = FEATURE_BY_SLUG.get((args.get("slug") or "").lower())
    if not f:
        return _out({"error": f"no feature {args.get('slug')!r}"})
    inits, projects = set(), []
    for key in f["implementation"]["tasks"]:
        for p in q.PROJECTS:
            if any(n["identifier"] == key for n in p["issues"]["nodes"]):
                projects.append(p["id"])
                inits.update(n["id"] for n in p["initiatives"]["nodes"])
    return _out({"feature": f["slug"], "projects": sorted(set(projects)),
                 "initiatives": sorted(inits)})


WIKI_SERVER = create_sdk_mcp_server(
    name="wiki",
    tools=[wiki_list_features, wiki_get_feature, wiki_feature_for_document, wiki_trace_to_goals],
)
WIKI_ALLOWED = [
    "mcp__wiki__wiki_list_features",
    "mcp__wiki__wiki_get_feature",
    "mcp__wiki__wiki_feature_for_document",
    "mcp__wiki__wiki_trace_to_goals",
]

WIKI_ARMS = {
    "docs": {
        "servers": {"pertool": PER_TOOL_SERVER, "docs": DOCS_SERVER},
        "allowed": PER_TOOL_ALLOWED + DOCS_ALLOWED,
    },
    "docs_plus_wiki": {
        "servers": {"pertool": PER_TOOL_SERVER, "docs": DOCS_SERVER, "wiki": WIKI_SERVER},
        "allowed": PER_TOOL_ALLOWED + DOCS_ALLOWED + WIKI_ALLOWED,
    },
}

_ = pj  # projections are imported for their side-effect-free helpers
