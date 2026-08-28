"""Grounded prompt templates for Claude dispatch actions."""

from __future__ import annotations

import json

from src.shared.types import TaskStatus

_DIFF_TRUNCATION_LIMIT = 8000


def build_pr_summary_prompt(
    pr_title: str,
    pr_description: str,
    diff_text: str,
    linked_tasks: list[dict],
    file_history: list[dict] | None = None,
) -> tuple[str, str]:
    """Build a prompt pair for summarizing a pull request.

    Returns:
        A ``(system_prompt, user_prompt)`` tuple.
    """
    system_prompt = (
        "You are Numen's engineering assistant. Summarize this PR for an "
        "engineer's daily briefing. Be concise (3 bullets max). Flag any risk "
        "areas. Connect to business goals if linked tasks have goal tags."
    )

    # Truncate diff to keep within reasonable token budget
    truncated_diff = diff_text[:_DIFF_TRUNCATION_LIMIT]
    if len(diff_text) > _DIFF_TRUNCATION_LIMIT:
        truncated_diff += "\n... [diff truncated]"

    # Format linked tasks
    task_lines: list[str] = []
    for task in linked_tasks:
        title = task.get("title", "Untitled")
        goal_tags = task.get("goal_tags", [])
        tag_str = f" (goals: {', '.join(goal_tags)})" if goal_tags else ""
        task_lines.append(f"- {title}{tag_str}")

    linked_section = "\n".join(task_lines) if task_lines else "No linked tasks."

    # Optional file-history context
    history_section = ""
    if file_history:
        history_section = "\n\n## Recent file history\n" + json.dumps(file_history, indent=2, default=str)

    user_prompt = (
        f"## PR: {pr_title}\n\n"
        f"### Description\n{pr_description or 'No description provided.'}\n\n"
        f"### Diff\n```\n{truncated_diff}\n```\n\n"
        f"### Linked tasks\n{linked_section}"
        f"{history_section}"
    )

    return system_prompt, user_prompt


def build_briefing_narrative_prompt(
    items: list[dict],
    role: str,
    person_name: str,
) -> tuple[str, str]:
    """Build a prompt pair for a morning briefing narrative.

    Returns:
        A ``(system_prompt, user_prompt)`` tuple.
    """
    system_prompt = (
        f"You are Numen, a work intelligence assistant. Write a brief, "
        f"friendly morning greeting and 2-3 sentence summary of today's "
        f"priorities for {person_name} ({role}). Be direct and actionable. "
        f"Do not use bullet points in the greeting — save those for the "
        f"items below."
    )

    # Format each item as structured data
    item_lines: list[str] = []
    for item in items:
        title = item.get("title", "Untitled")
        urgency = item.get("urgency_score", 0)
        why = item.get("why_it_matters", "")
        line = f"- **{title}** (urgency: {urgency:.1f}): {why}"
        item_lines.append(line)

    items_section = "\n".join(item_lines) if item_lines else "No items today."

    user_prompt = f"## Briefing items for {person_name}\n\n{items_section}"

    return system_prompt, user_prompt


def build_pr_task_link_prompt(
    prs: list[dict],
    tasks: list[dict],
) -> tuple[str, str]:
    """Build a prompt pair for matching PRs to tasks they implement.

    Returns:
        A ``(system_prompt, user_prompt)`` tuple.
    """
    system_prompt = (
        "You are Numen's engineering assistant. Your job is to match pull "
        "requests to the tasks they implement. Analyze these signals to "
        "determine which task(s) each PR is working on:\n\n"
        "1. Title/description/branch: Look for task identifiers, shared "
        "keywords, and semantic similarity between PR and task content.\n"
        "2. People overlap: If the PR author or a reviewer is also the task "
        "assignee, that is a strong signal they are related.\n"
        "3. Commit messages: They provide additional context about what the "
        "PR implements and may reference task identifiers.\n\n"
        "Return a JSON array of matches. Each match should have:\n"
        '- "pr_id": the PR identifier from the input\n'
        '- "task_id": the task identifier from the input\n'
        '- "confidence": a float between 0 and 1 (only include matches >= 0.4)\n'
        '- "reasoning": a brief one-sentence explanation of why they match\n\n'
        "Only return matches you are confident about. If a PR does not match "
        "any task, omit it. Return an empty array [] if no matches are found.\n\n"
        "Return ONLY the JSON array, no other text."
    )

    # Format PRs
    pr_lines: list[str] = []
    for pr in prs:
        pr_id = pr.get("id", "")
        title = pr.get("title", "")
        desc = pr.get("description", "")[:500]
        branch = pr.get("branch", "")
        author = pr.get("author", "")
        reviewers = pr.get("reviewers", [])
        commits = pr.get("commit_messages", [])
        line = f'- PR "{pr_id}": title="{title}", branch="{branch}", author="{author}"'
        if reviewers:
            line += f", reviewers=[{', '.join(reviewers)}]"
        if desc:
            line += f', description="{desc}"'
        if commits:
            # Include up to 5 commit messages for context
            commit_summary = "; ".join(commits[:5])
            line += f', commits="{commit_summary}"'
        pr_lines.append(line)

    # Format tasks
    task_lines: list[str] = []
    for task in tasks:
        task_id = task.get("id", "")
        title = task.get("title", "")
        desc = task.get("description", "")[:200]
        labels = task.get("labels", [])
        project = task.get("project", "")
        assignee = task.get("assignee", "")
        line = f'- Task "{task_id}": title="{title}"'
        if assignee:
            line += f', assignee="{assignee}"'
        if project:
            line += f', project="{project}"'
        if labels:
            line += f", labels=[{', '.join(labels)}]"
        if desc:
            line += f', description="{desc}"'
        task_lines.append(line)

    user_prompt = f"## Pull Requests\n{chr(10).join(pr_lines)}\n\n## Tasks\n{chr(10).join(task_lines)}"

    return system_prompt, user_prompt


def build_task_prompt_template(
    task: dict,
    goals: list[dict],
    blocking_chain: list[dict],
    related_prs: list[dict],
    project: dict | None,
    urgency: dict | None,
    assignee: dict | None,
) -> str:
    """Build a structured task prompt from context data (no LLM call).

    Returns a markdown-formatted prompt string ready for AI coding assistants.
    """
    props = task.get("properties", {})
    title = task.get("name", "Untitled")
    description = props.get("description", "")
    status = props.get("status", "unknown")
    priority = props.get("priority", "medium")
    labels = props.get("labels", [])
    due_date = props.get("due_date", "No due date")

    sections: list[str] = []

    # Header
    sections.append(f"# Task: {title}\n")

    # Description
    if description:
        sections.append(f"## Description\n{description}\n")

    # Status
    assignee_name = assignee.get("name", "Unassigned") if assignee else "Unassigned"
    sections.append(
        f"## Status\n"
        f"- Current status: {status}\n"
        f"- Priority: {priority}\n"
        f"- Assignee: {assignee_name}\n"
        f"- Due date: {due_date}\n"
    )

    # Business goals
    if goals:
        goal_lines = []
        for g in goals:
            g_name = g.get("name", "Untitled Goal")
            progress = g.get("progress", {})
            pct = progress.get("percentage", 0)
            done = progress.get("tasks_done", 0)
            total = progress.get("tasks_total", 0)
            goal_lines.append(f"- {g_name} (progress: {pct}%, {done}/{total} tasks done)")
        sections.append("## Business Goals\nThis task contributes to:\n" + "\n".join(goal_lines) + "\n")

    # Blocking chain
    if blocking_chain:
        blocker_lines = [f"- {b.get('name', 'Unknown')} ({b.get('status', '')})" for b in blocking_chain]
        sections.append("## Blocking Chain\nThis task is blocked by:\n" + "\n".join(blocker_lines) + "\n")
    else:
        sections.append("## Blocking Chain\nNo blocking dependencies.\n")

    # Related PRs
    if related_prs:
        pr_lines = []
        for pr in related_prs:
            pr_name = pr.get("name", "Untitled PR")
            pr_props = pr.get("properties", {})
            pr_status = pr_props.get("state", "")
            pr_url = pr_props.get("html_url", "")
            line = f"- {pr_name}"
            if pr_status:
                line += f" ({pr_status})"
            if pr_url:
                line += f" - {pr_url}"
            pr_lines.append(line)
        sections.append("## Related Pull Requests\n" + "\n".join(pr_lines) + "\n")

    # Project
    if project:
        proj_name = project.get("name", "Unknown Project")
        stats = project.get("stats", {})
        proj_done = stats.get(TaskStatus.DONE, 0)
        proj_total = stats.get("total", 0)
        proj_status = project.get("properties", {}).get("status", "")
        sections.append(
            f"## Project Context\n"
            f"Part of: {proj_name}"
            + (f" ({proj_status})" if proj_status else "")
            + f"\nProject progress: {proj_done}/{proj_total} tasks complete\n"
        )

    # Urgency
    if urgency:
        score = urgency.get("score", 0)
        provenance = urgency.get("provenance", [])
        sections.append(f"## Urgency\nScore: {score:.0f}/100\n")
        if provenance:
            prov_lines = [f"- {p.get('explanation', p.get('factor_name', ''))}" for p in provenance]
            sections.append("Key factors:\n" + "\n".join(prov_lines) + "\n")

    # Repo URLs
    repo_urls: set[str] = set()
    for pr in related_prs:
        pr_props = pr.get("properties", {})
        url = pr_props.get("html_url", "")
        if url:
            parts = url.split("/pull/")
            if len(parts) == 2:
                repo_urls.add(parts[0])
    task_source_ids = task.get("source_ids", {})
    if "github_repo_url" in task_source_ids:
        repo_urls.add(task_source_ids["github_repo_url"])
    if repo_urls:
        sections.append("## Repository\n" + "\n".join(f"- {u}" for u in sorted(repo_urls)) + "\n")

    # Labels
    if labels:
        sections.append(f"## Labels\n{', '.join(labels)}\n")

    # Instructions
    sections.append(
        "## Instructions\n"
        "You are working on the task described above. Here is what you need to do:\n"
        "1. Understand the business goal this connects to\n"
        "2. Check the blocking chain - resolve blockers first if any\n"
        "3. Review related PRs for context on prior work\n"
        "4. Implement the changes needed to complete this task\n"
        "5. Write tests for your changes\n"
        "6. Create a PR linking back to this task\n"
    )

    return "\n".join(sections)


def build_prompt_refinement_prompt(raw_prompt: str) -> tuple[str, str]:
    """Build a prompt pair to refine a raw task prompt into a better AI coding prompt.

    Returns:
        A ``(system_prompt, user_prompt)`` tuple.
    """
    system_prompt = (
        "You are a senior engineering lead who writes excellent, actionable task briefs "
        "for AI coding assistants. Take the structured task context below and rewrite it "
        "into a clear, prioritized prompt that an AI coding agent can execute. "
        "Keep all the factual details (IDs, URLs, names, scores) but:\n"
        "1. Lead with the most important context\n"
        "2. Prioritize actions based on blocking dependencies and urgency\n"
        "3. Be specific about what needs to be implemented\n"
        "4. Include relevant repo/PR links for context\n"
        "5. Keep it concise but comprehensive\n"
        "6. Use hyphens (-) not em dashes\n"
        "Return ONLY the refined prompt text, no commentary."
    )

    user_prompt = f"## Raw task context to refine:\n\n{raw_prompt}"

    return system_prompt, user_prompt


def build_bug_trace_prompt(
    error_info: dict,
    deploy_info: dict | None,
    related_files: list[str],
) -> tuple[str, str]:
    """Build a prompt pair for root-cause hypothesis generation (v1 stretch).

    Returns:
        A ``(system_prompt, user_prompt)`` tuple.
    """
    system_prompt = (
        "You are Numen's engineering assistant specializing in incident "
        "analysis. Given an error event, recent deploy information, and "
        "related source files, produce a concise root-cause hypothesis. "
        "Rank up to 3 possible causes by likelihood. For each, suggest "
        "one concrete investigation step."
    )

    # Format deploy context
    deploy_section = (
        json.dumps(deploy_info, indent=2, default=str) if deploy_info else "No recent deploy information available."
    )

    files_section = "\n".join(f"- {f}" for f in related_files) if related_files else "No related files identified."

    user_prompt = (
        f"## Error event\n```json\n"
        f"{json.dumps(error_info, indent=2, default=str)}\n```\n\n"
        f"## Recent deploy\n{deploy_section}\n\n"
        f"## Related files\n{files_section}"
    )

    return system_prompt, user_prompt
