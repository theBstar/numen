# System-Prompt Cookbook

Paste these into `CLAUDE.md`, `.cursor/rules/`, or your agent's project
instructions. They nudge the agent toward the right Numen tool calls
without constant prompting.

## Snippet A: Always orient with hello_numen

```
At the start of every Numen-connected session, call hello_numen first.
The response includes your org info, the available tool index, a sample
first call, and your latest briefing. Use it to scope what you can do.
```

## Snippet B: Dedup before create

```
Before calling create_task, ALWAYS call find_matching_task with the
user's description. If the response includes recommended_action:
"use_existing" (confidence >= 0.85), surface the recommended task to
the user and ask if they want to use it instead. Only create_task if
the user confirms there's no existing fit.
```

## Snippet C: Keep task status current

```
The task status pipeline is forward-only: todo -> in_progress ->
in_review -> merged -> done. Update_task_status as work progresses:

- update_task_status(status="in_progress") when you actually start
- update_task_status(status="in_review") when the PR opens
- update_task_status(status="done") only when work has shipped

Backward transitions are rejected. Don't try to "undo" a status -
talk to the user about cancelling instead.
```

## Snippet D: Propose, don't mutate, the spec

```
When your work changes the product spec (the wiki/PRD layer), DO NOT
silently update the wiki. Instead:

1. get_wiki_feature(slug=...) - read current state
2. propose_prd_update(slug, section_anchor, diff_md, rationale,
   expires_in_days=7) - file the proposal
3. Tell the user the URL: /prd-proposals/<id>
4. (Later) get_proposal_status to check if approved

If you get proposal_stale, the wiki changed - re-fetch and re-propose
with a fresh diff.
```

## Snippet E: Link PRs end-to-end

```
When opening a PR for a Numen task, drive the lifecycle through the
update_pr_state action discriminator:

- action="branch_pushed" right after pushing the branch (telemetry)
- action="link" when the PR is open (with pr_url, pr_number, draft)
- action="patch" if you poll for state changes (open -> merged etc.)
- action="merge" once merged (with merge_strategy + merged_commit_sha)

The merge action auto-advances the task status to DONE - no separate
update_task_status call needed at that point.
```

## Snippet F: Pull rich task context before working

```
Before working on a task, run this two-step:

1. get_task_context(task_id) - goals, blockers, urgency, PRs, project
2. get_context(task=<task.title>, max_tokens=4000) - relevant wiki +
   entity chunks ranked by the task description

The combination gives you ~the same context a human teammate would
have after reading the task + checking the wiki.
```

## Snippet G: Error envelope handling

```
Every Numen tool error returns:
  {"error": {"code": "<stable>", "message": "...",
             "hint": "...", "retryable": <bool>,
             "suggested_next_tool": "..."}}

Branch on `code`, not the message text. If `retryable: true`, wait and
retry. Otherwise, follow `suggested_next_tool` before asking the user.
Codes are stable across versions.
```

## Combining: a minimal CLAUDE.md block

```markdown
## Numen MCP rules

- Call hello_numen at session start. Read the briefing excerpt.
- Before create_task, always find_matching_task; surface high-confidence matches.
- Update task status forward-only as work progresses.
- Don't mutate the wiki; propose_prd_update with rationale and tell the user the URL.
- Drive PR lifecycle via update_pr_state action discriminator.
- On error, branch on error.code. Follow suggested_next_tool before asking me.
```
