"""One tool registry, shared by every surface.

Numen used to carry two: twelve read-only LangChain tools for web chat and
twenty-eight MCP tools for everyone else. They drifted, so a user in Claude
Desktop could create a task while a user in Numen's own chat panel could not.

This module is the single source of truth. Handlers delegate to the functions
in ``src.mcp.tools``, so logic lives in exactly one place, and the registry
adds the two things a conversation needs on top: resolution by name instead of
UUID, and permission filtering derived from who is asking and where.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.agent.principal import Principal
from src.agent.resolvers import (
    resolve_goal,
    resolve_person,
    resolve_project,
    resolve_task,
)
from src.graph import (
    get_blocking_chain,
    get_goal_coverage,
    get_org_workloads,
    get_person_prs,
    get_person_tasks,
    get_person_workload,
    get_project_stats,
    list_entities,
)
from src.mcp import tools as mcp_tools
from src.shared.models import Entity
from src.shared.types import EntityType, TaskStatus

logger = logging.getLogger(__name__)


@dataclass
class ToolContext:
    """Everything a tool handler needs, and nothing about the transport."""

    db: AsyncSession
    principal: Principal


@dataclass(frozen=True)
class ToolSpec:
    """A tool, described once and rendered for whichever runtime needs it."""

    name: str
    description: str
    args_model: type[BaseModel]
    handler: Callable[..., Awaitable[str]]
    writes: bool = False
    needs_private_audience: bool = False
    """Retrieval over private documents. Withheld when the answer is
    readable by a channel, since readers may not have the same access."""


def _error(message: str, hint: str | None = None) -> str:
    payload: dict[str, Any] = {"error": message}
    if hint:
        payload["hint"] = hint
    return json.dumps(payload)


def _entity_to_dict(e: Entity | None) -> dict:
    if e is None:
        return {}
    return {
        "id": str(e.id),
        "name": e.canonical_name,
        "type": e.type.value if e.type else None,
        "properties": e.properties or {},
    }


# ── Argument schemas ──────────────────────────────────────────────────


class NoArgs(BaseModel):
    pass


class SearchArgs(BaseModel):
    query: str = Field(description="Text to match against entity names")
    entity_type: str | None = Field(default=None, description="Optional filter: person, task, project, goal, feature")
    limit: int = Field(default=20, description="Maximum results")


class EntityTypeArgs(BaseModel):
    entity_type: str = Field(description="person, task, project, goal, or feature")
    limit: int = Field(default=50, description="Maximum results")


class ListTasksArgs(BaseModel):
    status: str | None = Field(default=None, description="todo, in_progress, in_review, merged, or done")
    priority: str | None = Field(default=None, description="low, medium, high, or urgent")
    assignee: str | None = Field(default=None, description="Assignee email")
    limit: int = Field(default=50, description="Maximum results")


class TaskNameArgs(BaseModel):
    task_name: str = Field(description="Title, or part of the title, of the task")


class GoalNameArgs(BaseModel):
    goal_name: str = Field(description="Name, or part of the name, of the goal")


class ProjectNameArgs(BaseModel):
    project_name: str = Field(description="Name, or part of the name, of the project")


class PersonNameArgs(BaseModel):
    person_name: str = Field(description="Name, or part of the name, of the person")


class PersonTasksArgs(BaseModel):
    person_name: str = Field(description="Name, or part of the name, of the person")
    since_days_ago: int | None = Field(default=None, description="Only tasks touched in the last N days")
    status: str | None = Field(default=None, description="Filter by task status")


class PersonPRsArgs(BaseModel):
    person_name: str = Field(description="Name, or part of the name, of the person")
    status: str | None = Field(default=None, description="open, merged, closed, or draft")
    role: str | None = Field(default=None, description="authored or reviewed; omit for both")


class UrgencyArgs(BaseModel):
    person_name: str | None = Field(default=None, description="Limit to one person")
    limit: int = Field(default=10, description="Maximum results")


class GoalsArgs(BaseModel):
    level: str | None = Field(default=None, description="Filter by goal level")
    include_tree: bool = Field(default=False, description="Include the goal hierarchy")


class BriefingArgs(BaseModel):
    member_email: str = Field(description="Email of the person whose briefing to fetch")


class ContextArgs(BaseModel):
    task: str = Field(description="What you are trying to do; used to retrieve relevant documents")
    max_tokens: int = Field(default=4000, description="Budget for the returned context")


class SourceArgs(BaseModel):
    source: str = Field(description="Source system, e.g. github, linear, slack")
    source_id: str = Field(description="Identifier in that system")


class WikiListArgs(BaseModel):
    status: str | None = Field(default=None, description="Filter by feature status")


class WikiFeatureArgs(BaseModel):
    slug: str = Field(description="Slug of the wiki feature")


class FindMatchingTaskArgs(BaseModel):
    description: str = Field(description="Description of the work about to start")
    project_hint: str | None = Field(default=None, description="Project name, if known")


class CreateTaskArgs(BaseModel):
    title: str = Field(description="Task title")
    description: str | None = Field(default=None, description="Task description")
    project_name: str | None = Field(default=None, description="Project to file it under")
    assignee_email: str | None = Field(default=None, description="Who to assign it to")
    priority: str = Field(default="medium", description="low, medium, high, or urgent")


class UpdateTaskStatusArgs(BaseModel):
    task_name: str = Field(description="Title, or part of the title, of the task")
    status: str = Field(description="todo, in_progress, in_review, merged, or done")


class UpdateTaskArgs(BaseModel):
    task_name: str = Field(description="Title, or part of the title, of the task")
    title: str | None = Field(default=None, description="New title")
    description: str | None = Field(default=None, description="New description")
    priority: str | None = Field(default=None, description="New priority")
    assignee_email: str | None = Field(default=None, description="Reassign to this person")


class LinkTaskArgs(BaseModel):
    task_name: str = Field(description="Task to link")
    project_name: str | None = Field(default=None, description="Project to file it under")
    goal_name: str | None = Field(default=None, description="Goal to connect it to")
    blocks_task_name: str | None = Field(default=None, description="Task that this one blocks")


class CreateProjectArgs(BaseModel):
    name: str = Field(description="Project name")
    description: str | None = Field(default=None, description="Project description")
    owner_email: str | None = Field(default=None, description="Owner")


class CreateGoalArgs(BaseModel):
    title: str = Field(description="Goal title")
    level: str = Field(description="Goal level, e.g. company, team")
    description: str | None = Field(default=None, description="Goal description")
    owner_email: str | None = Field(default=None, description="Owner")


class AppendWikiNoteArgs(BaseModel):
    feature_slug: str = Field(description="Slug of the wiki feature")
    note_markdown: str = Field(description="Note to append, in markdown")


class ProposePRDArgs(BaseModel):
    feature_slug: str = Field(description="Slug of the wiki feature")
    section_anchor: str = Field(description="Section to amend")
    diff_md: str = Field(description="Proposed replacement text, in markdown")
    rationale: str = Field(default="", description="Why this change is proposed")


# ── Read handlers ─────────────────────────────────────────────────────


async def _search_entities(ctx: ToolContext, query: str, entity_type: str | None = None, limit: int = 20) -> str:
    return await mcp_tools.search_entities(ctx.db, ctx.principal.org_id, query, entity_type, limit)


async def _list_entities_by_type(ctx: ToolContext, entity_type: str, limit: int = 50) -> str:
    try:
        et = EntityType(entity_type.lower())
    except ValueError:
        return _error(
            f"Unknown entity type '{entity_type}'.",
            f"Valid types: {', '.join(t.value for t in EntityType)}",
        )
    entities = await list_entities(ctx.db, ctx.principal.org_id, entity_type=et, limit=limit)
    return json.dumps([_entity_to_dict(e) for e in entities], default=str)


async def _list_tasks(
    ctx: ToolContext,
    status: str | None = None,
    priority: str | None = None,
    assignee: str | None = None,
    limit: int = 50,
) -> str:
    return await mcp_tools.list_tasks(
        ctx.db, ctx.principal.org_id, status=status, priority=priority, assignee=assignee, limit=limit
    )


async def _get_task_context(ctx: ToolContext, task_name: str) -> str:
    task, err = await resolve_task(ctx.db, ctx.principal.org_id, task_name)
    if err:
        return err
    return await mcp_tools.get_task_context(ctx.db, ctx.principal.org_id, str(task.id))


async def _list_goals(ctx: ToolContext, level: str | None = None, include_tree: bool = False) -> str:
    return await mcp_tools.list_goals(ctx.db, ctx.principal.org_id, level, include_tree)


async def _get_goal_progress(ctx: ToolContext, goal_name: str) -> str:
    goal, err = await resolve_goal(ctx.db, ctx.principal.org_id, goal_name)
    if err:
        return err
    return await mcp_tools.get_goal_progress(ctx.db, ctx.principal.org_id, str(goal.id))


async def _get_goal_coverage(ctx: ToolContext) -> str:
    coverage = await get_goal_coverage(ctx.db, ctx.principal.org_id)
    return json.dumps(coverage, default=str)


async def _get_urgency_scores(ctx: ToolContext, person_name: str | None = None, limit: int = 10) -> str:
    return await mcp_tools.get_urgency_scores(ctx.db, ctx.principal.org_id, person_name, limit)


async def _get_person_workload(ctx: ToolContext, person_name: str) -> str:
    person, err = await resolve_person(ctx.db, ctx.principal.org_id, person_name)
    if err:
        return err
    workload = await get_person_workload(ctx.db, person.id, org_id=ctx.principal.org_id)
    return json.dumps({"person": _entity_to_dict(person), "workload": workload}, default=str)


async def _get_person_tasks(
    ctx: ToolContext,
    person_name: str,
    since_days_ago: int | None = None,
    status: str | None = None,
) -> str:
    person, err = await resolve_person(ctx.db, ctx.principal.org_id, person_name)
    if err:
        return err

    since = None
    if since_days_ago:
        since = (datetime.now(timezone.utc) - timedelta(days=since_days_ago)).isoformat()

    tasks = await get_person_tasks(
        ctx.db,
        person.id,
        org_id=ctx.principal.org_id,
        since=since,
        statuses=[status] if status else None,
    )
    return json.dumps({"person": _entity_to_dict(person), "tasks": tasks}, default=str)


async def _get_person_prs(
    ctx: ToolContext,
    person_name: str,
    status: str | None = None,
    role: str | None = None,
) -> str:
    person, err = await resolve_person(ctx.db, ctx.principal.org_id, person_name)
    if err:
        return err
    prs = await get_person_prs(ctx.db, person.id, org_id=ctx.principal.org_id, status=status, role=role)
    return json.dumps({"person": _entity_to_dict(person), "pull_requests": prs}, default=str)


async def _get_project_stats(ctx: ToolContext, project_name: str) -> str:
    project, err = await resolve_project(ctx.db, ctx.principal.org_id, project_name)
    if err:
        return err
    stats = await get_project_stats(ctx.db, project.id, org_id=ctx.principal.org_id)
    return json.dumps({"project": _entity_to_dict(project), "stats": stats}, default=str)


async def _get_blocking_chain(ctx: ToolContext, task_name: str) -> str:
    task, err = await resolve_task(ctx.db, ctx.principal.org_id, task_name)
    if err:
        return err
    chain = await get_blocking_chain(ctx.db, task.id, org_id=ctx.principal.org_id)
    return json.dumps({"task": _entity_to_dict(task), "blocked_by": chain}, default=str)


async def _get_delayed_projects(ctx: ToolContext) -> str:
    """Projects past their end date that still have open work."""
    projects = await list_entities(ctx.db, ctx.principal.org_id, entity_type=EntityType.PROJECT, limit=500)
    now = datetime.now(timezone.utc)
    delayed = []

    for project in projects:
        properties = project.properties or {}
        if properties.get("status") == TaskStatus.DONE:
            continue
        raw_end = properties.get("end_date")
        if not raw_end:
            continue
        try:
            end_date = datetime.fromisoformat(str(raw_end))
        except (ValueError, TypeError):
            continue
        if end_date.tzinfo is None:
            end_date = end_date.replace(tzinfo=timezone.utc)
        if end_date >= now:
            continue

        stats = await get_project_stats(ctx.db, project.id, org_id=ctx.principal.org_id)
        delayed.append(
            {
                "project": _entity_to_dict(project),
                "stats": stats,
                "remaining_tasks": stats.get("total", 0) - stats.get("done", 0),
                "days_overdue": (now - end_date).days,
            }
        )

    return json.dumps(delayed, default=str)


async def _get_team_summary(ctx: ToolContext) -> str:
    """Everyone in the org with their open workload.

    Workloads come from one grouped graph query rather than one per person,
    which is what made the previous implementation issue hundreds of round
    trips on a large team.
    """
    org_id = ctx.principal.org_id
    people = await list_entities(ctx.db, org_id, entity_type=EntityType.PERSON, limit=500)
    if not people:
        return json.dumps([])

    workloads = await get_org_workloads(ctx.db, org_id)
    empty: dict = {"by_status": {}, "total": 0}
    summaries = [
        {
            "person": _entity_to_dict(person),
            "workload": workloads.get(str(person.id), empty),
        }
        for person in people
    ]
    return json.dumps(summaries, default=str)


async def _get_briefing(ctx: ToolContext, member_email: str) -> str:
    return await mcp_tools.get_briefing(ctx.db, ctx.principal.org_id, member_email)


async def _get_context(ctx: ToolContext, task: str, max_tokens: int = 4000) -> str:
    agent_id = ctx.principal.user_id
    if agent_id is None:
        return _error(
            "Document retrieval needs an identified user.",
            "Use an API key bound to a user, or sign in.",
        )
    return await mcp_tools.get_context(
        ctx.db, ctx.principal.org_id, agent_id, task=task, max_tokens=max_tokens
    )


async def _search_by_source(ctx: ToolContext, source: str, source_id: str) -> str:
    return await mcp_tools.search_by_source(ctx.db, ctx.principal.org_id, source, source_id)


async def _list_wiki_features(ctx: ToolContext, status: str | None = None) -> str:
    return await mcp_tools.list_wiki_features(ctx.db, ctx.principal.org_id, status)


async def _get_wiki_feature(ctx: ToolContext, slug: str) -> str:
    return await mcp_tools.get_wiki_feature(ctx.db, ctx.principal.org_id, slug)


async def _find_matching_task(ctx: ToolContext, description: str, project_hint: str | None = None) -> str:
    return await mcp_tools.find_matching_task(
        ctx.db, ctx.principal.org_id, description=description, project_hint=project_hint
    )


async def _get_pr_state(ctx: ToolContext, task_name: str) -> str:
    task, err = await resolve_task(ctx.db, ctx.principal.org_id, task_name)
    if err:
        return err
    return await mcp_tools.get_pr_state(ctx.db, ctx.principal.org_id, str(task.id))


async def _list_proposals(ctx: ToolContext) -> str:
    return await mcp_tools.list_proposals_tool(ctx.db, ctx.principal.org_id)


# ── Write handlers ────────────────────────────────────────────────────


def _writer_id(ctx: ToolContext):
    """The acting user, or None when this caller may not write."""
    return ctx.principal.user_id if ctx.principal.can_write else None


_WRITE_DENIED = (
    "This conversation cannot change records.",
    "Writes need a signed-in user and a private conversation, such as a direct message.",
)


async def _create_task(
    ctx: ToolContext,
    title: str,
    description: str | None = None,
    project_name: str | None = None,
    assignee_email: str | None = None,
    priority: str = "medium",
) -> str:
    actor = _writer_id(ctx)
    if actor is None:
        return _error(*_WRITE_DENIED)

    project_id = None
    if project_name:
        project, err = await resolve_project(ctx.db, ctx.principal.org_id, project_name)
        if err:
            return err
        project_id = str(project.id)

    return await mcp_tools.create_task(
        ctx.db,
        ctx.principal.org_id,
        actor,
        title=title,
        description=description,
        project_id=project_id,
        assignee_email=assignee_email,
        priority=priority,
    )


async def _update_task_status(ctx: ToolContext, task_name: str, status: str) -> str:
    actor = _writer_id(ctx)
    if actor is None:
        return _error(*_WRITE_DENIED)
    task, err = await resolve_task(ctx.db, ctx.principal.org_id, task_name)
    if err:
        return err
    return await mcp_tools.update_task_status(ctx.db, ctx.principal.org_id, actor, str(task.id), status)


async def _update_task(
    ctx: ToolContext,
    task_name: str,
    title: str | None = None,
    description: str | None = None,
    priority: str | None = None,
    assignee_email: str | None = None,
) -> str:
    actor = _writer_id(ctx)
    if actor is None:
        return _error(*_WRITE_DENIED)
    task, err = await resolve_task(ctx.db, ctx.principal.org_id, task_name)
    if err:
        return err
    return await mcp_tools.update_task(
        ctx.db,
        ctx.principal.org_id,
        actor,
        str(task.id),
        title=title,
        description=description,
        priority=priority,
        assignee_email=assignee_email,
    )


async def _link_task(
    ctx: ToolContext,
    task_name: str,
    project_name: str | None = None,
    goal_name: str | None = None,
    blocks_task_name: str | None = None,
) -> str:
    actor = _writer_id(ctx)
    if actor is None:
        return _error(*_WRITE_DENIED)
    task, err = await resolve_task(ctx.db, ctx.principal.org_id, task_name)
    if err:
        return err

    project_id = None
    if project_name:
        project, err = await resolve_project(ctx.db, ctx.principal.org_id, project_name)
        if err:
            return err
        project_id = str(project.id)

    goal_ids = None
    if goal_name:
        goal, err = await resolve_goal(ctx.db, ctx.principal.org_id, goal_name)
        if err:
            return err
        goal_ids = [str(goal.id)]

    blocks_id = None
    if blocks_task_name:
        blocked, err = await resolve_task(ctx.db, ctx.principal.org_id, blocks_task_name)
        if err:
            return err
        blocks_id = str(blocked.id)

    return await mcp_tools.link_task(
        ctx.db,
        ctx.principal.org_id,
        actor,
        str(task.id),
        project_id=project_id,
        goal_ids=goal_ids,
        blocks_task_id=blocks_id,
    )


async def _create_project(
    ctx: ToolContext,
    name: str,
    description: str | None = None,
    owner_email: str | None = None,
) -> str:
    actor = _writer_id(ctx)
    if actor is None:
        return _error(*_WRITE_DENIED)
    return await mcp_tools.create_project(
        ctx.db, ctx.principal.org_id, actor, name=name, description=description, owner_email=owner_email
    )


async def _create_goal(
    ctx: ToolContext,
    title: str,
    level: str,
    description: str | None = None,
    owner_email: str | None = None,
) -> str:
    actor = _writer_id(ctx)
    if actor is None:
        return _error(*_WRITE_DENIED)
    return await mcp_tools.create_goal(
        ctx.db, ctx.principal.org_id, actor, title=title, level=level, description=description, owner_email=owner_email
    )


async def _append_wiki_note(ctx: ToolContext, feature_slug: str, note_markdown: str) -> str:
    actor = _writer_id(ctx)
    if actor is None:
        return _error(*_WRITE_DENIED)
    return await mcp_tools.append_wiki_note(ctx.db, ctx.principal.org_id, actor, feature_slug, note_markdown)


async def _propose_prd_update(
    ctx: ToolContext,
    feature_slug: str,
    section_anchor: str,
    diff_md: str,
    rationale: str = "",
) -> str:
    actor = _writer_id(ctx)
    if actor is None:
        return _error(*_WRITE_DENIED)
    return await mcp_tools.propose_prd_update(
        ctx.db,
        ctx.principal.org_id,
        actor,
        feature_slug=feature_slug,
        section_anchor=section_anchor,
        diff_md=diff_md,
        rationale=rationale,
    )


# ── The registry ──────────────────────────────────────────────────────

TOOL_SPECS: list[ToolSpec] = [
    ToolSpec(
        name="search_entities",
        description="Search people, tasks, projects, goals and features by name.",
        args_model=SearchArgs,
        handler=_search_entities,
    ),
    ToolSpec(
        name="list_entities_by_type",
        description="List everything of one kind, e.g. every project.",
        args_model=EntityTypeArgs,
        handler=_list_entities_by_type,
    ),
    ToolSpec(
        name="list_tasks",
        description="List tasks, optionally filtered by status, priority or assignee.",
        args_model=ListTasksArgs,
        handler=_list_tasks,
    ),
    ToolSpec(
        name="get_task_context",
        description="Everything known about one task: goals, blockers, urgency, pull requests.",
        args_model=TaskNameArgs,
        handler=_get_task_context,
    ),
    ToolSpec(
        name="list_goals",
        description="List business goals, optionally as a hierarchy.",
        args_model=GoalsArgs,
        handler=_list_goals,
    ),
    ToolSpec(
        name="get_goal_progress",
        description="Completion percentage and key results for one goal.",
        args_model=GoalNameArgs,
        handler=_get_goal_progress,
    ),
    ToolSpec(
        name="get_goal_coverage",
        description="Every goal with how much work is linked to it. Finds goals nobody is working on.",
        args_model=NoArgs,
        handler=_get_goal_coverage,
    ),
    ToolSpec(
        name="get_urgency_scores",
        description="What Numen considers most urgent right now, optionally for one person.",
        args_model=UrgencyArgs,
        handler=_get_urgency_scores,
    ),
    ToolSpec(
        name="get_person_workload",
        description="How much work one person currently has, broken down by status.",
        args_model=PersonNameArgs,
        handler=_get_person_workload,
    ),
    ToolSpec(
        name="get_person_tasks",
        description="Tasks assigned to one person, with optional recency and status filters.",
        args_model=PersonTasksArgs,
        handler=_get_person_tasks,
    ),
    ToolSpec(
        name="get_person_prs",
        description="Pull requests one person authored or reviewed.",
        args_model=PersonPRsArgs,
        handler=_get_person_prs,
    ),
    ToolSpec(
        name="get_project_stats",
        description="Task counts by status for one project.",
        args_model=ProjectNameArgs,
        handler=_get_project_stats,
    ),
    ToolSpec(
        name="get_blocking_chain",
        description="What is blocking a task, following the chain of dependencies.",
        args_model=TaskNameArgs,
        handler=_get_blocking_chain,
    ),
    ToolSpec(
        name="get_delayed_projects",
        description="Projects past their end date that still have open work.",
        args_model=NoArgs,
        handler=_get_delayed_projects,
    ),
    ToolSpec(
        name="get_team_summary",
        description="Everyone in the org with their workload. Use for capacity and staffing questions.",
        args_model=NoArgs,
        handler=_get_team_summary,
    ),
    ToolSpec(
        name="get_briefing",
        description="The most recent daily briefing for one person.",
        args_model=BriefingArgs,
        handler=_get_briefing,
    ),
    ToolSpec(
        name="search_by_source",
        description="Find an entity by its identifier in a source system, e.g. a GitHub pull request number.",
        args_model=SourceArgs,
        handler=_search_by_source,
    ),
    ToolSpec(
        name="list_wiki_features",
        description="List product requirement documents and wiki features.",
        args_model=WikiListArgs,
        handler=_list_wiki_features,
    ),
    ToolSpec(
        name="get_wiki_feature",
        description="Read one wiki feature or requirements document.",
        args_model=WikiFeatureArgs,
        handler=_get_wiki_feature,
    ),
    ToolSpec(
        name="find_matching_task",
        description="Check whether work is already tracked before creating a duplicate task.",
        args_model=FindMatchingTaskArgs,
        handler=_find_matching_task,
    ),
    ToolSpec(
        name="get_pr_state",
        description="The pull request attached to a task, if any.",
        args_model=TaskNameArgs,
        handler=_get_pr_state,
    ),
    ToolSpec(
        name="list_proposals",
        description="List pending proposed edits to requirements documents.",
        args_model=NoArgs,
        handler=_list_proposals,
    ),
    ToolSpec(
        name="get_context",
        description="Retrieve passages from the organisation's documents relevant to what you are doing.",
        args_model=ContextArgs,
        handler=_get_context,
        needs_private_audience=True,
    ),
    # Writes
    ToolSpec(
        name="create_task",
        description="Create a task. Check find_matching_task first to avoid duplicates.",
        args_model=CreateTaskArgs,
        handler=_create_task,
        writes=True,
    ),
    ToolSpec(
        name="update_task_status",
        description="Move a task forward: todo, in_progress, in_review, merged, done. Backward moves are rejected.",
        args_model=UpdateTaskStatusArgs,
        handler=_update_task_status,
        writes=True,
    ),
    ToolSpec(
        name="update_task",
        description="Change a task's title, description, priority or assignee.",
        args_model=UpdateTaskArgs,
        handler=_update_task,
        writes=True,
    ),
    ToolSpec(
        name="link_task",
        description="Connect a task to a project or goal, or record that it blocks another task.",
        args_model=LinkTaskArgs,
        handler=_link_task,
        writes=True,
    ),
    ToolSpec(
        name="create_project",
        description="Create a project.",
        args_model=CreateProjectArgs,
        handler=_create_project,
        writes=True,
    ),
    ToolSpec(
        name="create_goal",
        description="Create a business goal.",
        args_model=CreateGoalArgs,
        handler=_create_goal,
        writes=True,
    ),
    ToolSpec(
        name="append_wiki_note",
        description="Record a durable note against a wiki feature.",
        args_model=AppendWikiNoteArgs,
        handler=_append_wiki_note,
        writes=True,
    ),
    ToolSpec(
        name="propose_prd_update",
        description="Propose an edit to a requirements document. A person reviews it before anything changes.",
        args_model=ProposePRDArgs,
        handler=_propose_prd_update,
        writes=True,
    ),
]

SPECS_BY_NAME: dict[str, ToolSpec] = {spec.name: spec for spec in TOOL_SPECS}


def tools_for(principal: Principal) -> list[ToolSpec]:
    """The tools this caller may use, on this surface."""
    selected = []
    for spec in TOOL_SPECS:
        if spec.writes and not principal.can_write:
            continue
        if spec.needs_private_audience and not principal.can_access_private_data:
            continue
        selected.append(spec)
    return selected


def build_langchain_tools(ctx: ToolContext) -> list[StructuredTool]:
    """Render the permitted tools for the LangGraph agent."""
    tools: list[StructuredTool] = []

    for spec in tools_for(ctx.principal):
        tools.append(_as_structured_tool(spec, ctx))
    return tools


def _as_structured_tool(spec: ToolSpec, ctx: ToolContext) -> StructuredTool:
    """Bind a spec to a context, exposing it as a LangChain tool.

    Handler errors become JSON the model can read and recover from, rather
    than exceptions that abort the run.
    """

    async def _run(**kwargs) -> str:
        try:
            return await spec.handler(ctx, **kwargs)
        except Exception as exc:
            logger.exception("Tool %s failed", spec.name)
            return _error(f"The {spec.name} tool failed: {exc}")

    return StructuredTool.from_function(
        coroutine=_run,
        name=spec.name,
        description=spec.description,
        args_schema=spec.args_model,
    )
