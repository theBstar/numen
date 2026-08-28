# L5: LLM Dispatch

> `src/llm/`

## Client (`client.py`)

- **Singleton** `AsyncOpenAI` client, lazily initialized
- **Default model**: `gpt-4o` (configurable via `OPENAI_MODEL` env var)
- **Retry**: 3 attempts with exponential backoff (1s, 2s, 4s) on `RateLimitError` and `APIError`
- `call_claude(system, user_message)` - returns text only (name kept for compatibility)
- `call_claude_with_trace(system, user_message)` - returns `LLMResponse` with model, token counts (input/output), latency_ms

## Actions (`actions.py`)

### `summarize_pr_diff`
- Input: PR entity with diff and description in properties
- Prompt: grounded with PR metadata, diff content
- Output: structured summary for briefing items

### `generate_briefing_narrative`
- Input: list of BriefingItems + member role + person name
- Output: narrative text wrapping the structured items
- Used in briefing delivery pipeline

## Prompt Generator (`prompt_generator.py`)

### `generate_task_prompt`
- Input: task entity ID + org_id
- Gathers context from graph: goals (via TAGGED_TO), blocking chain, related PRs (via SHIPS_TO), project (via CONTAINS), assignee, urgency score
- Assembles a structured markdown template via `build_task_prompt_template()`
- Refines the template via LLM using `build_prompt_refinement_prompt()`
- Falls back to raw template if LLM fails
- Output: `{ prompt, raw_prompt, task_title, repo_urls, has_blocking_chain, goal_count, llm_trace }`
- Endpoint: `POST /api/orgs/{org_id}/tasks/{task_id}/ai-prompt`
- Frontend: AiPromptModal component in TaskDetail with copy/open CTAs

## Link Suggester (`link_suggester.py`)

### `suggest_pr_task_links`
- Triggered after GitHub sync via `SyncCompleted` event
- Finds unlinked PRs and tasks in the org
- Uses OpenAI to suggest SHIPS_TO edges between PRs and tasks
- Creates `LinkSuggestion` records with confidence and reasoning
- Status lifecycle: pending -> accepted/dismissed by user

## Prompts (`prompts.py`)

- Grounded prompt templates that always include source entity data
- Design principle: every prompt includes provenance so LLM responses stay grounded in specific entities
- Never hallucinate entity references - always pass real IDs and names
