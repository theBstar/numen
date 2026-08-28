# Numen MCP — Recipes

Copy-paste sequences your agent can run. Each recipe is a real tool-call
chain that does one job end-to-end.

## Recipe 1: Dedup before create

When the user describes new work, find existing tasks first.

```
1. find_matching_task(description="<user's description>")
   -> {"candidates": [...], "method": "llm_rerank",
        "recommended_action": "use_existing",   # only if confidence >= 0.85
        "recommended_task_id": "...",
        "recommended_confidence": 0.91}

2. If recommended_action present:
     Surface the recommended task to the user.
     If they confirm: use_existing - no new task needed.
     If they decline: create_task(...)

3. If no recommended_action:
     Show top 3 candidates anyway (they're useful context).
     Ask the user before creating.
```

System prompt that nudges this:

> "Before calling create_task, always call find_matching_task and surface
> any high-confidence match. Only create after the user confirms there's
> no fit."

## Recipe 2: Link a PR end-to-end

The full lifecycle: branch push -> PR open -> merge -> task done.

```
1. update_pr_state(action="branch_pushed", task_id="<uuid>",
                   branch_name="feat/x", commit_sha="abcd1234")

2. update_pr_state(action="link", task_id="<uuid>",
                   branch_name="feat/x", base_branch="develop",
                   provider="github", pr_number=42,
                   pr_url="https://github.com/owner/repo/pull/42")
   # PR state moves to "open" (or "draft" if draft=true)

3. (Optional poll cycle as the PR's checks run)
   update_pr_state(action="patch", task_id="<uuid>",
                   pr_state="open", merge_state_status="clean",
                   commit_head_sha="<latest>")

4. update_pr_state(action="merge", task_id="<uuid>",
                   merge_strategy="squash",
                   merged_commit_sha="<merged_sha>")
   # Task auto-advances to DONE if non-terminal.
```

Read state at any time:

```
get_pr_state(task_id="<uuid>")
-> {"pr": {...}}  # or {"pr": null} if no PR row yet
```

## Recipe 3: Propose a PRD edit (with user approval)

When your work changes the spec, propose the diff. Don't mutate.

```
1. get_wiki_feature(slug="auth-flow")
   -> {"feature": {"content": "<current>", ...}}
   # Read current state so your diff is correct.

2. propose_prd_update(
     feature_slug="auth-flow",
     section_anchor="callbacks",
     diff_md="<the new full content for that section>",
     rationale="OAuth callback URL changed in PR #42",
     expires_in_days=7,
   )
   -> {"ok": true, "proposal": {"id": "...", "status": "pending"},
        "user_action_required":
          "Visit /prd-proposals/<id> to approve or reject."}

3. Tell the user the URL.

4. (Later) get_proposal_status(proposal_id="<id>")
   -> {"proposal": {"status": "applied|rejected|stale|pending|expired"}}

   If "stale": the wiki was edited between propose and approve.
     Re-fetch with get_wiki_feature, regenerate the diff, re-propose.
```

## Recipe 4: Debug task context

The agent needs a full picture of a task before working on it.

```
1. get_task_context(task_id="<uuid>")
   -> {"task": {...}, "goals": [...], "blocking_chain": [...],
        "urgency": ..., "prs": [...], "project": {...}}

2. get_context(task=task.title, max_tokens=4000)
   -> {"chunks": [...], "related_entities": [...]}
   # Pulls relevant wiki + entities ranked by your task description.

3. (Optional) search_entities(query=task.title, entity_type="task")
   -> sibling tasks for cross-reference.
```

## Recipe 5: First-call onboarding

What every agent should do on session start:

```
1. hello_numen()
   -> {"org": {...}, "available_tools": {...},
        "sample_first_call": {...}, "briefing_excerpt": "...",
        "next_steps": [...]}

2. Read briefing_excerpt - it's your tldr.
3. Use available_tools to scope what you can do this session.
4. If the user gave you a task, run Recipe 4 (debug task context) first.
```

## Recipe 6: Keep your task status current

Forward-only state machine; backward transitions are rejected.

```
todo -> in_progress -> in_review -> merged -> done
```

```
update_task_status(task_id="<uuid>", status="in_progress")  # when you start
update_task_status(task_id="<uuid>", status="in_review")    # when PR opens
update_task_status(task_id="<uuid>", status="done")         # after merge
```

`update_pr_state(action="merge", ...)` auto-advances the task to DONE -
you only need explicit `update_task_status` for the in-flight transitions.
